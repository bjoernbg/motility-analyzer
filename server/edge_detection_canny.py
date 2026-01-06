"""Canny edge detection method."""
import logging

import cv2
import numpy as np

from .edge_utils import interpolate_path_to_array, starting_point_detection

logger = logging.getLogger('uvicorn.error')


def detect_edge_at_x(
    *,
    edges: np.ndarray,
    x: int,
    y_center: float,
    band: int,
    polarity: str = "dark_to_light",
    smoothing_factor: float | None = None,
    prev_y: float | None = None,
) -> float:
    """Detect edge y position at a specific x coordinate using Canny edges.
    
    Args:
        edges: Binary edge image from Canny detection.
        x: X coordinate to detect edge at.
        y_center: Center of the search band.
        band: Width of the search band around y_center.
        polarity: "dark_to_light" or "light_to_dark" (for edge direction).
        smoothing_factor: Optional smoothing factor (0-1). If None, no smoothing applied.
        prev_y: Previous y value for smoothing. Required if smoothing_factor is not None.
    
    Returns:
        Detected y value (float).
    """
    H, W = edges.shape
    
    # Clamp x to valid range
    x = max(0, min(W - 1, x))
    
    # Calculate band boundaries
    y_lo = max(0, int(y_center) - band)
    y_hi = min(H, int(y_center) + band + 1)
    
    # Extract column and band values
    col = edges[y_lo:y_hi, x].astype(np.float32)
    
    # Find edge pixels (non-zero values)
    edge_indices = np.where(col > 0)[0]
    
    if len(edge_indices) == 0:
        # No edges found, return center
        y_detected = y_center
    else:
        # For dark_to_light: prefer edges from top (lower indices)
        # For light_to_dark: prefer edges from bottom (higher indices)
        if polarity == "dark_to_light":
            # Take the first (topmost) edge
            edge_idx = edge_indices[0]
        else:
            # Take the last (bottommost) edge
            edge_idx = edge_indices[-1]
        
        y_detected = y_lo + float(edge_idx)
    
    # Apply smoothing if requested
    if smoothing_factor is not None and prev_y is not None:
        y_detected = smoothing_factor * prev_y + (1 - smoothing_factor) * y_detected
    
    return float(y_detected)


def follow_path_canny(
    *,
    edges: np.ndarray,
    y_start: int,
    x_start: int,
    band: int = 20,
    smoothing_factor: float = 0.2,
    polarity: str = "dark_to_light",
    x_step: int = -1,
    x_end: int = 0,
) -> list[tuple[int, int]]:
    """Follow a path through Canny edge image.
    
    Args:
        edges: Binary edge image from Canny detection.
        y_start: Starting y-coordinate for the path.
        x_start: Starting x-coordinate for the path.
        band: Width of the search band around the current path position.
        smoothing_factor: Smoothing factor between 0-1 (higher = more smoothing).
        polarity: "dark_to_light" or "light_to_dark".
        x_step: Step size for x-direction traversal (-1 for left, 1 for right).
        x_end: Ending x-coordinate for the path traversal.
    
    Returns:
        List of (x, y) tuples representing the path.
    """
    logger.info(f"follow_path_canny: y_start={y_start}, x_start={x_start}, band={band}, smoothing_factor={smoothing_factor}, polarity={polarity}, x_step={x_step}, x_end={x_end}")
    H, W = edges.shape
    Xs = range(x_start, x_end + x_step, x_step * 3)
    X_list = list(Xs)
    
    path = []
    prev_y_center = float(y_start)
    
    for i in range(1, len(X_list)):
        x = X_list[i]
        
        y_detected = detect_edge_at_x(
            edges=edges,
            x=x,
            y_center=prev_y_center,
            band=band,
            polarity=polarity,
            smoothing_factor=smoothing_factor,
            prev_y=prev_y_center,
        )
        
        y_center = y_detected
        path.append((x, int(np.round(y_center))))
        prev_y_center = y_center
    
    return path


def edge_detection_canny_calculation(
    *,
    frame: np.ndarray,
    canny_threshold1: float = 50.0,
    canny_threshold2: float = 150.0,
    canny_aperture_size: int = 3,
    smoothing_factor: float = 0.2,
    path_storage: dict | None = None,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
    prev_path_top: list[tuple[int, int]] | None = None,
    prev_path_bottom: list[tuple[int, int]] | None = None,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Calculate edge paths using Canny edge detection.
    
    Args:
        frame: Input image as BGR or grayscale ndarray.
        canny_threshold1: Lower threshold for Canny edge detection.
        canny_threshold2: Upper threshold for Canny edge detection.
        canny_aperture_size: Aperture size for Canny edge detection (3, 5, or 7).
        smoothing_factor: Smoothing factor for path following (0-1).
        path_storage: Optional dict to store paths in.
        horizontal_window_x_left: Left boundary for horizontal window (pixels).
        horizontal_window_x_right: Right boundary for horizontal window (pixels).
        prev_path_top: Previous frame's top path. If provided, skips starting point detection.
        prev_path_bottom: Previous frame's bottom path. If provided, skips starting point detection.
    
    Returns:
        Tuple of (path_top, path_bottom) where paths are lists of (x, y) tuples.
    """
    logger.info(f"edge_detection_canny_calculation: canny_threshold1={canny_threshold1}, canny_threshold2={canny_threshold2}, canny_aperture_size={canny_aperture_size}, smoothing_factor={smoothing_factor}, horizontal_window_x_left={horizontal_window_x_left}, horizontal_window_x_right={horizontal_window_x_right}, prev_path_top={prev_path_top}, prev_path_bottom={prev_path_bottom}")
    if frame is None or not isinstance(frame, np.ndarray):
        raise TypeError("'frame' must be a numpy ndarray")
    
    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = frame.copy()
    
    H, W = img_gray.shape

    
    img_gray_thresholded = cv2.threshold(img_gray, 40, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    # blurred = cv2.GaussianBlur(img_gray_thresholded, (3, 3), 0)

    blurred = cv2.GaussianBlur(img_gray_thresholded, (7, 7), 2.0)

    
    # Apply Canny edge detection
    # Ensure aperture_size is valid (must be 3, 5, or 7)
    aperture_size = canny_aperture_size
    if aperture_size not in [3, 5, 7]:
        # Round to nearest valid value
        if aperture_size < 3:
            aperture_size = 3
        elif aperture_size > 7:
            aperture_size = 7
        else:
            # Round to nearest odd number
            aperture_size = int(np.round(aperture_size / 2) * 2 + 1)
            aperture_size = max(3, min(7, aperture_size))
    
    edges = cv2.Canny(
        blurred,
        threshold1=int(canny_threshold1),
        threshold2=int(canny_threshold2),
        apertureSize=aperture_size,
    )
    
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
    
    # Use a search band for path following (similar to costmap method)
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
                
                # Detect edges for all x coordinates
                y_top_detected = np.zeros(n_coords, dtype=np.float32)
                y_bottom_detected = np.zeros(n_coords, dtype=np.float32)
                
                for i in range(n_coords):
                    x = int(x_coords_clamped[i])
                    
                    # Top path detection (dark_to_light polarity)
                    y_top_detected[i] = detect_edge_at_x(
                        edges=edges,
                        x=x,
                        y_center=prev_y_top_array[i],
                        band=band,
                        polarity="dark_to_light",
                        smoothing_factor=smoothing_factor,
                        prev_y=prev_y_top_array[i],
                    )
                    
                    # Bottom path detection (light_to_dark polarity)
                    y_bottom_detected[i] = detect_edge_at_x(
                        edges=edges,
                        x=x,
                        y_center=prev_y_bottom_array[i],
                        band=band,
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
                logger.error(f"Error in Canny batch processing: {e}", exc_info=True)
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
        path_top_left = follow_path_canny(
            edges=edges,
            y_start=y_top,
            x_start=x_mid,
            band=band,
            smoothing_factor=smoothing_factor,
            polarity="dark_to_light",
            x_step=-1,
            x_end=x_end_left,
        )
        path_top_right = follow_path_canny(
            edges=edges,
            y_start=y_top,
            x_start=x_mid,
            band=band,
            smoothing_factor=smoothing_factor,
            polarity="dark_to_light",
            x_step=1,
            x_end=x_end_right,
        )
        path_bottom_left = follow_path_canny(
            edges=edges,
            y_start=y_bottom,
            x_start=x_mid,
            band=band,
            smoothing_factor=smoothing_factor,
            polarity="light_to_dark",
            x_step=-1,
            x_end=x_end_left,
        )
        path_bottom_right = follow_path_canny(
            edges=edges,
            y_start=y_bottom,
            x_start=x_mid,
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

