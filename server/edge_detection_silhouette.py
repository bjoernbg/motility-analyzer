"""Silhouette edge detection method using mask-based segmentation."""
import logging

import cv2
import numpy as np
from scipy.ndimage import median_filter

from .edge_utils import interpolate_path_to_array

logger = logging.getLogger('uvicorn.error')


def detect_mask_edges_at_x(
    *,
    mask: np.ndarray,
    x: int,
    y_center_top: float | None = None,
    y_center_bottom: float | None = None,
    band: int | None = None,
) -> tuple[float | None, float | None]:
    """
    For a given x, return (y_top, y_bottom) from a binary mask (object=255).
    Optionally restrict search to a vertical band around previous y estimates.
    Returns None if no object pixels found in that (banded) column.
    
    Args:
        mask: Binary mask image (uint8, 0/255).
        x: X coordinate to detect edges at.
        y_center_top: Optional center y for top edge search band.
        y_center_bottom: Optional center y for bottom edge search band.
        band: Optional width of vertical search band around y_center.
    
    Returns:
        Tuple of (y_top, y_bottom) where values are float or None if not found.
    """
    H, W = mask.shape
    x = max(0, min(W - 1, int(x)))

    if band is None or (y_center_top is None) or (y_center_bottom is None):
        ys = np.flatnonzero(mask[:, x])
    else:
        y_lo = max(0, int(min(y_center_top, y_center_bottom)) - band)
        y_hi = min(H, int(max(y_center_top, y_center_bottom)) + band + 1)
        ys_local = np.flatnonzero(mask[y_lo:y_hi, x])
        ys = ys_local + y_lo

    if ys.size == 0:
        return None, None

    return float(ys[0]), float(ys[-1])


def make_object_mask(
    img_gray: np.ndarray,
    *,
    roi: tuple[int, int, int, int] | None = None,
    blur_ksize: tuple[int, int] = (7, 7),
    blur_sigma: float = 1.5,
    close_k: int = 5,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """
    Create a binary mask of the largest object using Otsu thresholding and morphology.
    
    Args:
        img_gray: Grayscale input image.
        roi: Optional ROI as (x0, y0, w, h). If None, processes full frame.
        blur_ksize: Gaussian blur kernel size (width, height).
        blur_sigma: Gaussian blur sigma.
        close_k: Morphology kernel size for close/open operations.
    
    Returns:
        Tuple of (mask_full_frame, roi_used) where:
        - mask_full_frame: uint8 mask (0/255) in full-frame coordinates
        - roi_used: (x0, y0, w, h) of the ROI that was processed
    """
    H, W = img_gray.shape
    if roi is None:
        x0, y0, w, h = 0, 0, W, H
    else:
        x0, y0, w, h = roi
        x0 = max(0, min(W - 1, x0))
        y0 = max(0, min(H - 1, y0))
        w = max(1, min(W - x0, w))
        h = max(1, min(H - y0, h))

    g = img_gray[y0:y0+h, x0:x0+w]
    g_blur = cv2.GaussianBlur(g, blur_ksize, blur_sigma)

    # Object brighter than background
    _, m = cv2.threshold(g_blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Morphology to fill small gaps/holes and remove tiny specks
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=2)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k, iterations=1)

    # Keep largest connected component
    num, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if num <= 1:
        mask_full = np.zeros((H, W), np.uint8)
        return mask_full, (x0, y0, w, h)

    largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    m = (lab == largest).astype(np.uint8) * 255

    mask_full = np.zeros((H, W), np.uint8)
    mask_full[y0:y0+h, x0:x0+w] = m
    return mask_full, (x0, y0, w, h)


def edge_detection_silhouette_calculation(
    *,
    frame: np.ndarray,
    smoothing_factor: float = 0.2,  # kept for API compat; we'll use median smoothing instead
    path_storage: dict | None = None,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
    prev_path_top: list[tuple[int, int]] | None = None,
    prev_path_bottom: list[tuple[int, int]] | None = None,
    # new knobs (safe defaults for your case)
    blur_ksize: tuple[int, int] = (7, 7),
    blur_sigma: float = 1.5,
    close_k: int = 5,
    x_step: int = 3,
    band: int = 40,          # vertical band around prev curves (when prev paths exist)
    median_k: int = 31,      # 1D smoothing strength for ~800px ROI
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """
    Calculate edge paths using silhouette mask-based detection.
    
    Args:
        frame: Input image as BGR or grayscale ndarray.
        smoothing_factor: Kept for API compatibility (not used, median smoothing used instead).
        path_storage: Optional dict to store paths in.
        horizontal_window_x_left: Left boundary for horizontal window (pixels).
        horizontal_window_x_right: Right boundary for horizontal window (pixels).
        prev_path_top: Previous frame's top path. If provided, uses banded search.
        prev_path_bottom: Previous frame's bottom path. If provided, uses banded search.
        blur_ksize: Gaussian blur kernel size (width, height).
        blur_sigma: Gaussian blur sigma.
        close_k: Morphology kernel size for close/open operations.
        x_step: Step size for x-coordinate sampling.
        band: Vertical band width around previous paths (only used when prev paths exist).
        median_k: Median filter kernel size for 1D smoothing (must be odd).
    
    Returns:
        Tuple of (path_top, path_bottom) where paths are lists of (x, y) tuples.
    """
    if frame is None or not isinstance(frame, np.ndarray):
        raise TypeError("'frame' must be a numpy ndarray")

    # grayscale
    if frame.ndim == 3:
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = frame.copy()

    H, W = img_gray.shape

    # x-range based on horizontal window (extend margins similarly to your code)
    x_start = max(0, (horizontal_window_x_left - 100) if horizontal_window_x_left is not None else 0)
    x_end   = min(W - 1, (horizontal_window_x_right + 100) if horizontal_window_x_right is not None else W - 1)
    if x_end < x_start:
        return [], []

    # ROI optimization: only process the horizontal window region (plus margins)
    # This significantly speeds up morphology and connected components operations
    roi_width = x_end - x_start + 1
    mask, _ = make_object_mask(
        img_gray,
        roi=(x_start, 0, roi_width, H) if roi_width < W else None,
        blur_ksize=blur_ksize,
        blur_sigma=blur_sigma,
        close_k=close_k,
    )

    x_coords = np.arange(x_start, x_end + 1, x_step, dtype=np.int32)
    n = len(x_coords)
    if n == 0:
        return [], []

    # Prepare arrays
    y_top = np.full(n, np.nan, np.float32)
    y_bot = np.full(n, np.nan, np.float32)

    use_prev = prev_path_top is not None and prev_path_bottom is not None

    # Vectorized column extraction: extract all needed columns at once
    # This avoids repeated Python function call overhead
    x_coords_clamped = np.clip(x_coords, 0, W - 1)
    mask_cols = mask[:, x_coords_clamped]  # Shape: (H, n) - all columns extracted at once

    if use_prev:
        default_y = float(H // 2)
        prev_y_top = interpolate_path_to_array(prev_path_top, x_coords, default_y=default_y)
        prev_y_bot = interpolate_path_to_array(prev_path_bottom, x_coords, default_y=default_y)

        # Process each column with banded search
        for i in range(n):
            y_center_top = float(prev_y_top[i])
            y_center_bottom = float(prev_y_bot[i])
            
            # Calculate band boundaries
            y_lo = max(0, int(min(y_center_top, y_center_bottom)) - band)
            y_hi = min(H, int(max(y_center_top, y_center_bottom)) + band + 1)
            
            # Extract band from pre-extracted column
            col_band = mask_cols[y_lo:y_hi, i]
            ys_local = np.flatnonzero(col_band)
            
            if ys_local.size > 0:
                y_top[i] = float(ys_local[0] + y_lo)
                y_bot[i] = float(ys_local[-1] + y_lo)
    else:
        # First frame: scan all columns directly from pre-extracted mask
        for i in range(n):
            col = mask_cols[:, i]
            ys = np.flatnonzero(col)
            if ys.size > 0:
                y_top[i] = float(ys[0])
                y_bot[i] = float(ys[-1])

    # If too many NaNs, fail fast
    valid = np.isfinite(y_top) & np.isfinite(y_bot)
    if valid.sum() < max(10, int(0.2 * n)):
        return [], []

    # Fill gaps by interpolation (needed before median smoothing)
    xs = x_coords.astype(np.float32)
    y_top_f = y_top.copy()
    y_bot_f = y_bot.copy()
    y_top_f[~valid] = np.interp(xs[~valid], xs[valid], y_top[valid])
    y_bot_f[~valid] = np.interp(xs[~valid], xs[valid], y_bot[valid])

    # 1D median smoothing using scipy.ndimage.median_filter (optimized C implementation)
    median_k = int(median_k)
    if median_k % 2 == 0:
        median_k += 1
    median_k = max(3, median_k)

    # Use scipy's optimized median filter (much faster than Python loop)
    y_top_s = median_filter(y_top_f, size=median_k, mode='reflect')
    y_bot_s = median_filter(y_bot_f, size=median_k, mode='reflect')

    # Optional: trim edges of ROI (often messier). Keep center 90%
    lo = int(0.05 * n)
    hi = int(0.95 * n)
    x_coords = x_coords[lo:hi]
    y_top_s  = y_top_s[lo:hi]
    y_bot_s  = y_bot_s[lo:hi]

    path_top = [(int(x_coords[i]), int(round(float(y_top_s[i])))) for i in range(len(x_coords))]
    path_bot = [(int(x_coords[i]), int(round(float(y_bot_s[i])))) for i in range(len(x_coords))]

    if path_storage is not None:
        path_storage["path_top"] = path_top
        path_storage["path_bottom"] = path_bot

    return path_top, path_bot

