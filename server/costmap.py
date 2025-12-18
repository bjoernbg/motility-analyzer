"""Costmap calculation for edge detection."""
import cv2
import numpy as np

from .edge_utils import (
    interpolate_path_to_array,
    starting_point_detection,
)

# Optional Numba acceleration
try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    # Create dummy decorator if numba not available
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    prange = range


@njit(cache=True, parallel=False)
def _detect_y_batch_numba(
    all_cols: np.ndarray,
    y_centers: np.ndarray,
    x_coords_clamped: np.ndarray,
    H: int,
    detection_band: int,
    threshold_percentile: float,
    smoothing_factor: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Numba-accelerated batch y detection for multiple x coordinates.
    
    Args:
        all_cols: Array of shape (H, n_coords) containing column data.
        y_centers: Array of y-center positions for each x coordinate.
        x_coords_clamped: Clamped x coordinates (for reference, not used in computation).
        H: Height of the image.
        detection_band: Width of the search band.
        threshold_percentile: Percentile threshold (0-100).
        smoothing_factor: Smoothing factor (0-1).
    
    Returns:
        Tuple of (y_top_detected, y_bottom_detected) arrays.
    """
    n_coords = len(y_centers)
    y_detected = np.zeros(n_coords, dtype=np.float32)
    
    for i in range(n_coords):
        y_center = y_centers[i]
        y_lo = max(0, int(y_center) - detection_band)
        y_hi = min(H, int(y_center) + detection_band + 1)
        
        # Extract band values
        band_size = y_hi - y_lo
        band_vals = np.zeros(band_size, dtype=np.float32)
        for j in range(band_size):
            band_vals[j] = all_cols[y_lo + j, i]
        
        # Compute percentile threshold (simple approximation for numba)
        # Sort and find threshold index
        sorted_vals = np.sort(band_vals)
        threshold_idx = int(band_size * threshold_percentile / 100.0)
        if threshold_idx >= band_size:
            threshold_idx = band_size - 1
        threshold_value = sorted_vals[threshold_idx]
        
        # Apply threshold and compute center of gravity
        total_weight = 0.0
        weighted_sum = 0.0
        
        for j in range(band_size):
            val = band_vals[j]
            if val >= threshold_value:
                weight = (val / 255.0) ** 2.5
                weighted_sum += j * weight
                total_weight += weight
        
        if total_weight > 0.0:
            y_raw = y_lo + weighted_sum / total_weight
        else:
            y_raw = y_center
        
        # Apply smoothing
        y_detected[i] = smoothing_factor * y_center + (1 - smoothing_factor) * y_raw
    
    return y_detected


def detect_y_at_x(
    *,
    combined: np.ndarray,
    x: int,
    y_center: float,
    band: int,
    threshold_percentile: float = 80.0,
    smoothing_factor: float | None = None,
    prev_y: float | None = None,
) -> float:
    """Detect y value for a single x coordinate within a y-band.
    
    Args:
        combined: The costmap array.
        x: The x coordinate to detect at.
        y_center: Center of the y-band to search.
        band: Width of the search band around y_center.
        threshold_percentile: Percentile threshold for keeping brightest pixels (0-100).
        smoothing_factor: Optional smoothing factor (0-1). If None, no smoothing applied.
        prev_y: Previous y value for smoothing. Required if smoothing_factor is not None.
    
    Returns:
        Detected y value (float).
    """
    H, W = combined.shape
    
    # Clamp x to valid range
    x = max(0, min(W - 1, x))
    
    # Calculate band boundaries
    y_lo = max(0, int(y_center) - band)  # inclusive
    y_hi = min(H, int(y_center) + band + 1)  # exclusive
    
    # Extract column and band values
    col = combined[:, x].astype(np.float32)
    band_vals = col[y_lo:y_hi].copy()
    
    # Keep only pixels above the threshold percentile
    threshold_value = np.percentile(band_vals, threshold_percentile)
    band_vals[band_vals < threshold_value] = 0
    
    # Avoid division by zero if all pixels were below threshold
    if np.sum(band_vals) == 0:
        y_detected = y_center  # Keep center position if no bright pixels
    else:
        indices = np.arange(len(band_vals))
        # Apply a power to emphasize bright pixels
        weighted_vals = (band_vals / 255.0) ** 2.5
        center_of_gravity = np.sum(indices * weighted_vals) / np.sum(weighted_vals)
        y_detected = y_lo + center_of_gravity
    
    # Apply smoothing if requested
    if smoothing_factor is not None and prev_y is not None:
        y_detected = smoothing_factor * prev_y + (1 - smoothing_factor) * y_detected
    
    return float(y_detected)


def follow_path(
    *,
    combined: np.ndarray,
    y_start: int,
    x_start: int,
    band: int = 20,
    smoothing_factor: float = 0.2,
    threshold_percentile: float = 80.0,
    x_step: int = -1,
    x_end: int = 0,
) -> list[tuple[int, int]]:
    """Follow a path through the costmap image by tracking bright features.

    Args:
        combined: The costmap image to follow the path in.
        y_start: Starting y-coordinate for the path.
        x_start: Starting x-coordinate for the path.
        band: Width of the search band around the current path position.
        smoothing_factor: Smoothing factor between 0-1 (higher = more smoothing).
        threshold_percentile: Percentile threshold for keeping brightest pixels (0-100). Higher values keep more pixels.
        x_step: Step size for x-direction traversal (-1 for left, 1 for right).
        x_end: Ending x-coordinate for the path traversal.

    Returns:
        List of (x, y) tuples representing the path.
    """
    H, W = combined.shape
    Xs = range(x_start, x_end + x_step, x_step * 3)
    X_list = list(Xs)

    path = []
    prev_y_center = y_start

    for i in range(1, len(list(Xs))):
        x = X_list[i]

        y_center = prev_y_center
        y_lo = max(0, int(y_center) - band)  # inclusive
        y_hi = min(H, int(y_center) + band + 1)  # exclusive

        col = combined[:, x].astype(np.float32)
        band_vals = col[y_lo:y_hi].copy()

        # Keep only pixels above the threshold percentile
        threshold_value = np.percentile(band_vals, threshold_percentile)
        band_vals[band_vals < threshold_value] = 0

        # Avoid division by zero if all pixels were below threshold
        if np.sum(band_vals) == 0:
            y_center = prev_y_center  # Keep previous position if no bright pixels
        else:
            indices = np.arange(len(band_vals))
            # Apply a power to emphasize bright pixels
            weighted_vals = (band_vals / 255.0) ** 2.5  # or use band_vals ** 1.5
            center_of_gravity = np.sum(indices * weighted_vals) / np.sum(weighted_vals)
            y_center_raw = y_lo + center_of_gravity
            y_center = smoothing_factor * prev_y_center + (1 - smoothing_factor) * y_center_raw

        path.append((x, int(np.round(y_center))))

        prev_y_center = y_center

    return path


def costmap_calculation(
    *,
    frame: np.ndarray,
    alpha: float = 1.5,
    band: int = 20,
    smoothing_factor: float = 0.2,
    threshold_percentile: float = 80.0,
    path_storage: dict | None = None,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
    prev_path_top: list[tuple[int, int]] | None = None,
    prev_path_bottom: list[tuple[int, int]] | None = None,
    subsequent_frame_band: int | None = None,
) -> tuple[np.ndarray, list[tuple[int, int]], list[tuple[int, int]]]:
    """Calculate oriented cost maps to find boundary starting points and visualize them on the frame.

    Args:
        frame: Input image as BGR or grayscale ndarray.
        alpha: Contrast enhancement factor for costmap display.
        band: Width of the search band around the current path position (for first frame).
        smoothing_factor: Smoothing factor for path following (0-1, higher = more smoothing).
        threshold_percentile: Percentile threshold for keeping brightest pixels (0-100).
        path_storage: Optional dict to store paths in.
        horizontal_window_x_left: Left boundary for horizontal window (pixels).
        horizontal_window_x_right: Right boundary for horizontal window (pixels).
        prev_path_top: Previous frame's top path (list of (x, y) tuples). If provided, skips starting point detection.
        prev_path_bottom: Previous frame's bottom path. If provided, skips starting point detection.
        subsequent_frame_band: Band width for subsequent frames. If None, uses `band` value.

    Returns:
        Tuple of (output_frame, path_top, path_bottom) where paths are lists of (x, y) tuples.
    """
    if frame is None or not isinstance(frame, np.ndarray):
        raise TypeError("'frame' must be a numpy ndarray")


    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = frame.copy()

    ksize = -1  # 3 for Sobel, -1 for Scharr

    # Calculate the gradients using CV_16S for faster computation
    # CV_16S is faster than CV_32F and sufficient for magnitude calculation
    gX = cv2.Sobel(img_gray, ddepth=cv2.CV_16S, dx=1, dy=0, ksize=ksize)
    gY = cv2.Sobel(img_gray, ddepth=cv2.CV_16S, dx=0, dy=1, ksize=ksize)

    # Convert to absolute values and combine (faster than convertScaleAbs for intermediate steps)
    gX_abs = np.abs(gX).astype(np.uint16)
    gY_abs = np.abs(gY).astype(np.uint16)
    
    # Combine gradients with equal weight
    combined = ((gX_abs + gY_abs) // 2).astype(np.uint8)
    
    # Apply contrast enhancement
    combined = cv2.convertScaleAbs(combined, alpha=alpha, beta=0)
    output_frame = frame.copy()

    H, W = combined.shape
    
    # Determine x range based on horizontal window or frame width
    # Extend 100px beyond the horizontal window for better path coverage
    x_start = (
        max(0, horizontal_window_x_left - 100)
        if horizontal_window_x_left is not None and horizontal_window_x_left >= 0
        else 0
    )
    x_end = (
        min(W - 1, horizontal_window_x_right + 100)
        if horizontal_window_x_right is not None and horizontal_window_x_right >= 0
        else W - 1
    )

    # Check if we have previous paths (subsequent frame optimization)
    use_previous_paths = prev_path_top is not None and prev_path_bottom is not None
    
    if use_previous_paths:
        # Use optimized detection for subsequent frames with vectorized batch processing
        detection_band = subsequent_frame_band if subsequent_frame_band is not None else band
        
        # Get all x coordinates in range (extended 100px beyond horizontal window)
        x_coords = np.array(list(range(x_start, x_end + 1, 3)), dtype=np.int32)
        n_coords = len(x_coords)
        
        if n_coords == 0:
            path_top = []
            path_bottom = []
        else:
            # Pre-compute y-centers from previous paths using vectorized interpolation
            default_y = float(H // 2)
            prev_y_top_array = interpolate_path_to_array(prev_path_top, x_coords, default_y=default_y)
            prev_y_bottom_array = interpolate_path_to_array(prev_path_bottom, x_coords, default_y=default_y)
            
            # Clamp x coordinates to valid range
            x_coords_clamped = np.clip(x_coords, 0, W - 1)
            
            # Extract all columns at once for better cache locality
            # Shape: (H, n_coords)
            all_cols = combined[:, x_coords_clamped].astype(np.float32)
            
            # Pre-allocate arrays for band boundaries and results
            y_top_centers = prev_y_top_array.copy()
            y_bottom_centers = prev_y_bottom_array.copy()
            
            # Use Numba-accelerated detection if available, otherwise fall back to Python
            if NUMBA_AVAILABLE:
                # Numba-accelerated batch processing
                y_top_detected = _detect_y_batch_numba(
                    all_cols=all_cols,
                    y_centers=y_top_centers,
                    x_coords_clamped=x_coords_clamped,
                    H=H,
                    detection_band=detection_band,
                    threshold_percentile=threshold_percentile,
                    smoothing_factor=smoothing_factor,
                )
                y_bottom_detected = _detect_y_batch_numba(
                    all_cols=all_cols,
                    y_centers=y_bottom_centers,
                    x_coords_clamped=x_coords_clamped,
                    H=H,
                    detection_band=detection_band,
                    threshold_percentile=threshold_percentile,
                    smoothing_factor=smoothing_factor,
                )
            else:
                # Fallback to pure Python implementation
                y_top_detected = np.zeros(n_coords, dtype=np.float32)
                y_bottom_detected = np.zeros(n_coords, dtype=np.float32)
                
                # Process each x coordinate (still need loop for percentile threshold per column)
                for i in range(n_coords):
                    # Top path detection
                    y_center_top = y_top_centers[i]
                    y_lo_top = max(0, int(y_center_top) - detection_band)
                    y_hi_top = min(H, int(y_center_top) + detection_band + 1)
                    
                    band_vals_top = all_cols[y_lo_top:y_hi_top, i].copy()
                    
                    # Apply percentile threshold
                    threshold_value_top = np.percentile(band_vals_top, threshold_percentile)
                    band_vals_top[band_vals_top < threshold_value_top] = 0
                    
                    if np.sum(band_vals_top) == 0:
                        y_top_detected[i] = y_center_top
                    else:
                        indices = np.arange(len(band_vals_top))
                        weighted_vals = (band_vals_top / 255.0) ** 2.5
                        center_of_gravity = np.sum(indices * weighted_vals) / np.sum(weighted_vals)
                        y_top_detected[i] = y_lo_top + center_of_gravity
                    
                    # Apply smoothing
                    y_top_detected[i] = smoothing_factor * y_top_centers[i] + (1 - smoothing_factor) * y_top_detected[i]
                    y_top_centers[i] = y_top_detected[i]  # Update for next iteration if needed
                    
                    # Bottom path detection
                    y_center_bottom = y_bottom_centers[i]
                    y_lo_bottom = max(0, int(y_center_bottom) - detection_band)
                    y_hi_bottom = min(H, int(y_center_bottom) + detection_band + 1)
                    
                    band_vals_bottom = all_cols[y_lo_bottom:y_hi_bottom, i].copy()
                    
                    # Apply percentile threshold
                    threshold_value_bottom = np.percentile(band_vals_bottom, threshold_percentile)
                    band_vals_bottom[band_vals_bottom < threshold_value_bottom] = 0
                    
                    if np.sum(band_vals_bottom) == 0:
                        y_bottom_detected[i] = y_center_bottom
                    else:
                        indices = np.arange(len(band_vals_bottom))
                        weighted_vals = (band_vals_bottom / 255.0) ** 2.5
                        center_of_gravity = np.sum(indices * weighted_vals) / np.sum(weighted_vals)
                        y_bottom_detected[i] = y_lo_bottom + center_of_gravity
                    
                    # Apply smoothing
                    y_bottom_detected[i] = smoothing_factor * y_bottom_centers[i] + (1 - smoothing_factor) * y_bottom_detected[i]
                    y_bottom_centers[i] = y_bottom_detected[i]  # Update for next iteration if needed
            
            # Convert to (x, y) tuples with integer y (already sorted by x)
            path_top = [(int(x_coords[i]), int(np.round(y_top_detected[i]))) for i in range(n_coords)]
            path_bottom = [(int(x_coords[i]), int(np.round(y_bottom_detected[i]))) for i in range(n_coords)]
        
        # Draw paths on output frame
        if path_top:
            cv2.polylines(
                output_frame, [np.array(path_top)], isClosed=False, color=(0, 0, 255), thickness=1
            )
        if path_bottom:
            cv2.polylines(
                output_frame, [np.array(path_bottom)], isClosed=False, color=(0, 255, 0), thickness=1
            )
    
    else:
        # First frame: use original logic with starting point detection
        y_top, y_bottom, x_mid = starting_point_detection(frame=frame)

        cv2.line(output_frame, (x_mid, y_top - 10), (x_mid, y_top + 10), (0, 0, 255), 1)
        cv2.line(output_frame, (x_mid, y_bottom - 10), (x_mid, y_bottom + 10), (0, 255, 0), 1)

        # Determine x_end values based on horizontal window if available
        # For left paths (x_step=-1, going left): stop at horizontal_window_x_left if available
        # Extend 100px beyond the horizontal window for better path coverage
        x_end_left = (
            max(0, horizontal_window_x_left - 100)
            if horizontal_window_x_left is not None and horizontal_window_x_left >= 0
            else 0
        )
        # For right paths (x_step=1, going right): stop at horizontal_window_x_right if available
        # Extend 100px beyond the horizontal window for better path coverage
        x_end_right = (
            min(W - 1, horizontal_window_x_right + 100)
            if horizontal_window_x_right is not None and horizontal_window_x_right >= 0
            else W - 1
        )

        # follow path
        path_top_left = follow_path(
            combined=combined,
            y_start=y_top,
            x_start=x_mid,
            band=band,
            smoothing_factor=smoothing_factor,
            threshold_percentile=threshold_percentile,
            x_step=-1,
            x_end=x_end_left,
        )
        path_top_right = follow_path(
            combined=combined,
            y_start=y_top,
            x_start=x_mid,
            band=band,
            smoothing_factor=smoothing_factor,
            threshold_percentile=threshold_percentile,
            x_step=1,
            x_end=x_end_right,
        )
        path_bottom_left = follow_path(
            combined=combined,
            y_start=y_bottom,
            x_start=x_mid,
            band=band,
            smoothing_factor=smoothing_factor,
            threshold_percentile=threshold_percentile,
            x_step=-1,
            x_end=x_end_left,
        )
        path_bottom_right = follow_path(
            combined=combined,
            y_start=y_bottom,
            x_start=x_mid,
            band=band,
            smoothing_factor=smoothing_factor,
            threshold_percentile=threshold_percentile,
            x_step=1,
            x_end=x_end_right,
        )
        cv2.polylines(
            output_frame, [np.array(path_top_left)], isClosed=False, color=(0, 0, 255), thickness=1
        )
        cv2.polylines(
            output_frame, [np.array(path_top_right)], isClosed=False, color=(0, 0, 255), thickness=1
        )
        cv2.polylines(
            output_frame, [np.array(path_bottom_left)], isClosed=False, color=(0, 255, 0), thickness=1
        )
        cv2.polylines(
            output_frame, [np.array(path_bottom_right)], isClosed=False, color=(0, 255, 0), thickness=1
        )

        # Combine paths: reverse left paths so they go from left to right, then combine with right paths
        # path_top: left (reversed) + right, path_bottom: left (reversed) + right
        path_top_left_reversed = list(reversed(path_top_left))
        path_bottom_left_reversed = list(reversed(path_bottom_left))

        # Combine into single paths
        path_top = path_top_left_reversed + path_top_right
        path_bottom = path_bottom_left_reversed + path_bottom_right

    # Store paths in path_storage if provided
    if path_storage is not None:
        path_storage["path_top"] = path_top
        path_storage["path_bottom"] = path_bottom


    return output_frame, path_top, path_bottom

