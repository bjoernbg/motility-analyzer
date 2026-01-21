"""Contraction detection algorithm for identifying contraction waves in thickness heatmaps."""
import numpy as np
from scipy.ndimage import (
    gaussian_filter,
    binary_opening,
    binary_closing,
    generate_binary_structure,
    label,
)
from typing import Optional
import logging

from .config import PIXEL_TO_MM_FACTOR

logger = logging.getLogger('uvicorn.error')


def preprocess(thickness: np.ndarray, sigma: tuple[float, float] = (1.0, 1.0)) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Preprocess thickness data: smooth, normalize, and invert.
    
    Args:
        thickness: Array of shape (Y, T) where Y is point-pair index and T is frame/time index
        sigma: Smoothing sigma in (y, t) index units
    
    Returns:
        Tuple of (contraction_score, smoothed_thickness, normalized_thickness)
    """
    X = thickness.astype(np.float32)
    
    # Apply 2D Gaussian smoothing
    Xs = gaussian_filter(X, sigma=sigma)
    
    # Remove per-y baseline (median) to normalize across indices
    baseline = np.median(Xs, axis=1, keepdims=True)
    Xn = Xs - baseline
    
    # Invert so "contraction strength" is high (lower thickness => higher score)
    S = -Xn
    
    return S, Xs, Xn


def contraction_mask(
    thickness_smooth_or_norm: np.ndarray,
    thr: Optional[float] = None,
    percentile: float = 10.0,
) -> tuple[np.ndarray, float]:
    """
    Create binary mask where thickness is below threshold.
    
    Args:
        thickness_smooth_or_norm: Preprocessed thickness array
        thr: Manual threshold (if None, uses percentile)
        percentile: Percentile for automatic threshold (0-100)
    
    Returns:
        Tuple of (binary_mask, threshold_used)
    """
    X = thickness_smooth_or_norm
    if thr is None:
        thr = np.percentile(X, percentile)
    
    mask = X <= thr
    return mask, float(thr)


def clean_and_label(
    mask: np.ndarray,
    open_iters: int = 1,
    close_iters: int = 2,
) -> tuple[np.ndarray, np.ndarray, int]:
    """
    Clean binary mask and label connected components.
    
    Args:
        mask: Binary mask
        open_iters: Number of binary opening iterations (removes speckles)
        close_iters: Number of binary closing iterations (fills holes)
    
    Returns:
        Tuple of (cleaned_mask, labeled_array, num_components)
    """
    # 8-connectivity in 2D (y, t)
    st = generate_binary_structure(2, 2)
    
    m = mask.copy()
    
    if open_iters > 0:
        m = binary_opening(m, structure=st, iterations=open_iters)
    if close_iters > 0:
        m = binary_closing(m, structure=st, iterations=close_iters)
    
    lbl, n = label(m, structure=st)
    
    return m, lbl, n


def fit_contraction_line(coords_y: np.ndarray, coords_t: np.ndarray) -> tuple[float, float]:
    """
    Fit a line y = a*t + b using least squares.
    
    Args:
        coords_y: Y coordinates (point-pair indices)
        coords_t: T coordinates (frame indices)
    
    Returns:
        Tuple of (slope_a, intercept_b)
    """
    t = coords_t.astype(np.float64)
    y = coords_y.astype(np.float64)
    
    # Solve y = a*t + b using least squares
    # A = [t, 1], x = [a, b]
    A = np.vstack([t, np.ones_like(t)]).T
    result = np.linalg.lstsq(A, y, rcond=None)
    a, b = result[0]
    
    return float(a), float(b)


def calculate_physical_spacing(analysis_id: str, results_storage) -> float:
    """
    Calculate physical spacing (dy) between point pairs.
    
    Uses average distance between consecutive center points in the first frame.
    
    Args:
        analysis_id: Analysis ID
        results_storage: ResultsStorage instance
    
    Returns:
        Physical spacing in mm (defaults to 1.0 if calculation fails)
    """
    try:
        # Get first frame
        first_frame = results_storage.get_frame(analysis_id, 0)
        if not first_frame or not first_frame.mpp:
            return 1.0
        
        # Extract center points from mpp (indices 0, 1 are cx, cy)
        center_points = []
        for mpp_entry in first_frame.mpp:
            if len(mpp_entry) >= 2:
                center_points.append((float(mpp_entry[0]), float(mpp_entry[1])))
        
        if len(center_points) < 2:
            return 1.0
        
        # Calculate average distance between consecutive points
        distances = []
        for i in range(len(center_points) - 1):
            x1, y1 = center_points[i]
            x2, y2 = center_points[i + 1]
            dist = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            distances.append(dist)
        
        if distances:
            avg_distance = np.mean(distances)
            return float(avg_distance) / PIXEL_TO_MM_FACTOR
        else:
            return 1.0
    except Exception as e:
        logger.warning(f"Failed to calculate physical spacing: {e}, using default 1.0")
        return 1.0


def detect_contractions(
    thickness: np.ndarray,
    dt: float,
    dy: Optional[float] = None,
    thr: Optional[float] = None,
    percentile: float = 10.0,
    smooth_sigma: tuple[float, float] = (1.0, 1.0),
    min_pixels: int = 200,
    min_area: Optional[float] = None,
    min_height: Optional[float] = None,
    open_iters: int = 1,
    close_iters: int = 2,
) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """
    Detect contraction waves in thickness heatmap.
    
    Args:
        thickness: Array of shape (Y, T) where Y is point-pair index and T is frame index
        dt: Seconds per frame
        dy: Physical distance per y-index in mm (if None, uses 1.0)
        thr: Manual threshold (if None, uses percentile)
        percentile: Percentile for automatic threshold (0-100)
        smooth_sigma: Smoothing sigma in (y, t) index units
        min_pixels: Minimum pixels per event to keep
        min_area: Minimum area in mm²·s to keep (if None, no area filtering)
        min_height: Minimum height in mm to keep (if None, no height filtering)
        open_iters: Binary opening iterations
        close_iters: Binary closing iterations
    
    Returns:
        Tuple of (events_list, cleaned_mask, labeled_array)
    """
    Y, T = thickness.shape
    logger.info(f"Starting contraction detection: input shape ({Y}, {T}) = {Y} points × {T} frames")
    
    if dy is None:
        dy = 1.0
    
    # Preprocess
    logger.info("Preprocessing: applying Gaussian smoothing and baseline correction...")
    S, Xs, Xn = preprocess(thickness, sigma=smooth_sigma)
    logger.info(f"Preprocessing complete: smoothed with sigma=({smooth_sigma[0]}, {smooth_sigma[1]})")
    
    # Threshold on normalized thickness
    logger.info(f"Thresholding: using {'manual' if thr is not None else f'{percentile}th percentile'} threshold...")
    mask, used_thr = contraction_mask(Xn, thr=thr, percentile=percentile)
    mask_pixels = int(np.sum(mask))
    mask_percent = 100.0 * mask_pixels / mask.size
    logger.info(f"Thresholding complete: threshold={used_thr:.4f}, {mask_pixels} pixels ({mask_percent:.1f}%) below threshold")
    
    # Clean and label
    logger.info(f"Cleaning and labeling: opening iterations={open_iters}, closing iterations={close_iters}...")
    mask_c, lbl, n = clean_and_label(mask, open_iters=open_iters, close_iters=close_iters)
    logger.info(f"Labeling complete: found {n} connected components")
    
    events = []
    filtered_by_pixels = 0
    filtered_by_height = 0
    filtered_by_area = 0

    for k in range(1, n + 1):
        # Get coordinates for this component
        yy, tt = np.where(lbl == k)

        # Filter 1: Pixel count (cheapest check first)
        if yy.size < min_pixels:
            filtered_by_pixels += 1
            continue

        # Calculate bounding box and extents
        t0, t1 = int(tt.min()), int(tt.max())
        y0, y1 = int(yy.min()), int(yy.max())

        duration = (t1 - t0 + 1) * dt
        height = (y1 - y0 + 1) * dy

        # Filter 2: Height threshold
        if min_height is not None and height < min_height:
            filtered_by_height += 1
            continue

        # Calculate exact area (below threshold)
        area_exact = yy.size * dy * dt

        # Filter 3: Area threshold
        if min_area is not None and area_exact < min_area:
            filtered_by_area += 1
            continue

        # Only fit line for events that passed all filters (expensive operation)
        a, b = fit_contraction_line(yy, tt)

        # Triangle approximation
        area_triangle = 0.5 * duration * height

        # Convert slope to physical velocity (dy per dt)
        # a is in "y-indices per frame", convert to mm/s
        velocity = a * (dy / dt)  # positive means moving to higher y over time

        events.append({
            "label": int(k),
            "n_pixels": int(yy.size),
            "threshold_used": float(used_thr),
            "t_range_frames": (t0, t1),
            "y_range_idx": (y0, y1),
            "duration_s": float(duration),
            "height_phys": float(height),
            "velocity_phys_per_s": float(velocity),
            "line_fit": {"a_idx_per_frame": float(a), "b": float(b)},
            "area_exact": float(area_exact),
            "area_triangle": float(area_triangle),
        })

    # Log filtering statistics
    total_filtered = filtered_by_pixels + filtered_by_height + filtered_by_area
    if total_filtered > 0:
        parts = []
        if filtered_by_pixels > 0:
            parts.append(f"{filtered_by_pixels} by min_pixels (<{min_pixels})")
        if filtered_by_height > 0:
            parts.append(f"{filtered_by_height} by min_height (<{min_height:.2f} mm)")
        if filtered_by_area > 0:
            parts.append(f"{filtered_by_area} by min_area (<{min_area:.2f} mm²·s)")
        logger.info(f"Filtered out {total_filtered} components: {', '.join(parts)}")
    
    # Sort by start time
    events.sort(key=lambda e: e["t_range_frames"][0])
    
    logger.info(f"Contraction detection complete: detected {len(events)} contraction event(s)")
    
    return events, mask_c, lbl

