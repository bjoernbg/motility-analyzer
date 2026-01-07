# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Motility Analyzer is a full-stack video analysis application for detecting and tracking biological motility patterns in microscopy videos. The system processes videos frame-by-frame to detect edges, track movement, generate heatmaps, and detect contraction patterns in the data.

**Tech Stack:**
- **Backend:** FastAPI (Python 3.12+), OpenCV, NumPy, SciPy, Numba
- **Frontend:** Vue 3 + TypeScript, Vite, Pinia, TailwindCSS
- **Database:** SQLite (for analysis metadata, frame results, contraction events)
- **Storage:** File-based storage for videos and cached results

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
1. **Video ingestion** → `storage.py` (VideoStorage)
2. **Metadata extraction** → `metadata.py` (cached video properties: FPS, frame count, dimensions)
3. **Analysis execution** → `tasks.py` (TaskManager coordinates async frame processing)
4. **Edge detection** → Multiple methods available:
   - `costmap.py` - Original cost map pathfinding algorithm
   - `edge_detection_1d.py` - 1D signal-based detection
   - `edge_detection_canny.py` - Canny edge detection
   - `edge_detection_silhouette.py` - Mask-based segmentation
   - `edge_utils.py` - Shared utilities (path smoothing, clipping)
5. **Path calculation** → `analysis.py` (center path, measurement point pairs)
6. **Data storage** → `database.py` (SQLite: analyses, frames, contraction_events)
7. **Contraction detection** → `contraction_detection.py` (spatiotemporal pattern detection on heatmaps)

**Key Modules:**
- `models.py` - Pydantic models for API contracts (Video, Analysis, FrameData, ContractionEvent, etc.)
- `video_pool.py` - Efficient video frame extraction with handle pooling and caching
- `horizontal_window_detection.py` - Auto-detection of analysis region boundaries
- `config.py` - Configuration constants (file paths, size limits)

**Analysis Flow:**
1. User uploads video → stored in `data/videos/`
2. Start analysis with parameters → TaskManager creates background task
3. Each frame: read → edge detection → path calculation → measurement points → store in DB
4. Results stored per-frame in SQLite `frames` table (JSON serialized)
5. Heatmap built on-demand from stored measurement point pairs (mpp data)
6. Contraction detection runs post-analysis on the heatmap matrix

**Database Schema:**
- `analyses` - Analysis metadata (video_id, parameters, status, progress)
- `frames` - Per-frame results (analysis_id, frame_number, frame_data JSON)
- `contraction_events` - Detected contractions (analysis_id, temporal/spatial ranges, velocity, areas)

### Frontend Structure

Vue 3 application with TypeScript, using Composition API and `<script setup>`:

**State Management (Pinia):**
- `stores/analysis.ts` - Central store for analysis state, video metadata, frame data, contraction events

**Key Components:**
- `VideoSelector.vue` - Video upload and selection UI
- `VideoPlayer.vue` - Video playback with overlay rendering (paths, measurement points)
- `MediaController.vue` - Playback controls (play/pause/seek)
- `AnalysisParams.vue` - Large form for edge detection parameters (method-specific fields)
- `AnalysisResults.vue` - Analysis progress, controls (start/stop/resume/restart)
- `HeatmapViewer.vue` - Heatmap visualization with contraction overlays
- `ContractionDetectionControls.vue` - Contraction detection parameter controls
- `ContractionEventsList.vue` - List of detected contraction events with statistics

**Data Flow:**
1. User selects video → metadata fetched → stored in Pinia
2. Adjust parameters → live preview via `/api/analysis/frame` endpoint
3. Start analysis → poll status endpoint for progress updates
4. View results → fetch frame data in chunks, render overlays on video
5. Generate heatmap → fetch binary heatmap data, render with Canvas
6. Detect contractions → POST to contraction detection endpoint, overlay events on heatmap

**API Client:**
- `lib/api.ts` - Typed API wrapper with request cancellation (AbortController)
- Types mirror backend Pydantic models for type safety

**Composables:**
- `composables/useHeatmapCache.ts` - Client-side heatmap data caching

### Integration Points

**API Endpoints:**
- `/api/videos/*` - Video management (upload, list, stream, metadata)
- `/api/analysis/*` - Analysis lifecycle (start, stop, resume, restart, status, frames)
- `/api/analysis/{id}/heatmap/*` - Heatmap data (metadata, raw binary Float32Array)
- `/api/analysis/{id}/detect-contractions` - POST to trigger contraction detection
- `/api/analysis/{id}/contractions` - GET contraction detection results
- `/api/videos/{id}/settings` - GET/PUT saved analysis parameters per video

**CORS Configuration:**
- Backend allows `http://localhost:5173` and `http://127.0.0.1:5173` (dev frontend)
- Update `server/main.py` CORS middleware when adding new origins

**Environment Variables:**
- Frontend: `VITE_API_BASE_URL` (defaults to `http://localhost:8000`)

### Edge Detection Methods

The system supports four edge detection methods, each with distinct parameters:

1. **Costmap** (original) - Uses cost map pathfinding with contrast enhancement
   - Parameters: `alpha`, `band`, `threshold_percentile`, `subsequent_frame_band`

2. **Signal 1D** - Analyzes horizontal strips as 1D signals
   - Parameters: `strip_width`, `band_height`, `sigma`

3. **Canny** - Classical Canny edge detection with path following
   - Parameters: `canny_threshold1`, `canny_threshold2`, `canny_aperture_size`

4. **Silhouette** - Mask-based segmentation approach
   - Parameters: `silhouette_blur_ksize_x/y`, `silhouette_blur_sigma`, `silhouette_close_k`, `silhouette_x_step`, `silhouette_band`, `silhouette_median_k`

Common parameters across methods: `smoothing_factor`, `horizontal_window_x_left/right`, `num_tracking_points`, `distribution_method`

### Analysis Resume/Restart System

The system supports flexible analysis control:
- **Stop** - Cancel running analysis (status → cancelled)
- **Resume** - Continue from last processed frame (cancelled/failed → processing)
- **Restart** - Clear all results, start from frame 0 (optionally with new parameters)

Resume logic checks last stored frame number and continues from there, reusing stored paths for continuity.

### Caching Strategy

**Backend Caching:**
- Video metadata cached to `{video_stem}.json` (FPS, frame count, codec, etc.)
- Heatmap metadata cached to `{video_stem}_analysis_{id}_heatmap_meta.json`
- Heatmap binary data cached to `{video_stem}_analysis_{id}_heatmap_raw.bin`
- Cache invalidation: Empty matrices (width=0 or height=0) are regenerated

**Frontend Caching:**
- Heatmap data cached in composable with `Map<string, Float32Array>`
- Browser HTTP cache used for frame images (1-hour cache headers)

### Video Frame Delivery

The system delivers video content frame-by-frame as JPEG images, NOT as streaming video:
- Frontend requests specific frames: `GET /api/videos/{id}/frame/{frame_number}/image`
- Backend uses OpenCV (`cv2.VideoCapture`) to seek and extract the exact frame
- Frame is encoded as JPEG and returned with HTTP caching headers (1-hour TTL)
- `video_pool.py` implements efficient frame extraction:
  - LRU cache of video file handles (max 5 handles)
  - Idle timeout closes unused handles after 60 seconds
  - Reuses handles across requests to same video
- Each frame request is deterministic (same frame always returns same image)
- No HTML `<video>` element or video streaming protocols in the frontend
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
- Analysis runs in background asyncio tasks
- Task cancellation supported via `asyncio.Task.cancel()`
- TaskManager tracks active tasks by analysis_id

**Compression:**
- Brotli compression (quality 6) for API responses >500 bytes
- Fallback to GZip if client doesn't support Brotli

### Testing Practices

- Backend: Use pytest with httpx.AsyncClient for endpoint testing
- Frontend: Use Vitest + Vue Test Utils for component tests
- Mock external dependencies with `app.dependency_overrides` (FastAPI)
- Add regression tests for bugfixes

### Settings Persistence

Analysis parameters are saved per-video in JSON files alongside videos:
- File: `{video_path}.json`
- Structure: `{"parameters": {...}, "metadata": {"frame_multiplier": 1.0}}`
- `frame_multiplier` accounts for downsampled videos (seek frame N → actual frame N*multiplier)

### Contraction Detection Algorithm

Post-analysis feature that operates on heatmap data:
1. Build heatmap matrix from stored measurement point pairs
2. Transpose to (points, frames) format
3. Apply Gaussian smoothing (configurable sigma for y/t axes)
4. Threshold with percentile or manual value
5. Binary morphology (opening/closing) to clean regions
6. Connected component labeling
7. Filter by minimum pixel count
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
   - `analyze_frame` endpoint (line ~672)
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
4. Check database directly: `sqlite3 data/analyses.db` → `.schema` → `SELECT * FROM analyses WHERE id='...'`
5. Backend logs in terminal (uvicorn default logging)
6. Frontend network tab for API errors

### Working with Video Frame Multipliers

Some videos are pre-processed with frame skipping (e.g., every 5th frame). The `frame_multiplier` setting accounts for this:
- User requests frame N → backend seeks to frame `N * frame_multiplier`
- Stored in video metadata JSON: `{"metadata": {"frame_multiplier": 5.0}}`
- Applied in: `get_frame_image`, `analyze_frame` endpoints

## Type Safety

- Backend: Pydantic models enforce runtime validation
- Frontend: TypeScript strict mode enabled (`noImplicitAny`, `strictNullChecks`)
- Keep backend Pydantic models and frontend TypeScript types in sync
- Update both in same PR when changing API contracts

## Dependency Management

- Backend: `uv` for Python dependencies (fast, deterministic)
- Frontend: npm for JavaScript dependencies
- Keep dependencies minimal; document rationale for new deps in PRs
- Node 20.19+ or 22.12+ required (per `package.json` engines)
