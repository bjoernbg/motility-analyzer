"""1D signal-based edge detection method."""
import cv2
import numpy as np
from scipy import ndimage, optimize, special

from .edge_utils import interpolate_path_to_array, starting_point_detection


def collapse_to_1d(
    frame: np.ndarray,
    x: int,
    y_center: float,
    strip_width: int,
    band_height: int,
) -> np.ndarray:
    """Collapse a horizontal strip to a 1D vertical signal.
    
    Args:
        frame: Input grayscale image.
        x: X coordinate (center of strip).
        y_center: Y coordinate (center of band).
        strip_width: Width of horizontal strip (pixels).
        band_height: Height of vertical band (pixels).
    
    Returns:
        1D array of length band_height with median values across width.
    """
    H, W = frame.shape
    
    # Calculate strip boundaries
    half_width = strip_width // 2
    x_left = max(0, x - half_width)
    x_right = min(W, x + half_width + 1)
    
    # Calculate band boundaries
    half_height = band_height // 2
    y_top = max(0, int(y_center) - half_height)
    y_bottom = min(H, int(y_center) + half_height + 1)
    
    # Extract strip (shape: (band_height, strip_width))
    strip = frame[y_top:y_bottom, x_left:x_right]
    
    # Compute median across width (robust to artifacts)
    # Result: 1D array of length band_height
    signal_1d = np.median(strip, axis=1).astype(np.float32)
    
    return signal_1d


def smooth_signal(
    signal: np.ndarray,
    sigma: float,
) -> np.ndarray:
    """Smooth a 1D signal using Gaussian blur.
    
    Args:
        signal: 1D input signal.
        sigma: Gaussian sigma parameter.
    
    Returns:
        Smoothed signal (same length as input).
    """
    return ndimage.gaussian_filter1d(signal, sigma=sigma)




def erf_edge_model(y: np.ndarray, a: float, b: float, y0: float, sigma: float) -> np.ndarray:
    """Error function model for edge: I(y) = a + b * erf((y - y0) / sigma).
    
    Args:
        y: Y coordinates (array).
        a: Baseline intensity.
        b: Amplitude.
        y0: Edge center position.
        sigma: Blur width.
    
    Returns:
        Modeled intensity values.
    """
    return a + b * special.erf((y - y0) / sigma)


def find_edge_sigmoid_fit(
    signal: np.ndarray,
    polarity: str,
    y_center_rough: float,
    band_height: int,
) -> float | None:
    """Find edge center using sigmoid/erf fit.
    
    Args:
        signal: 1D smoothed signal.
        polarity: "dark_to_light" or "light_to_dark".
        y_center_rough: Rough estimate of edge center (for fitting window).
        band_height: Height of the band (for coordinate mapping).
    
    Returns:
        Edge position (index in signal), or None if fit fails.
    """
    y_indices = np.arange(len(signal), dtype=np.float32)
    
    # Determine fitting window (±5 pixels around rough edge)
    window_size = 5
    center_idx = int(y_center_rough)
    start_idx = max(0, center_idx - window_size)
    end_idx = min(len(signal), center_idx + window_size + 1)
    
    if end_idx - start_idx < 3:
        # Window too small for fitting
        return None
    
    # Extract window for fitting
    y_window = y_indices[start_idx:end_idx]
    signal_window = signal[start_idx:end_idx]
    
    # Initial parameter estimates
    a_init = np.min(signal_window)  # Baseline
    b_init = np.max(signal_window) - a_init  # Amplitude
    
    # Adjust for polarity
    if polarity == "light_to_dark":
        b_init = -b_init
    
    y0_init = float(center_idx)  # Edge center
    sigma_init = 2.0  # Blur width
    
    try:
        # Fit the model
        popt, _ = optimize.curve_fit(
            erf_edge_model,
            y_window,
            signal_window,
            p0=[a_init, b_init, y0_init, sigma_init],
            bounds=(
                [a_init - abs(b_init), -2 * abs(b_init), y0_init - window_size, 0.5],
                [a_init + abs(b_init), 2 * abs(b_init), y0_init + window_size, 10.0],
            ),
        )
        
        # Extract edge center (y0 parameter)
        edge_center = popt[2]
        
        # Clamp to valid range
        edge_center = max(0, min(len(signal) - 1, edge_center))
        
        return edge_center
    except (RuntimeError, ValueError):
        # Fit failed, return None
        return None


def detect_edge_1d(
    frame: np.ndarray,
    y_center: float,
    x: int,
    strip_width: int = 5,
    band_height: int = 30,
    sigma: float = 2.0,
    polarity: str = "dark_to_light",
) -> float:
    """Detect edge position using 1D signal analysis.
    
    Args:
        frame: Input grayscale image.
        y_center: Rough estimate of edge center (y coordinate).
        x: X coordinate to detect edge at.
        strip_width: Width of horizontal strip (pixels).
        band_height: Height of vertical band (pixels).
        sigma: Gaussian sigma parameter.
        polarity: "dark_to_light" or "light_to_dark".
    
    Returns:
        Detected edge y position (float).
    """
    H, W = frame.shape
    
    # Clamp x to valid range
    x = max(0, min(W - 1, x))
    
    # Step 1: Collapse width to 1D
    signal_1d = collapse_to_1d(frame, x, y_center, strip_width, band_height)
    
    if len(signal_1d) == 0:
        return y_center
    
    # Step 2: Smooth with Gaussian filter
    signal_smooth = smooth_signal(signal_1d, sigma)
    
    # Step 3: Find edge center using sigmoid fit
    # Calculate rough edge position relative to signal
    half_height = band_height // 2
    y_top = max(0, int(y_center) - half_height)
    signal_center_idx = int(y_center) - y_top
    signal_center_idx = max(0, min(len(signal_smooth) - 1, signal_center_idx))
    
    edge_idx = find_edge_sigmoid_fit(signal_smooth, polarity, signal_center_idx, band_height)
    
    if edge_idx is None:
        # Fallback to center if detection fails
        return y_center
    
    # Convert signal index back to image y coordinate
    edge_y = y_top + edge_idx
    
    # Clamp to valid range
    edge_y = max(0, min(H - 1, edge_y))
    
    return float(edge_y)


def follow_path_1d(
    *,
    frame: np.ndarray,
    y_start: int,
    x_start: int,
    strip_width: int = 5,
    band_height: int = 30,
    sigma: float = 2.0,
    polarity: str = "dark_to_light",
    smoothing_factor: float = 0.2,
    x_step: int = -1,
    x_end: int = 0,
) -> list[tuple[int, int]]:
    """Follow a path using 1D edge detection.
    
    Args:
        frame: Input grayscale image.
        y_start: Starting y-coordinate for the path.
        x_start: Starting x-coordinate for the path.
        strip_width: Width of horizontal strip (pixels).
        band_height: Height of vertical band (pixels).
        sigma: Gaussian sigma parameter.
        polarity: "dark_to_light" or "light_to_dark".
        smoothing_factor: Smoothing factor between 0-1 (higher = more smoothing).
        x_step: Step size for x-direction traversal (-1 for left, 1 for right).
        x_end: Ending x-coordinate for the path traversal.
    
    Returns:
        List of (x, y) tuples representing the path.
    """
    H, W = frame.shape
    Xs = range(x_start, x_end + x_step, x_step * 3)
    X_list = list(Xs)
    
    path = []
    prev_y_center = float(y_start)
    
    for i in range(1, len(X_list)):
        x = X_list[i]
        
        # Detect edge at this x position
        y_detected = detect_edge_1d(
            frame=frame,
            y_center=prev_y_center,
            x=x,
            strip_width=strip_width,
            band_height=band_height,
            sigma=sigma,
            polarity=polarity,
        )
        
        # Apply smoothing
        y_center = smoothing_factor * prev_y_center + (1 - smoothing_factor) * y_detected
        
        path.append((x, int(np.round(y_center))))
        prev_y_center = y_center
    
    return path


def edge_detection_1d_calculation(
    *,
    frame: np.ndarray,
    strip_width: int = 5,
    band_height: int = 30,
    sigma: float = 2.0,
    smoothing_factor: float = 0.2,
    path_storage: dict | None = None,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
    prev_path_top: list[tuple[int, int]] | None = None,
    prev_path_bottom: list[tuple[int, int]] | None = None,
) -> tuple[np.ndarray, list[tuple[int, int]], list[tuple[int, int]]]:
    """Calculate edge paths using 1D signal-based detection.
    
    Args:
        frame: Input image as BGR or grayscale ndarray.
        strip_width: Width of horizontal strip (pixels).
        band_height: Height of vertical band (pixels).
        sigma: Gaussian sigma parameter for smoothing.
        smoothing_factor: Smoothing factor for path following (0-1).
        path_storage: Optional dict to store paths in.
        horizontal_window_x_left: Left boundary for horizontal window (pixels).
        horizontal_window_x_right: Right boundary for horizontal window (pixels).
        prev_path_top: Previous frame's top path. If provided, skips starting point detection.
        prev_path_bottom: Previous frame's bottom path. If provided, skips starting point detection.
    
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
    
    output_frame = frame.copy()
    H, W = img_gray.shape
    
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
        # Use optimized detection for subsequent frames
        # Get all x coordinates in range
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
            
            # Detect edges for each x coordinate
            y_top_detected = np.zeros(n_coords, dtype=np.float32)
            y_bottom_detected = np.zeros(n_coords, dtype=np.float32)
            
            for i in range(n_coords):
                x = int(x_coords_clamped[i])
                
                # Top edge: dark to light (upper edge)
                y_center_top = prev_y_top_array[i]
                y_top_raw = detect_edge_1d(
                    frame=img_gray,
                    y_center=y_center_top,
                    x=x,
                    strip_width=strip_width,
                    band_height=band_height,
                    sigma=sigma,
                    polarity="dark_to_light",
                )
                # Apply smoothing
                y_top_detected[i] = smoothing_factor * y_center_top + (1 - smoothing_factor) * y_top_raw
                
                # Bottom edge: light to dark (lower edge)
                y_center_bottom = prev_y_bottom_array[i]
                y_bottom_raw = detect_edge_1d(
                    frame=img_gray,
                    y_center=y_center_bottom,
                    x=x,
                    strip_width=strip_width,
                    band_height=band_height,
                    sigma=sigma,
                    polarity="light_to_dark",
                )
                # Apply smoothing
                y_bottom_detected[i] = smoothing_factor * y_center_bottom + (1 - smoothing_factor) * y_bottom_raw
            
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
        # First frame: use starting point detection
        y_top, y_bottom, x_mid = starting_point_detection(frame=frame)
        
        if y_top < 0 or y_bottom < 0:
            # Detection failed, return empty paths
            return output_frame, [], []
        
        cv2.line(output_frame, (x_mid, y_top - 10), (x_mid, y_top + 10), (0, 0, 255), 1)
        cv2.line(output_frame, (x_mid, y_bottom - 10), (x_mid, y_bottom + 10), (0, 255, 0), 1)
        
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
        path_top_left = follow_path_1d(
            frame=img_gray,
            y_start=y_top,
            x_start=x_mid,
            strip_width=strip_width,
            band_height=band_height,
            sigma=sigma,
            polarity="dark_to_light",
            smoothing_factor=smoothing_factor,
            x_step=-1,
            x_end=x_end_left,
        )
        path_top_right = follow_path_1d(
            frame=img_gray,
            y_start=y_top,
            x_start=x_mid,
            strip_width=strip_width,
            band_height=band_height,
            sigma=sigma,
            polarity="dark_to_light",
            smoothing_factor=smoothing_factor,
            x_step=1,
            x_end=x_end_right,
        )
        path_bottom_left = follow_path_1d(
            frame=img_gray,
            y_start=y_bottom,
            x_start=x_mid,
            strip_width=strip_width,
            band_height=band_height,
            sigma=sigma,
            polarity="light_to_dark",
            smoothing_factor=smoothing_factor,
            x_step=-1,
            x_end=x_end_left,
        )
        path_bottom_right = follow_path_1d(
            frame=img_gray,
            y_start=y_bottom,
            x_start=x_mid,
            strip_width=strip_width,
            band_height=band_height,
            sigma=sigma,
            polarity="light_to_dark",
            smoothing_factor=smoothing_factor,
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
