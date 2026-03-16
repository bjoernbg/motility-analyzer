/** Pinia store for video analysis state. */
import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import type {
  Video,
  Analysis,
  AnalysisParameters,
  FrameData,
  ContractionDetectionParameters,
  ContractionDetectionResult,
  ContractionEvent,
  ReencodeStatistics,
  MultiViewSession,
  MultiViewValidationResult,
  MultiViewAlignmentSuggestResponse,
  MultiViewAlignmentSuggestion,
  MultiViewAlignmentState,
  MultiViewRealignJob,
  DeleteVideoResult,
  MultiViewAnalysisDirection,
} from '../lib/api';
import { useHeatmapCache } from '../composables/useHeatmapCache';
import { resolveMultiViewDirectionPair } from '../lib/domain/multiViewDirections';
import {
  buildFrameCacheKey,
  evictLeastRecentlyUsedFrame,
  keepOnlyAnalysisFrames,
  parametersMatch,
  type FrameCacheEntry,
} from './analysis/helpers';
import {
  uploadVideo,
  listVideos,
  getVideoMetadata,
  reencodeVideo,
  startAnalysis,
  getAnalysisStatus,
  listAnalyses,
  getAnalysisFrame,
  stopAnalysis,
  analyzeFrame,
  detectHorizontalWindow,
  getVideoSettings,
  saveVideoSettings,
  deleteAnalysis,
  deleteVideo as deleteVideoApi,
  clearAllData as clearAllDataApi,
  detectContractions,
  getContractionEvents,
  clearContractionEvents,
  validateMultiViewPair,
  createMultiViewSession,
  listMultiViewSessions,
  getMultiViewSession,
  deleteMultiViewSession,
  updateMultiViewSessionName,
  calibrateVideo,
  updateAnalysisDisplayName,
  updateVideoDisplayName,
  getVideoDisplaySettings,
  updateVideoDisplaySettings,
  suggestMultiViewAlignment,
  updateMultiViewAlignment,
  autoReanalyzeMultiViewSession,
  updateMultiViewSessionDirections,
  updateMultiViewSessionSources,
  type HorizontalWindowDetectionResult,
} from '../lib/api';

type WorkspaceEntityType = 'video' | 'combined' | null;

export const useAnalysisStore = defineStore('analysis', () => {
  // State
  const activeEntityType = ref<WorkspaceEntityType>(null);
  const activeEntityId = ref<string | null>(null);
  const videos = ref<Video[]>([]);
  const currentVideo = ref<Video | null>(null);
  const currentAnalysis = ref<Analysis | null>(null);
  const progress = ref(0);
  const progressStatus = ref<'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'>('pending');
  const currentFrame = ref<number | null>(null);
  const lastFrameWithData = ref<number | null>(null);
  const totalFrames = ref<number | null>(null);
  const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null);
  const pollingInterval = ref(10000); // 10 seconds
  const isLoading = ref(false);
  const isLoadingMetadata = ref(false);
  const error = ref<string | null>(null);
  // Accumulate frame data as it arrives during processing (small reactive map for current/recent frames)
  const liveFrameData = ref<Map<number, FrameData>>(new Map());
  // Store current parameters for single-frame analysis (even when no full analysis is running)
  const currentParameters = ref<AnalysisParameters | null>(null);
  // Track pending frame analysis requests to prevent duplicates
  const pendingFrameRequests = ref<Set<number>>(new Set());
  // Track pending settings requests by video ID to prevent duplicates
  const pendingSettingsRequests = ref<Set<string>>(new Set());
  // List of available analyses for the current video
  const availableAnalyses = ref<Analysis[]>([]);
  // Flag to track when analysis switch is in progress (skip unnecessary work)
  const isAnalysisSwitching = ref(false);
  // Contraction detection state
  const contractionEvents = ref<ContractionEvent[]>([]);
  const isDetectingContractions = ref(false);
  const contractionDetectionError = ref<string | null>(null);
  // Track if user is actively seeking (dragging slider, etc.) to prevent auto-seek conflicts
  const isUserSeeking = ref(false);

  // Multi-view sessions state
  const multiViewSessions = ref<MultiViewSession[]>([]);
  const currentMultiViewSession = ref<MultiViewSession | null>(null);
  const leftAnalysis = ref<Analysis | null>(null);
  const rightAnalysis = ref<Analysis | null>(null);
  const leftVideo = ref<Video | null>(null);
  const rightVideo = ref<Video | null>(null);
  const rightTimeShiftSec = ref(0);
  const syncedTimeSec = ref(0);
  const minSyncedTimeSec = ref(0);
  const maxSyncedTimeSec = ref(0);
  const latestAlignmentSuggestion = ref<MultiViewAlignmentSuggestion | null>(null);
  const currentAlignmentState = ref<MultiViewAlignmentState | null>(null);
  const realignJob = ref<MultiViewRealignJob | null>(null);
  const isComputingAlignment = ref(false);
  const isStartingAutoReanalyze = ref(false);
  const isUpdatingAlignment = ref(false);
  const isUpdatingDirections = ref(false);
  const realignPollingTimer = ref<ReturnType<typeof setInterval> | null>(null);

  // Simple LRU cache for frame data (max 20 frames)
  const frameDataCache = ref<Map<string, FrameCacheEntry>>(new Map());
  const MAX_FRAME_CACHE_SIZE = 20;

  // Computed
  const isProcessing = computed(() => progressStatus.value === 'processing');
  const isCompleted = computed(() => progressStatus.value === 'completed');
  const hasResults = computed(() => {
    return (currentAnalysis.value?.global_data !== null && currentAnalysis.value?.global_data !== undefined) || liveFrameData.value.size > 0;
  });

  const isInVideoMode = computed(() => activeEntityType.value === 'video' && activeEntityId.value !== null);
  const isInCombinedMode = computed(() => activeEntityType.value === 'combined' && activeEntityId.value !== null);
  const isInMultiViewMode = computed(() => isInCombinedMode.value);
  const activeAnalysis = computed(() => (isInVideoMode.value ? currentAnalysis.value : null));
  const activeVideo = computed(() => (isInVideoMode.value ? currentVideo.value : null));
  const currentMultiViewDirections = computed(() =>
    resolveMultiViewDirectionPair(currentMultiViewSession.value?.metadata)
  );

  function applyVideoUpdate(updatedVideo: Video): void {
    const videoIndex = videos.value.findIndex((video) => video.id === updatedVideo.id);
    if (videoIndex !== -1) {
      videos.value[videoIndex] = { ...videos.value[videoIndex], ...updatedVideo };
    }

    if (currentVideo.value?.id === updatedVideo.id) {
      currentVideo.value = { ...currentVideo.value, ...updatedVideo };
    }

    if (leftVideo.value?.id === updatedVideo.id) {
      leftVideo.value = { ...leftVideo.value, ...updatedVideo };
    }

    if (rightVideo.value?.id === updatedVideo.id) {
      rightVideo.value = { ...rightVideo.value, ...updatedVideo };
    }
  }

  function applyAnalysisUpdate(updatedAnalysis: Analysis): void {
    const analysisIndex = availableAnalyses.value.findIndex((analysis) => analysis.id === updatedAnalysis.id);
    if (analysisIndex !== -1) {
      availableAnalyses.value[analysisIndex] = { ...availableAnalyses.value[analysisIndex], ...updatedAnalysis };
    }

    if (currentAnalysis.value?.id === updatedAnalysis.id) {
      currentAnalysis.value = { ...currentAnalysis.value, ...updatedAnalysis };
    }

    if (leftAnalysis.value?.id === updatedAnalysis.id) {
      leftAnalysis.value = { ...leftAnalysis.value, ...updatedAnalysis };
    }

    if (rightAnalysis.value?.id === updatedAnalysis.id) {
      rightAnalysis.value = { ...rightAnalysis.value, ...updatedAnalysis };
    }
  }

  function applyMultiViewSessionUpdate(updatedSession: MultiViewSession): void {
    const sessionIndex = multiViewSessions.value.findIndex((session) => session.id === updatedSession.id);
    if (sessionIndex !== -1) {
      multiViewSessions.value[sessionIndex] = { ...multiViewSessions.value[sessionIndex], ...updatedSession };
    } else {
      multiViewSessions.value.unshift(updatedSession);
    }

    if (currentMultiViewSession.value?.id === updatedSession.id) {
      currentMultiViewSession.value = { ...currentMultiViewSession.value, ...updatedSession };
    }
  }

  function clearVideoSelection(): void {
    currentVideo.value = null;
    currentAnalysis.value = null;
    availableAnalyses.value = [];
    liveFrameData.value.clear();
    frameDataCache.value.clear();
    progress.value = 0;
    progressStatus.value = 'pending';
    currentFrame.value = null;
    totalFrames.value = null;
    currentParameters.value = null;
    contractionEvents.value = [];
    contractionDetectionError.value = null;
    isUserSeeking.value = false;
    stopPolling();
  }

  function stopRealignPolling(): void {
    if (realignPollingTimer.value) {
      clearInterval(realignPollingTimer.value);
      realignPollingTimer.value = null;
    }
  }

  function recomputeSyncedRange(): void {
    const leftDuration = leftVideo.value?.metadata?.duration ?? 0;
    const rightDuration = rightVideo.value?.metadata?.duration ?? 0;
    const shift = rightTimeShiftSec.value;

    const nextMin = Math.max(0, -shift);
    const nextMax = Math.min(leftDuration, rightDuration - shift);

    minSyncedTimeSec.value = Number.isFinite(nextMin) ? Math.max(0, nextMin) : 0;
    maxSyncedTimeSec.value = Number.isFinite(nextMax)
      ? Math.max(minSyncedTimeSec.value, nextMax)
      : minSyncedTimeSec.value;

    if (syncedTimeSec.value < minSyncedTimeSec.value) {
      syncedTimeSec.value = minSyncedTimeSec.value;
    } else if (syncedTimeSec.value > maxSyncedTimeSec.value) {
      syncedTimeSec.value = maxSyncedTimeSec.value;
    }
  }

  function clearCombinedSelection(): void {
    stopRealignPolling();
    currentMultiViewSession.value = null;
    leftAnalysis.value = null;
    rightAnalysis.value = null;
    leftVideo.value = null;
    rightVideo.value = null;
    rightTimeShiftSec.value = 0;
    syncedTimeSec.value = 0;
    minSyncedTimeSec.value = 0;
    maxSyncedTimeSec.value = 0;
    latestAlignmentSuggestion.value = null;
    currentAlignmentState.value = null;
    realignJob.value = null;
  }

  function setActiveEntity(type: WorkspaceEntityType, id: string | null): void {
    activeEntityType.value = type;
    activeEntityId.value = id;
  }

  // Actions
  async function loadVideos() {
    try {
      isLoading.value = true;
      error.value = null;
      videos.value = await listVideos();
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load videos';
      console.error('Failed to load videos:', err);
    } finally {
      isLoading.value = false;
    }
  }

  async function autoCalibrateVideoDisplaySettings(videoId: string) {
    try {
      const calibration = await calibrateVideo(videoId, 0);
      const currentDisplaySettings = await getVideoDisplaySettings(videoId);
      await updateVideoDisplaySettings(videoId, {
        ...currentDisplaySettings,
        pixel_to_mm_factor: calibration.pixel_to_mm_factor,
      });
    } catch (err) {
      // Calibration should not block upload flow.
      console.warn('Auto-calibration after upload failed:', err);
    }
  }

  async function handleVideoUpload(file: File) {
    try {
      isLoading.value = true;
      error.value = null;
      const video = await uploadVideo(file);
      videos.value.unshift(video); // Add to beginning
      
      // Reset analysis state before loading metadata
      currentAnalysis.value = null;
      liveFrameData.value.clear();
      progress.value = 0;
      progressStatus.value = 'pending';
      stopPolling();
      
      // Fetch video metadata before initializing the video
      isLoadingMetadata.value = true;
      try {
        const metadata = await getVideoMetadata(video.id);
        video.metadata = metadata;
        // Also update in videos list
        const videoInList = videos.value.find(v => v.id === video.id);
        if (videoInList) {
          videoInList.metadata = metadata;
        }

        await autoCalibrateVideoDisplaySettings(video.id);

        // Only set currentVideo after metadata is loaded
        clearCombinedSelection();
        currentVideo.value = video;
        setActiveEntity('video', video.id);
        
        // Load saved settings for this video (with deduplication)
        try {
          // Skip if already loading settings for this video
          if (pendingSettingsRequests.value.has(video.id)) {
            return;
          }
          pendingSettingsRequests.value.add(video.id);
          
          const savedSettings = await getVideoSettings(video.id);
          if (savedSettings) {
            currentParameters.value = savedSettings;
          } else {
            // Reset to defaults if no saved settings
            currentParameters.value = null;
          }
        } catch (err) {
          // Don't fail video upload if settings can't be loaded
          if (err instanceof Error && err.name !== 'AbortError') {
            console.warn('Failed to load video settings:', err);
          }
          currentParameters.value = null;
        } finally {
          pendingSettingsRequests.value.delete(video.id);
        }
      } catch (err) {
        error.value = err instanceof Error ? err.message : 'Failed to load video metadata';
        console.error('Failed to fetch video metadata:', err);
        throw err; // Throw error since metadata is required
      } finally {
        isLoadingMetadata.value = false;
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to upload video';
      console.error('Failed to upload video:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  async function selectVideo(video: Video) {
    clearCombinedSelection();

    // Reset analysis state before loading metadata
    currentAnalysis.value = null;
    liveFrameData.value.clear();
    progress.value = 0;
    progressStatus.value = 'pending';
    stopPolling();
    availableAnalyses.value = [];
    
    // Clear current video while loading metadata
    currentVideo.value = null;
    
    // Fetch video metadata before initializing the video
    isLoadingMetadata.value = true;
    try {
      const metadata = await getVideoMetadata(video.id);
      video.metadata = metadata;
      // Only set currentVideo after metadata is loaded
      currentVideo.value = video;
      setActiveEntity('video', video.id);
      
      // Load saved settings for this video (with deduplication)
      try {
        // Skip if already loading settings for this video
        if (pendingSettingsRequests.value.has(video.id)) {
          return;
        }
        pendingSettingsRequests.value.add(video.id);
        
        const savedSettings = await getVideoSettings(video.id);
        if (savedSettings) {
          currentParameters.value = savedSettings;
        } else {
          // Reset to defaults if no saved settings
          currentParameters.value = null;
        }
      } catch (err) {
        // Don't fail video selection if settings can't be loaded
        if (err instanceof Error && err.name !== 'AbortError') {
          console.warn('Failed to load video settings:', err);
        }
        currentParameters.value = null;
      } finally {
        pendingSettingsRequests.value.delete(video.id);
      }
      
      // Load available analyses for this video
      await loadAnalysesForVideo(video.id);
      
      // Auto-select the newest completed analysis
      const completedAnalyses = availableAnalyses.value.filter(a => a.status === 'completed');
      if (completedAnalyses.length > 0) {
        // Sort by created_at descending (newest first)
        completedAnalyses.sort((a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        const newestAnalysis = completedAnalyses[0];
        if (newestAnalysis) {
          await selectAnalysis(newestAnalysis.id);
        }
      }

      // Auto-load contraction events for selected analysis (moved outside conditional)
      const analysisToLoad = currentAnalysis.value as Analysis | null;
      if (analysisToLoad && analysisToLoad.status === 'completed') {
        await loadContractionEvents(analysisToLoad.id);
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load video metadata';
      console.error('Failed to fetch video metadata:', err);
      // Don't set currentVideo if metadata loading fails
      throw err;
    } finally {
      isLoadingMetadata.value = false;
    }
  }

  async function selectVideoEntity(videoId: string) {
    if (!videoId) {
      throw new Error('Video ID is required');
    }

    if (videos.value.length === 0) {
      await loadVideos();
    }

    let video = videos.value.find((item) => item.id === videoId);
    if (!video) {
      await loadVideos();
      video = videos.value.find((item) => item.id === videoId);
    }

    if (!video) {
      throw new Error('Video not found');
    }

    await selectVideo(video);
  }

  async function reencodeCurrentVideo(): Promise<ReencodeStatistics> {
    if (!currentVideo.value) {
      throw new Error('No video selected');
    }

    try {
      isLoading.value = true;
      error.value = null;

      // Call re-encode API (blocking operation)
      const result = await reencodeVideo(currentVideo.value.id);

      // Clear analysis state
      currentAnalysis.value = null;
      availableAnalyses.value = [];
      liveFrameData.value.clear();
      frameDataCache.value.clear();
      progress.value = 0;
      progressStatus.value = 'pending';
      contractionEvents.value = [];

      // Fetch updated metadata
      const metadata = await getVideoMetadata(result.video.id);
      result.video.metadata = metadata;

      // Update current video with new metadata
      currentVideo.value = result.video;

      // Update in videos list
      const videoIndex = videos.value.findIndex(v => v.id === result.video.id);
      if (videoIndex !== -1) {
        videos.value[videoIndex] = result.video;
      }

      return result.statistics;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to re-encode video';
      console.error('Failed to re-encode video:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  async function runAnalysis(parameters: AnalysisParameters) {
    if (!currentVideo.value) {
      throw new Error('No video selected');
    }

    if (!currentVideo.value.metadata) {
      throw new Error('Video metadata not loaded. Please wait for metadata to load before starting analysis.');
    }

    try {
      isLoading.value = true;
      error.value = null;

      // Check if a matching completed analysis already exists
      const matchingAnalysis = findMatchingAnalysis(parameters);
      if (matchingAnalysis) {
        // Select the existing analysis instead of creating new one
        await selectAnalysis(matchingAnalysis.id);
        return;
      }

      // Check if matching in-progress analysis exists (prevent duplicates)
      const processingAnalyses = availableAnalyses.value.filter(a => a.status === 'processing');
      for (const analysis of processingAnalyses) {
        if (parametersMatch(analysis.parameters, parameters)) {
          // Select the in-progress analysis
          await selectAnalysis(analysis.id);
          return;
        }
      }

      // No match found - create new analysis
      const analysis = await startAnalysis(currentVideo.value.id, parameters);
      currentAnalysis.value = analysis;
      progressStatus.value = analysis.status as typeof progressStatus.value;
      progress.value = analysis.progress;

      // Refresh analysis list to include the new analysis
      if (currentVideo.value) {
        await loadAnalysesForVideo(currentVideo.value.id);
      }

      // Start polling for progress updates
      startPolling(analysis.id);

      // Don't load results eagerly - frames are too large
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to start analysis';
      console.error('Failed to start analysis:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  function startPolling(analysisId: string) {
    // Stop existing polling
    stopPolling();

    // Poll for status updates
    const poll = async () => {
      // Capture target ID at start to avoid race conditions
      const targetId = analysisId;
      
      // Check if we should stop polling before making API call
      if (!currentAnalysis.value || currentAnalysis.value.id !== targetId) {
        stopPolling();
        return;
      }

      try {
        const analysis = await getAnalysisStatus(targetId);
        
        // Check again after API call (analysis might have changed)
        if (!currentAnalysis.value || currentAnalysis.value.id !== targetId) {
          stopPolling();
          return;
        }
        
        currentAnalysis.value = analysis;
        progress.value = analysis.progress;
        progressStatus.value = analysis.status as typeof progressStatus.value;

        // Stop polling if analysis is finished
        if (analysis.status === 'completed' || analysis.status === 'failed' || analysis.status === 'cancelled') {
          stopPolling();

          // Invalidate stale partial heatmap cache
          useHeatmapCache().invalidate(targetId);

          // Refresh the completed analyses list
          if (currentVideo.value) {
            loadAnalysesForVideo(currentVideo.value.id);
          }

          // Load contraction events if analysis completed successfully
          if (analysis.status === 'completed') {
            loadContractionEvents(targetId);
          }
        }
      } catch (err) {
        console.error('Failed to poll analysis status:', err);
        // Continue polling even on error (might be temporary network issue)
      }
    };

    // Poll immediately, then set up interval
    poll();
    pollingTimer.value = setInterval(poll, pollingInterval.value);
  }

  function stopPolling() {
    if (pollingTimer.value) {
      clearInterval(pollingTimer.value);
      pollingTimer.value = null;
    }
  }

  async function stopCurrentAnalysis() {
    if (!currentAnalysis.value) {
      return;
    }

    try {
      isLoading.value = true;
      error.value = null;
      
      const analysis = await stopAnalysis(currentAnalysis.value.id);
      currentAnalysis.value = analysis;
      progressStatus.value = analysis.status as typeof progressStatus.value;
      
      // Disconnect WebSocket
      stopPolling();
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to stop analysis';
      console.error('Failed to stop analysis:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  async function refreshAnalysisStatus() {
    if (!currentAnalysis.value) {
      return;
    }

    try {
      const analysis = await getAnalysisStatus(currentAnalysis.value.id);
      currentAnalysis.value = analysis;
      progress.value = analysis.progress;
      progressStatus.value = analysis.status as typeof progressStatus.value;
    } catch (err) {
      console.error('Failed to refresh analysis status:', err);
    }
  }

  async function loadAnalysesForVideo(videoId: string) {
    // Load all analyses for a video (including in-progress ones)
    try {
      const analyses = await listAnalyses(videoId, undefined, 100, 0);
      availableAnalyses.value = analyses;
    } catch (err) {
      console.error('Failed to load analyses for video:', err);
      availableAnalyses.value = [];
    }
  }

  async function selectAnalysis(analysisId: string) {
    // Switch to a different analysis (does not load frame data - too large)
    try {
      error.value = null;
      
      // Find the analysis in available analyses
      const analysis = availableAnalyses.value.find(a => a.id === analysisId);
      if (!analysis) {
        throw new Error('Analysis not found');
      }
      
      // Mark that we're switching (skip unnecessary frame analysis during switch)
      isAnalysisSwitching.value = true;
      
      // Set as current analysis
      currentAnalysis.value = analysis;
      progressStatus.value = analysis.status as typeof progressStatus.value;
      progress.value = analysis.progress;
      
      // Auto-load the analysis parameters
      currentParameters.value = analysis.parameters as AnalysisParameters;
      
      // Clear live frame data and cache when switching analyses
      liveFrameData.value.clear();
      // Keep only cache entries for the selected analysis.
      keepOnlyAnalysisFrames(frameDataCache.value, analysisId);
      
      // Load contraction events if analysis is completed
      if (analysis.status === 'completed') {
        await loadContractionEvents(analysisId);
      } else {
        contractionEvents.value = [];
      }
      
      // Start polling if analysis is still running
      if (analysis.status === 'processing') {
        startPolling(analysisId);
      }
      
      // Allow a brief delay for UI to update before enabling frame analysis again
      await new Promise(resolve => setTimeout(resolve, 100));
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to select analysis';
      console.error('Failed to select analysis:', err);
    } finally {
      isAnalysisSwitching.value = false;
    }
  }


  function findMatchingAnalysis(parameters: AnalysisParameters): Analysis | null {
    // Find a completed analysis with matching parameters (with tolerance for floats)
    const completedAnalyses = availableAnalyses.value.filter(a => a.status === 'completed');
    
    for (const analysis of completedAnalyses) {
      if (parametersMatch(analysis.parameters, parameters)) {
        return analysis;
      }
    }
    
    return null;
  }

  async function getFrameData(frameNum: number): Promise<FrameData | null> {
    // First check if we already have it in liveFrameData (immediate display)
    const cached = liveFrameData.value.get(frameNum);
    if (cached) {
      return cached;
    }

    // If we have a current analysis, try to get from cache or fetch directly
    if (currentAnalysis.value) {
      const cacheKey = buildFrameCacheKey(currentAnalysis.value.id, frameNum);
      
      // Check LRU cache first
      const cacheEntry = frameDataCache.value.get(cacheKey);
      if (cacheEntry) {
        // Update last accessed time
        cacheEntry.lastAccessed = Date.now();
        // Update liveFrameData for immediate display
        liveFrameData.value.set(frameNum, cacheEntry.data);
        lastFrameWithData.value = frameNum;
        return cacheEntry.data;
      }
      
      // Not in cache - fetch from API
      try {
        const frameData = await getAnalysisFrame(currentAnalysis.value.id, frameNum);
        
        // Store in cache (evict LRU if needed)
        evictLeastRecentlyUsedFrame(frameDataCache.value, MAX_FRAME_CACHE_SIZE);
        frameDataCache.value.set(cacheKey, {
          data: frameData,
          lastAccessed: Date.now(),
        });
        
        // Update liveFrameData for immediate display
        liveFrameData.value.set(frameNum, frameData);
        lastFrameWithData.value = frameNum;
        return frameData;
      } catch (err) {
        console.error(`Failed to get frame ${frameNum}:`, err);
        return null;
      }
    }

    return null;
  }

  async function analyzeCurrentFrame(parameters?: AnalysisParameters) {
    if (!currentVideo.value) {
      return;
    }

    // Skip during analysis switch to avoid unnecessary API calls
    if (isAnalysisSwitching.value) {
      return;
    }

    // Use provided parameters or stored current parameters
    const params = parameters ?? currentParameters.value;
    if (!params) {
      return;
    }

    // Store parameters for future use
    currentParameters.value = params;

    // Get current frame number from video player
    // This will be set by the video player component
    const frameNum = currentFrame.value;
    if (frameNum === null) {
      return;
    }

    // Validate frame number is within bounds
    const totalFrames = currentVideo.value.metadata?.total_frames;
    if (totalFrames !== undefined && totalFrames !== null) {
      if (frameNum < 0 || frameNum >= totalFrames) {
        // Frame is out of bounds, don't try to analyze it
        console.warn(`Frame ${frameNum} is out of bounds (0-${totalFrames - 1}). Skipping analysis.`);
        return;
      }
    }

    // First, check if we have cached results for this frame
    // Check if current parameters match a completed analysis
    const matchingAnalysis = findMatchingAnalysis(params);
    
    // If we have a matching analysis, use it (and initialize cache if needed)
    if (matchingAnalysis) {
      // If this is a different analysis, select it first
      if (currentAnalysis.value?.id !== matchingAnalysis.id) {
        await selectAnalysis(matchingAnalysis.id);
      }
      
      // Try to get frame from cache
      const frameData = await getFrameData(frameNum);
      if (frameData) {
        return; // Successfully got frame data
      }
    } else if (currentAnalysis.value) {
      // No matching analysis, but we have a current one - try to get frame anyway
      const frameData = await getFrameData(frameNum);
      if (frameData) {
        return; // Successfully got frame data
      }
    }

    // If frame not found in any analysis, use on-the-fly analysis
    // Prevent duplicate concurrent requests for the same frame
    if (pendingFrameRequests.value.has(frameNum)) {
      return;
    }

    // Mark request as pending
    pendingFrameRequests.value.add(frameNum);

    try {
      error.value = null;
      const frameData = await analyzeFrame(currentVideo.value.id, frameNum, params);
      // Update the liveFrameData map
      liveFrameData.value.set(frameData.f, frameData);
      lastFrameWithData.value = frameData.f;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to analyze frame';
      console.error('Failed to analyze frame:', err);
    } finally {
      // Remove from pending requests
      pendingFrameRequests.value.delete(frameNum);
    }
  }

  async function detectHorizontalWindowForCurrentFrame(): Promise<HorizontalWindowDetectionResult | null> {
    if (!currentVideo.value) {
      return null;
    }

    // Get current frame number from video player
    const frameNum = currentFrame.value;
    if (frameNum === null) {
      return null;
    }

    try {
      error.value = null;
      const result = await detectHorizontalWindow(currentVideo.value.id, frameNum);
      return result;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to detect window';
      console.error('Failed to detect window:', err);
      return null;
    }
  }

  async function saveCurrentSettings() {
    if (!currentVideo.value || !currentParameters.value) {
      return;
    }
    
    try {
      await saveVideoSettings(currentVideo.value.id, currentParameters.value);
    } catch (err) {
      console.error('Failed to save video settings:', err);
      // Don't throw - settings save failure shouldn't break the app
    }
  }

  async function renameVideo(videoId: string, displayName: string | null) {
    try {
      error.value = null;
      const updatedVideo = await updateVideoDisplayName(videoId, displayName);
      applyVideoUpdate(updatedVideo);
      return updatedVideo;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to rename video';
      throw err;
    }
  }

  async function deleteVideoById(videoId: string): Promise<DeleteVideoResult> {
    try {
      error.value = null;
      const result = await deleteVideoApi(videoId);

      videos.value = videos.value.filter((video) => video.id !== videoId);

      const deletedSessionIds = new Set(result.deleted_multi_view_session_ids);
      if (deletedSessionIds.size > 0) {
        multiViewSessions.value = multiViewSessions.value.filter(
          (session) => !deletedSessionIds.has(session.id)
        );

        const activeCombinedDeleted =
          activeEntityType.value === 'combined' &&
          activeEntityId.value !== null &&
          deletedSessionIds.has(activeEntityId.value);

        if (activeCombinedDeleted) {
          clearActiveEntity();
        } else if (
          currentMultiViewSession.value &&
          deletedSessionIds.has(currentMultiViewSession.value.id)
        ) {
          clearCombinedSelection();
        }
      }

      const activeVideoDeleted =
        activeEntityType.value === 'video' &&
        activeEntityId.value !== null &&
        activeEntityId.value === videoId;

      if (currentVideo.value?.id === videoId) {
        clearVideoSelection();
      }

      if (activeVideoDeleted) {
        setActiveEntity(null, null);
      }

      return result;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete video';
      throw err;
    }
  }

  async function renameAnalysis(analysisId: string, displayName: string | null) {
    try {
      error.value = null;
      const updatedAnalysis = await updateAnalysisDisplayName(analysisId, displayName);
      applyAnalysisUpdate(updatedAnalysis);
      return updatedAnalysis;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to rename analysis';
      throw err;
    }
  }

  async function deleteAnalysisById(analysisId: string) {
    try {
      error.value = null;
      
      // If this is the current analysis, clear it
      if (currentAnalysis.value?.id === analysisId) {
        currentAnalysis.value = null;
        liveFrameData.value.clear();
        progress.value = 0;
        progressStatus.value = 'pending';
        stopPolling();
      }
      
      // Delete from backend
      await deleteAnalysis(analysisId);
      
      // Remove from available analyses list
      availableAnalyses.value = availableAnalyses.value.filter(a => a.id !== analysisId);
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete analysis';
      console.error('Failed to delete analysis:', err);
      throw err;
    }
  }

  async function detectContractionsForAnalysis(analysisId: string, parameters?: ContractionDetectionParameters) {
    try {
      isDetectingContractions.value = true;
      contractionDetectionError.value = null;
      
      const result = await detectContractions(analysisId, parameters);
      contractionEvents.value = result.events;
      
      return result;
    } catch (err) {
      contractionDetectionError.value = err instanceof Error ? err.message : 'Failed to detect contractions';
      throw err;
    } finally {
      isDetectingContractions.value = false;
    }
  }

  async function loadContractionEvents(analysisId: string) {
    try {
      contractionDetectionError.value = null;
      const result = await getContractionEvents(analysisId);
      contractionEvents.value = result.events;
    } catch (err) {
      // Don't set error if contraction detection hasn't been run (404 is expected)
      if (err instanceof Error && err.message.includes('404')) {
        contractionEvents.value = [];
        return;
      }
      contractionDetectionError.value = err instanceof Error ? err.message : 'Failed to load contraction events';
      contractionEvents.value = [];
    }
  }

  async function clearContractionEventsForAnalysis(analysisId: string) {
    try {
      await clearContractionEvents(analysisId);
      contractionEvents.value = [];
      contractionDetectionError.value = null;
    } catch (err) {
      contractionDetectionError.value = err instanceof Error ? err.message : 'Failed to clear contraction events';
      throw err;
    }
  }

  function setUserSeeking(seeking: boolean) {
    isUserSeeking.value = seeking;
  }

  async function seekToFrame(frame: number) {
    // Clamp to valid range
    const totalFrames = currentVideo.value?.metadata?.total_frames;
    if (totalFrames) {
      frame = Math.max(0, Math.min(frame, totalFrames - 1));
    } else {
      // At least ensure non-negative
      frame = Math.max(0, frame);
    }

    currentFrame.value = frame;

    // Auto-trigger analysis if parameters exist and not switching
    if (currentVideo.value && currentParameters.value && !isAnalysisSwitching.value) {
      await analyzeCurrentFrame(currentParameters.value);
    }
  }

  function reset() {
    clearVideoSelection();
    clearCombinedSelection();
    setActiveEntity(null, null);
    error.value = null;
  }

  async function clearAllData() {
    try {
      stopPolling();
      await clearAllDataApi();
      // Reset all state
      reset();
      videos.value = [];
      multiViewSessions.value = [];
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to clear all data';
      throw err;
    }
  }

  // Watch for lastFrameWithData and auto-seek during processing (unless user is actively seeking)
  watch(() => lastFrameWithData.value, (frame) => {
    if (frame !== null && isProcessing.value && !isUserSeeking.value) {
      currentFrame.value = frame;
    }
  });

  // Watch for parameter changes and auto-deselect if they no longer match
  watch(
    () => currentParameters.value,
    (newParams) => {
      // Only check if we have a selected analysis
      if (!currentAnalysis.value || !newParams) {
        return;
      }

      // Skip during analysis switching to avoid unnecessary deselection
      if (isAnalysisSwitching.value) {
        return;
      }

      // Check if current parameters still match the selected analysis
      if (!parametersMatch(currentAnalysis.value.parameters, newParams)) {
        // Parameters no longer match - deselect the analysis
        currentAnalysis.value = null;
        liveFrameData.value.clear();
        progress.value = 0;
        progressStatus.value = 'pending';
        stopPolling();
      }
    },
    { deep: true }
  );

  // Multi-view session actions
  async function validateMultiViewSelection(
    leftAnalysisId: string,
    rightAnalysisId: string
  ): Promise<MultiViewValidationResult> {
    return validateMultiViewPair(leftAnalysisId, rightAnalysisId);
  }

  function syncCurrentSessionMetadata(session: MultiViewSession): void {
    currentAlignmentState.value = session.metadata?.alignment ?? null;
    latestAlignmentSuggestion.value = session.metadata?.latest_alignment_suggestion ?? null;
    realignJob.value = session.metadata?.realign_job ?? null;
    rightTimeShiftSec.value = session.metadata?.alignment?.right_time_shift_sec ?? 0;
    if (leftVideo.value && rightVideo.value) {
      recomputeSyncedRange();
    }
  }

  async function refreshMultiViewSessionMetadata(sessionId: string): Promise<MultiViewSession> {
    const refreshed = await getMultiViewSession(sessionId);
    applyMultiViewSessionUpdate(refreshed);
    if (currentMultiViewSession.value?.id === sessionId) {
      currentMultiViewSession.value = refreshed;
      syncCurrentSessionMetadata(refreshed);
    }
    return refreshed;
  }

  let isRealignPollingRequestInFlight = false;
  function startRealignPolling(sessionId: string): void {
    stopRealignPolling();

    const poll = async () => {
      if (isRealignPollingRequestInFlight) {
        return;
      }
      if (currentMultiViewSession.value?.id !== sessionId) {
        stopRealignPolling();
        return;
      }

      isRealignPollingRequestInFlight = true;
      try {
        const session = await refreshMultiViewSessionMetadata(sessionId);
        const job = session.metadata?.realign_job;

        if (!job || job.status === 'failed' || job.status === 'committed') {
          stopRealignPolling();
          return;
        }

        if (job.status === 'ready_to_commit') {
          await updateMultiViewSessionSources(sessionId, {
            left_analysis_id: job.left_analysis_id,
            right_analysis_id: job.right_analysis_id,
          });
          stopRealignPolling();
          await selectMultiViewSession(sessionId);
          return;
        }
      } catch (err) {
        console.error('Realign polling failed:', err);
      } finally {
        isRealignPollingRequestInFlight = false;
      }
    };

    void poll();
    realignPollingTimer.value = setInterval(() => {
      void poll();
    }, 5000);
  }

  async function loadMultiViewSessions() {
    try {
      multiViewSessions.value = await listMultiViewSessions();
    } catch (err) {
      console.error('Failed to load multi-view sessions:', err);
      error.value = err instanceof Error ? err.message : 'Failed to load multi-view sessions';
    }
  }

  async function computeMultiViewAlignment(
    options?: { sampleFrames?: number; maxShiftSec?: number; applyTimeShift?: boolean }
  ): Promise<MultiViewAlignmentSuggestResponse> {
    if (!currentMultiViewSession.value) {
      throw new Error('No combined analysis selected');
    }

    try {
      isComputingAlignment.value = true;
      error.value = null;
      const response = await suggestMultiViewAlignment(currentMultiViewSession.value.id, {
        sample_frames: options?.sampleFrames,
        max_shift_sec: options?.maxShiftSec,
        apply_time_shift: options?.applyTimeShift ?? true,
      });

      latestAlignmentSuggestion.value = response.suggestion;
      currentAlignmentState.value = response.alignment;
      rightTimeShiftSec.value = response.alignment.right_time_shift_sec;
      recomputeSyncedRange();
      await refreshMultiViewSessionMetadata(currentMultiViewSession.value.id);
      return response;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to compute alignment';
      throw err;
    } finally {
      isComputingAlignment.value = false;
    }
  }

  async function setMultiViewTimeShift(rightShiftSec: number): Promise<MultiViewSession> {
    if (!currentMultiViewSession.value) {
      throw new Error('No combined analysis selected');
    }

    try {
      isUpdatingAlignment.value = true;
      error.value = null;
      const updated = await updateMultiViewAlignment(currentMultiViewSession.value.id, {
        right_time_shift_sec: rightShiftSec,
      });
      applyMultiViewSessionUpdate(updated);
      if (currentMultiViewSession.value?.id === updated.id) {
        currentMultiViewSession.value = updated;
        syncCurrentSessionMetadata(updated);
      }
      return updated;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update alignment';
      throw err;
    } finally {
      isUpdatingAlignment.value = false;
    }
  }

  async function updateCurrentMultiViewDirections(
    leftDirection: MultiViewAnalysisDirection,
    rightDirection: MultiViewAnalysisDirection
  ): Promise<MultiViewSession> {
    if (!currentMultiViewSession.value) {
      throw new Error('No combined analysis selected');
    }

    try {
      isUpdatingDirections.value = true;
      error.value = null;
      const updated = await updateMultiViewSessionDirections(currentMultiViewSession.value.id, {
        left_direction: leftDirection,
        right_direction: rightDirection,
      });
      applyMultiViewSessionUpdate(updated);
      if (currentMultiViewSession.value?.id === updated.id) {
        currentMultiViewSession.value = updated;
        syncCurrentSessionMetadata(updated);
      }
      return updated;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update directions';
      throw err;
    } finally {
      isUpdatingDirections.value = false;
    }
  }

  async function startAutoReanalyzeFromAlignment(): Promise<MultiViewRealignJob> {
    if (!currentMultiViewSession.value) {
      throw new Error('No combined analysis selected');
    }

    try {
      isStartingAutoReanalyze.value = true;
      error.value = null;
      const job = await autoReanalyzeMultiViewSession(currentMultiViewSession.value.id, {
        use_latest_suggestion: true,
      });
      realignJob.value = job;
      await refreshMultiViewSessionMetadata(currentMultiViewSession.value.id);
      startRealignPolling(currentMultiViewSession.value.id);
      return job;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to start auto-reanalysis';
      throw err;
    } finally {
      isStartingAutoReanalyze.value = false;
    }
  }

  async function renameMultiViewSession(sessionId: string, name: string) {
    try {
      error.value = null;
      const updatedSession = await updateMultiViewSessionName(sessionId, name);
      applyMultiViewSessionUpdate(updatedSession);
      return updatedSession;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to rename combined analysis';
      throw err;
    }
  }

  async function selectMultiViewSession(sessionId: string) {
    try {
      isLoading.value = true;
      error.value = null;
      stopPolling();
      stopRealignPolling();

      const session = await getMultiViewSession(sessionId);
      currentMultiViewSession.value = session;
      setActiveEntity('combined', session.id);
      syncCurrentSessionMetadata(session);

      try {
        const [left, right] = await Promise.all([
          getAnalysisStatus(session.left_analysis_id),
          getAnalysisStatus(session.right_analysis_id),
        ]);
        leftAnalysis.value = left;
        rightAnalysis.value = right;

        const [leftMeta, rightMeta] = await Promise.all([
          getVideoMetadata(left.video_id),
          getVideoMetadata(right.video_id),
        ]);

        const videosById = new Map(videos.value.map((video) => [video.id, video]));
        const fallbackVideos = videosById.size === 0 ? await listVideos() : [];
        for (const video of fallbackVideos) {
          videosById.set(video.id, video);
        }
        if (fallbackVideos.length > 0) {
          videos.value = fallbackVideos;
        }

        const leftKnownVideo = videosById.get(left.video_id);
        const rightKnownVideo = videosById.get(right.video_id);

        leftVideo.value = {
          id: left.video_id,
          filename: leftKnownVideo?.filename ?? left.video_id,
          display_name: leftKnownVideo?.display_name ?? null,
          upload_date: leftKnownVideo?.upload_date ?? new Date().toISOString(),
          file_path: leftKnownVideo?.file_path ?? '',
          metadata: leftMeta,
        };
        rightVideo.value = {
          id: right.video_id,
          filename: rightKnownVideo?.filename ?? right.video_id,
          display_name: rightKnownVideo?.display_name ?? null,
          upload_date: rightKnownVideo?.upload_date ?? new Date().toISOString(),
          file_path: rightKnownVideo?.file_path ?? '',
          metadata: rightMeta,
        };

        recomputeSyncedRange();
        syncedTimeSec.value = minSyncedTimeSec.value;
      } catch (err) {
        stopRealignPolling();
        leftAnalysis.value = null;
        rightAnalysis.value = null;
        leftVideo.value = null;
        rightVideo.value = null;
        rightTimeShiftSec.value = 0;
        syncedTimeSec.value = 0;
        minSyncedTimeSec.value = 0;
        maxSyncedTimeSec.value = 0;
        const message = err instanceof Error ? err.message : 'Unknown error';
        error.value = `Combined analysis "${session.name}" is stale: one or more source analyses or videos are missing (${message}).`;
      }

      if (realignJob.value?.status === 'running') {
        startRealignPolling(session.id);
      } else {
        stopRealignPolling();
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to select multi-view session';
      console.error('Failed to select multi-view session:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  async function createMultiViewSessionAction(
    name: string,
    leftAnalysisId: string,
    rightAnalysisId: string,
    leftDirection: MultiViewAnalysisDirection,
    rightDirection: MultiViewAnalysisDirection
  ) {
    try {
      isLoading.value = true;
      error.value = null;

      const validation = await validateMultiViewPair(leftAnalysisId, rightAnalysisId);
      if (!validation.compatible) {
        throw new Error(`Incompatible analyses: ${validation.errors.join(', ')}`);
      }

      const session = await createMultiViewSession({
        name,
        left_analysis_id: leftAnalysisId,
        right_analysis_id: rightAnalysisId,
        left_direction: leftDirection,
        right_direction: rightDirection,
      });

      await loadMultiViewSessions();
      await selectCombinedEntity(session.id);

      return session;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create multi-view session';
      console.error('Failed to create multi-view session:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  async function deleteMultiViewSessionById(sessionId: string) {
    try {
      await deleteMultiViewSession(sessionId);
      multiViewSessions.value = multiViewSessions.value.filter((session) => session.id !== sessionId);
      if (activeEntityType.value === 'combined' && activeEntityId.value === sessionId) {
        clearActiveEntity();
      } else if (currentMultiViewSession.value?.id === sessionId) {
        clearCombinedSelection();
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete multi-view session';
      throw err;
    }
  }

  async function selectCombinedEntity(sessionId: string) {
    if (!sessionId) {
      throw new Error('Combined analysis ID is required');
    }

    if (multiViewSessions.value.length === 0) {
      await loadMultiViewSessions();
    }

    await selectMultiViewSession(sessionId);
  }

  function setSyncedTime(timeSec: number) {
    const bounded = Math.max(minSyncedTimeSec.value, Math.min(timeSec, maxSyncedTimeSec.value));
    syncedTimeSec.value = bounded;
  }

  function clearActiveEntity() {
    clearVideoSelection();
    clearCombinedSelection();
    setActiveEntity(null, null);
    error.value = null;
  }

  function exitMultiViewMode() {
    clearActiveEntity();
  }

  return {
    // State
    activeEntityType,
    activeEntityId,
    videos,
    currentVideo,
    currentAnalysis,
    progress,
    progressStatus,
    currentFrame,
    lastFrameWithData,
    totalFrames,
    isLoading,
    isLoadingMetadata,
    isAnalysisSwitching,
    error,
    liveFrameData,
    currentParameters,
    availableAnalyses,
    contractionEvents,
    isDetectingContractions,
    contractionDetectionError,
    isUserSeeking,
    // Multi-view state
    multiViewSessions,
    currentMultiViewSession,
    leftAnalysis,
    rightAnalysis,
    leftVideo,
    rightVideo,
    rightTimeShiftSec,
    syncedTimeSec,
    minSyncedTimeSec,
    maxSyncedTimeSec,
    latestAlignmentSuggestion,
    currentAlignmentState,
    realignJob,
    isComputingAlignment,
    isStartingAutoReanalyze,
    isUpdatingAlignment,
    isUpdatingDirections,
    // Computed
    isProcessing,
    isCompleted,
    hasResults,
    isInVideoMode,
    isInCombinedMode,
    isInMultiViewMode,
    activeAnalysis,
    activeVideo,
    currentMultiViewDirections,
    // Actions
    loadVideos,
    handleVideoUpload,
    selectVideo,
    selectVideoEntity,
    reencodeCurrentVideo,
    runAnalysis,
    startPolling,
    stopPolling,
    refreshAnalysisStatus,
    stopCurrentAnalysis,
    analyzeCurrentFrame,
    getFrameData,
    detectHorizontalWindowForCurrentFrame,
    saveCurrentSettings,
    renameVideo,
    deleteVideoById,
    renameAnalysis,
    loadAnalysesForVideo,
    selectAnalysis,
    findMatchingAnalysis,
    deleteAnalysisById,
    detectContractionsForAnalysis,
    loadContractionEvents,
    clearContractionEventsForAnalysis,
    setUserSeeking,
    seekToFrame,
    reset,
    clearAllData,
    // Multi-view session actions
    validateMultiViewSelection,
    loadMultiViewSessions,
    renameMultiViewSession,
    selectMultiViewSession,
    selectCombinedEntity,
    createMultiViewSession: createMultiViewSessionAction,
    deleteMultiViewSessionById,
    computeMultiViewAlignment,
    setMultiViewTimeShift,
    updateCurrentMultiViewDirections,
    startAutoReanalyzeFromAlignment,
    refreshMultiViewSessionMetadata,
    setSyncedTime,
    clearActiveEntity,
    exitMultiViewMode,
  };
});
