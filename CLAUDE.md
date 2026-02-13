# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Motility Analyzer is a full-stack video analysis application for detecting and tracking biological motility patterns in microscopy videos. The system processes videos frame-by-frame to detect edges, track movement, generate heatmaps, detect contraction patterns, and compare analyses.

**Tech Stack:**
- **Backend:** FastAPI (Python 3.12+), OpenCV, NumPy, SciPy, Numba
- **Frontend:** Vue 3 + TypeScript, Vite, Pinia, TailwindCSS, shadcn-vue
- **Database:** SQLite (for analysis metadata, frame results, contraction events, combined analyses)
- **Storage:** File-based storage for videos, cached heatmaps, and settings

## Development Commands

### Backend (FastAPI)

```bash
cd server

# Install dependencies (using uv)
uv sync

# Start development server
uv run fastapi dev server.main:app --port 8000
# or
uv run uvicorn server.main:app --reload --port 8000

# Linting and formatting
ruff check server
ruff format server

# Run tests (if pytest is set up)
uv run pytest
```

### Frontend (Vue + Vite)

```bash
cd client

# Install dependencies
npm install

# Start development server (default port 5173)
npm run dev

# Type checking
npm run type-check

# Build for production
npm run build

# Preview production build
npm run preview

# Format code
npm run format
```

## Architecture

### Backend Structure

The backend is a monolithic FastAPI application (`server/main.py`) with domain-specific modules:

**Core Processing Pipeline:**
1. **Video ingestion** → `storage.py` (VideoStorage, ResultsStorage, AnalysisStorage)
2. **Metadata extraction** → `metadata.py` (cached video properties: FPS, frame count, dimensions)
3. **Video re-encoding** → `encoder.py` (FFmpeg-based conversion to H.264/libx264)
4. **Analysis execution** → `tasks.py` (TaskManager coordinates background frame processing via ThreadPoolExecutor)
5. **Edge detection** → `edge_detection_silhouette.py` (mask-based segmentation with morphological operations)
6. **Edge utilities** → `edge_utils.py` (starting point detection, path smoothing, path interpolation)
7. **Path calculation** → `analysis.py` (center path, tangent/normal intersection, measurement point pairs)
8. **Data storage** → `database.py` (AnalysisDB + CombinedAnalysisDB, SQLite with WAL mode)
9. **Contraction detection** → `contraction_detection.py` (spatiotemporal pattern detection on heatmaps)
10. **Calibration** → `calibration.py` (tube-width measurement for pixel-to-mm conversion)
11. **Combination validation** → `combination_validation.py` (compatibility checks for combining two analyses)

**Key Modules:**
- `models.py` - Pydantic models for API contracts (Video, Analysis, FrameData, ContractionEvent, CombinedAnalysis, DisplaySettings, etc.)
- `video_pool.py` - LRU video handle pooling for efficient frame extraction (max 5 handles, 60s idle timeout)
- `horizontal_window_detection.py` - Auto-detection of analysis region boundaries
- `config.py` - Configuration constants (directories, file extensions, database path, worker counts)

**Analysis Flow:**
1. User uploads video → stored in `server/videos/`
2. Start analysis with parameters → TaskManager creates background task in ThreadPoolExecutor
3. Each frame: read → edge detection → path calculation → measurement points → batch to buffer
4. Frame results batched and persisted to SQLite every 25 frames (configurable)
5. On completion, contraction detection auto-runs on the heatmap matrix
6. Heatmap built on-demand from stored measurement point pairs (mpp data), cached to disk

**Database Schema (SQLite with WAL mode, foreign keys enabled):**
- `analyses` - Analysis metadata (id, video_id, parameters JSON, status, progress, global_data JSON, created_at, completed_at, error_message)
- `frames` - Per-frame results (analysis_id FK, frame_number, frame_data JSON; composite PK)
- `contraction_events` - Detected contractions (id, analysis_id FK, event metrics: duration, height, velocity, line_fit, areas, etc.)
- `combined_analyses` - Combined analysis pairs (id, name, analysis_ids JSON array of 2, created_at, metadata JSON)

### Frontend Structure

Vue 3 application with TypeScript, using Composition API and `<script setup>`:

**Routing (Vue Router):**
- `/` → HomeView (main application)
- `/video/:videoId` → HomeView (URL-based video preloading)
- `/about` → AboutView (lazy-loaded)

**State Management (Pinia):**
- `stores/analysis.ts` - Central store (~1200 lines) managing videos, analyses, frame data, contraction events, combined analyses, and polling

**Key Components:**
- `VideoSelector.vue` - Video upload, selection, re-encoding UI, and clear-all-data
- `VideoPlayer.vue` - Frame-by-frame rendering via `<img>`, canvas overlay for paths/regions/measurement points
- `MediaController.vue` - Playback controls (play/pause/seek/timeline), combined mode synced seeking
- `MediaViewer.vue` - Viewport switcher (Video/Heatmap/Heatmap Diff), overlay toggles, preview position
- `AnalysisParams.vue` - Edge detection parameter form with auto-detection and settings persistence
- `AnalysisResults.vue` - Progress display, analysis controls (start/stop/restart), statistics, events-per-minute
- `HeatmapViewer.vue` - Canvas heatmap with zoom/pan, axis labels, tooltips, contraction overlays
- `HeatmapDiffViewer.vue` - Diverging color scale (blue/white/red) for combined analysis comparison
- `ContractionDetectionControls.vue` - Detection parameter controls with detect/clear buttons
- `ContractionEventsList.vue` - Sortable event table with CSV export
- `DisplaySettingsControls.vue` - Pixel-to-MM calibration, auto-calibrate, heatmap color range settings
- `CombineAnalysisDialog.vue` - Modal for combining two analyses with validation
- `AnalysisTabNavigation.vue` - Tab switcher for combined mode (Analysis 1 / Analysis 2 / Combined)

**UI Component Library:**
- shadcn-vue based components in `components/ui/` (button, input, label, slider, popover, radio-group, checkbox, select, button-group, item, separator, icon)

**Data Flow:**
1. User selects video → metadata fetched → stored in Pinia
2. Adjust parameters → live preview via `/api/analysis/frame` endpoint
3. Start analysis → poll status endpoint every 10s for progress updates
4. View results → fetch frame data in chunks, render overlays on video
5. Generate heatmap → fetch binary heatmap data, render with Canvas
6. Detect contractions → auto-run on completion or manual trigger, overlay events on heatmap
7. Compare analyses → combine two analyses, view heatmap diffs

**Lib Modules:**
- `lib/api.ts` - Typed API wrapper with AbortController-based request cancellation (prevents duplicate concurrent requests)
- `lib/colormap.ts` - Heatmap color gradient generation
- `lib/constants.ts` - Shared constants (PIXEL_TO_MM_FACTOR, HEATMAP_MIN_MM, HEATMAP_MAX_MM)
- `lib/utils.ts` - General utilities

**Composables:**
- `composables/useHeatmapCache.ts` - Session-level heatmap caching with LRU eviction (max 10 analyses)

### Integration Points

**API Endpoints:**

*Video Management:*
- `POST /api/videos/upload` - Upload video file
- `GET /api/videos` - List all videos
- `GET /api/videos/{id}/metadata` - Video metadata (FPS, frames, dimensions, codec)
- `POST /api/videos/{id}/reencode` - Re-encode video to H.264
- `GET /api/videos/{id}/frame/{frame_number}/image` - Frame as JPEG image
- `POST /api/videos/{id}/calibrate` - Tube-based calibration for pixel-to-mm
- `GET /api/videos/{id}/settings` - Get saved analysis parameters
- `PUT /api/videos/{id}/settings` - Save analysis parameters
- `GET /api/videos/{id}/display-settings` - Get video display settings
- `PUT /api/videos/{id}/display-settings` - Update video display settings

*Analysis Lifecycle:*
- `POST /api/analysis/start` - Start new analysis
- `GET /api/analysis` - List analyses (with optional video_id/status filters)
- `GET /api/analysis/{id}/status` - Analysis progress and status
- `POST /api/analysis/{id}/stop` - Stop running analysis
- `DELETE /api/analysis/{id}` - Delete analysis and results

*Analysis Data:*
- `POST /api/analysis/frame` - Analyze single frame (live preview)
- `GET /api/analysis/{id}/frame/{frame_number}` - Single frame data
- `GET /api/analysis/{id}/frames` - Multiple frames (paginated, max 3000)
- `GET /api/analysis/{id}/frame-index` - List of processed frame numbers
- `POST /api/analysis/detect-window` - Detect horizontal window boundaries

*Heatmap:*
- `GET /api/analysis/{id}/heatmap/meta` - Heatmap metadata (width, height, min/max)
- `GET /api/analysis/{id}/heatmap/raw` - Raw binary heatmap (Float32Array)

*Display Settings:*
- `GET /api/analysis/{id}/display-settings` - Analysis display settings
- `PUT /api/analysis/{id}/display-settings` - Update display settings
- `GET /api/analysis/{id}/display-settings/suggestions` - Auto-calculated display range

*Contraction Detection:*
- `POST /api/analysis/{id}/detect-contractions` - Run contraction detection
- `GET /api/analysis/{id}/contractions` - Get contraction events
- `DELETE /api/analysis/{id}/contractions` - Clear contraction results

*Combined Analyses:*
- `POST /api/combined-analyses/validate` - Check compatibility of two analyses
- `POST /api/combined-analyses` - Create combined analysis
- `GET /api/combined-analyses` - List combined analyses
- `GET /api/combined-analyses/{id}` - Get combined analysis details
- `DELETE /api/combined-analyses/{id}` - Delete combined analysis
- `GET /api/combined-analyses/{id}/heatmap-diff/metadata` - Heatmap diff metadata
- `GET /api/combined-analyses/{id}/heatmap-diff/raw` - Heatmap diff binary data

*Maintenance:*
- `DELETE /api/clear-all-data` - Factory reset: clear all data and caches

**CORS Configuration:**
- Backend allows `http://localhost:5173` and `http://127.0.0.1:5173` (dev frontend)
- Update `server/main.py` CORS middleware when adding new origins

**Environment Variables:**
- Frontend: `VITE_API_BASE_URL` (defaults to `http://localhost:8000`)
- Backend: `ANALYSIS_MAX_WORKERS` (default: cpu_count - 1), `ANALYSIS_PERSIST_EVERY_N_FRAMES` (default: 25)

### Edge Detection

The system currently uses the **Silhouette** method (`edge_detection_silhouette.py`) — a mask-based segmentation approach:

1. Apply Gaussian blur to frame
2. Create binary object mask via thresholding
3. Morphological closing to fill gaps
4. Detect top/bottom edges at evenly-spaced x positions
5. Smooth and interpolate paths

**Silhouette Parameters (in `AnalysisParameters`):**
- `silhouette_blur_ksize_x/y` (1-50, default 7) - Gaussian blur kernel size
- `silhouette_blur_sigma` (0.1-10.0, default 1.6) - Gaussian blur sigma
- `silhouette_close_k` (1-50, default 5) - Morphological closing kernel size
- `silhouette_x_step` (1-20, default 7) - X sampling step
- `silhouette_band` (1-200, default 60) - Band height for edge search
- `silhouette_median_k` (3-101 odd, default 3) - Median filter kernel

**Common Parameters:**
- `smoothing_factor` (0.0-1.0, default 0.2) - Path smoothing strength
- `horizontal_window_x_left/right` (optional) - Region-of-interest boundaries
- `num_tracking_points` (30|50|80|120|200, default 30) - Number of measurement points
- `distribution_method` ("center_line_projection"|"x_axis_even", default "center_line_projection")

### Analysis Control System

The system supports flexible analysis control:
- **Start** - Begin new analysis with current parameters
- **Stop** - Cancel running analysis (status → cancelled)
- **Restart** - Clear all results, start from frame 0 (optionally with new parameters)

### Combined Analysis Feature

Allows comparing two analyses side-by-side:
1. **Validate** - Check compatibility (same tracking points, distribution method, both completed)
2. **Create** - Store combined analysis pair with name
3. **View** - Tab-based switching between Analysis 1 / Analysis 2 / Combined
4. **Heatmap Diff** - Compute and visualize differences between the two heatmaps
5. **Synced Playback** - Frame seeking synchronized across both videos

### Calibration

Tube-based calibration for physical measurements:
- Measures tube width in pixels at the right edge of the frame
- Computes pixel-to-mm conversion factor from known tube width (default 11mm)
- Auto-triggered on video upload
- Factor shared between backend (`config.py`) and frontend (`lib/constants.ts`) — must stay in sync

### Video Re-encoding

Videos using AV1 or other non-H.264 codecs can be re-encoded:
- `encoder.py` handles FFmpeg-based conversion to H.264/libx264
- Frontend auto-detects when re-encoding is needed
- Shows encoding progress and size reduction statistics

### Caching Strategy

**Backend Caching:**
- Video metadata cached to `{video_stem}.json` alongside video file
- Heatmap metadata cached to `{video_stem}_analysis_{id}_heatmap_meta.json`
- Heatmap binary data cached to `{video_stem}_analysis_{id}_heatmap_raw.bin`
- Cache invalidation: Empty matrices (width=0 or height=0) are regenerated

**Frontend Caching:**
- Heatmap data: session-level LRU cache (max 10 analyses) in `useHeatmapCache` composable
- Frame data: store-level LRU cache (max 20 frames, 40 in combined mode)
- Browser HTTP cache for frame images (1-hour cache headers)
- AbortController-based request cancellation prevents stale concurrent requests

### Video Frame Delivery

The system delivers video content frame-by-frame as JPEG images, NOT as streaming video:
- Frontend requests specific frames: `GET /api/videos/{id}/frame/{frame_number}/image`
- Backend uses OpenCV (`cv2.VideoCapture`) to seek and extract the exact frame
- Frame is encoded as JPEG and returned with HTTP caching headers (1-hour TTL)
- `video_pool.py` implements efficient frame extraction:
  - LRU cache of video file handles (max 5 handles)
  - Idle timeout closes unused handles after 60 seconds
  - Reuses handles across requests to same video
- Frontend uses `<img>` element with dynamic `src` pointing to frame endpoint

**Why frame-by-frame instead of streaming?**
- Deterministic frame access for reproducible analysis
- Precise frame synchronization with overlays and analysis data
- Simpler state management (no need to handle video seeking callbacks)
- Works better with frame multiplier system (see below)

### Performance Considerations

**Memory Management:**
- Explicit `del matrix` after heatmap operations (matrices can be 100s of MB)
- Video frame pooling with LRU cache and idle timeout (video_pool.py)
- Frame data fetched in chunks (max 3000 frames per request)

**Async Processing:**
- Analysis runs in ThreadPoolExecutor (max workers = cpu_count - 1)
- Frame results batched and persisted every 25 frames
- Task cancellation supported
- Contraction detection auto-runs on analysis completion

**Compression:**
- Brotli compression (quality 6) for API responses >500 bytes
- Fallback to GZip (level 6) if client doesn't support Brotli

### Testing Practices

- Backend: Use pytest with httpx.AsyncClient for endpoint testing
- Frontend: Use Vitest + Vue Test Utils for component tests
- Mock external dependencies with `app.dependency_overrides` (FastAPI)
- Add regression tests for bugfixes

### Settings Persistence

**Per-video settings** saved in JSON files alongside videos:
- File: `{video_path}.json`
- Structure: `{"parameters": {...}, "metadata": {"frame_multiplier": 1.0}, "display_settings": {...}}`
- `frame_multiplier` accounts for downsampled videos (seek frame N → actual frame N*multiplier)

**Per-analysis display settings** stored in the `analyses` table and accessed via API.

### Contraction Detection Algorithm

Post-analysis feature that operates on heatmap data (auto-runs on completion, can also be triggered manually):
1. Build heatmap matrix from stored measurement point pairs
2. Transpose to (points, frames) format
3. Apply Gaussian smoothing (configurable sigma for y/t axes)
4. Threshold with percentile or manual value
5. Binary morphology (opening/closing) to clean regions
6. Connected component labeling
7. Filter by minimum pixel count, area, and height
8. Calculate statistics: velocity, duration, height, area (exact + triangle approximation)
9. Fit line to each event (slope = velocity)
10. Store in `contraction_events` table with foreign key to analysis

## Common Tasks

### Adding a New Edge Detection Method

1. Create `server/edge_detection_<method>.py` with function signature:
   ```python
   def edge_detection_<method>_calculation(
       frame: np.ndarray,
       smoothing_factor: float,
       horizontal_window_x_left: int | None,
       horizontal_window_x_right: int | None,
       <method_specific_params>,
   ) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
       # Returns (path_top, path_bottom)
   ```

2. Add method-specific parameters to `AnalysisParameters` in `server/models.py`

3. Add dispatch case in `server/main.py`:
   - `analyze_frame` endpoint
   - Background analysis in `server/tasks.py` (`process_frame_with_context`)

4. Update TypeScript types in `client/src/lib/api.ts` (`AnalysisParameters`)

5. Add parameter controls to `client/src/components/AnalysisParams.vue`

### Adding a New API Endpoint

1. Define Pydantic request/response models in `server/models.py`
2. Add route in `server/main.py` with type annotations
3. Update `client/src/lib/api.ts` with TypeScript types and API function
4. Use in Pinia store or component via composable pattern

### Debugging Analysis Issues

1. Check analysis status: `GET /api/analysis/{id}/status`
2. Look at processed frames count vs. total frames
3. Examine stored frame data: `GET /api/analysis/{id}/frame/{frame_number}`
4. Check database directly: `sqlite3 server/analyses.db` → `.schema` → `SELECT * FROM analyses WHERE id='...'`
5. Backend logs in terminal (uvicorn default logging)
6. Frontend network tab for API errors

### Working with Video Frame Multipliers

Some videos are pre-processed with frame skipping (e.g., every 5th frame). The `frame_multiplier` setting accounts for this:
- User requests frame N → backend seeks to frame `N * frame_multiplier`
- Stored in video settings JSON: `{"metadata": {"frame_multiplier": 5.0}}`
- Applied in: `get_frame_image`, `analyze_frame` endpoints

## Storage Layout

```
server/
  videos/          # Uploaded video files + per-video settings JSON
  results/         # (Reserved for future use)
  analyses.db      # SQLite database (WAL mode)
```

## Type Safety

- Backend: Pydantic models enforce runtime validation
- Frontend: TypeScript strict mode enabled (`noImplicitAny`, `strictNullChecks`)
- Keep backend Pydantic models and frontend TypeScript types in sync
- Update both in same PR when changing API contracts

## Dependency Management

- Backend: `uv` for Python dependencies (fast, deterministic). Key deps: fastapi, opencv-python, scipy, numba, brotli-asgi, python-ffmpeg
- Frontend: npm for JavaScript dependencies. Key deps: vue 3, pinia, vue-router, tailwindcss, shadcn-vue, reka-ui, @vueuse/core
- Keep dependencies minimal; document rationale for new deps in PRs
- Node 20.19+ or 22.12+ required (per `package.json` engines)
