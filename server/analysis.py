"""Analysis engine for video processing using costmap algorithm."""
import asyncio
import time
from typing import Awaitable, Callable, Optional

import logging

import cv2  # type: ignore[import-untyped]
import numpy as np

from .edge_detection_silhouette import edge_detection_silhouette_calculation
from .metadata import get_video_metadata
from .models import AnalysisParameters, AnalysisResult, FrameData
from .storage import VideoStorage

logger = logging.getLogger('uvicorn.error')

def calculate_path_tangent(
    path: list[tuple[int, int]] | np.ndarray,
    point_idx: int,
    look_ahead: int = 30,
) -> tuple[float, float] | None:
    """Calculate the tangent direction (normalized) at a point on a path.
    
    Args:
        path: List of (x, y) tuples or NumPy array representing the path
        point_idx: Index of the point to calculate tangent for
        look_ahead: Number of points to look ahead/behind for tangent calculation
    
    Returns:
        Normalized tangent vector (dx, dy) as tuple, or None if calculation fails
    """
    if isinstance(path, np.ndarray):
        if len(path) == 0 or point_idx < 0 or point_idx >= len(path):
            return None
        
        # Use neighboring points to estimate tangent
        idx_start = max(0, point_idx - look_ahead)
        idx_end = min(len(path) - 1, point_idx + look_ahead)
        
        if idx_start >= idx_end:
            return None
        
        x_start, y_start = float(path[idx_start, 0]), float(path[idx_start, 1])
        x_end, y_end = float(path[idx_end, 0]), float(path[idx_end, 1])
    else:
        if not path or point_idx < 0 or point_idx >= len(path):
            return None
        
        # Use neighboring points to estimate tangent
        idx_start = max(0, point_idx - look_ahead)
        idx_end = min(len(path) - 1, point_idx + look_ahead)
        
        if idx_start >= idx_end:
            return None
        
        x_start, y_start = path[idx_start]
        x_end, y_end = path[idx_end]
    
    # Calculate direction vector
    dx = float(x_end - x_start)
    dy = float(y_end - y_start)
    
    # Normalize
    length = np.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        return None
    
    return (dx / length, dy / length)


def find_nearest_point_on_path(
    path: list[tuple[int, int]],
    point: tuple[float, float],
    direction: tuple[float, float] | None = None,
) -> tuple[int, int] | None:
    """Find the nearest point on a path to a given point, optionally along a direction.
    
    Args:
        path: List of (x, y) tuples representing the path
        point: The point (x, y) to find nearest path point for
        direction: Optional direction vector (dx, dy) to constrain search along perpendicular
    
    Returns:
        Nearest point on path as (x, y) tuple, or None if path is empty
    """
    if not path:
        return None
    
    px, py = point
    
    if direction is None:
        # Simple nearest point search
        min_dist_sq = float('inf')
        nearest_point = None
        
        for x, y in path:
            dist_sq = (x - px) ** 2 + (y - py) ** 2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                nearest_point = (x, y)
        
        return nearest_point
    
    # Search along perpendicular direction
    dx, dy = direction
    # Perpendicular direction (rotate 90 degrees)
    perp_dx = -dy
    perp_dy = dx
    
    min_dist_sq = float('inf')
    nearest_point = None
    
    for x, y in path:
        # Vector from point to path point
        vec_x = x - px
        vec_y = y - py
        
        # Project onto perpendicular direction
        proj = vec_x * perp_dx + vec_y * perp_dy
        
        # Distance along perpendicular
        perp_dist_sq = proj * proj
        
        # Also consider distance along the path direction (to prefer closer points)
        along_dist_sq = (vec_x * dx + vec_y * dy) ** 2
        
        # Combined distance metric (prioritize perpendicular alignment)
        dist_sq = perp_dist_sq + 0.1 * along_dist_sq
        
        if dist_sq < min_dist_sq:
            min_dist_sq = dist_sq
            nearest_point = (x, y)
    
    return nearest_point


def find_nearest_point_on_path_vectorized(
    path_np: np.ndarray,
    point: tuple[float, float],
    direction: tuple[float, float] | None = None,
) -> tuple[int, int] | None:
    """Find the nearest point on a path to a given point, optionally along a direction.
    Vectorized version using NumPy arrays for better performance.
    
    Args:
        path_np: NumPy array of shape (N, 2) with (x, y) coordinates
        point: The point (x, y) to find nearest path point for
        direction: Optional direction vector (dx, dy) to constrain search along perpendicular
    
    Returns:
        Nearest point on path as (x, y) tuple, or None if path is empty
    """
    if len(path_np) == 0:
        return None
    
    px, py = point
    
    if direction is None:
        # Vectorized simple nearest point search
        dists_sq = (path_np[:, 0] - px) ** 2 + (path_np[:, 1] - py) ** 2
        idx = np.argmin(dists_sq)
        return (int(path_np[idx, 0]), int(path_np[idx, 1]))
    
    # Search along perpendicular direction
    dx, dy = direction
    # Perpendicular direction (rotate 90 degrees)
    perp_dx = -dy
    perp_dy = dx
    
    # Vector from point to all path points
    vec = path_np - np.array([px, py], dtype=np.float32)  # Shape: (N, 2)
    
    # Project onto perpendicular direction
    proj = vec[:, 0] * perp_dx + vec[:, 1] * perp_dy
    perp_dist_sq = proj ** 2
    
    # Also consider distance along the path direction (to prefer closer points)
    along_dist_sq = (vec[:, 0] * dx + vec[:, 1] * dy) ** 2
    
    # Combined distance metric (prioritize perpendicular alignment)
    dist_sq = perp_dist_sq + 0.1 * along_dist_sq
    
    idx = np.argmin(dist_sq)
    return (int(path_np[idx, 0]), int(path_np[idx, 1]))


def project_perpendicular(
    center_point: tuple[int, int],
    center_path: list[tuple[int, int]] | np.ndarray,
    center_point_idx: int,
    target_path: list[tuple[int, int]] | np.ndarray,
) -> tuple[int, int] | None:
    """Project a point from the center path perpendicularly onto a target path.
    
    Args:
        center_point: The point (x, y) on the center path
        center_path: The center path for calculating tangent (list or NumPy array)
        center_point_idx: Index of center_point in center_path
        target_path: The path to project onto (list or NumPy array)
    
    Returns:
        Projected point on target path as (x, y) tuple, or None if calculation fails
    """
    # Convert target_path to NumPy array if it's a list (cache this if called in loop)
    if isinstance(target_path, list):
        target_path_np = np.array(target_path, dtype=np.int32)
    else:
        target_path_np = target_path
    
    # Calculate tangent at center point (now works directly with numpy arrays)
    tangent = calculate_path_tangent(center_path, center_point_idx)
    if tangent is None:
        # Fallback: use simple nearest point (vectorized)
        return find_nearest_point_on_path_vectorized(target_path_np, center_point)
    
    # Perpendicular direction (rotate 90 degrees)
    perp_dx, perp_dy = -tangent[1], tangent[0]
    
    # Find nearest point on target path along perpendicular direction (vectorized)
    return find_nearest_point_on_path_vectorized(target_path_np, center_point, (perp_dx, perp_dy))


def calculate_center_path(
    path_top: list[tuple[int, int]],
    path_bottom: list[tuple[int, int]],
    smoothing_window: int = 15,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
) -> list[tuple[int, int]]:
    """Calculate the center path between top and bottom paths using midpoint and smoothing.
    
    Args:
        path_top: List of (x, y) tuples for the top path
        path_bottom: List of (x, y) tuples for the bottom path
        smoothing_window: Window size for moving average smoothing (default: 15)
        horizontal_window_x_left: Left boundary of horizontal window (unused, kept for API compatibility)
        horizontal_window_x_right: Right boundary of horizontal window (unused, kept for API compatibility)
    
    Returns:
        List of (x, y) tuples for the center path
    """
    if not path_top or not path_bottom:
        return []
    
    # Step 1: Calculate center path using simple midpoint
    # Create dictionary mapping x to y for bottom path
    bottom_dict = {x: y for x, y in path_bottom}
    
    # Calculate center path by finding midpoint for each x-coordinate
    # We'll use the x-coordinates from the top path as the base
    center_path = []
    for x, y_top in path_top:
        if x in bottom_dict:
            y_bottom = bottom_dict[x]
            # Calculate midpoint
            y_center = (y_top + y_bottom) / 2.0
            center_path.append((x, y_center))
        else:
            # If x not in bottom path, use top path y as fallback (shouldn't happen normally)
            center_path.append((x, float(y_top)))
    
    # Step 2: Apply smoothing using vectorized moving average with proper edge handling
    if len(center_path) < smoothing_window:
        # If path is shorter than window, return as-is
        return [(x, int(round(y))) for x, y in center_path]
    
    # Extract y values for smoothing
    y_values = np.array([y for _, y in center_path], dtype=np.float32)
    smoothed_y = y_values.copy()  # Start with original values
    
    # Vectorized smoothing with proper edge handling
    # Use a symmetric window that adapts at edges (like original implementation)
    half_window = smoothing_window // 2
    
    # For each point (except first and last), calculate mean over available window
    # This is vectorized using cumulative sums for efficiency
    # Create cumulative sum for fast windowed averages
    cumsum = np.cumsum(y_values, dtype=np.float32)
    
    # Process middle points (skip first and last)
    for i in range(1, len(y_values) - 1):
        # Calculate symmetric window boundaries
        start_idx = max(0, i - half_window)
        end_idx = min(len(y_values), i + half_window + 1)
        
        # Calculate mean over the available window using cumulative sum
        if start_idx == 0:
            window_sum = cumsum[end_idx - 1]
        else:
            window_sum = cumsum[end_idx - 1] - cumsum[start_idx - 1]
        
        window_size = end_idx - start_idx
        smoothed_y[i] = window_sum / window_size
    
    # Reconstruct path with smoothed y values, preserving original x coordinates
    # First and last points keep their original (unsmoothed) values
    smoothed_path = [
        (x, int(round(y_smooth)))
        for (x, _), y_smooth in zip(center_path, smoothed_y)
    ]
    
    return smoothed_path


def get_y_from_path_at_x(path: list[tuple[int, int]], x: float) -> float | None:
    """Get y coordinate from path at a given x coordinate using interpolation.
    
    Uses binary search for O(log n) performance since paths are sorted by x-coordinate.
    
    Args:
        path: List of (x, y) tuples representing the path (must be sorted by x)
        x: X coordinate to find y for
    
    Returns:
        Y coordinate (interpolated if needed), or None if x is outside path range
    """
    if not path:
        return None
    
    # Convert to numpy array for efficient binary search
    path_np = np.array(path, dtype=np.float32)
    x_coords = path_np[:, 0]
    
    # Check if x is outside path range
    if x < x_coords[0] or x > x_coords[-1]:
        return None
    
    # Use binary search to find insertion point
    # searchsorted returns the index where x would be inserted to maintain sorted order
    idx = np.searchsorted(x_coords, x, side='left')
    
    # Handle exact matches
    if idx < len(x_coords) and x_coords[idx] == x:
        return float(path_np[idx, 1])
    
    # If x is at the beginning or end, return the endpoint
    if idx == 0:
        return float(path_np[0, 1])
    if idx >= len(x_coords):
        return float(path_np[-1, 1])
    
    # Interpolate between the point before and at the insertion index
    x1, y1 = path_np[idx - 1, 0], path_np[idx - 1, 1]
    x2, y2 = path_np[idx, 0], path_np[idx, 1]
    
    # Linear interpolation
    if x2 != x1:  # Avoid division by zero
        t = (x - x1) / (x2 - x1)
        y = y1 + t * (y2 - y1)
        return float(y)
    else:
        return float(y1)


def calculate_path_arc_length(path: list[tuple[int, int]], start_idx: int = 0, end_idx: int | None = None) -> float:
    """Calculate the arc length of a path segment.
    
    Args:
        path: List of (x, y) tuples representing the path
        start_idx: Starting index (inclusive)
        end_idx: Ending index (exclusive, or None for end of path)
    
    Returns:
        Total arc length of the path segment
    """
    if not path or start_idx >= len(path):
        return 0.0
    
    if end_idx is None:
        end_idx = len(path)
    
    total_length = 0.0
    for i in range(start_idx, end_idx - 1):
        if i + 1 < len(path):
            x1, y1 = path[i]
            x2, y2 = path[i + 1]
            dx = x2 - x1
            dy = y2 - y1
            total_length += np.sqrt(dx * dx + dy * dy)
    
    return total_length


def calculate_measurement_point_pairs(
    path_top: list[tuple[int, int]],
    path_bottom: list[tuple[int, int]],
    path_center: list[tuple[int, int]],
    num_tracking_points: int,
    distribution_method: str,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
) -> list[list[float]]:
    """Calculate measurement point pairs based on distribution method.
    
    Args:
        path_top: List of (x, y) tuples for the top path
        path_bottom: List of (x, y) tuples for the bottom path
        path_center: List of (x, y) tuples for the center path
        num_tracking_points: Number of points to distribute
        distribution_method: "center_line_projection" or "x_axis_even"
        horizontal_window_x_left: Left boundary of horizontal window
        horizontal_window_x_right: Right boundary of horizontal window
    
    Returns:
        List of point pair arrays: [[cx, cy, tx, ty, bx, by, distance], ...]
    """
    if not path_top or not path_bottom:
        return []
    
    # Check if horizontal window is defined
    if horizontal_window_x_left is None or horizontal_window_x_right is None:
        return []
    
    point_pairs = []
    
    if distribution_method == "center_line_projection":
        # Method a: Distribute points evenly along center line within horizontal window
        if not path_center:
            return []
        
        # Filter center path to points within horizontal window
        center_in_window = [
            (x, y) for x, y in path_center
            if horizontal_window_x_left <= x <= horizontal_window_x_right
        ]
        
        if not center_in_window:
            return []
        
        # Calculate total arc length of center path within window
        total_length = calculate_path_arc_length(center_in_window)
        if total_length < 1e-6:
            # If path is too short, just use the points as-is
            center_in_window = center_in_window[:num_tracking_points]
        else:
            # Distribute points evenly along arc length
            if num_tracking_points > 1:
                target_lengths = [i * total_length / (num_tracking_points - 1) for i in range(num_tracking_points)]
            else:
                target_lengths = [total_length / 2.0]
            
            # Find points at target arc lengths
            selected_center_points = []
            accumulated_length = 0.0
            path_idx = 0
            
            for target_length in target_lengths:
                # Find the segment where this target length falls
                while path_idx < len(center_in_window) - 1:
                    x1, y1 = center_in_window[path_idx]
                    x2, y2 = center_in_window[path_idx + 1]
                    segment_length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                    
                    if accumulated_length + segment_length >= target_length or path_idx == len(center_in_window) - 2:
                        # Interpolate within this segment
                        if segment_length > 1e-6:
                            t = (target_length - accumulated_length) / segment_length
                            x = x1 + t * (x2 - x1)
                            y = y1 + t * (y2 - y1)
                        else:
                            x, y = x1, y1
                        selected_center_points.append((int(round(x)), int(round(y))))
                        break
                    
                    accumulated_length += segment_length
                    path_idx += 1
                else:
                    # If we've reached the end, use the last point
                    if center_in_window:
                        selected_center_points.append(center_in_window[-1])
            
            center_in_window = selected_center_points
        
        # Pre-convert paths to numpy arrays for efficient projection
        path_center_np = np.array(path_center, dtype=np.int32)
        path_top_np = np.array(path_top, dtype=np.int32)
        path_bottom_np = np.array(path_bottom, dtype=np.int32)
        
        # For each center point, project perpendicularly to top and bottom paths
        for center_point in center_in_window:
            # Find the index of this point in the original center path
            # Optimize: use vectorized search instead of loop
            center_point_np = np.array([center_point[0], center_point[1]], dtype=np.int32)
            dists_sq = (path_center_np[:, 0] - center_point_np[0]) ** 2 + (path_center_np[:, 1] - center_point_np[1]) ** 2
            
            # First try exact match (within 2 pixels)
            close_mask = dists_sq <= 4  # 2^2 = 4
            if np.any(close_mask):
                center_idx = int(np.argmax(close_mask))  # Get first match
            else:
                # If not found, use nearest point
                center_idx = int(np.argmin(dists_sq))
            
            # Project to top and bottom paths using pre-converted numpy arrays
            top_projected = project_perpendicular(center_point, path_center_np, center_idx, path_top_np)
            bottom_projected = project_perpendicular(center_point, path_center_np, center_idx, path_bottom_np)
            
            if top_projected is not None and bottom_projected is not None:
                # Calculate distance between top and bottom points
                dx = top_projected[0] - bottom_projected[0]
                dy = top_projected[1] - bottom_projected[1]
                distance = np.sqrt(dx * dx + dy * dy)
                
                # Format: [cx, cy, tx, ty, bx, by, distance]
                point_pairs.append([
                    float(center_point[0]),
                    float(center_point[1]),
                    float(top_projected[0]),
                    float(top_projected[1]),
                    float(bottom_projected[0]),
                    float(bottom_projected[1]),
                    float(distance),
                ])
    
    elif distribution_method == "x_axis_even":
        # Method b: Distribute points evenly along x-axis within horizontal window
        window_width = horizontal_window_x_right - horizontal_window_x_left
        
        if window_width <= 0:
            return []
        
        # Calculate evenly spaced x positions
        if num_tracking_points > 1:
            x_positions = [
                horizontal_window_x_left + i * window_width / (num_tracking_points - 1)
                for i in range(num_tracking_points)
            ]
        else:
            x_positions = [horizontal_window_x_left + window_width / 2.0]
        
        # For each x position, find corresponding points on top and bottom paths
        for x in x_positions:
            y_top = get_y_from_path_at_x(path_top, x)
            y_bottom = get_y_from_path_at_x(path_bottom, x)
            
            if y_top is not None and y_bottom is not None:
                # Calculate distance between top and bottom points (Euclidean distance)
                # For x-axis method, both points have the same x, so distance is just |y_top - y_bottom|
                # but we use the standard formula for consistency
                dx = 0.0  # Same x coordinate
                dy = y_top - y_bottom
                distance = np.sqrt(dx * dx + dy * dy)
                
                # Calculate center point as midpoint between top and bottom
                cx = float(x)
                cy = (y_top + y_bottom) / 2.0
                
                # Format: [cx, cy, tx, ty, bx, by, distance]
                point_pairs.append([
                    cx,
                    cy,
                    float(x),
                    y_top,
                    float(x),
                    y_bottom,
                    float(distance),
                ])
    
    return point_pairs


async def process_video(
    video_id: str,
    parameters: AnalysisParameters,
    progress_callback: Callable[[float, int, int, FrameData], Awaitable[None]],
    start_frame: int = 0,
    existing_results: Optional[AnalysisResult] = None,
) -> tuple[AnalysisResult, int]:
    """
    Process video with costmap analysis.
    
    Args:
        video_id: ID of the video to process
        parameters: Analysis parameters
        progress_callback: Function to call with (progress, current_frame, total_frames, frame_data)
        start_frame: Frame number to start processing from (for resuming)
        existing_results: Existing results to load previous frame paths from (for resuming)
    
    Returns:
        Tuple of (AnalysisResult with per-frame and global data, total_frames)
    """
    # Get video file path
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        raise ValueError(f"Video file not found for video_id: {video_id}")
    
    # Get metadata (automatically loads from cache or generates if needed)
    metadata = get_video_metadata(video_path)
    total_frames = metadata.total_frames
    
    if total_frames == 0:
        raise ValueError(f"Video has no frames: {video_path}")
    
    # Validate start_frame
    if start_frame < 0:
        start_frame = 0
    if start_frame >= total_frames:
        raise ValueError(f"start_frame ({start_frame}) must be less than total_frames ({total_frames})")
    
    per_frame_data = []
    
    # Track previous frame paths for optimization
    prev_path_top: list[tuple[int, int]] | None = None
    prev_path_bottom: list[tuple[int, int]] | None = None
    
    # If resuming, load previous frame paths from existing results
    if start_frame > 0 and existing_results:
        # Find the last frame before start_frame to get previous paths
        previous_frames = [f for f in existing_results.per_frame if f.f < start_frame]
        if previous_frames:
            # Sort by frame number and get the last one
            previous_frames.sort(key=lambda f: f.f)
            last_frame = previous_frames[-1]
            # Convert paths back to tuples for costmap calculation
            prev_path_top = [tuple(pt) for pt in last_frame.pt] if last_frame.pt else None
            prev_path_bottom = [tuple(pb) for pb in last_frame.pb] if last_frame.pb else None
    
    # Process each frame with costmap
    cap = cv2.VideoCapture(str(video_path))
    try:
        # Skip to start_frame
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        time_start = time.perf_counter()
        chunk_size = 100
        for frame_num in range(start_frame, total_frames):
            # Check for cancellation periodically (every frame)
            await asyncio.sleep(0)  # Yield to event loop to allow cancellation
            
            # Read frame
            ret, frame = cap.read()
            if not ret:
                break
            
            # Convert to numpy array if needed
            frame_np = np.array(frame)
            
            # Edge detection using silhouette method
            path_top, path_bottom = edge_detection_silhouette_calculation(
                frame=frame_np,
                smoothing_factor=parameters.smoothing_factor,
                horizontal_window_x_left=parameters.horizontal_window_x_left,
                horizontal_window_x_right=parameters.horizontal_window_x_right,
                prev_path_top=prev_path_top,
                prev_path_bottom=prev_path_bottom,
                blur_ksize=(parameters.silhouette_blur_ksize_x, parameters.silhouette_blur_ksize_y),
                blur_sigma=parameters.silhouette_blur_sigma,
                close_k=parameters.silhouette_close_k,
                x_step=parameters.silhouette_x_step,
                band=parameters.silhouette_band,
                median_k=parameters.silhouette_median_k,
            )
            
            # Update previous paths for next frame
            prev_path_top = path_top
            prev_path_bottom = path_bottom
            
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
            
            # No colored regions for now (can be added later if needed)
            colored_regions = []
            
            frame_data = FrameData(
                f=frame_num,
                pt=path_top_array,
                pb=path_bottom_array,
                pc=path_center_array,
                colored_regions=colored_regions,
                mpp=measurement_point_pairs if measurement_point_pairs else None,
            )
            per_frame_data.append(frame_data)
            
            # Update progress with frame data (send every frame)
            progress = ((frame_num + 1) / total_frames) * 100.0

            if(frame_num % chunk_size == 0):
                elapsed_time = time.perf_counter() - time_start
                logger.warning(f"progress: {progress:.2f}% (frame {frame_num + 1} of {total_frames}) @ {(chunk_size / elapsed_time):.2f}fps")
                time_start = time.perf_counter()

            await progress_callback(progress, frame_num + 1, total_frames, frame_data)
    finally:
        cap.release()
    
    # If resuming, merge with existing results
    if start_frame > 0 and existing_results:
        # Combine existing frames (before start_frame) with new frames
        existing_frames = [f for f in existing_results.per_frame if f.f < start_frame]
        all_frames = existing_frames + per_frame_data
        all_frames.sort(key=lambda f: f.f)
        per_frame_data = all_frames
    
    # Generate global statistics
    global_data = {
        "total_frames": total_frames,
        "total_points_top": sum(len(frame.pt) for frame in per_frame_data),
        "total_points_bottom": sum(len(frame.pb) for frame in per_frame_data),
        "total_points_center": sum(len(frame.pc) for frame in per_frame_data),
        "total_regions": sum(len(frame.colored_regions) for frame in per_frame_data),
        "average_points_top_per_frame": sum(len(frame.pt) for frame in per_frame_data) / total_frames if total_frames > 0 else 0,
        "average_points_bottom_per_frame": sum(len(frame.pb) for frame in per_frame_data) / total_frames if total_frames > 0 else 0,
        "average_points_center_per_frame": sum(len(frame.pc) for frame in per_frame_data) / total_frames if total_frames > 0 else 0,
        "average_regions_per_frame": sum(len(frame.colored_regions) for frame in per_frame_data) / total_frames if total_frames > 0 else 0,
        "parameters_used": {
            "smoothing_factor": parameters.smoothing_factor,
            "horizontal_window_x_left": parameters.horizontal_window_x_left,
            "horizontal_window_x_right": parameters.horizontal_window_x_right,
            "num_tracking_points": parameters.num_tracking_points,
        },
    }
    
    return (
        AnalysisResult(
            per_frame=per_frame_data,
            global_data=global_data,
        ),
        total_frames,
    )

