"""FastAPI application for video analysis."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated
from copy import deepcopy
import logging

import cv2
import json
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from brotli_asgi import BrotliMiddleware

import numpy as np

from .analysis import calculate_center_path, calculate_measurement_point_pairs
from .calibration import calibrate_tube_width
from .config import ALLOWED_VIDEO_EXTENSIONS, MAX_UPLOAD_SIZE, PIXEL_TO_MM_FACTOR
from .edge_detection_silhouette import edge_detection_silhouette_calculation
from .database import (
    MultiViewSessionDB,
    VideoLabelDB,
    clear_all_data,
    init_database,
)
from .encoder import reencode_video
from .horizontal_window_detection import horizontal_window_detection
from .metadata import get_video_metadata
from .models import (
    Analysis,
    AnalysisParameters,
    CalibrationResult,
    DisplaySettings,
    FrameData,
    HeatmapMeta,
    ReencodeResult,
    ReencodeStatistics,
    SuggestedDisplaySettings,
    Video,
    VideoMetadata,
    ContractionDetectionParameters,
    ContractionDetectionResult,
    ContractionEvent,
    ContractionEventLineFit,
    MultiViewSession,
    MultiViewSessionCreate,
    MultiViewSessionNameUpdate,
    MultiViewSessionMetadata,
    MultiViewAlignmentState,
    MultiViewAlignmentSuggestRequest,
    MultiViewAlignmentSuggestResponse,
    MultiViewAlignmentUpdate,
    MultiViewAutoReanalyzeRequest,
    MultiViewSessionSourcesUpdate,
    MultiViewRealignJob,
    MultiViewValidationRequest,
    MultiViewValidationResult,
    DisplayNameUpdate,
    VideoDeleteResult,
)
from .storage import (
    AnalysisStorage,
    ResultsStorage,
    VideoStorage,
    clear_all_video_caches,
    delete_all_video_files,
)
from .tasks import task_manager
from .video_pool import VideoHandlePool
from .contraction_detection import detect_contractions, calculate_physical_spacing
from .multiview_validation import validate_multi_view_pair
from .multiview_alignment import (
    AUTO_APPLY_CONFIDENCE_THRESHOLD,
    compute_alignment_suggestion,
)

# Initialize database on startup
init_database()

app = FastAPI(title="Video Analysis API", version="1.0.0")
logger = logging.getLogger("uvicorn.error")

# Initialize video handle pool for efficient frame extraction
video_pool = VideoHandlePool(max_handles=5, idle_timeout=60.0)
video_label_db = VideoLabelDB()

# Compression middleware (supports gzip and brotli)
# Compresses responses larger than 500 bytes, especially useful for JSON data
# Brotli is preferred if client supports it, falls back to gzip
# Order matters: Brotli first (checked first), then GZip as fallback
app.add_middleware(
    BrotliMiddleware,
    quality=6,  # Compression quality 1-11 (6 is a good balance)
    minimum_size=500,  # Only compress responses larger than 500 bytes
)
app.add_middleware(
    GZipMiddleware,
    minimum_size=500,
    compresslevel=6,  # Compression level 1-9 (6 is a good balance)
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Width", "X-Height", "X-Dtype"],
)


def _load_video_display_settings(video_path: Path) -> DisplaySettings:
    """Load display settings from the per-video JSON file."""
    settings_path = video_path.with_suffix(".json")
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                all_data = json.load(f)
                if "display_settings" in all_data:
                    return DisplaySettings(**all_data["display_settings"])
        except (json.JSONDecodeError, IOError, ValueError):
            pass
    return DisplaySettings(
        pixel_to_mm_factor=PIXEL_TO_MM_FACTOR, heatmap_min_mm=3.0, heatmap_max_mm=30.0
    )


def _save_video_display_settings(video_path: Path, settings: DisplaySettings) -> None:
    """Save display settings to the per-video JSON file, preserving other keys."""
    settings_path = video_path.with_suffix(".json")
    existing_data = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                existing_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing_data = {}
    existing_data["display_settings"] = settings.model_dump()
    with open(settings_path, "w") as f:
        json.dump(existing_data, f, indent=2, default=str)


def _normalize_optional_display_name(raw_name: str | None) -> str | None:
    """Normalize optional display names; empty values clear the custom name."""
    if raw_name is None:
        return None
    cleaned = raw_name.strip()
    return cleaned if cleaned else None


@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "Video Analysis API"}


def parameters_match(params1: dict, params2: dict, tolerance: float = 0.001) -> bool:
    """Compare two parameter dictionaries with tolerance for floating-point values.

    Args:
        params1: First parameter dictionary
        params2: Second parameter dictionary
        tolerance: Tolerance for floating-point comparisons

    Returns:
        True if parameters match (within tolerance for floats)
    """
    # Check if all keys match
    if set(params1.keys()) != set(params2.keys()):
        return False

    for key in params1:
        val1 = params1[key]
        val2 = params2[key]

        # Handle None values
        if val1 is None and val2 is None:
            continue
        if val1 is None or val2 is None:
            return False

        # Compare floating-point numbers with tolerance
        if isinstance(val1, float) and isinstance(val2, float):
            if abs(val1 - val2) > tolerance:
                return False
        # Compare integers and other types exactly
        elif val1 != val2:
            return False

    return True


@app.post("/api/videos/upload", response_model=Video)
async def upload_video(file: Annotated[UploadFile, File(...)]):
    """Upload a video file."""
    # Check file size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_VIDEO_EXTENSIONS:
        allowed_extensions = ", ".join(sorted(ALLOWED_VIDEO_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed extensions: {allowed_extensions}",
        )

    # Save file
    file_path = VideoStorage.save_uploaded_file(contents, file.filename)

    # Create video record using filename stem as ID (consistent with list_videos)
    video_id = Path(file_path).stem
    video = Video(
        id=video_id,
        filename=Path(file_path).name,
        file_path=file_path,
    )

    return video


@app.get("/api/videos", response_model=list[Video])
def list_videos():
    """List all available videos."""
    videos = VideoStorage.list_videos()
    display_name_map = video_label_db.list_display_names([video.id for video in videos])
    for video in videos:
        video.display_name = display_name_map.get(video.id)
    return videos


@app.put("/api/videos/{video_id}/display-name", response_model=Video)
def update_video_display_name(video_id: str, body: DisplayNameUpdate):
    """Update or clear a custom video display name."""
    video = VideoStorage.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    display_name = _normalize_optional_display_name(body.display_name)
    video_label_db.set_display_name(video_id, display_name)
    video.display_name = display_name
    return video


@app.delete("/api/videos/{video_id}", response_model=VideoDeleteResult)
async def delete_video(video_id: str):
    """Delete a video and all dependent analysis/session records."""
    video = VideoStorage.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video_path = Path(video.file_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    analysis_storage = AnalysisStorage()
    analyses = analysis_storage.list_analyses(video_id=video_id, limit=1000)
    analysis_ids = [analysis.id for analysis in analyses]

    # Stop in-flight analyses for this video before deletion.
    for analysis in analyses:
        if analysis.status == "processing":
            await task_manager.stop_analysis(analysis.id)

    deleted_multi_view_session_ids: list[str] = []
    if analysis_ids:
        deleted_multi_view_session_ids = (
            multi_view_session_db.delete_sessions_by_analysis_ids(analysis_ids)
        )

    for analysis_id in analysis_ids:
        analysis_storage.delete_analysis(analysis_id)
        task_manager.analyses.pop(analysis_id, None)
        task_manager.tasks.pop(analysis_id, None)

    clear_all_video_caches(video_id, analysis_ids)
    video_label_db.set_display_name(video_id, None)
    video_pool.close_video(video_path)

    try:
        video_path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete video file: {exc}") from exc

    return VideoDeleteResult(
        message="Video deleted successfully",
        deleted_analysis_ids=analysis_ids,
        deleted_multi_view_session_ids=deleted_multi_view_session_ids,
    )


@app.get("/api/videos/{video_id}/metadata", response_model=VideoMetadata)
def get_video_metadata_endpoint(video_id: str):
    """Get video metadata (frames, fps, size, etc.)."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        # Use the metadata module which automatically loads from cache or generates
        metadata = get_video_metadata(video_path)
        return metadata
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/videos/{video_id}/reencode", response_model=ReencodeResult)
async def reencode_video_endpoint(video_id: str):
    """
    Re-encode a video with optimized settings and replace the original.

    This operation:
    1. Deletes all analyses associated with the video
    2. Clears all cached metadata and heatmap files
    3. Re-encodes the video using libsvtav1 codec with optimized settings
    4. Replaces the original video file (converts to .mp4)
    5. Regenerates video metadata

    The operation is blocking and may take several minutes for large videos.

    Args:
        video_id: ID of the video to re-encode

    Returns:
        Updated Video object with new metadata

    Raises:
        404: Video not found
        500: Re-encoding failed (original video is preserved)
    """
    # Validate video exists
    video = VideoStorage.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    try:
        # Get all analyses for this video
        analysis_storage = AnalysisStorage()
        analyses = analysis_storage.list_analyses(video_id=video_id, limit=1000)
        analysis_ids = [analysis.id for analysis in analyses]

        # Get original metadata for codec info
        original_metadata = get_video_metadata(video_path)
        original_codec = original_metadata.codec

        # Delete all analyses
        for analysis in analyses:
            try:
                analysis_storage.delete_analysis(analysis.id)
            except Exception as e:
                # Log but continue if deletion fails
                print(f"Warning: Failed to delete analysis {analysis.id}: {e}")

        # Clear all caches (metadata, heatmaps)
        clear_all_video_caches(video_id, analysis_ids)

        # Re-encode the video (this may take minutes and is blocking)
        new_video_path, stats = reencode_video(video_path)

        # Force-regenerate metadata
        get_video_metadata(new_video_path, force_regenerate=True)

        # Create updated Video object
        # Note: video_id is based on stem, which remains the same even if extension changed
        updated_video = Video(
            id=new_video_path.stem,
            filename=new_video_path.name,
            display_name=video_label_db.get_display_name(new_video_path.stem),
            file_path=str(new_video_path),
        )

        # Create statistics object
        statistics = ReencodeStatistics(
            duration_seconds=stats["duration_seconds"],
            original_size_bytes=stats["original_size_bytes"],
            new_size_bytes=stats["new_size_bytes"],
            size_reduction_percent=stats["size_reduction_percent"],
            original_codec=original_codec,
            new_codec="libsvtav1",
        )

        return ReencodeResult(video=updated_video, statistics=statistics)

    except RuntimeError as e:
        # Re-encoding failed, original video is preserved
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=500, detail=f"Re-encoding failed: {str(e)}"
        ) from e


@app.post("/api/analysis/start", response_model=Analysis)
async def start_analysis(video_id: str, parameters: AnalysisParameters):
    """Start analysis for a video."""
    # Check if video exists
    video = VideoStorage.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Create analysis
    analysis = Analysis(
        video_id=video_id,
        parameters=parameters.model_dump(),
    )

    # Register analysis
    task_manager.register_analysis(analysis)

    # Check if results already exist (based on video_id and parameters hash)
    # For simplicity, we'll create a new analysis each time
    # In production, you might want to hash parameters and check for existing results

    # Start background task
    task = asyncio.create_task(
        task_manager.start_analysis(analysis.id, video_id, parameters)
    )
    task_manager.tasks[analysis.id] = task

    return analysis


@app.get("/api/analysis/{analysis_id}/status", response_model=Analysis)
def get_analysis_status(analysis_id: str):
    """Get analysis status."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@app.put("/api/analysis/{analysis_id}/display-name", response_model=Analysis)
def update_analysis_display_name(analysis_id: str, body: DisplayNameUpdate):
    """Update or clear a custom analysis display name."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    display_name = _normalize_optional_display_name(body.display_name)
    analysis_storage = AnalysisStorage()
    analysis_storage.update_analysis(analysis_id, display_name=display_name)
    analysis.display_name = display_name
    task_manager.analyses[analysis_id] = analysis
    return analysis


@app.post("/api/analysis/{analysis_id}/stop", response_model=Analysis)
async def stop_analysis(analysis_id: str):
    """Stop a running analysis."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    success = await task_manager.stop_analysis(analysis_id)
    if not success:
        raise HTTPException(
            status_code=400, detail="Analysis is not running or cannot be stopped"
        )

    return analysis


@app.get("/api/analysis/{analysis_id}/heatmap/meta", response_model=HeatmapMeta)
def get_heatmap_meta(analysis_id: str):
    """Return metadata for heatmap: width (frames), height (points), dtype, min, max, fps."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    is_processing = analysis.status == "processing"

    # Get video metadata for FPS
    video_path = VideoStorage.get_video_path(analysis.video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Check for cached response (skip for processing analyses to get fresh data)
    cache_file = (
        video_path.parent
        / f"{video_path.stem}_analysis_{analysis_id}_heatmap_meta.json"
    )
    if not is_processing and cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                cached_data = json.load(f)
                cached_meta = HeatmapMeta(**cached_data)
                # Don't trust cached metadata if it's empty (width=0 or height=0)
                # This can happen if the cache was created before the analysis completed
                # or if there was no mpp data at the time
                if cached_meta.width > 0 and cached_meta.height > 0:
                    return cached_meta
                # If cached metadata is empty, regenerate it (analysis might be complete now)
        except (json.JSONDecodeError, IOError, ValueError):
            # If cache is corrupted, regenerate
            pass

    try:
        video_metadata = get_video_metadata(video_path)
        fps = video_metadata.fps
    except ValueError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get video metadata: {str(e)}"
        ) from e

    # Build heatmap matrix
    results_storage = ResultsStorage()
    db = results_storage.db
    matrix, min_val, max_val = db.build_heatmap_matrix(analysis_id)

    # Get display settings from video JSON
    display_settings = _load_video_display_settings(video_path)

    if matrix.size == 0:
        # No data available - explicitly delete empty matrix
        del matrix
        result = HeatmapMeta(
            width=0,
            height=0,
            dtype="float32",
            min=0.0,
            max=0.0,
            fps=fps,
            display_settings=display_settings,
        )
    else:
        frame_count, point_count = matrix.shape
        result = HeatmapMeta(
            width=frame_count,
            height=point_count,
            dtype="float32",
            min=min_val,
            max=max_val,
            fps=fps,
            display_settings=display_settings,
        )
        # Explicitly delete the matrix to free memory immediately
        # This is critical for large matrices that can be hundreds of MB
        del matrix

    # Cache the response (skip for processing analyses to avoid caching partial data)
    if not is_processing:
        try:
            with open(cache_file, "w") as f:
                json.dump(result.model_dump(), f, indent=2)
        except IOError:
            # If caching fails, continue without caching
            pass

    return result


@app.get("/api/analysis/{analysis_id}/heatmap/raw")
def get_heatmap_raw(analysis_id: str):
    """Return binary Float32Array (row-major: frame0[pt0..ptN], frame1[...], ...)."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    is_processing = analysis.status == "processing"

    # Get video path for cache location
    video_path = VideoStorage.get_video_path(analysis.video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Check for cached response (skip for processing analyses to get fresh data)
    cache_file = (
        video_path.parent / f"{video_path.stem}_analysis_{analysis_id}_heatmap_raw.bin"
    )
    cache_meta_file = (
        video_path.parent
        / f"{video_path.stem}_analysis_{analysis_id}_heatmap_raw_meta.json"
    )

    if not is_processing and cache_file.exists() and cache_meta_file.exists():
        try:
            # Load cached metadata for headers
            with open(cache_meta_file, "r") as f:
                meta = json.load(f)

            # Don't trust cached data if it's empty (width=0 or height=0)
            # This can happen if the cache was created before the analysis completed
            # or if there was no mpp data at the time
            if meta.get("width", 0) > 0 and meta.get("height", 0) > 0:
                # Load cached binary data
                with open(cache_file, "rb") as f:
                    cached_content = f.read()

                return Response(
                    content=cached_content,
                    media_type="application/octet-stream",
                    headers={
                        "X-Width": str(meta["width"]),
                        "X-Height": str(meta["height"]),
                        "X-Dtype": meta["dtype"],
                    },
                )
            # If cached metadata is empty, regenerate it (analysis might be complete now)
        except (json.JSONDecodeError, IOError, KeyError):
            # If cache is corrupted, regenerate
            pass

    # Build heatmap matrix
    results_storage = ResultsStorage()
    db = results_storage.db
    matrix, _, _ = db.build_heatmap_matrix(analysis_id)

    if matrix.size == 0:
        # Return empty response - explicitly delete empty matrix
        del matrix
        return Response(
            content=b"",
            media_type="application/octet-stream",
            headers={
                "X-Width": "0",
                "X-Height": "0",
                "X-Dtype": "float32",
            },
        )

    # Store shape before conversion (needed for headers and caching)
    matrix_shape = matrix.shape

    # Ensure float32 and contiguous (row-major, C-order)
    matrix = np.asarray(matrix, dtype=np.float32, order="C")
    matrix_bytes = matrix.tobytes()

    # Explicitly delete the matrix to free memory immediately
    # This is critical for large matrices that can be hundreds of MB
    del matrix

    # Cache the response (skip for processing analyses to avoid caching partial data)
    if not is_processing:
        try:
            with open(cache_file, "wb") as f:
                f.write(matrix_bytes)
            with open(cache_meta_file, "w") as f:
                json.dump(
                    {
                        "width": matrix_shape[0],
                        "height": matrix_shape[1],
                        "dtype": "float32",
                    },
                    f,
                )
        except IOError:
            # If caching fails, continue without caching
            pass

    # Return raw bytes
    return Response(
        content=matrix_bytes,
        media_type="application/octet-stream",
        headers={
            "X-Width": str(matrix_shape[0]),
            "X-Height": str(matrix_shape[1]),
            "X-Dtype": "float32",
        },
    )


@app.get("/api/analysis/{analysis_id}/display-settings", response_model=DisplaySettings)
def get_display_settings(analysis_id: str):
    """Get current display settings for an analysis (delegates to video-level settings)."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    video_path = VideoStorage.get_video_path(analysis.video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    return _load_video_display_settings(video_path)


@app.put("/api/analysis/{analysis_id}/display-settings", response_model=DisplaySettings)
def update_display_settings(analysis_id: str, settings: DisplaySettings):
    """Update display settings for an analysis (delegates to video-level settings)."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return update_video_display_settings(analysis.video_id, settings)


@app.get(
    "/api/analysis/{analysis_id}/display-settings/suggestions",
    response_model=SuggestedDisplaySettings,
)
def get_suggested_display_settings(analysis_id: str):
    """Calculate suggested display settings based on actual heatmap data."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Get current pixel_to_mm_factor from video-level display settings
    video_path = VideoStorage.get_video_path(analysis.video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    video_display_settings = _load_video_display_settings(video_path)
    current_factor = video_display_settings.pixel_to_mm_factor

    # Build heatmap matrix
    results_storage = ResultsStorage()
    db = results_storage.db
    matrix, min_val_px, max_val_px = db.build_heatmap_matrix(analysis_id)

    if matrix.size == 0:
        raise HTTPException(status_code=400, detail="No heatmap data available")

    # Convert to mm
    data_mm = matrix / current_factor

    # Calculate statistics
    min_mm = float(np.min(data_mm))
    max_mm = float(np.max(data_mm))
    median_mm = float(np.median(data_mm))

    # Use percentiles for suggested range (handles outliers better)
    suggested_min = float(np.percentile(data_mm, 5))  # 5th percentile
    suggested_max = float(np.percentile(data_mm, 95))  # 95th percentile

    # Round to reasonable precision
    suggested_min = round(suggested_min, 1)
    suggested_max = round(suggested_max, 1)

    # Explicitly delete matrix to free memory
    del matrix
    del data_mm

    return SuggestedDisplaySettings(
        pixel_to_mm_factor=current_factor,
        heatmap_min_mm=suggested_min,
        heatmap_max_mm=suggested_max,
        data_min_mm=round(min_mm, 2),
        data_max_mm=round(max_mm, 2),
        data_median_mm=round(median_mm, 2),
    )


@app.get("/api/analysis", response_model=list[Analysis])
def list_analyses(
    video_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List analyses with optional filters."""
    analysis_storage = AnalysisStorage()
    return analysis_storage.list_analyses(
        video_id=video_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@app.get("/api/analysis/{analysis_id}/frame/{frame_number}", response_model=FrameData)
def get_analysis_frame(analysis_id: str, frame_number: int):
    """Get frame data from stored analysis results."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if analysis.status != "completed":
        raise HTTPException(status_code=400, detail="Analysis not completed")

    results_storage = ResultsStorage()
    frame_data = results_storage.get_frame(analysis_id, frame_number)
    if not frame_data:
        raise HTTPException(
            status_code=404,
            detail=f"Frame {frame_number} not found in analysis results",
        )

    return frame_data


@app.get("/api/analysis/{analysis_id}/frames")
def get_analysis_frames(
    analysis_id: str,
    start: int = 0,
    count: int = 100,
):
    """Get a range of frames efficiently."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Cap chunk size to prevent oversized responses
    count = min(count, 3000)

    results_storage = ResultsStorage()
    db = results_storage.db

    # Get frames in the requested range
    frames = db.get_frames_range(analysis_id, start, count)

    # Get total count of available frames
    available_frames = db.get_available_frame_numbers(analysis_id)
    total_available = len(available_frames)

    return {
        "frames": [frame.model_dump() for frame in frames],
        "total_available": total_available,
        "requested_range": [start, start + count],
    }


@app.get("/api/analysis/{analysis_id}/frame-index")
def get_frame_index(analysis_id: str):
    """Return list of available frame numbers (for cache awareness)."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    results_storage = ResultsStorage()
    db = results_storage.db

    frame_numbers = db.get_available_frame_numbers(analysis_id)

    return {
        "frames": frame_numbers,
        "total": len(frame_numbers),
    }


@app.post("/api/analysis/frame", response_model=FrameData)
async def analyze_frame(
    video_id: str, frame_number: int, parameters: AnalysisParameters
):
    """Analyze a single frame of a video."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Load metadata to get frame_multiplier
    settings_path = video_path.with_suffix(".json")
    frame_multiplier = 1.0  # Default fallback
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                all_data = json.load(f)
                if (
                    "metadata" in all_data
                    and "frame_multiplier" in all_data["metadata"]
                ):
                    frame_multiplier = float(all_data["metadata"]["frame_multiplier"])
        except (json.JSONDecodeError, IOError, KeyError, ValueError):
            # If metadata can't be loaded, use default
            pass

    # Open video with OpenCV
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise HTTPException(status_code=500, detail="Failed to open video file")

    try:
        # Seek to the requested frame using multiplier from metadata
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_number * frame_multiplier))
        ret, frame = cap.read()
        if not ret:
            raise HTTPException(
                status_code=400, detail=f"Failed to read frame {frame_number}"
            )

        # Convert to numpy array
        frame_np = np.array(frame)

        # Edge detection using silhouette method
        path_top, path_bottom = edge_detection_silhouette_calculation(
            frame=frame_np,
            smoothing_factor=parameters.smoothing_factor,
            horizontal_window_x_left=parameters.horizontal_window_x_left,
            horizontal_window_x_right=parameters.horizontal_window_x_right,
            blur_ksize=(
                parameters.silhouette_blur_ksize_x,
                parameters.silhouette_blur_ksize_y,
            ),
            blur_sigma=parameters.silhouette_blur_sigma,
            close_k=parameters.silhouette_close_k,
            x_step=parameters.silhouette_x_step,
            band=parameters.silhouette_band,
            median_k=parameters.silhouette_median_k,
        )

        # Calculate center path with perpendicular projection
        path_center = calculate_center_path(
            path_top,
            path_bottom,
            horizontal_window_x_left=parameters.horizontal_window_x_left,
            horizontal_window_x_right=parameters.horizontal_window_x_right,
        )

        # Convert paths to array format: [[x, y], ...]
        path_top_array = [[x, y] for x, y in path_top]
        path_bottom_array = [[x, y] for x, y in path_bottom]
        path_center_array = [[x, y] for x, y in path_center]

        # Calculate measurement point pairs
        measurement_point_pairs = calculate_measurement_point_pairs(
            path_top=path_top,
            path_bottom=path_bottom,
            path_center=path_center,
            num_tracking_points=parameters.num_tracking_points,
            distribution_method=parameters.distribution_method,
            horizontal_window_x_left=parameters.horizontal_window_x_left,
            horizontal_window_x_right=parameters.horizontal_window_x_right,
        )

        # No colored regions for now
        colored_regions = []

        return FrameData(
            f=frame_number,
            pt=path_top_array,
            pb=path_bottom_array,
            pc=path_center_array,
            colored_regions=colored_regions,
            mpp=measurement_point_pairs if measurement_point_pairs else None,
        )
    finally:
        cap.release()


@app.get("/api/videos/{video_id}/frame/{frame_number}/image")
def get_frame_image(video_id: str, frame_number: int):
    """Extract and return a specific frame as a JPEG image."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Load metadata to get frame_multiplier
    settings_path = video_path.with_suffix(".json")
    frame_multiplier = 1.0  # Default fallback
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                all_data = json.load(f)
                if (
                    "metadata" in all_data
                    and "frame_multiplier" in all_data["metadata"]
                ):
                    frame_multiplier = float(all_data["metadata"]["frame_multiplier"])
        except (json.JSONDecodeError, IOError, KeyError, ValueError):
            # If metadata can't be loaded, use default
            pass

    # Use video pool for efficient frame extraction
    frame_bytes = video_pool.get_frame(video_path, frame_number, frame_multiplier)
    if frame_bytes is None:
        raise HTTPException(
            status_code=500, detail=f"Failed to extract frame {frame_number}"
        )

    # Return JPEG image with cache headers for better performance
    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        },
    )


@app.post("/api/analysis/detect-window")
async def detect_horizontal_window(
    video_id: str, frame_number: int, y: int | None = None
):
    """Detect horizontal window boundaries (x_left, x_right) for a specific frame."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Open video with OpenCV
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise HTTPException(status_code=500, detail="Failed to open video file")

    try:
        # Seek to the requested frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        if not ret:
            raise HTTPException(
                status_code=400, detail=f"Failed to read frame {frame_number}"
            )

        # Convert to numpy array
        frame_np = np.array(frame)

        # Run horizontal window detection
        x_left, x_right, y_mid = horizontal_window_detection(frame=frame_np, y=y)

        # Convert numpy types to Python native types for JSON serialization
        return {
            "x_left": int(x_left) if x_left >= 0 else -1,
            "x_right": int(x_right) if x_right >= 0 else -1,
            "y_mid": int(y_mid),
        }
    finally:
        cap.release()


@app.post("/api/videos/{video_id}/calibrate", response_model=CalibrationResult)
async def calibrate_video(
    video_id: str, frame_number: int = 0, tube_width_mm: float = 11.0
):
    """Calibrate pixel-to-mm factor by measuring the tube at the right edge of the frame."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Load metadata to get frame_multiplier
    settings_path = video_path.with_suffix(".json")
    frame_multiplier = 1.0
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                all_data = json.load(f)
                if (
                    "metadata" in all_data
                    and "frame_multiplier" in all_data["metadata"]
                ):
                    frame_multiplier = float(all_data["metadata"]["frame_multiplier"])
        except (json.JSONDecodeError, IOError, KeyError, ValueError):
            pass

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise HTTPException(status_code=500, detail="Failed to open video file")

    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_number * frame_multiplier))
        ret, frame = cap.read()
        if not ret:
            raise HTTPException(
                status_code=400, detail=f"Failed to read frame {frame_number}"
            )

        result = calibrate_tube_width(
            np.array(frame), tube_known_width_mm=tube_width_mm
        )
        return CalibrationResult(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        cap.release()


@app.get("/api/videos/{video_id}/settings")
def get_video_settings(video_id: str):
    """Get saved settings for a video."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Settings file is next to video file with .json extension
    settings_path = video_path.with_suffix(".json")

    if not settings_path.exists():
        # Return empty/default settings if file doesn't exist
        return {}

    try:
        with open(settings_path, "r") as f:
            all_data = json.load(f)
            # Return only parameters if they exist, otherwise return empty dict
            # This maintains backward compatibility with the frontend
            return all_data.get("parameters", {})
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to read settings: {str(e)}"
        ) from e


@app.put("/api/videos/{video_id}/settings")
def save_video_settings(video_id: str, settings: dict):
    """Save settings for a video."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    # Settings file is next to video file with .json extension
    settings_path = video_path.with_suffix(".json")

    try:
        # Load existing data to preserve metadata
        existing_data = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r") as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                # If file is corrupted, start fresh
                existing_data = {}

        # Update parameters while preserving metadata
        existing_data["parameters"] = settings

        # Write back to file
        with open(settings_path, "w") as f:
            json.dump(existing_data, f, indent=2, default=str)
        return {"message": "Settings saved successfully"}
    except IOError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save settings: {str(e)}"
        ) from e


@app.get("/api/videos/{video_id}/display-settings", response_model=DisplaySettings)
def get_video_display_settings(video_id: str):
    """Get display settings for a video."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return _load_video_display_settings(video_path)


@app.put("/api/videos/{video_id}/display-settings", response_model=DisplaySettings)
def update_video_display_settings(video_id: str, settings: DisplaySettings):
    """Update display settings for a video. Invalidates heatmap meta caches for all analyses of this video."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    settings.updated_at = datetime.now().isoformat()
    _save_video_display_settings(video_path, settings)

    # Invalidate heatmap metadata cache for all analyses of this video
    analysis_storage = AnalysisStorage()
    analyses = analysis_storage.list_analyses(video_id=video_id, limit=1000)
    for analysis in analyses:
        cache_file = (
            video_path.parent
            / f"{video_path.stem}_analysis_{analysis.id}_heatmap_meta.json"
        )
        if cache_file.exists():
            cache_file.unlink()

    return settings


@app.post(
    "/api/analysis/{analysis_id}/detect-contractions",
    response_model=ContractionDetectionResult,
)
async def detect_contractions_endpoint(
    analysis_id: str,
    parameters: Annotated[ContractionDetectionParameters | None, Body()] = None,
):
    """Trigger contraction detection for a completed analysis."""
    import logging

    logger = logging.getLogger("uvicorn.error")

    logger.info(f"Contraction detection requested for analysis {analysis_id}")

    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Check if analysis is completed
    if analysis.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Analysis must be completed to detect contractions. Current status: {analysis.status}",
        )

    # Use provided parameters or defaults
    if parameters is None:
        parameters = ContractionDetectionParameters()
        logger.info("Using default contraction detection parameters")
    else:
        logger.info(
            f"Using custom parameters: sigma=({parameters.smooth_sigma_y}, {parameters.smooth_sigma_t}), "
            f"percentile={parameters.threshold_percentile}, min_pixels={parameters.min_pixels}"
        )

    # Get video metadata for FPS
    video_path = VideoStorage.get_video_path(analysis.video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        video_metadata = get_video_metadata(video_path)
        fps = video_metadata.fps
        dt = 1.0 / fps if fps > 0 else 1.0
    except ValueError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get video metadata: {str(e)}"
        ) from e

    # Build heatmap matrix
    results_storage = ResultsStorage()
    db = results_storage.db
    matrix, _, _ = db.build_heatmap_matrix(analysis_id)

    if matrix.size == 0:
        raise HTTPException(
            status_code=400,
            detail="No heatmap data available. Analysis must have measurement point pairs (mpp) data.",
        )

    # Transpose matrix: build_heatmap_matrix returns (frames, points), but detect_contractions expects (points, frames)
    # Actually, looking at the code, build_heatmap_matrix returns (num_frames, num_points)
    # But detect_contractions expects (Y, T) where Y is point-pair index and T is frame index
    # So we need to transpose: (frames, points) -> (points, frames)
    thickness = matrix.T  # Shape: (num_points, num_frames)

    # Calculate physical spacing if not provided
    dy = parameters.dy
    if dy is None:
        dy = calculate_physical_spacing(analysis_id, results_storage)

    # Run contraction detection
    try:
        events, mask_c, lbl = detect_contractions(
            thickness=thickness,
            dt=dt,
            dy=dy,
            thr=parameters.threshold,
            percentile=parameters.threshold_percentile,
            smooth_sigma=(parameters.smooth_sigma_y, parameters.smooth_sigma_t),
            min_pixels=parameters.min_pixels,
            min_area=parameters.min_area,
            min_height=parameters.min_height,
            open_iters=parameters.open_iters,
            close_iters=parameters.close_iters,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Contraction detection failed: {str(e)}"
        ) from e

    # Store events in database
    try:
        db.save_contraction_events(analysis_id, events)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save contraction events: {str(e)}"
        ) from e

    # Retrieve events from database to get proper IDs
    events_dict = db.get_contraction_events(analysis_id)

    # Convert events to ContractionEvent models
    contraction_events = []
    for event in events_dict:
        contraction_events.append(
            ContractionEvent(
                id=event["id"],
                label=event["label"],
                n_pixels=event["n_pixels"],
                threshold_used=event["threshold_used"],
                t_range_frames=event["t_range_frames"],
                y_range_idx=event["y_range_idx"],
                duration_s=event["duration_s"],
                height_phys=event["height_phys"],
                velocity_phys_per_s=event["velocity_phys_per_s"],
                line_fit=ContractionEventLineFit(
                    a_idx_per_frame=event["line_fit"]["a_idx_per_frame"],
                    b=event["line_fit"]["b"],
                ),
                area_exact=event["area_exact"],
                area_triangle=event["area_triangle"],
                created_at=event["created_at"],
            )
        )

    return ContractionDetectionResult(
        events=contraction_events,
        parameters_used=parameters,
        total_events=len(contraction_events),
    )


@app.get(
    "/api/analysis/{analysis_id}/contractions",
    response_model=ContractionDetectionResult,
)
def get_contraction_events(analysis_id: str):
    """Get contraction detection results for an analysis."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Check if contraction events exist
    results_storage = ResultsStorage()
    db = results_storage.db

    if not db.contraction_events_exist(analysis_id):
        raise HTTPException(
            status_code=404,
            detail="Contraction detection has not been run for this analysis. Use POST /api/analysis/{analysis_id}/detect-contractions to run detection.",
        )

    # Get events from database
    events_dict = db.get_contraction_events(analysis_id)

    # Convert to ContractionEvent models
    contraction_events = []
    for event in events_dict:
        contraction_events.append(
            ContractionEvent(
                id=event["id"],
                label=event["label"],
                n_pixels=event["n_pixels"],
                threshold_used=event["threshold_used"],
                t_range_frames=event["t_range_frames"],
                y_range_idx=event["y_range_idx"],
                duration_s=event["duration_s"],
                height_phys=event["height_phys"],
                velocity_phys_per_s=event["velocity_phys_per_s"],
                line_fit=ContractionEventLineFit(
                    a_idx_per_frame=event["line_fit"]["a_idx_per_frame"],
                    b=event["line_fit"]["b"],
                ),
                area_exact=event["area_exact"],
                area_triangle=event["area_triangle"],
                created_at=event["created_at"],
            )
        )

    # For parameters_used, we'll use defaults since we don't store them
    # In a production system, you might want to store parameters with events
    parameters_used = ContractionDetectionParameters()

    return ContractionDetectionResult(
        events=contraction_events,
        parameters_used=parameters_used,
        total_events=len(contraction_events),
    )


@app.delete("/api/analysis/{analysis_id}/contractions")
def clear_contraction_events(analysis_id: str):
    """Clear contraction detection results for an analysis."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    results_storage = ResultsStorage()
    db = results_storage.db

    db.clear_contraction_events(analysis_id)

    return {"message": "Contraction events cleared successfully"}


@app.delete("/api/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str):
    """Delete an analysis and its results."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Stop the analysis if it's currently running
    if analysis.status == "processing":
        await task_manager.stop_analysis(analysis_id)

    # Delete from database (this will cascade delete frames and contraction_events)
    analysis_storage = AnalysisStorage()
    analysis_storage.delete_analysis(analysis_id)

    # Remove from in-memory cache if present
    if analysis_id in task_manager.analyses:
        del task_manager.analyses[analysis_id]
    if analysis_id in task_manager.tasks:
        del task_manager.tasks[analysis_id]

    return {"message": "Analysis deleted successfully"}


@app.delete("/api/clear-all-data")
async def clear_all_data_endpoint():
    """Factory reset: cancel tasks, drop database, delete all video files."""
    # 1. Cancel all running analysis tasks
    tasks_cancelled = 0
    for analysis_id in list(task_manager.analyses.keys()):
        analysis = task_manager.analyses[analysis_id]
        if analysis.status == "processing":
            await task_manager.stop_analysis(analysis_id)
            tasks_cancelled += 1

    # 2. Clear in-memory state
    task_manager.tasks.clear()
    task_manager.analyses.clear()

    # 3. Close all video pool handles
    video_pool.close_all()

    # 4. Drop and recreate database
    clear_all_data()

    # 5. Delete all files in videos directory
    files_deleted = delete_all_video_files()

    return {
        "message": "All data cleared successfully",
        "tasks_cancelled": tasks_cancelled,
        "files_deleted": files_deleted,
    }


# Multi-View Session Endpoints

multi_view_session_db = MultiViewSessionDB()


def _parse_session_metadata(raw_metadata: dict | None) -> MultiViewSessionMetadata:
    if raw_metadata is None or not isinstance(raw_metadata, dict):
        return MultiViewSessionMetadata(
            validated=True,
            frame_count_diff=0,
            duration_diff=0.0,
        )

    merged = {
        "validated": raw_metadata.get("validated", True),
        "frame_count_diff": raw_metadata.get("frame_count_diff", 0),
        "duration_diff": raw_metadata.get("duration_diff", 0.0),
        **raw_metadata,
    }
    return MultiViewSessionMetadata(**merged)


def _session_row_to_model(row: dict) -> MultiViewSession:
    return MultiViewSession(
        id=row["id"],
        name=row["name"],
        left_analysis_id=row["left_analysis_id"],
        right_analysis_id=row["right_analysis_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        metadata=_parse_session_metadata(row.get("metadata")),
    )


def _get_session_or_404(session_id: str) -> dict:
    row = multi_view_session_db.get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Multi-view session not found")
    return row


def _persist_session_metadata(session_id: str, metadata: MultiViewSessionMetadata) -> None:
    logger.info("Persisting session metadata: session_id=%s", session_id)
    updated = multi_view_session_db.update_session_metadata(
        session_id, metadata.model_dump(mode="json")
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Multi-view session not found")


def _refresh_realign_job_status(session_row: dict) -> dict:
    metadata = _parse_session_metadata(session_row.get("metadata"))
    job = metadata.realign_job
    if not job or job.status != "running":
        return session_row

    analysis_storage = AnalysisStorage()
    left = analysis_storage.get_analysis(job.left_analysis_id)
    right = analysis_storage.get_analysis(job.right_analysis_id)
    if not left or not right:
        logger.warning(
            "Realign job failed (missing analyses): session_id=%s job_id=%s",
            session_row["id"],
            job.id,
        )
        metadata.realign_job = job.copy(
            update={
                "status": "failed",
                "completed_at": datetime.now(),
                "error": "Auto-reanalysis outputs are missing.",
            }
        )
        _persist_session_metadata(session_row["id"], metadata)
        return _get_session_or_404(session_row["id"])

    left_status = left.status
    right_status = right.status
    if left_status == "completed" and right_status == "completed":
        logger.info(
            "Realign job ready_to_commit: session_id=%s job_id=%s",
            session_row["id"],
            job.id,
        )
        metadata.realign_job = job.copy(
            update={
                "status": "ready_to_commit",
                "completed_at": datetime.now(),
                "error": None,
            }
        )
        _persist_session_metadata(session_row["id"], metadata)
        return _get_session_or_404(session_row["id"])

    terminal_failures = {"failed", "cancelled"}
    if left_status in terminal_failures or right_status in terminal_failures:
        logger.warning(
            "Realign job failed: session_id=%s job_id=%s left=%s right=%s",
            session_row["id"],
            job.id,
            left_status,
            right_status,
        )
        metadata.realign_job = job.copy(
            update={
                "status": "failed",
                "completed_at": datetime.now(),
                "error": f"Reanalysis failed (left={left_status}, right={right_status}).",
            }
        )
        _persist_session_metadata(session_row["id"], metadata)
        return _get_session_or_404(session_row["id"])

    return session_row


def _build_auto_realign_analysis_name(side: str) -> str:
    timestamp = datetime.now().strftime("%H:%M")
    return f"AutoAlign {side} · {timestamp}"


def _start_background_analysis_for_video(
    video_id: str, parameters_dict: dict, display_name: str | None = None
) -> Analysis:
    parameters = AnalysisParameters(**parameters_dict)
    analysis = Analysis(
        video_id=video_id,
        display_name=display_name,
        parameters=parameters.model_dump(),
    )
    task_manager.register_analysis(analysis)
    task = asyncio.create_task(
        task_manager.start_analysis(analysis.id, video_id, parameters)
    )
    task_manager.tasks[analysis.id] = task
    return analysis


@app.post("/api/multi-view/validate", response_model=MultiViewValidationResult)
async def validate_multi_view_pair_endpoint(body: MultiViewValidationRequest):
    """Validate whether two analyses can be used in one multi-view session."""
    analysis_storage = AnalysisStorage()
    left_analysis = analysis_storage.get_analysis(body.left_analysis_id)
    right_analysis = analysis_storage.get_analysis(body.right_analysis_id)

    if not left_analysis or not right_analysis:
        raise HTTPException(status_code=404, detail="One or both analyses not found")

    video_storage = VideoStorage()
    left_video = video_storage.get_video(left_analysis.video_id)
    right_video = video_storage.get_video(right_analysis.video_id)

    if not left_video or not right_video:
        raise HTTPException(status_code=404, detail="One or both videos not found")

    left_metadata = get_video_metadata(Path(left_video.file_path))
    right_metadata = get_video_metadata(Path(right_video.file_path))

    return validate_multi_view_pair(
        left_analysis,
        right_analysis,
        left_metadata,
        right_metadata,
    )


@app.post("/api/multi-view/sessions", response_model=MultiViewSession)
async def create_multi_view_session(body: MultiViewSessionCreate):
    """Create a persisted multi-view session after validation."""
    normalized_name = body.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=422, detail="Session name cannot be empty")

    validation = await validate_multi_view_pair_endpoint(
        MultiViewValidationRequest(
            left_analysis_id=body.left_analysis_id,
            right_analysis_id=body.right_analysis_id,
        )
    )

    if not validation.compatible:
        raise HTTPException(
            status_code=400,
            detail=f"Incompatible analyses: {', '.join(validation.errors)}",
        )

    metadata = MultiViewSessionMetadata(
        validated=True,
        frame_count_diff=int(validation.details.get("frame_count_diff", 0)),
        duration_diff=float(validation.details.get("duration_diff", 0.0)),
    )

    session = MultiViewSession(
        name=normalized_name,
        left_analysis_id=body.left_analysis_id,
        right_analysis_id=body.right_analysis_id,
        metadata=metadata,
    )

    session_dict = {
        "id": session.id,
        "name": session.name,
        "left_analysis_id": session.left_analysis_id,
        "right_analysis_id": session.right_analysis_id,
        "created_at": session.created_at.isoformat(),
        "metadata": session.metadata.model_dump() if session.metadata else None,
    }

    multi_view_session_db.create_session(session_dict)
    return session


@app.get("/api/multi-view/sessions", response_model=list[MultiViewSession])
async def list_multi_view_sessions(limit: int = 100, offset: int = 0):
    """List persisted multi-view sessions."""
    results = multi_view_session_db.list_sessions(limit, offset)
    return [_session_row_to_model(row) for row in results]


@app.get("/api/multi-view/sessions/{session_id}", response_model=MultiViewSession)
async def get_multi_view_session(session_id: str):
    """Get one persisted multi-view session."""
    return _session_row_to_model(_refresh_realign_job_status(_get_session_or_404(session_id)))


@app.put("/api/multi-view/sessions/{session_id}/name", response_model=MultiViewSession)
async def update_multi_view_session_name(
    session_id: str, body: MultiViewSessionNameUpdate
):
    """Rename a persisted multi-view session."""
    normalized_name = body.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=422, detail="Session name cannot be empty")

    _get_session_or_404(session_id)

    updated = multi_view_session_db.update_session_name(session_id, normalized_name)
    if not updated:
        raise HTTPException(status_code=404, detail="Multi-view session not found")

    return _session_row_to_model(_get_session_or_404(session_id))


@app.post(
    "/api/multi-view/sessions/{session_id}/alignment/suggest",
    response_model=MultiViewAlignmentSuggestResponse,
)
async def suggest_multi_view_alignment(
    session_id: str, body: MultiViewAlignmentSuggestRequest
):
    """Generate alignment suggestions from analysis and video signals."""
    logger.info(
        "Alignment suggest requested: session_id=%s sample_frames=%s max_shift_sec=%.2f apply_time_shift=%s",
        session_id,
        body.sample_frames,
        body.max_shift_sec,
        body.apply_time_shift,
    )
    session_row = _get_session_or_404(session_id)
    session = _session_row_to_model(session_row)

    analysis_storage = AnalysisStorage()
    left_analysis = analysis_storage.get_analysis(session.left_analysis_id)
    right_analysis = analysis_storage.get_analysis(session.right_analysis_id)
    if not left_analysis or not right_analysis:
        raise HTTPException(status_code=404, detail="One or both analyses not found")

    video_storage = VideoStorage()
    left_video = video_storage.get_video(left_analysis.video_id)
    right_video = video_storage.get_video(right_analysis.video_id)
    if not left_video or not right_video:
        raise HTTPException(status_code=404, detail="One or both videos not found")

    left_video_path = Path(left_video.file_path)
    right_video_path = Path(right_video.file_path)
    left_metadata = get_video_metadata(left_video_path)
    right_metadata = get_video_metadata(right_video_path)

    left_settings = _load_video_display_settings(left_video_path)
    right_settings = _load_video_display_settings(right_video_path)

    db = ResultsStorage().db
    suggestion = compute_alignment_suggestion(
        db=db,
        left_analysis=left_analysis,
        right_analysis=right_analysis,
        left_metadata=left_metadata,
        right_metadata=right_metadata,
        left_pixel_to_mm_factor=left_settings.pixel_to_mm_factor,
        right_pixel_to_mm_factor=right_settings.pixel_to_mm_factor,
        left_video_path=left_video_path,
        right_video_path=right_video_path,
        sample_frames=body.sample_frames,
        max_shift_sec=body.max_shift_sec,
    )

    metadata = session.metadata or MultiViewSessionMetadata(
        validated=True,
        frame_count_diff=0,
        duration_diff=0.0,
    )
    existing_alignment = metadata.alignment or MultiViewAlignmentState()

    auto_applied = (
        body.apply_time_shift
        and suggestion.time_shift.confidence >= AUTO_APPLY_CONFIDENCE_THRESHOLD
    )
    logger.info(
        "Alignment suggest result: session_id=%s shift=%.4f confidence=%.3f method=%s auto_applied=%s",
        session_id,
        suggestion.time_shift.right_time_shift_sec,
        suggestion.time_shift.confidence,
        suggestion.time_shift.method,
        auto_applied,
    )

    if auto_applied:
        existing_alignment = MultiViewAlignmentState(
            right_time_shift_sec=suggestion.time_shift.right_time_shift_sec,
            source="auto",
        )

    warning = suggestion.time_shift.warning
    if body.apply_time_shift and not auto_applied and warning is None:
        warning = "Low-confidence shift suggestion. Not auto-applied."

    suggestion = suggestion.copy(
        update={
            "time_shift": suggestion.time_shift.copy(
                update={
                    "auto_applied": auto_applied,
                    "warning": warning,
                }
            )
        }
    )

    metadata.alignment = existing_alignment
    metadata.latest_alignment_suggestion = suggestion
    _persist_session_metadata(session_id, metadata)

    return MultiViewAlignmentSuggestResponse(
        session_id=session_id,
        suggestion=suggestion,
        alignment=existing_alignment,
    )


@app.put(
    "/api/multi-view/sessions/{session_id}/alignment",
    response_model=MultiViewSession,
)
async def update_multi_view_alignment(
    session_id: str, body: MultiViewAlignmentUpdate
):
    """Manually update persisted alignment settings."""
    logger.info(
        "Manual alignment update: session_id=%s right_time_shift_sec=%.4f",
        session_id,
        body.right_time_shift_sec,
    )
    session = _session_row_to_model(_get_session_or_404(session_id))
    metadata = session.metadata or MultiViewSessionMetadata(
        validated=True,
        frame_count_diff=0,
        duration_diff=0.0,
    )

    metadata.alignment = MultiViewAlignmentState(
        right_time_shift_sec=body.right_time_shift_sec,
        source="manual",
    )
    _persist_session_metadata(session_id, metadata)
    return _session_row_to_model(_get_session_or_404(session_id))


@app.post(
    "/api/multi-view/sessions/{session_id}/alignment/auto-reanalyze",
    response_model=MultiViewRealignJob,
)
async def auto_reanalyze_multi_view_alignment(
    session_id: str,
    body: MultiViewAutoReanalyzeRequest = Body(
        default=MultiViewAutoReanalyzeRequest()
    ),
):
    """Start auto-reanalysis for both sides using suggested window adjustments."""
    logger.info("Auto-reanalyze requested: session_id=%s", session_id)
    session = _session_row_to_model(_get_session_or_404(session_id))

    analysis_storage = AnalysisStorage()
    left_analysis = analysis_storage.get_analysis(session.left_analysis_id)
    right_analysis = analysis_storage.get_analysis(session.right_analysis_id)
    if not left_analysis or not right_analysis:
        raise HTTPException(status_code=404, detail="One or both analyses not found")

    if left_analysis.status != "completed" or right_analysis.status != "completed":
        raise HTTPException(
            status_code=400, detail="Both analyses must be completed before reanalysis"
        )

    metadata = session.metadata or MultiViewSessionMetadata(
        validated=True,
        frame_count_diff=0,
        duration_diff=0.0,
    )
    suggestion = metadata.latest_alignment_suggestion
    if body.use_latest_suggestion and not suggestion:
        raise HTTPException(
            status_code=400,
            detail="No alignment suggestion available. Run alignment suggestion first.",
        )

    left_params = deepcopy(left_analysis.parameters)
    right_params = deepcopy(right_analysis.parameters)

    if suggestion:
        if suggestion.window.left_suggested_x_left is not None:
            left_params["horizontal_window_x_left"] = suggestion.window.left_suggested_x_left
        if suggestion.window.left_suggested_x_right is not None:
            left_params["horizontal_window_x_right"] = suggestion.window.left_suggested_x_right
        if suggestion.window.right_suggested_x_left is not None:
            right_params["horizontal_window_x_left"] = suggestion.window.right_suggested_x_left
        if suggestion.window.right_suggested_x_right is not None:
            right_params["horizontal_window_x_right"] = suggestion.window.right_suggested_x_right

    left_display_name = _build_auto_realign_analysis_name("L")
    right_display_name = _build_auto_realign_analysis_name("R")

    left_new_analysis = _start_background_analysis_for_video(
        left_analysis.video_id, left_params, display_name=left_display_name
    )
    right_new_analysis = _start_background_analysis_for_video(
        right_analysis.video_id, right_params, display_name=right_display_name
    )

    realign_job = MultiViewRealignJob(
        status="running",
        left_analysis_id=left_new_analysis.id,
        right_analysis_id=right_new_analysis.id,
    )
    metadata.realign_job = realign_job
    _persist_session_metadata(session_id, metadata)
    logger.info(
        "Auto-reanalyze started: session_id=%s left_new=%s right_new=%s left_name=%s right_name=%s",
        session_id,
        left_new_analysis.id,
        right_new_analysis.id,
        left_display_name,
        right_display_name,
    )
    return realign_job


@app.put(
    "/api/multi-view/sessions/{session_id}/sources",
    response_model=MultiViewSession,
)
async def update_multi_view_session_sources(
    session_id: str, body: MultiViewSessionSourcesUpdate
):
    """Relink a session to different source analyses after compatibility checks."""
    logger.info(
        "Session source relink requested: session_id=%s left=%s right=%s",
        session_id,
        body.left_analysis_id,
        body.right_analysis_id,
    )
    _get_session_or_404(session_id)

    analysis_storage = AnalysisStorage()
    left_analysis = analysis_storage.get_analysis(body.left_analysis_id)
    right_analysis = analysis_storage.get_analysis(body.right_analysis_id)
    if not left_analysis or not right_analysis:
        raise HTTPException(status_code=404, detail="One or both analyses not found")

    if left_analysis.status != "completed" or right_analysis.status != "completed":
        raise HTTPException(status_code=400, detail="Both analyses must be completed")

    video_storage = VideoStorage()
    left_video = video_storage.get_video(left_analysis.video_id)
    right_video = video_storage.get_video(right_analysis.video_id)
    if not left_video or not right_video:
        raise HTTPException(status_code=404, detail="One or both videos not found")

    validation = validate_multi_view_pair(
        left_analysis,
        right_analysis,
        get_video_metadata(Path(left_video.file_path)),
        get_video_metadata(Path(right_video.file_path)),
    )
    if not validation.compatible:
        raise HTTPException(
            status_code=400,
            detail=f"Incompatible analyses: {', '.join(validation.errors)}",
        )

    updated_sources = multi_view_session_db.update_session_sources(
        session_id, body.left_analysis_id, body.right_analysis_id
    )
    if not updated_sources:
        raise HTTPException(status_code=404, detail="Multi-view session not found")

    updated_session = _session_row_to_model(_get_session_or_404(session_id))
    metadata = updated_session.metadata or MultiViewSessionMetadata(
        validated=True,
        frame_count_diff=0,
        duration_diff=0.0,
    )
    if metadata.realign_job:
        if (
            metadata.realign_job.left_analysis_id == body.left_analysis_id
            and metadata.realign_job.right_analysis_id == body.right_analysis_id
        ):
            metadata.realign_job = metadata.realign_job.copy(
                update={
                    "status": "committed",
                    "completed_at": datetime.now(),
                    "error": None,
                }
            )
        else:
            metadata.realign_job = metadata.realign_job.copy(
                update={
                    "status": "failed",
                    "completed_at": datetime.now(),
                    "error": "Relinked to analyses that do not match active realign job.",
                }
            )
        _persist_session_metadata(session_id, metadata)

    logger.info("Session source relink successful: session_id=%s", session_id)
    return _session_row_to_model(_get_session_or_404(session_id))


@app.delete("/api/multi-view/sessions/{session_id}")
async def delete_multi_view_session(session_id: str):
    """Delete a persisted multi-view session."""
    _get_session_or_404(session_id)

    multi_view_session_db.delete_session(session_id)
    return {"message": "Multi-view session deleted successfully"}
