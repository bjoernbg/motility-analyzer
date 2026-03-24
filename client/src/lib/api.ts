/** API client for video analysis backend. */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function getApiAssetUrl(path: string): string {
  if (import.meta.env.DEV) {
    return path;
  }

  if (typeof window !== 'undefined') {
    const apiOrigin = new URL(API_BASE_URL, window.location.href).origin;
    if (apiOrigin === window.location.origin) {
      return path;
    }
  }

  return `${API_BASE_URL}${path}`;
}

// Request cancellation management
const activeRequests = new Map<string, AbortController>();

/**
 * Get or create an AbortController for a given endpoint key.
 * Cancels any existing request for the same key before creating a new one.
 */
function getAbortController(endpointKey: string): AbortController {
  // Cancel any existing request for this endpoint
  const existing = activeRequests.get(endpointKey);
  if (existing) {
    existing.abort();
  }
  
  // Create new controller
  const controller = new AbortController();
  activeRequests.set(endpointKey, controller);
  
  return controller;
}

/**
 * Remove the AbortController for an endpoint after request completes.
 */
function cleanupAbortController(endpointKey: string): void {
  activeRequests.delete(endpointKey);
}

// Types matching backend models
export interface VideoMetadata {
  total_frames: number;
  fps: number;
  frame_multiplier: number;
  width: number;
  height: number;
  display_aspect_ratio: number | null;
  duration: number;
  file_size: number;
  codec: string | null;
  needs_reencoding?: () => boolean;  // Method to check if reencoding is needed
}

export interface ReencodeStatistics {
  duration_seconds: number;
  original_size_bytes: number;
  new_size_bytes: number;
  size_reduction_percent: number;
  original_codec: string | null;
  new_codec: string;
}

export interface ReencodeResult {
  video: Video;
  statistics: ReencodeStatistics;
}

export interface DeleteVideoResult {
  message: string;
  deleted_analysis_ids: string[];
  deleted_multi_view_session_ids: string[];
}

export interface Video {
  id: string;
  filename: string;
  display_name?: string | null;
  upload_date: string;
  file_path: string;
  metadata?: VideoMetadata;
}

export interface AnalysisParameters {
  // Smoothing factor
  smoothing_factor?: number;
  // Silhouette method parameters
  silhouette_blur_ksize_x?: number;
  silhouette_blur_ksize_y?: number;
  silhouette_blur_sigma?: number;
  silhouette_close_k?: number;
  silhouette_x_step?: number;
  silhouette_band?: number;
  silhouette_median_k?: number;
  // Horizontal window parameters
  horizontal_window_x_left?: number | null;
  horizontal_window_x_right?: number | null;
  // Measurement configuration
  num_tracking_points?: 30 | 50 | 80 | 120 | 200;
  distribution_method?: "center_line_projection" | "x_axis_even";
}

export interface Analysis {
  id: string;
  video_id: string;
  display_name?: string | null;
  parameters: Record<string, unknown>;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  processed_frames?: number | null;
  results_path: string | null;
  global_data?: Record<string, unknown> | null;
  created_at: string;
}

export interface FrameData {
  f: number; // frame_number
  pt: Array<[number, number]>; // path_top: [[x, y], ...]
  pb: Array<[number, number]>; // path_bottom: [[x, y], ...]
  pc: Array<[number, number]>; // path_center: [[x, y], ...]
  colored_regions: Array<{
    x: number;
    y: number;
    width: number;
    height: number;
    color: string;
    opacity: number;
  }>;
  mpp?: Array<[number, number, number, number, number, number, number]>; // measurement_point_pairs: [[cx, cy, tx, ty, bx, by, distance], ...]
}

export interface AnalysisResult {
  per_frame: FrameData[];
  global_data: Record<string, unknown>;
}

export interface ProgressUpdate {
  analysis_id: string;
  progress: number;
  status: string;
  current_frame: number | null;
  total_frames: number | null;
  frame_data?: FrameData; // Optional frame data for live updates
}

// HTTP API functions
type RequestOptions = RequestInit & {
  endpointKey?: string;
  includeJsonContentType?: boolean;
};

async function getResponseErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    const body = await response.json().catch(() => null);
    if (body && typeof body === 'object') {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === 'string' && detail.trim().length > 0) {
        return detail;
      }
      const message = (body as { message?: unknown }).message;
      if (typeof message === 'string' && message.trim().length > 0) {
        return message;
      }
    }
  }

  const text = await response.text().catch(() => '');
  if (text.trim().length > 0) {
    return text;
  }

  return response.statusText || `HTTP ${response.status}`;
}

function toRequestError(error: unknown): Error {
  if (error instanceof Error) {
    if (error.name === 'AbortError') {
      return error;
    }

    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      return new Error(
        `Network error: Could not reach server at ${API_BASE_URL}. Make sure the backend server is running.`
      );
    }

    return error;
  }

  return new Error('Unknown request error');
}

async function fetchResponse(url: string, options: RequestOptions = {}): Promise<Response> {
  const {
    endpointKey = url,
    includeJsonContentType = true,
    headers: rawHeaders,
    ...requestOptions
  } = options;
  const controller = getAbortController(endpointKey);
  const headers = new Headers(rawHeaders);

  if (includeJsonContentType && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  try {
    const response = await fetch(`${API_BASE_URL}${url}`, {
      ...requestOptions,
      signal: controller.signal,
      headers,
    });

    if (!response.ok) {
      throw new Error(await getResponseErrorMessage(response));
    }

    return response;
  } catch (error) {
    const requestError = toRequestError(error);
    if (requestError.name === 'AbortError') {
      throw requestError;
    }
    throw requestError;
  } finally {
    cleanupAbortController(endpointKey);
  }
}

async function fetchJson<T>(url: string, options?: RequestOptions): Promise<T> {
  const response = await fetchResponse(url, options);
  return response.json() as Promise<T>;
}

async function fetchMultipartJson<T>(url: string, options?: RequestOptions): Promise<T> {
  const response = await fetchResponse(url, {
    ...options,
    includeJsonContentType: false,
  });
  return response.json() as Promise<T>;
}

async function fetchBinary(
  url: string,
  options?: RequestOptions
): Promise<{ response: Response; buffer: ArrayBuffer }> {
  const response = await fetchResponse(url, {
    ...options,
    includeJsonContentType: false,
  });
  return { response, buffer: await response.arrayBuffer() };
}

export async function uploadVideo(file: File): Promise<Video> {
  const formData = new FormData();
  formData.append('file', file);
  return fetchMultipartJson<Video>('/api/videos/upload', {
    method: 'POST',
    body: formData,
    endpointKey: 'uploadVideo',
  });
}

export async function listVideos(): Promise<Video[]> {
  return fetchJson<Video[]>('/api/videos');
}

export function getFrameImageUrl(videoId: string, frameNumber: number): string {
  return getApiAssetUrl(
    `/api/videos/${encodeURIComponent(videoId)}/frame/${frameNumber}/image`
  );
}

export async function getVideoMetadata(videoId: string): Promise<VideoMetadata> {
  return fetchJson<VideoMetadata>(`/api/videos/${encodeURIComponent(videoId)}/metadata`, {
    endpointKey: `metadata:${videoId}`,
  });
}

export async function reencodeVideo(videoId: string): Promise<ReencodeResult> {
  return fetchJson<ReencodeResult>(`/api/videos/${encodeURIComponent(videoId)}/reencode`, {
    method: 'POST',
    endpointKey: `reencode:${videoId}`,
  });
}

export async function updateVideoDisplayName(
  videoId: string,
  displayName: string | null
): Promise<Video> {
  return fetchJson<Video>(`/api/videos/${encodeURIComponent(videoId)}/display-name`, {
    method: 'PUT',
    body: JSON.stringify({ display_name: displayName }),
  });
}

export async function deleteVideo(videoId: string): Promise<DeleteVideoResult> {
  return fetchJson<DeleteVideoResult>(`/api/videos/${encodeURIComponent(videoId)}`, {
    method: 'DELETE',
  });
}

export function videoNeedsReencoding(metadata: VideoMetadata | undefined): boolean {
  if (!metadata || !metadata.codec) {
    return true;  // Unknown codec, assume it needs re-encoding
  }

  const codecLower = metadata.codec.toLowerCase().trim();
  // Check if already using AV1
  if (codecLower.includes('av1') || codecLower.includes('av01')) {
    return false;
  }

  return true;
}

export async function startAnalysis(
  videoId: string,
  parameters: AnalysisParameters
): Promise<Analysis> {
  return fetchJson<Analysis>(`/api/analysis/start?video_id=${encodeURIComponent(videoId)}`, {
    method: 'POST',
    body: JSON.stringify(parameters),
  });
}

export async function getAnalysisStatus(analysisId: string): Promise<Analysis> {
  return fetchJson<Analysis>(`/api/analysis/${analysisId}/status`, {
    endpointKey: `status:${analysisId}`,
  });
}

export async function updateAnalysisDisplayName(
  analysisId: string,
  displayName: string | null
): Promise<Analysis> {
  return fetchJson<Analysis>(`/api/analysis/${encodeURIComponent(analysisId)}/display-name`, {
    method: 'PUT',
    body: JSON.stringify({ display_name: displayName }),
  });
}

export async function listAnalyses(
  videoId?: string,
  status?: string,
  limit?: number,
  offset?: number
): Promise<Analysis[]> {
  const params = new URLSearchParams();
  if (videoId) params.append('video_id', videoId);
  if (status) params.append('status', status);
  if (limit !== undefined) params.append('limit', limit.toString());
  if (offset !== undefined) params.append('offset', offset.toString());
  
  const queryString = params.toString();
  return fetchJson<Analysis[]>(`/api/analysis${queryString ? `?${queryString}` : ''}`);
}

export async function getAnalysisFrame(analysisId: string, frameNumber: number): Promise<FrameData> {
  return fetchJson<FrameData>(`/api/analysis/${analysisId}/frame/${frameNumber}`, {
    endpointKey: `frame:${analysisId}:${frameNumber}`,
  });
}

export interface FramesChunkResponse {
  frames: FrameData[];
  total_available: number;
  requested_range: [number, number];
}

export async function getFramesChunk(
  analysisId: string,
  start: number = 0,
  count: number = 100
): Promise<FramesChunkResponse> {
  const params = new URLSearchParams({
    start: start.toString(),
    count: count.toString(),
  });
  return fetchJson<FramesChunkResponse>(`/api/analysis/${encodeURIComponent(analysisId)}/frames?${params.toString()}`);
}

export interface FrameIndexResponse {
  frames: number[];
  total: number;
}

export async function getFrameIndex(analysisId: string): Promise<FrameIndexResponse> {
  return fetchJson<FrameIndexResponse>(`/api/analysis/${encodeURIComponent(analysisId)}/frame-index`);
}

export async function stopAnalysis(analysisId: string): Promise<Analysis> {
  return fetchJson<Analysis>(`/api/analysis/${analysisId}/stop`, {
    method: 'POST',
  });
}

export interface HorizontalWindowDetectionResult {
  x_left: number;
  x_right: number;
  y_mid: number;
}

export interface CalibrationResult {
  pixel_to_mm_factor: number;
  tube_width_px: number;
  x_start: number;
  x_end: number;
  y_top: number;
  y_bottom: number;
}

export async function analyzeFrame(
  videoId: string,
  frameNumber: number,
  parameters: AnalysisParameters
): Promise<FrameData> {
  return fetchJson<FrameData>(
    `/api/analysis/frame?video_id=${encodeURIComponent(videoId)}&frame_number=${frameNumber}`,
    {
      method: 'POST',
      body: JSON.stringify(parameters),
      endpointKey: `analyzeFrame:${videoId}:${frameNumber}`,
    }
  );
}

export async function detectHorizontalWindow(
  videoId: string,
  frameNumber: number,
  y?: number | null
): Promise<HorizontalWindowDetectionResult> {
  const params = new URLSearchParams({
    video_id: videoId,
    frame_number: frameNumber.toString(),
  });
  if (y !== null && y !== undefined) {
    params.append('y', y.toString());
  }
  return fetchJson<HorizontalWindowDetectionResult>(`/api/analysis/detect-window?${params.toString()}`, {
    method: 'POST',
  });
}

export async function calibrateVideo(
  videoId: string,
  frameNumber: number = 0,
  tubeWidthMm: number = 11.0
): Promise<CalibrationResult> {
  const params = new URLSearchParams({
    frame_number: frameNumber.toString(),
    tube_width_mm: tubeWidthMm.toString(),
  });
  return fetchJson<CalibrationResult>(
    `/api/videos/${encodeURIComponent(videoId)}/calibrate?${params.toString()}`,
    {
      method: 'POST',
      endpointKey: `calibrate:${videoId}`,
    }
  );
}

export async function getVideoSettings(videoId: string): Promise<AnalysisParameters | null> {
  try {
    const settings = await fetchJson<AnalysisParameters>(`/api/videos/${encodeURIComponent(videoId)}/settings`, {
      endpointKey: `settings:${videoId}`,
    });
    // Return null if settings object is empty (no saved settings)
    if (!settings || Object.keys(settings).length === 0) {
      return null;
    }
    return settings;
  } catch (error) {
    // If request was aborted, re-throw
    if (error instanceof Error && error.name === 'AbortError') {
      throw error;
    }
    // If settings file doesn't exist, return null (not an error)
    if (error instanceof Error && error.message.includes('404')) {
      return null;
    }
    throw error;
  }
}

export async function saveVideoSettings(videoId: string, settings: AnalysisParameters): Promise<void> {
  await fetchJson(`/api/videos/${encodeURIComponent(videoId)}/settings`, {
    method: 'PUT',
    body: JSON.stringify(settings),
  });
}

export async function deleteAnalysis(analysisId: string): Promise<void> {
  await fetchJson(`/api/analysis/${encodeURIComponent(analysisId)}`, {
    method: 'DELETE',
  });
}

export interface DisplaySettings {
  pixel_to_mm_factor: number;
  heatmap_min_mm: number;
  heatmap_max_mm: number;
  updated_at?: string;
}

export interface HeatmapMeta {
  width: number;
  height: number;
  dtype: string;
  min: number;
  max: number;
  fps: number;
  display_settings?: DisplaySettings;
}

export async function getHeatmapMeta(analysisId: string): Promise<HeatmapMeta> {
  return fetchJson<HeatmapMeta>(`/api/analysis/${encodeURIComponent(analysisId)}/heatmap/meta`, {
    endpointKey: `heatmap-meta:${analysisId}`,
  });
}

export interface HeatmapRawResult {
  buffer: ArrayBuffer;
  width: number;
  height: number;
}

export async function getHeatmapRaw(analysisId: string): Promise<HeatmapRawResult> {
  const { response, buffer } = await fetchBinary(
    `/api/analysis/${encodeURIComponent(analysisId)}/heatmap/raw`,
    {
      endpointKey: `heatmap-raw:${analysisId}`,
    }
  );
  const width = parseInt(response.headers.get('X-Width') || '0', 10);
  const height = parseInt(response.headers.get('X-Height') || '0', 10);

  return { buffer, width, height };
}

export interface ContractionDetectionParameters {
  smooth_sigma_y?: number;
  smooth_sigma_t?: number;
  threshold_percentile?: number;
  threshold?: number | null;
  open_iters?: number;
  close_iters?: number;
  min_pixels?: number;
  min_duration_s?: number;
  min_span_mm?: number | null;
  area_threshold_median_fraction?: number;
  merge_max_gap_s?: number;
  merge_max_offset_mm?: number;
  merge_max_velocity_delta_mm_s?: number;
  min_area?: number | null;
  min_height?: number | null;
  dy?: number | null;
}

export const CONTRACTION_DETECTION_VERSION_V2 = 'v2';
export const CONTRACTION_DETECTION_VERSION_LEGACY = 'legacy-v1';

export interface ContractionEventLineFit {
  a_idx_per_frame: number;
  b: number;
}

export interface ContractionEvent {
  id: string;
  label: number;
  n_pixels: number;
  threshold_used: number;
  t_range_frames: [number, number];
  y_range_idx: [number, number];
  duration_s: number;
  height_phys: number;
  velocity_phys_per_s: number;
  line_fit: ContractionEventLineFit;
  area_exact: number;
  area_triangle: number;
  created_at: string;
}

export interface ContractionDetectionResult {
  events: ContractionEvent[];
  parameters_used: ContractionDetectionParameters;
  total_events: number;
  detection_version: string;
}

export type MultiViewAnalysisDirection = 'front' | 'bottom';

export interface MultiViewSessionMetadata {
  validated: boolean;
  frame_count_diff: number;
  duration_diff: number;
  alignment?: MultiViewAlignmentState | null;
  latest_alignment_suggestion?: MultiViewAlignmentSuggestion | null;
  realign_job?: MultiViewRealignJob | null;
  left_direction?: MultiViewAnalysisDirection;
  right_direction?: MultiViewAnalysisDirection;
}

export interface MultiViewAlignmentState {
  right_time_shift_sec: number;
  updated_at: string;
  source: 'default' | 'auto' | 'manual';
}

export interface MultiViewTimeShiftSuggestion {
  right_time_shift_sec: number;
  confidence: number;
  method: 'analysis' | 'video_fallback';
  peak_correlation: number;
  prominence: number;
  auto_applied: boolean;
  warning?: string | null;
}

export interface MultiViewWindowSuggestion {
  sample_frames: number[];
  left_right_margin_px: number;
  right_right_margin_px: number;
  right_margin_delta_px: number;
  left_window_delta_px: number;
  right_window_delta_px: number;
  left_suggested_x_left?: number | null;
  left_suggested_x_right?: number | null;
  right_suggested_x_left?: number | null;
  right_suggested_x_right?: number | null;
  left_span_mm?: number | null;
  right_span_mm?: number | null;
  scale_mismatch_ratio?: number | null;
  left_anchor_x_px?: number | null;
  right_anchor_x_px?: number | null;
  target_offset_mm?: number | null;
  target_window_width_mm?: number | null;
  left_tube_end_x_left_px?: number | null;
  left_tube_end_x_right_px?: number | null;
  left_tube_end_y_top_px?: number | null;
  left_tube_end_y_bottom_px?: number | null;
  right_tube_end_x_left_px?: number | null;
  right_tube_end_x_right_px?: number | null;
  right_tube_end_y_top_px?: number | null;
  right_tube_end_y_bottom_px?: number | null;
}

export interface MultiViewAlignmentSuggestion {
  computed_at: string;
  left_analysis_id?: string | null;
  right_analysis_id?: string | null;
  time_shift: MultiViewTimeShiftSuggestion;
  window: MultiViewWindowSuggestion;
  notes: string[];
}

export interface MultiViewRealignJob {
  id: string;
  status: 'running' | 'ready_to_commit' | 'committed' | 'failed';
  left_analysis_id: string;
  right_analysis_id: string;
  created_at: string;
  completed_at?: string | null;
  error?: string | null;
}

export interface MultiViewAlignmentSuggestRequest {
  sample_frames?: number;
  max_shift_sec?: number;
  apply_time_shift?: boolean;
}

export interface MultiViewAlignmentSuggestResponse {
  session_id: string;
  suggestion: MultiViewAlignmentSuggestion;
  alignment: MultiViewAlignmentState;
}

export interface MultiViewAlignmentUpdateRequest {
  right_time_shift_sec: number;
}

export interface MultiViewAutoReanalyzeRequest {
  use_latest_suggestion?: boolean;
}

export interface MultiViewSessionSourcesUpdateRequest {
  left_analysis_id: string;
  right_analysis_id: string;
}

export interface MultiViewSessionCreate {
  name: string;
  left_analysis_id: string;
  right_analysis_id: string;
  left_direction?: MultiViewAnalysisDirection;
  right_direction?: MultiViewAnalysisDirection;
}

export interface MultiViewSessionDirectionsUpdateRequest {
  left_direction: MultiViewAnalysisDirection;
  right_direction: MultiViewAnalysisDirection;
}

export interface MultiViewSession {
  id: string;
  name: string;
  left_analysis_id: string;
  right_analysis_id: string;
  created_at: string;
  metadata?: MultiViewSessionMetadata | null;
}

export interface MultiViewValidationResult {
  compatible: boolean;
  errors: string[];
  details: Record<string, unknown>;
}

export async function detectContractions(
  analysisId: string,
  parameters?: ContractionDetectionParameters
): Promise<ContractionDetectionResult> {
  return fetchJson<ContractionDetectionResult>(
    `/api/analysis/${encodeURIComponent(analysisId)}/detect-contractions`,
    {
      method: 'POST',
      body: parameters ? JSON.stringify(parameters) : undefined,
      endpointKey: `detectContractions:${analysisId}`,
    }
  );
}

export async function getContractionEvents(analysisId: string): Promise<ContractionDetectionResult> {
  return fetchJson<ContractionDetectionResult>(
    `/api/analysis/${encodeURIComponent(analysisId)}/contractions`,
    {
      endpointKey: `contractionEvents:${analysisId}`,
    }
  );
}

export async function clearContractionEvents(analysisId: string): Promise<void> {
  await fetchJson(`/api/analysis/${encodeURIComponent(analysisId)}/contractions`, {
    method: 'DELETE',
  });
}

export async function clearAllData(): Promise<{ message: string; tasks_cancelled: number; files_deleted: number }> {
  return fetchJson('/api/clear-all-data', { method: 'DELETE' });
}

export async function getVideoDisplaySettings(videoId: string): Promise<DisplaySettings> {
  return fetchJson<DisplaySettings>(`/api/videos/${encodeURIComponent(videoId)}/display-settings`, {
    endpointKey: `videoDisplaySettings:${videoId}`,
  });
}

export async function updateVideoDisplaySettings(
  videoId: string,
  settings: DisplaySettings
): Promise<DisplaySettings> {
  return fetchJson<DisplaySettings>(`/api/videos/${encodeURIComponent(videoId)}/display-settings`, {
    method: 'PUT',
    body: JSON.stringify(settings),
  });
}

export async function getDisplaySettings(analysisId: string): Promise<DisplaySettings> {
  return fetchJson<DisplaySettings>(`/api/analysis/${encodeURIComponent(analysisId)}/display-settings`, {
    endpointKey: `displaySettings:${analysisId}`,
  });
}

export async function updateDisplaySettings(
  analysisId: string,
  settings: DisplaySettings
): Promise<DisplaySettings> {
  return fetchJson<DisplaySettings>(`/api/analysis/${encodeURIComponent(analysisId)}/display-settings`, {
    method: 'PUT',
    body: JSON.stringify(settings),
  });
}

// Multi-view sessions API

export async function validateMultiViewPair(
  leftAnalysisId: string,
  rightAnalysisId: string
): Promise<MultiViewValidationResult> {
  return fetchJson<MultiViewValidationResult>('/api/multi-view/validate', {
    method: 'POST',
    body: JSON.stringify({
      left_analysis_id: leftAnalysisId,
      right_analysis_id: rightAnalysisId,
    }),
    endpointKey: `validateMultiViewPair:${leftAnalysisId}:${rightAnalysisId}`,
  });
}

export async function createMultiViewSession(
  data: MultiViewSessionCreate
): Promise<MultiViewSession> {
  return fetchJson<MultiViewSession>('/api/multi-view/sessions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listMultiViewSessions(): Promise<MultiViewSession[]> {
  return fetchJson<MultiViewSession[]>('/api/multi-view/sessions', {
    endpointKey: 'listMultiViewSessions',
  });
}

export async function getMultiViewSession(sessionId: string): Promise<MultiViewSession> {
  return fetchJson<MultiViewSession>(`/api/multi-view/sessions/${encodeURIComponent(sessionId)}`, {
    endpointKey: `multiViewSession:${sessionId}`,
  });
}

export async function updateMultiViewSessionName(
  sessionId: string,
  name: string
): Promise<MultiViewSession> {
  return fetchJson<MultiViewSession>(`/api/multi-view/sessions/${encodeURIComponent(sessionId)}/name`, {
    method: 'PUT',
    body: JSON.stringify({ name }),
  });
}

export async function updateMultiViewSessionDirections(
  sessionId: string,
  body: MultiViewSessionDirectionsUpdateRequest
): Promise<MultiViewSession> {
  return fetchJson<MultiViewSession>(
    `/api/multi-view/sessions/${encodeURIComponent(sessionId)}/directions`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    }
  );
}

export async function deleteMultiViewSession(sessionId: string): Promise<void> {
  await fetchJson(`/api/multi-view/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
}

export async function suggestMultiViewAlignment(
  sessionId: string,
  body: MultiViewAlignmentSuggestRequest = {}
): Promise<MultiViewAlignmentSuggestResponse> {
  return fetchJson<MultiViewAlignmentSuggestResponse>(
    `/api/multi-view/sessions/${encodeURIComponent(sessionId)}/alignment/suggest`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    }
  );
}

export async function updateMultiViewAlignment(
  sessionId: string,
  body: MultiViewAlignmentUpdateRequest
): Promise<MultiViewSession> {
  return fetchJson<MultiViewSession>(
    `/api/multi-view/sessions/${encodeURIComponent(sessionId)}/alignment`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    }
  );
}

export async function autoReanalyzeMultiViewSession(
  sessionId: string,
  body: MultiViewAutoReanalyzeRequest = {}
): Promise<MultiViewRealignJob> {
  return fetchJson<MultiViewRealignJob>(
    `/api/multi-view/sessions/${encodeURIComponent(sessionId)}/alignment/auto-reanalyze`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    }
  );
}

export async function updateMultiViewSessionSources(
  sessionId: string,
  body: MultiViewSessionSourcesUpdateRequest
): Promise<MultiViewSession> {
  return fetchJson<MultiViewSession>(
    `/api/multi-view/sessions/${encodeURIComponent(sessionId)}/sources`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    }
  );
}
