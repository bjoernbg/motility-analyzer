"""1D signal-based edge detection method."""
import logging
import math

import cv2
import numpy as np
from scipy import ndimage

from .edge_utils import interpolate_path_to_array, starting_point_detection

logger = logging.getLogger(__name__)

# Optional Numba acceleration
try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    # Create dummy decorator if numba not available
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


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
        1D array of length band_height with mean values across width.
    """
    H, W = frame.shape
    
    # Calculate strip boundaries
    half_width = strip_width // 2
    x_left = max(0, x - half_width)
    x_right = min(W, x + half_width + 1)
    
    # Calculate band boundaries - ensure range is exactly band_height
    half_height = band_height // 2
    y_top = max(0, int(y_center) - half_height)
    # Ensure y_bottom is exactly band_height pixels from y_top (or at image boundary)
    y_bottom = min(H, y_top + band_height)
    
    # Extract strip (shape: (band_height, strip_width))
    strip = frame[y_top:y_bottom, x_left:x_right]
    
    # Compute mean across width (faster than median, sufficient for small strips)
    # Result: 1D array of length band_height (or less if at image boundary)
    signal_1d = np.mean(strip, axis=1).astype(np.float32)
    
    return signal_1d


@njit(cache=True)
def _extract_strips_batch_numba(
    frame: np.ndarray,
    x_coords: np.ndarray,
    y_centers: np.ndarray,
    strip_width: int,
    band_height: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Numba-accelerated extraction and collapse of strips for multiple x coordinates.
    
    Args:
        frame: Input grayscale image.
        x_coords: Array of x coordinates.
        y_centers: Array of y-center positions for each x coordinate.
        strip_width: Width of horizontal strip (pixels).
        band_height: Height of vertical band (pixels).
    
    Returns:
        Tuple of (all_signals, y_tops) where:
        - all_signals: Array of shape (n_coords, band_height) with 1D signals
        - y_tops: Array of y-top positions for each coordinate
    """
    H, W = frame.shape
    n_coords = len(x_coords)
    half_width = strip_width // 2
    half_height = band_height // 2
    
    all_signals = np.zeros((n_coords, band_height), dtype=np.float32)
    y_tops = np.zeros(n_coords, dtype=np.int32)
    
    for i in range(n_coords):
        x = int(x_coords[i])
        y_center = y_centers[i]
        
        # Calculate strip boundaries
        x_left = max(0, x - half_width)
        x_right = min(W, x + half_width + 1)
        
        # Calculate band boundaries - ensure range is exactly band_height
        y_top = max(0, int(y_center) - half_height)
        # Ensure y_bottom is exactly band_height pixels from y_top (or at image boundary)
        y_bottom = min(H, y_top + band_height)
        
        y_tops[i] = y_top
        
        # Compute mean across width manually (avoid NumPy call overhead)
        actual_height = y_bottom - y_top
        actual_width = x_right - x_left
        
        if actual_height > 0 and actual_width > 0:
            # Manual mean calculation: sum across width, then divide
            for y_idx in range(actual_height):
                y = y_top + y_idx
                sum_val = 0.0
                for x_idx in range(actual_width):
                    x_pos = x_left + x_idx
                    sum_val += float(frame[y, x_pos])
                
                # Compute mean
                mean_val = sum_val / float(actual_width)
                all_signals[i, y_idx] = mean_val
            
    return all_signals, y_tops


def extract_strips_batch(
    frame: np.ndarray,
    x_coords: np.ndarray,
    y_centers: np.ndarray,
    strip_width: int,
    band_height: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract and collapse strips for multiple x coordinates in batch.
    
    Args:
        frame: Input grayscale image.
        x_coords: Array of x coordinates.
        y_centers: Array of y-center positions for each x coordinate.
        strip_width: Width of horizontal strip (pixels).
        band_height: Height of vertical band (pixels).
    
    Returns:
        Tuple of (all_signals, y_tops) where:
        - all_signals: Array of shape (n_coords, band_height) with 1D signals
        - y_tops: Array of y-top positions for each coordinate
    """
    logger.debug(f"extract_strips_batch: n_coords={len(x_coords)}, frame shape={frame.shape}")
    
    # Use Numba-accelerated version if available, otherwise fall back to Python
    if NUMBA_AVAILABLE:
        return _extract_strips_batch_numba(frame, x_coords, y_centers, strip_width, band_height)
    else:
        # Fallback Python implementation
        H, W = frame.shape
        n_coords = len(x_coords)
        half_width = strip_width // 2
        half_height = band_height // 2
        
        all_signals = np.zeros((n_coords, band_height), dtype=np.float32)
        y_tops = np.zeros(n_coords, dtype=np.int32)
        
        for i in range(n_coords):
            x = int(x_coords[i])
            y_center = y_centers[i]
            
            # Calculate strip boundaries
            x_left = max(0, x - half_width)
            x_right = min(W, x + half_width + 1)
            
            # Calculate band boundaries - ensure range is exactly band_height
            y_top = max(0, int(y_center) - half_height)
            # Ensure y_bottom is exactly band_height pixels from y_top (or at image boundary)
            y_bottom = min(H, y_top + band_height)
            
            y_tops[i] = y_top
            
            # Extract strip
            strip = frame[y_top:y_bottom, x_left:x_right]
            
            # Compute mean across width
            if strip.size > 0:
                signal = np.mean(strip, axis=1).astype(np.float32)
                actual_height = len(signal)
                
                # Ensure we don't exceed band_height (defensive check)
                if actual_height > band_height:
                    actual_height = band_height
                
                all_signals[i, :actual_height] = signal[:actual_height]
                
        return all_signals, y_tops


@njit(cache=True)
def _compute_gradient_1d(signal: np.ndarray) -> np.ndarray:
    """Compute gradient of 1D signal (Numba-accelerated).
    
    Args:
        signal: 1D input signal.
    
    Returns:
        Gradient array (same length as input).
    """
    n = len(signal)
    gradient = np.zeros(n, dtype=np.float32)
    
    if n < 2:
        return gradient
    
    # Forward difference at start
    gradient[0] = signal[1] - signal[0]
    
    # Central difference in middle
    for i in range(1, n - 1):
        gradient[i] = (signal[i + 1] - signal[i - 1]) / 2.0
    
    # Backward difference at end
    gradient[n - 1] = signal[n - 1] - signal[n - 2]
    
    return gradient


@njit(cache=True)
def _find_edge_gradient_numba(
    signal: np.ndarray,
    polarity_is_dark_to_light: bool,
    y_center_rough: float,
) -> float:
    """Numba-accelerated gradient-based edge detection.
    
    Args:
        signal: 1D smoothed signal.
        polarity_is_dark_to_light: True for dark_to_light, False for light_to_dark.
        y_center_rough: Rough estimate of edge center.
    
    Returns:
        Edge position (index in signal).
    """
    n = len(signal)
    if n < 3:
        return y_center_rough
    
    # Compute gradient
    gradient = _compute_gradient_1d(signal)
    
    # Adjust for polarity
    if not polarity_is_dark_to_light:
        for i in range(n):
            gradient[i] = -gradient[i]
    
    # Search window around rough center
    window_size = 10
    center_idx = int(y_center_rough)
    start_idx = max(0, center_idx - window_size)
    end_idx = min(n, center_idx + window_size + 1)
    
    if end_idx - start_idx < 3:
        return y_center_rough
    
    # Find peak in window
    peak_idx = start_idx
    max_val = gradient[start_idx]
    for i in range(start_idx + 1, end_idx):
        if gradient[i] > max_val:
            max_val = gradient[i]
            peak_idx = i
    
    # Sub-pixel refinement via parabolic interpolation
    if 0 < peak_idx < n - 1:
        y0 = gradient[peak_idx - 1]
        y1 = gradient[peak_idx]
        y2 = gradient[peak_idx + 1]
        
        denominator = y0 - 2.0 * y1 + y2
        if abs(denominator) > 1e-10:
            offset = 0.5 * (y0 - y2) / denominator
            edge_center = float(peak_idx) + offset
        else:
            edge_center = float(peak_idx)
    else:
        edge_center = float(peak_idx)
    
    # Clamp to valid range
    if edge_center < 0.0:
        edge_center = 0.0
    elif edge_center >= n:
        edge_center = float(n - 1)
    
    return edge_center


@njit(cache=True)
def _detect_edges_batch_numba(
    all_smoothed: np.ndarray,
    y_tops: np.ndarray,
    polarity_is_dark_to_light: bool,
    smoothing_factor: float,
    prev_y_centers: np.ndarray,
) -> np.ndarray:
    """Numba-accelerated batch edge detection for multiple x coordinates.
    
    Args:
        all_smoothed: Array of shape (n_coords, band_height) containing smoothed signals.
        y_tops: Array of y-top positions for each coordinate (for converting to image coords).
        polarity_is_dark_to_light: True for dark_to_light, False for light_to_dark.
        smoothing_factor: Smoothing factor (0-1).
        prev_y_centers: Previous y-center positions for smoothing.
    
    Returns:
        Array of detected edge y positions (image coordinates).
    """
    n_coords = all_smoothed.shape[0]
    results = np.zeros(n_coords, dtype=np.float32)
    
    for i in range(n_coords):
        signal = all_smoothed[i]
        y_top = y_tops[i]
        prev_y_center = prev_y_centers[i]
        
        # Calculate rough center relative to signal
        signal_center_idx = prev_y_center - y_top
        if signal_center_idx < 0:
            signal_center_idx = 0
        elif signal_center_idx >= len(signal):
            signal_center_idx = len(signal) - 1
        
        # Find edge using gradient
        edge_idx = _find_edge_gradient_numba(
            signal, polarity_is_dark_to_light, float(signal_center_idx)
        )
        
        # Convert to image coordinates
        edge_y = y_top + edge_idx
        
        # Apply smoothing
        results[i] = smoothing_factor * prev_y_center + (1.0 - smoothing_factor) * edge_y
    
    return results


def find_edge_gradient(
    signal: np.ndarray,
    polarity: str,
    y_center_rough: float,
) -> float | None:
    """Find edge center using gradient peak with sub-pixel interpolation.
    
    This is much faster than curve fitting while maintaining good accuracy.
    
    Args:
        signal: 1D smoothed signal.
        polarity: "dark_to_light" or "light_to_dark".
        y_center_rough: Rough estimate of edge center (for search window).
    
    Returns:
        Edge position (index in signal), or None if detection fails.
    """
    if len(signal) < 3:
        return None
    
    # Compute gradient (first derivative)
    gradient = np.gradient(signal)
    
    # For dark_to_light: positive gradient peak
    # For light_to_dark: negative gradient peak (invert to find maximum)
    if polarity == "light_to_dark":
        gradient = -gradient
    
    # Search window around rough center (±10 pixels)
    window_size = 10
    center_idx = int(y_center_rough)
    start_idx = max(0, center_idx - window_size)
    end_idx = min(len(gradient), center_idx + window_size + 1)
    
    if end_idx - start_idx < 3:
        return None
    
    # Find peak in window
    gradient_window = gradient[start_idx:end_idx]
    peak_idx_rel = np.argmax(gradient_window)
    peak_idx = start_idx + peak_idx_rel
    
    # Sub-pixel refinement via parabolic interpolation
    if 0 < peak_idx < len(gradient) - 1:
        y0 = gradient[peak_idx - 1]
        y1 = gradient[peak_idx]
        y2 = gradient[peak_idx + 1]
        
        # Parabolic fit: y = ax^2 + bx + c
        # Peak at x = -b/(2a)
        # Using three points: (peak_idx-1, y0), (peak_idx, y1), (peak_idx+1, y2)
        # Solve for offset from peak_idx
        denominator = y0 - 2 * y1 + y2
        if abs(denominator) > 1e-10:
            offset = 0.5 * (y0 - y2) / denominator
            edge_center = peak_idx + offset
        else:
            edge_center = float(peak_idx)
    else:
        edge_center = float(peak_idx)
    
    # Clamp to valid range
    edge_center = max(0.0, min(len(signal) - 1, edge_center))
    
    return edge_center


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
        frame: Input grayscale image (should already be smoothed if sigma > 0).
        y_center: Rough estimate of edge center (y coordinate).
        x: X coordinate to detect edge at.
        strip_width: Width of horizontal strip (pixels).
        band_height: Height of vertical band (pixels).
        sigma: Gaussian sigma parameter (unused, kept for API compatibility).
        polarity: "dark_to_light" or "light_to_dark".
    
    Returns:
        Detected edge y position (float).
    """
    H, W = frame.shape
    
    # Clamp x to valid range
    x = max(0, min(W - 1, x))
    
    # Step 1: Collapse width to 1D (frame is already smoothed)
    signal_1d = collapse_to_1d(frame, x, y_center, strip_width, band_height)
    
    if len(signal_1d) == 0:
        return y_center
    
    # Step 2: Find edge center using gradient peak (no smoothing needed, already done on image)
    # Calculate rough edge position relative to signal
    half_height = band_height // 2
    y_top = max(0, int(y_center) - half_height)
    signal_center_idx = int(y_center) - y_top
    signal_center_idx = max(0, min(len(signal_1d) - 1, signal_center_idx))
    
    edge_idx = find_edge_gradient(signal_1d, polarity, signal_center_idx)
    
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
        frame: Input grayscale image (should already be smoothed if sigma > 0).
        y_start: Starting y-coordinate for the path.
        x_start: Starting x-coordinate for the path.
        strip_width: Width of horizontal strip (pixels).
        band_height: Height of vertical band (pixels).
        sigma: Gaussian sigma parameter (unused, kept for API compatibility).
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
    
    # Apply vertical-only Gaussian blur to the whole image once
    # This replaces per-strip smoothing with a single efficient OpenCV operation
    if sigma > 0:
        # Vertical-only blur: ksize=(1, k) means vertical-only blur (cheap, SIMD-optimized)
        # sigmaX=0 means no horizontal blur, sigmaY=sigma means blur along y-axis
        # Compute kernel size from sigma: k = 2 * ceil(3 * sigma) + 1 (must be odd)
        k = int(2 * math.ceil(3 * sigma) + 1)
        if k % 2 == 0:
            k += 1  # Ensure odd
        img_gray = cv2.GaussianBlur(img_gray, ksize=(1, k), sigmaX=0, sigmaY=sigma)
    
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
            try:
                # Pre-compute y-centers from previous paths using vectorized interpolation
                default_y = float(H // 2)
                prev_y_top_array = interpolate_path_to_array(prev_path_top, x_coords, default_y=default_y)
                prev_y_bottom_array = interpolate_path_to_array(prev_path_bottom, x_coords, default_y=default_y)
                
                # Clamp x coordinates to valid range
                x_coords_clamped = np.clip(x_coords, 0, W - 1)
                
                # Extract all strips in batch (img_gray is already smoothed)
                all_signals_top, y_tops_top = extract_strips_batch(
                    img_gray, x_coords_clamped, prev_y_top_array, strip_width, band_height
                )
                all_signals_bottom, y_tops_bottom = extract_strips_batch(
                    img_gray, x_coords_clamped, prev_y_bottom_array, strip_width, band_height
                )
                
                # No per-strip smoothing needed - image is already smoothed
                # Use Numba-accelerated batch detection if available, otherwise fall back to Python
                if NUMBA_AVAILABLE:
                    y_top_detected = _detect_edges_batch_numba(
                        all_signals_top,
                        y_tops_top.astype(np.float32),
                        polarity_is_dark_to_light=True,
                        smoothing_factor=smoothing_factor,
                        prev_y_centers=prev_y_top_array,
                    )
                    
                    y_bottom_detected = _detect_edges_batch_numba(
                        all_signals_bottom,
                        y_tops_bottom.astype(np.float32),
                        polarity_is_dark_to_light=False,
                        smoothing_factor=smoothing_factor,
                        prev_y_centers=prev_y_bottom_array,
                    )
                else:
                    # Fallback to Python implementation
                    y_top_detected = np.zeros(n_coords, dtype=np.float32)
                    y_bottom_detected = np.zeros(n_coords, dtype=np.float32)
                    
                    for i in range(n_coords):
                        # Top edge: dark to light
                        signal_top = all_signals_top[i]
                        y_top = y_tops_top[i]
                        signal_center_idx = prev_y_top_array[i] - y_top
                        signal_center_idx = max(0, min(len(signal_top) - 1, signal_center_idx))
                        
                        edge_idx = find_edge_gradient(signal_top, "dark_to_light", signal_center_idx)
                        if edge_idx is not None:
                            edge_y = y_top + edge_idx
                            y_top_detected[i] = smoothing_factor * prev_y_top_array[i] + (1 - smoothing_factor) * edge_y
                        else:
                            y_top_detected[i] = prev_y_top_array[i]
                        
                        # Bottom edge: light to dark
                        signal_bottom = all_signals_bottom[i]
                        y_bottom = y_tops_bottom[i]
                        signal_center_idx = prev_y_bottom_array[i] - y_bottom
                        signal_center_idx = max(0, min(len(signal_bottom) - 1, signal_center_idx))
                        
                        edge_idx = find_edge_gradient(signal_bottom, "light_to_dark", signal_center_idx)
                        if edge_idx is not None:
                            edge_y = y_bottom + edge_idx
                            y_bottom_detected[i] = smoothing_factor * prev_y_bottom_array[i] + (1 - smoothing_factor) * edge_y
                        else:
                            y_bottom_detected[i] = prev_y_bottom_array[i]
                
                # Clamp results to valid image bounds
                y_top_detected = np.clip(y_top_detected, 0, H - 1)
                y_bottom_detected = np.clip(y_bottom_detected, 0, H - 1)
                
                # Convert to (x, y) tuples with integer y (already sorted by x)
                path_top = [(int(x_coords[i]), int(np.round(y_top_detected[i]))) for i in range(n_coords)]
                path_bottom = [(int(x_coords[i]), int(np.round(y_bottom_detected[i]))) for i in range(n_coords)]
            except Exception as e:
                logger.error(f"Error in batch processing: {e}", exc_info=True)
                raise
        
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
        logger.info("First frame: using starting point detection")
        # First frame: use starting point detection
        try:
            y_top, y_bottom, x_mid = starting_point_detection(frame=frame)
        except Exception:
            raise
        
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
