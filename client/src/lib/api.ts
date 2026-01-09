/** API client for video analysis backend. */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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

export interface Video {
  id: string;
  filename: string;
  upload_date: string;
  file_path: string;
  metadata?: VideoMetadata;
}

export interface AnalysisParameters {
  // Edge detection method selection
  edge_detection_method?: "costmap" | "signal_1d" | "canny" | "silhouette";
  // Costmap parameters (only used when edge_detection_method="costmap")
  alpha?: number;
  band?: number;
  threshold_percentile?: number;
  subsequent_frame_band?: number | null;
  // Smoothing factor (used by both methods)
  smoothing_factor?: number;
  // 1D Signal method parameters (only used when edge_detection_method="signal_1d")
  strip_width?: number;
  band_height?: number;
  sigma?: number;
  // Canny method parameters (only used when edge_detection_method="canny")
  canny_threshold1?: number;
  canny_threshold2?: number;
  canny_aperture_size?: number;
  // Silhouette method parameters (only used when edge_detection_method="silhouette")
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
  num_tracking_points?: number;
  distribution_method?: "center_line_projection" | "x_axis_even";
}

export interface Analysis {
  id: string;
  video_id: string;
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
async function fetchJson<T>(url: string, options?: RequestInit & { endpointKey?: string }): Promise<T> {
  const endpointKey = options?.endpointKey || url;
  const controller = getAbortController(endpointKey);
  
  try {
    const response = await fetch(`${API_BASE_URL}${url}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const result = await response.json();
    cleanupAbortController(endpointKey);
    return result;
  } catch (error) {
    cleanupAbortController(endpointKey);
    
    // Don't throw error if request was aborted
    if (error instanceof Error && error.name === 'AbortError') {
      throw error;
    }
    
    // Re-throw with more context if it's a network error
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      throw new Error(`Network error: Could not reach server at ${API_BASE_URL}. Make sure the backend server is running.`);
    }
    throw error;
  }
}

export async function uploadVideo(file: File): Promise<Video> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/api/videos/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function listVideos(): Promise<Video[]> {
  return fetchJson<Video[]>('/api/videos');
}

export function getFrameImageUrl(videoId: string, frameNumber: number): string {
  return `${API_BASE_URL}/api/videos/${encodeURIComponent(videoId)}/frame/${frameNumber}/image`;
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

export interface HeatmapMeta {
  width: number;
  height: number;
  dtype: string;
  min: number;
  max: number;
  fps: number;
}

export async function getHeatmapMeta(analysisId: string): Promise<HeatmapMeta> {
  return fetchJson<HeatmapMeta>(`/api/analysis/${encodeURIComponent(analysisId)}/heatmap/meta`, {
    endpointKey: `heatmap-meta:${analysisId}`,
  });
}

export async function getHeatmapRaw(analysisId: string): Promise<ArrayBuffer> {
  const endpointKey = `heatmap-raw:${analysisId}`;
  const controller = getAbortController(endpointKey);
  
  try {
    const response = await fetch(`${API_BASE_URL}/api/analysis/${encodeURIComponent(analysisId)}/heatmap/raw`, {
      signal: controller.signal,
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    
    cleanupAbortController(endpointKey);
    return response.arrayBuffer();
  } catch (error) {
    cleanupAbortController(endpointKey);
    
    // Re-throw AbortError so it can be handled by the caller
    if (error instanceof Error && error.name === 'AbortError') {
      throw error;
    }
    
    throw error;
  }
}

export interface ContractionDetectionParameters {
  smooth_sigma_y?: number;
  smooth_sigma_t?: number;
  threshold_percentile?: number;
  threshold?: number | null;
  open_iters?: number;
  close_iters?: number;
  min_pixels?: number;
  dy?: number | null;
}

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


