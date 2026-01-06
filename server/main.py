"""FastAPI application for video analysis."""
import asyncio
from pathlib import Path

import cv2
import json
from fastapi import Body, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from brotli_asgi import BrotliMiddleware

import numpy as np

from .analysis import calculate_center_path, calculate_measurement_point_pairs
from .config import MAX_UPLOAD_SIZE
from .costmap import costmap_calculation
from .edge_detection_1d import edge_detection_1d_calculation
from .edge_detection_canny import edge_detection_canny_calculation
from .edge_detection_silhouette import edge_detection_silhouette_calculation
from .database import init_database
from .horizontal_window_detection import horizontal_window_detection
from .metadata import get_video_metadata
from .models import Analysis, AnalysisParameters, FrameData, HeatmapMeta, Video, VideoMetadata
from .storage import AnalysisStorage, ResultsStorage, VideoStorage
from .tasks import task_manager
from .video_pool import VideoHandlePool

# Initialize database on startup
init_database()

app = FastAPI(title="Video Analysis API", version="1.0.0")

# Initialize video handle pool for efficient frame extraction
video_pool = VideoHandlePool(max_handles=5, idle_timeout=60.0)

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
)


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
    
    for key in params1.keys():
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
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file."""
    # Check file size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large")
    
    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
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
    return VideoStorage.list_videos()


@app.get("/api/videos/{video_id}/file")
async def get_video_file(video_id: str, request: Request):
    """Serve video file with optimized range request support."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")
    
    # If no range header, serve the entire file
    if not range_header:
        return FileResponse(
            video_path,
            media_type="video/mp4",
            filename=video_path.name,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            },
        )
    
    # Parse range header (e.g., "bytes=0-1023" or "bytes=1024-")
    try:
        range_match = range_header.replace("bytes=", "").split("-")
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else file_size - 1
    except (ValueError, IndexError):
        raise HTTPException(status_code=416, detail="Invalid range header")
    
    # Validate range
    if start < 0 or start >= file_size or end < start:
        raise HTTPException(
            status_code=416,
            detail="Range Not Satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    
    # Clamp end to file size
    end = min(end, file_size - 1)
    content_length = end - start + 1
    
    # Async generator to stream file chunks efficiently
    async def generate():
        chunk_size = 2 * 1024 * 1024  # 2MB chunks for efficient streaming (larger = fewer file opens)
        # Use thread pool for file I/O to avoid blocking the event loop
        def read_chunk(file_path, offset, size):
            with open(file_path, "rb") as f:
                f.seek(offset)
                return f.read(size)
        
        remaining = content_length
        current_offset = start
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            # Run file I/O in thread pool to keep event loop responsive
            # OS file cache will make subsequent opens fast
            chunk = await asyncio.to_thread(read_chunk, video_path, current_offset, read_size)
            if not chunk:
                break
            yield chunk
            remaining -= len(chunk)
            current_offset += len(chunk)
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": "video/mp4",
        "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
    }
    
    return StreamingResponse(
        generate(),
        status_code=206,
        headers=headers,
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
        raise HTTPException(status_code=500, detail=str(e))


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


@app.post("/api/analysis/{analysis_id}/stop", response_model=Analysis)
async def stop_analysis(analysis_id: str):
    """Stop a running analysis."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    success = await task_manager.stop_analysis(analysis_id)
    if not success:
        raise HTTPException(status_code=400, detail="Analysis is not running or cannot be stopped")
    
    return analysis


@app.post("/api/analysis/{analysis_id}/resume", response_model=Analysis)
async def resume_analysis(analysis_id: str):
    """Resume a cancelled or failed analysis from the last analyzed frame."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    # Check if analysis is already running
    if analysis.status == "processing":
        raise HTTPException(status_code=400, detail="Analysis is already running")
    
    # Check if analysis can be resumed (must be cancelled or failed)
    if analysis.status not in ("cancelled", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume analysis with status '{analysis.status}'. Only cancelled or failed analyses can be resumed."
        )
    
    # Get video_id and parameters from analysis
    video_id = analysis.video_id
    parameters = AnalysisParameters(**analysis.parameters)
    
    # Update analysis status to processing
    analysis.status = "processing"
    task_manager.analysis_storage.update_analysis(analysis_id, status="processing")
    
    # Start background task with resume=True
    task = asyncio.create_task(
        task_manager.start_analysis(analysis.id, video_id, parameters, resume=True)
    )
    task_manager.tasks[analysis.id] = task
    
    return analysis


@app.post("/api/analysis/{analysis_id}/restart", response_model=Analysis)
async def restart_analysis(analysis_id: str, parameters: AnalysisParameters | None = Body(None)):
    """Restart an analysis from frame 0, optionally with new parameters."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    # Check if analysis is already running
    if analysis.status == "processing":
        raise HTTPException(status_code=400, detail="Analysis is already running. Stop it first.")
    
    # Get video_id
    video_id = analysis.video_id
    
    # Use provided parameters or keep existing ones
    if parameters is not None:
        # Update analysis parameters
        analysis.parameters = parameters.model_dump()
        task_manager.analysis_storage.update_analysis(analysis_id, parameters=parameters.model_dump())
    else:
        # Use existing parameters
        parameters = AnalysisParameters(**analysis.parameters)
    
    # Clear all existing results
    results_storage = ResultsStorage()
    results_storage.clear_results(analysis_id)
    
    # Reset analysis status and progress
    analysis.status = "processing"
    analysis.progress = 0.0
    task_manager.analysis_storage.update_analysis(analysis_id, status="processing", progress=0.0)
    
    # Stop any existing task for this analysis
    if analysis_id in task_manager.tasks:
        task_manager.tasks[analysis_id].cancel()
        del task_manager.tasks[analysis_id]
    
    # Start background task from frame 0
    task = asyncio.create_task(
        task_manager.start_analysis(analysis.id, video_id, parameters, resume=False)
    )
    task_manager.tasks[analysis.id] = task
    
    return analysis


@app.get("/api/analysis/{analysis_id}/heatmap/meta", response_model=HeatmapMeta)
def get_heatmap_meta(analysis_id: str):
    """Return metadata for heatmap: width (frames), height (points), dtype, min, max, fps."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    # Get video metadata for FPS
    video_path = VideoStorage.get_video_path(analysis.video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check for cached response
    cache_file = video_path.parent / f"{video_path.stem}_analysis_{analysis_id}_heatmap_meta.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
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
        raise HTTPException(status_code=500, detail=f"Failed to get video metadata: {str(e)}")
    
    # Build heatmap matrix
    results_storage = ResultsStorage()
    db = results_storage.db
    matrix, min_val, max_val = db.build_heatmap_matrix(analysis_id)
    
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
        )
        # Explicitly delete the matrix to free memory immediately
        # This is critical for large matrices that can be hundreds of MB
        del matrix
    
    # Cache the response
    try:
        with open(cache_file, 'w') as f:
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
    
    # Get video path for cache location
    video_path = VideoStorage.get_video_path(analysis.video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check for cached response
    cache_file = video_path.parent / f"{video_path.stem}_analysis_{analysis_id}_heatmap_raw.bin"
    cache_meta_file = video_path.parent / f"{video_path.stem}_analysis_{analysis_id}_heatmap_raw_meta.json"
    
    if cache_file.exists() and cache_meta_file.exists():
        try:
            # Load cached metadata for headers
            with open(cache_meta_file, 'r') as f:
                meta = json.load(f)
            
            # Don't trust cached data if it's empty (width=0 or height=0)
            # This can happen if the cache was created before the analysis completed
            # or if there was no mpp data at the time
            if meta.get("width", 0) > 0 and meta.get("height", 0) > 0:
                # Load cached binary data
                with open(cache_file, 'rb') as f:
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
    
    # Cache the response
    try:
        with open(cache_file, 'wb') as f:
            f.write(matrix_bytes)
        with open(cache_meta_file, 'w') as f:
            json.dump({
                "width": matrix_shape[0],
                "height": matrix_shape[1],
                "dtype": "float32",
            }, f)
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
        raise HTTPException(status_code=404, detail=f"Frame {frame_number} not found in analysis results")
    
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
async def analyze_frame(video_id: str, frame_number: int, parameters: AnalysisParameters):
    """Analyze a single frame of a video."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Load metadata to get frame_multiplier
    settings_path = video_path.with_suffix('.json')
    frame_multiplier = 1.0  # Default fallback
    if settings_path.exists():
        try:
            with open(settings_path, 'r') as f:
                all_data = json.load(f)
                if 'metadata' in all_data and 'frame_multiplier' in all_data['metadata']:
                    frame_multiplier = float(all_data['metadata']['frame_multiplier'])
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
            raise HTTPException(status_code=400, detail=f"Failed to read frame {frame_number}")
        
        # Convert to numpy array
        frame_np = np.array(frame)
        
        # Dispatch to correct edge detection method
        if parameters.edge_detection_method == "signal_1d":
            path_top, path_bottom = edge_detection_1d_calculation(
                frame=frame_np,
                strip_width=parameters.strip_width,
                band_height=parameters.band_height,
                sigma=parameters.sigma,
                smoothing_factor=parameters.smoothing_factor,
                horizontal_window_x_left=parameters.horizontal_window_x_left,
                horizontal_window_x_right=parameters.horizontal_window_x_right,
            )
        elif parameters.edge_detection_method == "canny":
            path_top, path_bottom = edge_detection_canny_calculation(
                frame=frame_np,
                canny_threshold1=parameters.canny_threshold1,
                canny_threshold2=parameters.canny_threshold2,
                canny_aperture_size=parameters.canny_aperture_size,
                smoothing_factor=parameters.smoothing_factor,
                horizontal_window_x_left=parameters.horizontal_window_x_left,
                horizontal_window_x_right=parameters.horizontal_window_x_right,
            )
        elif parameters.edge_detection_method == "silhouette":
            path_top, path_bottom = edge_detection_silhouette_calculation(
                frame=frame_np,
                smoothing_factor=parameters.smoothing_factor,
                horizontal_window_x_left=parameters.horizontal_window_x_left,
                horizontal_window_x_right=parameters.horizontal_window_x_right,
                blur_ksize=(parameters.silhouette_blur_ksize_x, parameters.silhouette_blur_ksize_y),
                blur_sigma=parameters.silhouette_blur_sigma,
                close_k=parameters.silhouette_close_k,
                x_step=parameters.silhouette_x_step,
                band=parameters.silhouette_band,
                median_k=parameters.silhouette_median_k,
            )
        else:
            # Default to costmap method
            _, path_top, path_bottom = costmap_calculation(
                frame=frame_np,
                alpha=parameters.alpha,
                band=parameters.band,
                smoothing_factor=parameters.smoothing_factor,
                threshold_percentile=parameters.threshold_percentile,
                horizontal_window_x_left=parameters.horizontal_window_x_left,
                horizontal_window_x_right=parameters.horizontal_window_x_right,
                subsequent_frame_band=parameters.subsequent_frame_band,
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
    settings_path = video_path.with_suffix('.json')
    frame_multiplier = 1.0  # Default fallback
    if settings_path.exists():
        try:
            with open(settings_path, 'r') as f:
                all_data = json.load(f)
                if 'metadata' in all_data and 'frame_multiplier' in all_data['metadata']:
                    frame_multiplier = float(all_data['metadata']['frame_multiplier'])
        except (json.JSONDecodeError, IOError, KeyError, ValueError):
            # If metadata can't be loaded, use default
            pass
    
    # Use video pool for efficient frame extraction
    frame_bytes = video_pool.get_frame(video_path, frame_number, frame_multiplier)
    if frame_bytes is None:
        raise HTTPException(status_code=500, detail=f"Failed to extract frame {frame_number}")
    
    # Return JPEG image with cache headers for better performance
    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        }
    )


@app.post("/api/analysis/detect-window")
async def detect_horizontal_window(video_id: str, frame_number: int, y: int | None = None):
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
            raise HTTPException(status_code=400, detail=f"Failed to read frame {frame_number}")
        
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


@app.get("/api/videos/{video_id}/settings")
def get_video_settings(video_id: str):
    """Get saved settings for a video."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Settings file is next to video file with .json extension
    settings_path = video_path.with_suffix('.json')
    
    if not settings_path.exists():
        # Return empty/default settings if file doesn't exist
        return {}
    
    try:
        with open(settings_path, 'r') as f:
            all_data = json.load(f)
            # Return only parameters if they exist, otherwise return empty dict
            # This maintains backward compatibility with the frontend
            return all_data.get('parameters', {})
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {str(e)}")


@app.put("/api/videos/{video_id}/settings")
def save_video_settings(video_id: str, settings: dict):
    """Save settings for a video."""
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Settings file is next to video file with .json extension
    settings_path = video_path.with_suffix('.json')
    
    try:
        # Load existing data to preserve metadata
        existing_data = {}
        if settings_path.exists():
            try:
                with open(settings_path, 'r') as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                # If file is corrupted, start fresh
                existing_data = {}
        
        # Update parameters while preserving metadata
        existing_data['parameters'] = settings
        
        # Write back to file
        with open(settings_path, 'w') as f:
            json.dump(existing_data, f, indent=2, default=str)
        return {"message": "Settings saved successfully"}
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")


@app.delete("/api/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str):
    """Delete an analysis and its results."""
    analysis = task_manager.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    # Stop the analysis if it's currently running
    if analysis.status == "processing":
        await task_manager.stop_analysis(analysis_id)
    
    # Delete from database (this will cascade delete frames)
    analysis_storage = AnalysisStorage()
    analysis_storage.delete_analysis(analysis_id)
    
    # Remove from in-memory cache if present
    if analysis_id in task_manager.analyses:
        del task_manager.analyses[analysis_id]
    if analysis_id in task_manager.tasks:
        del task_manager.tasks[analysis_id]
    
    return {"message": "Analysis deleted successfully"}


