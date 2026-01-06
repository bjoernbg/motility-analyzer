"""Morphology-based edge detection method using distance transform."""
import logging

import cv2
import numpy as np

from .edge_utils import interpolate_path_to_array, starting_point_detection

logger = logging.getLogger('uvicorn.error')


def detect_boundary_at_x(
    *,
    dist: np.ndarray,
    x: int,
    y_center: float,
    band: int,
    distance_threshold: float,
    y_min: int,
    polarity: str = "dark_to_light",
    smoothing_factor: float | None = None,
    prev_y: float | None = None,
) -> float:
    """Detect boundary y position at a specific x coordinate using distance transform.
    
    Args:
        dist: Normalized distance transform image (0-1 range).
        x: X coordinate to detect boundary at.
        y_center: Center of the search band.
        band: Width of the search band around y_center.
        distance_threshold: Threshold for boundary detection (points with dist < threshold are boundaries).
        y_min: Minimum y coordinate to filter noise.
        polarity: "dark_to_light" or "light_to_dark" (for edge direction).
        smoothing_factor: Optional smoothing factor (0-1). If None, no smoothing applied.
        prev_y: Previous y value for smoothing. Required if smoothing_factor is not None.
    
    Returns:
        Detected y value (float).
    """
    H, W = dist.shape
    
    # Clamp x to valid range
    x = max(0, min(W - 1, x))
    
    # Calculate band boundaries
    y_lo = max(y_min, int(y_center) - band)
    y_hi = min(H, int(y_center) + band + 1)
    
    # Extract column and band values
    col = dist[y_lo:y_hi, x]
    
    # Find boundary pixels (where distance < threshold)
    boundary_mask = col < distance_threshold
    boundary_indices = np.where(boundary_mask)[0]
    
    if len(boundary_indices) == 0:
        # No boundaries found, return center
        y_detected = y_center
    else:
        # For dark_to_light: prefer boundaries from top (lower indices)
        # For light_to_dark: prefer boundaries from bottom (higher indices)
        if polarity == "dark_to_light":
            # Take the first (topmost) boundary
            boundary_idx = boundary_indices[0]
        else:
            # Take the last (bottommost) boundary
            boundary_idx = boundary_indices[-1]
        
        y_detected = y_lo + float(boundary_idx)
    
    # Apply smoothing if requested
    if smoothing_factor is not None and prev_y is not None:
        y_detected = smoothing_factor * prev_y + (1 - smoothing_factor) * y_detected
    
    return float(y_detected)


def follow_path_morphology(
    *,
    dist: np.ndarray,
    y_start: int,
    x_start: int,
    distance_threshold: float,
    y_min: int,
    band: int = 20,
    smoothing_factor: float = 0.2,
    polarity: str = "dark_to_light",
    x_step: int = -1,
    x_end: int = 0,
) -> list[tuple[int, int]]:
    """Follow a path through distance transform image.
    
    Args:
        dist: Normalized distance transform image (0-1 range).
        y_start: Starting y-coordinate for the path.
        x_start: Starting x-coordinate for the path.
        distance_threshold: Threshold for boundary detection.
        y_min: Minimum y coordinate to filter noise.
        band: Width of the search band around the current path position.
        smoothing_factor: Smoothing factor between 0-1 (higher = more smoothing).
        polarity: "dark_to_light" or "light_to_dark".
        x_step: Step size for x-direction traversal (-1 for left, 1 for right).
        x_end: Ending x-coordinate for the path traversal.
    
    Returns:
        List of (x, y) tuples representing the path.
    """
    logger.info(f"follow_path_morphology: y_start={y_start}, x_start={x_start}, band={band}, smoothing_factor={smoothing_factor}, polarity={polarity}, x_step={x_step}, x_end={x_end}")
    H, W = dist.shape
    Xs = range(x_start, x_end + x_step, x_step * 3)
    X_list = list(Xs)
    
    path = []
    prev_y_center = float(y_start)
    
    for i in range(1, len(X_list)):
        x = X_list[i]
        
        y_detected = detect_boundary_at_x(
            dist=dist,
            x=x,
            y_center=prev_y_center,
            band=band,
            distance_threshold=distance_threshold,
            y_min=y_min,
            polarity=polarity,
            smoothing_factor=smoothing_factor,
            prev_y=prev_y_center,
        )
        
        y_center = y_detected
        path.append((x, int(np.round(y_center))))
        prev_y_center = y_center
    
    return path


def edge_detection_morphology_calculation(
    *,
    frame: np.ndarray,
    threshold_value: float = 40.0,
    gaussian_kernel_size: int = 3,
    closing_kernel_size: int = 3,
    distance_threshold: float = 0.02,
    y_min: int = 150,
    smoothing_factor: float = 0.2,
    path_storage: dict | None = None,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
    prev_path_top: list[tuple[int, int]] | None = None,
    prev_path_bottom: list[tuple[int, int]] | None = None,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Calculate edge paths using morphology-based distance transform detection.
    
    Args:
        frame: Input image as BGR or grayscale ndarray.
        threshold_value: Threshold value for OTSU thresholding.
        gaussian_kernel_size: Kernel size for Gaussian blur (must be odd).
        closing_kernel_size: Kernel size for morphological closing.
        distance_threshold: Threshold for boundary detection (points with dist < threshold are boundaries).
        y_min: Minimum y coordinate to filter noise.
        smoothing_factor: Smoothing factor for path following (0-1).
        path_storage: Optional dict to store paths in.
        horizontal_window_x_left: Left boundary for horizontal window (pixels).
        horizontal_window_x_right: Right boundary for horizontal window (pixels).
        prev_path_top: Previous frame's top path. If provided, skips starting point detection.
        prev_path_bottom: Previous frame's bottom path. If provided, skips starting point detection.
    
    Returns:
        Tuple of (path_top, path_bottom) where paths are lists of (x, y) tuples.
    """
    logger.info(f"edge_detection_morphology_calculation: threshold_value={threshold_value}, gaussian_kernel_size={gaussian_kernel_size}, closing_kernel_size={closing_kernel_size}, distance_threshold={distance_threshold}, y_min={y_min}, smoothing_factor={smoothing_factor}, horizontal_window_x_left={horizontal_window_x_left}, horizontal_window_x_right={horizontal_window_x_right}, prev_path_top={prev_path_top}, prev_path_bottom={prev_path_bottom}")
    if frame is None or not isinstance(frame, np.ndarray):
        raise TypeError("'frame' must be a numpy ndarray")
    
    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = frame.copy()
    
    H, W = img_gray.shape
    
    # Step 1: Apply OTSU thresholding
    _, bw = cv2.threshold(img_gray, threshold_value, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    
    # Step 2: Apply Gaussian blur
    # Ensure kernel size is odd
    if gaussian_kernel_size % 2 == 0:
        gaussian_kernel_size += 1
    img_blurred = cv2.GaussianBlur(bw, (gaussian_kernel_size, gaussian_kernel_size), 0)
    
    # Step 3: Apply morphological closing
    kernel = np.ones((closing_kernel_size, closing_kernel_size), np.uint8)
    img_closed = cv2.morphologyEx(img_blurred, cv2.MORPH_CLOSE, kernel)
    
    # Step 4: Compute distance transform
    dist = cv2.distanceTransform(img_closed, cv2.DIST_L2, 5)
    
    # Step 5: Normalize distance transform to 0-1 range
    cv2.normalize(dist, dist, 0, 1.0, cv2.NORM_MINMAX)
    
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
    
    # Use a search band for path following
    band = 100
    
    if use_previous_paths:
        # Use optimized detection for subsequent frames
        # Get all x coordinates in range
        x_coords = np.array(list(range(x_start, x_end + 1, 3)), dtype=np.int32)
        n_coords = len(x_coords)
        
        if n_coords == 0:
            path_top = []
            path_bottom = []
        else:
            try:
                # Pre-compute y-centers from previous paths using vectorized interpolation
                default_y = float(H // 2)
                prev_y_top_array = interpolate_path_to_array(prev_path_top, x_coords, default_y=default_y)
                prev_y_bottom_array = interpolate_path_to_array(prev_path_bottom, x_coords, default_y=default_y)
                
                # Clamp x coordinates to valid range
                x_coords_clamped = np.clip(x_coords, 0, W - 1)
                
                # Detect boundaries for all x coordinates
                y_top_detected = np.zeros(n_coords, dtype=np.float32)
                y_bottom_detected = np.zeros(n_coords, dtype=np.float32)
                
                for i in range(n_coords):
                    x = int(x_coords_clamped[i])
                    
                    # Top path detection (dark_to_light polarity)
                    y_top_detected[i] = detect_boundary_at_x(
                        dist=dist,
                        x=x,
                        y_center=prev_y_top_array[i],
                        band=band,
                        distance_threshold=distance_threshold,
                        y_min=y_min,
                        polarity="dark_to_light",
                        smoothing_factor=smoothing_factor,
                        prev_y=prev_y_top_array[i],
                    )
                    
                    # Bottom path detection (light_to_dark polarity)
                    y_bottom_detected[i] = detect_boundary_at_x(
                        dist=dist,
                        x=x,
                        y_center=prev_y_bottom_array[i],
                        band=band,
                        distance_threshold=distance_threshold,
                        y_min=y_min,
                        polarity="light_to_dark",
                        smoothing_factor=smoothing_factor,
                        prev_y=prev_y_bottom_array[i],
                    )
                
                # Clamp results to valid image bounds
                y_top_detected = np.clip(y_top_detected, 0, H - 1)
                y_bottom_detected = np.clip(y_bottom_detected, 0, H - 1)
                
                # Convert to (x, y) tuples with integer y (already sorted by x)
                path_top = [(int(x_coords[i]), int(np.round(y_top_detected[i]))) for i in range(n_coords)]
                path_bottom = [(int(x_coords[i]), int(np.round(y_bottom_detected[i]))) for i in range(n_coords)]
            except Exception as e:
                logger.error(f"Error in morphology batch processing: {e}", exc_info=True)
                raise
    
    else:
        logger.info("First frame: using starting point detection")
        # First frame: use starting point detection
        try:
            y_top, y_bottom, x_mid = starting_point_detection(frame=frame)
        except Exception:
            raise
        
        if y_top < 0 or y_bottom < 0:
            # Detection failed, return empty paths
            return [], []
        
        # Determine x_end values based on horizontal window if available
        x_end_left = (
            max(0, horizontal_window_x_left - 100)
            if horizontal_window_x_left is not None and horizontal_window_x_left >= 0
            else 0
        )
        x_end_right = (
            min(W - 1, horizontal_window_x_right + 100)
            if horizontal_window_x_right is not None and horizontal_window_x_right >= 0
            else W - 1
        )
        
        # Follow paths
        path_top_left = follow_path_morphology(
            dist=dist,
            y_start=y_top,
            x_start=x_mid,
            distance_threshold=distance_threshold,
            y_min=y_min,
            band=band,
            smoothing_factor=smoothing_factor,
            polarity="dark_to_light",
            x_step=-1,
            x_end=x_end_left,
        )
        path_top_right = follow_path_morphology(
            dist=dist,
            y_start=y_top,
            x_start=x_mid,
            distance_threshold=distance_threshold,
            y_min=y_min,
            band=band,
            smoothing_factor=smoothing_factor,
            polarity="dark_to_light",
            x_step=1,
            x_end=x_end_right,
        )
        path_bottom_left = follow_path_morphology(
            dist=dist,
            y_start=y_bottom,
            x_start=x_mid,
            distance_threshold=distance_threshold,
            y_min=y_min,
            band=band,
            smoothing_factor=smoothing_factor,
            polarity="light_to_dark",
            x_step=-1,
            x_end=x_end_left,
        )
        path_bottom_right = follow_path_morphology(
            dist=dist,
            y_start=y_bottom,
            x_start=x_mid,
            distance_threshold=distance_threshold,
            y_min=y_min,
            band=band,
            smoothing_factor=smoothing_factor,
            polarity="light_to_dark",
            x_step=1,
            x_end=x_end_right,
        )
        
        # Combine paths: reverse left paths so they go from left to right, then combine with right paths
        path_top_left_reversed = list(reversed(path_top_left))
        path_bottom_left_reversed = list(reversed(path_bottom_left))
        
        # Combine into single paths
        path_top = path_top_left_reversed + path_top_right
        path_bottom = path_bottom_left_reversed + path_bottom_right
    
    # Store paths in path_storage if provided
    if path_storage is not None:
        path_storage["path_top"] = path_top
        path_storage["path_bottom"] = path_bottom
    
    return path_top, path_bottom

