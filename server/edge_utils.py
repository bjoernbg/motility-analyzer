"""Shared utility functions for edge detection methods."""

import cv2
import numpy as np


def starting_point_detection(*, frame: np.ndarray):
    """Detect starting points for top and bottom boundaries.

    This function is shared between costmap and 1D signal edge detection methods.

    Args:
        frame: Input image as BGR or grayscale ndarray.

    Returns:
        Tuple of (y_top, y_bottom, x_mid) where y_top and y_bottom are the detected
        edge positions and x_mid is the center x coordinate.
    """
    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = frame.copy()

    ksize = -1  # 3 for Sobel, -1 for Scharr
    # Use CV_32F here because cv2.magnitude() requires floating point types
    gX = cv2.Sobel(img_gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=ksize)
    gY = cv2.Sobel(img_gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=ksize)

    # normalize the magnitude to 0-1
    mag = cv2.magnitude(gX, gY)
    mag = cv2.normalize(mag, None, 0.0, 1.0, cv2.NORM_MINMAX)

    # get the center line
    h, w = mag.shape
    x_mid = w // 2
    center_line = mag[:, x_mid].copy()  # shape (h,)

    # Suppress borders (often noisy)
    border = 10
    y0, y1 = border, h - border
    sig = center_line[y0:y1]

    # Find the top two peaks with a "do-not-pick-too-close" rule (simple greedy non-maximum selection)
    idxs = np.arange(y0, y1)
    cand = sig.copy()

    peaks = []
    taken = np.zeros_like(cand, dtype=bool)
    for _ in range(2):
        # pick current max
        i_rel = np.argmax(np.where(~taken, cand, -np.inf))
        if not np.isfinite(cand[i_rel]):
            break  # no more peaks
        peaks.append(idxs[i_rel])

        # exclude a neighborhood around the chosen peak
        peak_min_distance = 30
        left = max(0, i_rel - peak_min_distance)
        right = min(len(cand), i_rel + peak_min_distance + 1)
        taken[left:right] = True

    if len(peaks) < 2:
        return -1, -1, x_mid

    y_top = min(peaks)
    y_bottom = max(peaks)

    return y_top, y_bottom, x_mid


def get_y_from_path(path: list[tuple[int, int]], x: int) -> float | None:
    """Get y value from a path for a given x coordinate using interpolation.

    Args:
        path: List of (x, y) tuples sorted by x (left to right).
        x: The x coordinate to get y value for.

    Returns:
        Interpolated y value, or None if x is outside path range.
    """
    if not path:
        return None

    # Extract x and y arrays
    path_x = [p[0] for p in path]
    path_y = [p[1] for p in path]

    # Check if x is outside path range
    if x < path_x[0] or x > path_x[-1]:
        # Use nearest neighbor for out-of-range x
        if x < path_x[0]:
            return float(path_y[0])
        else:
            return float(path_y[-1])

    # Find the two points to interpolate between
    for i in range(len(path_x) - 1):
        if path_x[i] <= x <= path_x[i + 1]:
            # Linear interpolation
            x0, y0 = path_x[i], path_y[i]
            x1, y1 = path_x[i + 1], path_y[i + 1]

            if x1 == x0:
                return float(y0)

            # Linear interpolation: y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            return float(y)

    # Should not reach here, but return last y if needed
    return float(path_y[-1])


def interpolate_path_to_array(
    path: list[tuple[int, int]],
    x_coords: np.ndarray,
    default_y: float | None = None,
) -> np.ndarray:
    """Pre-interpolate path y-values for all x coordinates at once using vectorized operations.

    Args:
        path: List of (x, y) tuples sorted by x (left to right).
        x_coords: Array of x coordinates to interpolate for.
        default_y: Default y value to use if path is empty or x is out of range. If None, uses nearest neighbor.

    Returns:
        Array of interpolated y values (float32), same length as x_coords.
    """
    if not path:
        if default_y is not None:
            return np.full(len(x_coords), default_y, dtype=np.float32)
        return np.full(len(x_coords), np.nan, dtype=np.float32)

    path_x = np.array([p[0] for p in path], dtype=np.float32)
    path_y = np.array([p[1] for p in path], dtype=np.float32)

    # Handle out-of-range x coordinates with nearest neighbor
    result = np.interp(x_coords, path_x, path_y).astype(np.float32)

    # Clamp to nearest neighbor for out-of-range values
    if default_y is None:
        # Use nearest neighbor: first or last path point
        mask_left = x_coords < path_x[0]
        mask_right = x_coords > path_x[-1]
        result[mask_left] = path_y[0]
        result[mask_right] = path_y[-1]
    else:
        # Use default for out-of-range
        mask_out = (x_coords < path_x[0]) | (x_coords > path_x[-1])
        result[mask_out] = default_y

    return result
