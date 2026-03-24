"""Contraction detection algorithm for identifying contraction waves in thickness heatmaps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import logging

import numpy as np
from scipy.ndimage import (
    binary_closing,
    binary_dilation,
    binary_opening,
    gaussian_filter,
    generate_binary_structure,
    label,
)

from .config import PIXEL_TO_MM_FACTOR
from .models import ContractionDetectionParameters

logger = logging.getLogger("uvicorn.error")

CONTRACTION_DETECTION_VERSION_V2 = "v2"
CONTRACTION_DETECTION_VERSION_LEGACY = "legacy-v1"


@dataclass(slots=True)
class SeedComponent:
    """Connected-component seed that may be merged into a final contraction."""

    label: int
    coords_y: np.ndarray
    coords_t: np.ndarray
    n_pixels: int
    threshold_used: float
    t0: int
    t1: int
    y0: int
    y1: int
    duration_s: float
    span_mm: float
    velocity_mm_s: float
    line_slope_idx_per_frame: float
    line_intercept_idx: float

    def predicted_y(self, frame_index: float) -> float:
        """Evaluate the fitted line at a frame index."""
        return (self.line_slope_idx_per_frame * frame_index) + self.line_intercept_idx


def preprocess(
    thickness: np.ndarray, sigma: tuple[float, float] = (1.0, 1.0)
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Preprocess thickness data: smooth, normalize, and invert.

    Args:
        thickness: Array of shape (Y, T) where Y is point-pair index and T is frame/time index
        sigma: Smoothing sigma in (y, t) index units

    Returns:
        Tuple of (contraction_score, smoothed_thickness, normalized_thickness)
    """
    X = thickness.astype(np.float32, copy=False)

    # Apply 2D Gaussian smoothing.
    Xs = gaussian_filter(X, sigma=sigma)

    # Remove per-y baseline (median) to normalize across indices.
    baseline = np.median(Xs, axis=1, keepdims=True)
    Xn = Xs - baseline

    # Invert so "contraction strength" is high (lower thickness => higher score).
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

    mask = X <= thr  # noqa: SIM300 - keep threshold-on-right form for readability.
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


def fit_contraction_line(
    coords_y: np.ndarray, coords_t: np.ndarray
) -> tuple[float, float]:
    """
    Fit a line y = a*t + b using least squares.

    Args:
        coords_y: Y coordinates (point-pair indices)
        coords_t: T coordinates (frame indices)

    Returns:
        Tuple of (slope_a, intercept_b)
    """
    t = coords_t.astype(np.float64, copy=False)
    y = coords_y.astype(np.float64, copy=False)

    # Solve y = a*t + b using least squares.
    A = np.vstack([t, np.ones_like(t)]).T
    result = np.linalg.lstsq(A, y, rcond=None)
    a, b = result[0]

    return float(a), float(b)


def calculate_physical_spacing(
    analysis_id: str,
    results_storage,
    pixel_to_mm_factor: float | None = None,
) -> float:
    """
    Calculate physical spacing (dy) between point pairs.

    Uses average distance between consecutive center points in the first frame.

    Args:
        analysis_id: Analysis ID
        results_storage: ResultsStorage instance
        pixel_to_mm_factor: Pixels per millimeter for physical conversion

    Returns:
        Physical spacing in mm (defaults to 1.0 if calculation fails)
    """
    factor = (
        float(pixel_to_mm_factor)
        if pixel_to_mm_factor is not None and pixel_to_mm_factor > 0
        else PIXEL_TO_MM_FACTOR
    )

    try:
        first_frame = results_storage.get_frame(analysis_id, 0)
        if not first_frame or not first_frame.mpp:
            return 1.0

        center_points = []
        for mpp_entry in first_frame.mpp:
            if len(mpp_entry) >= 2:
                center_points.append((float(mpp_entry[0]), float(mpp_entry[1])))

        if len(center_points) < 2:
            return 1.0

        distances = []
        for i in range(len(center_points) - 1):
            x1, y1 = center_points[i]
            x2, y2 = center_points[i + 1]
            distances.append(np.hypot(x2 - x1, y2 - y1))

        if distances:
            return float(np.mean(distances)) / factor
        return 1.0
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning(
            "Failed to calculate physical spacing: %s, using default 1.0", exc
        )
        return 1.0


def _build_seed_components(
    lbl: np.ndarray,
    n_components: int,
    *,
    dt: float,
    dy: float,
    min_pixels: int,
    threshold_used: float,
) -> tuple[list[SeedComponent], int]:
    """Build seed descriptors for sufficiently large connected components."""
    components: list[SeedComponent] = []
    filtered_by_pixels = 0

    for label_index in range(1, n_components + 1):
        yy, tt = np.where(lbl == label_index)
        if yy.size < min_pixels:
            filtered_by_pixels += 1
            continue

        t0, t1 = int(tt.min()), int(tt.max())
        y0, y1 = int(yy.min()), int(yy.max())
        duration_s = (t1 - t0 + 1) * dt
        span_mm = (y1 - y0 + 1) * dy
        line_slope, line_intercept = fit_contraction_line(yy, tt)
        velocity_mm_s = line_slope * (dy / dt) if dt > 0 else 0.0

        components.append(
            SeedComponent(
                label=label_index,
                coords_y=yy,
                coords_t=tt,
                n_pixels=int(yy.size),
                threshold_used=threshold_used,
                t0=t0,
                t1=t1,
                y0=y0,
                y1=y1,
                duration_s=float(duration_s),
                span_mm=float(span_mm),
                velocity_mm_s=float(velocity_mm_s),
                line_slope_idx_per_frame=float(line_slope),
                line_intercept_idx=float(line_intercept),
            )
        )

    components.sort(key=lambda component: (component.t0, component.y0))
    return components, filtered_by_pixels


def _seed_components_should_merge(
    left: SeedComponent,
    right: SeedComponent,
    *,
    dt: float,
    dy: float,
    merge_max_gap_s: float,
    merge_max_offset_mm: float,
    merge_max_velocity_delta_mm_s: float,
) -> bool:
    """Decide whether two seed components belong to the same contraction wave."""
    if abs(left.velocity_mm_s - right.velocity_mm_s) > merge_max_velocity_delta_mm_s:
        return False

    max_gap_frames = int(np.ceil(merge_max_gap_s / dt)) if dt > 0 else 0
    gap_frames = max(0, right.t0 - left.t1 - 1)
    if gap_frames > max_gap_frames:
        return False

    if right.t0 <= left.t1:
        compare_frame = float(max(left.t0, right.t0) + min(left.t1, right.t1)) * 0.5
    else:
        compare_frame = 0.5 * float(left.t1 + right.t0)

    offset_mm = abs(left.predicted_y(compare_frame) - right.predicted_y(compare_frame)) * dy
    return offset_mm <= merge_max_offset_mm


def _merge_seed_components(
    components: list[SeedComponent],
    *,
    dt: float,
    dy: float,
    merge_max_gap_s: float,
    merge_max_offset_mm: float,
    merge_max_velocity_delta_mm_s: float,
) -> list[list[SeedComponent]]:
    """Merge seed components by continuity graph connectivity."""
    if not components:
        return []

    parent = list(range(len(components)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root != right_root:
            parent[right_root] = left_root

    max_gap_frames = int(np.ceil(merge_max_gap_s / dt)) if dt > 0 else 0

    for left_index, left_component in enumerate(components):
        for right_index in range(left_index + 1, len(components)):
            right_component = components[right_index]
            if right_component.t0 > left_component.t1 + max_gap_frames:
                break
            if _seed_components_should_merge(
                left_component,
                right_component,
                dt=dt,
                dy=dy,
                merge_max_gap_s=merge_max_gap_s,
                merge_max_offset_mm=merge_max_offset_mm,
                merge_max_velocity_delta_mm_s=merge_max_velocity_delta_mm_s,
            ):
                union(left_index, right_index)

    groups: dict[int, list[SeedComponent]] = {}
    for component_index, component in enumerate(components):
        root = find(component_index)
        groups.setdefault(root, []).append(component)

    merged_groups = list(groups.values())
    merged_groups.sort(key=lambda group: min(component.t0 for component in group))
    return merged_groups


def _select_area_connected_mask(
    threshold_crop: np.ndarray,
    seed_crop_mask: np.ndarray,
) -> np.ndarray:
    """Keep the connected thresholded region that touches the merged seed."""
    structure = generate_binary_structure(2, 2)
    labels, num_labels = label(threshold_crop, structure=structure)
    if num_labels == 0:
        return np.zeros_like(threshold_crop, dtype=bool)

    touching_labels = np.unique(labels[np.logical_and(threshold_crop, seed_crop_mask)])
    touching_labels = touching_labels[touching_labels > 0]

    if touching_labels.size == 0:
        dilated_seed = binary_dilation(seed_crop_mask, structure=structure, iterations=1)
        touching_labels = np.unique(labels[np.logical_and(threshold_crop, dilated_seed)])
        touching_labels = touching_labels[touching_labels > 0]

    if touching_labels.size == 0:
        return np.zeros_like(threshold_crop, dtype=bool)

    return np.isin(labels, touching_labels)


def _build_merged_event(
    group: list[SeedComponent],
    *,
    event_label: int,
    thickness_mm: np.ndarray,
    threshold_used: float,
    area_threshold_mm: float,
    min_area: float | None,
    dt: float,
    dy: float,
    merge_max_gap_s: float,
    merge_max_offset_mm: float,
) -> dict | None:
    """Build a final merged event and compute the connected area metric."""
    coords_y = np.concatenate([component.coords_y for component in group])
    coords_t = np.concatenate([component.coords_t for component in group])

    t0, t1 = int(coords_t.min()), int(coords_t.max())
    y0, y1 = int(coords_y.min()), int(coords_y.max())
    duration_s = (t1 - t0 + 1) * dt
    span_mm = (y1 - y0 + 1) * dy
    line_slope, line_intercept = fit_contraction_line(coords_y, coords_t)
    velocity_mm_s = line_slope * (dy / dt) if dt > 0 else 0.0

    t_pad = int(np.ceil(merge_max_gap_s / dt)) if dt > 0 else 0
    y_pad = int(np.ceil(merge_max_offset_mm / dy)) if dy > 0 else 0

    crop_t0 = max(0, t0 - t_pad)
    crop_t1 = min(thickness_mm.shape[1] - 1, t1 + t_pad)
    crop_y0 = max(0, y0 - y_pad)
    crop_y1 = min(thickness_mm.shape[0] - 1, y1 + y_pad)

    crop = thickness_mm[crop_y0 : crop_y1 + 1, crop_t0 : crop_t1 + 1]
    threshold_crop = crop <= area_threshold_mm
    seed_crop_mask = np.zeros_like(threshold_crop, dtype=bool)
    seed_crop_mask[coords_y - crop_y0, coords_t - crop_t0] = True
    area_connected_mask = _select_area_connected_mask(threshold_crop, seed_crop_mask)
    area_exact = float(np.sum(crop[area_connected_mask], dtype=np.float64) * dy * dt)

    if min_area is not None and area_exact < min_area:
        return None

    area_triangle = float(0.5 * duration_s * span_mm * area_threshold_mm)

    return {
        "label": int(event_label),
        "n_pixels": int(coords_y.size),
        "threshold_used": float(threshold_used),
        "t_range_frames": (t0, t1),
        "y_range_idx": (y0, y1),
        "duration_s": float(duration_s),
        "height_phys": float(span_mm),
        "velocity_phys_per_s": float(velocity_mm_s),
        "line_fit": {
            "a_idx_per_frame": float(line_slope),
            "b": float(line_intercept),
        },
        "area_exact": area_exact,
        "area_triangle": area_triangle,
    }


def detect_contractions(
    thickness: np.ndarray,
    dt: float,
    dy: Optional[float] = None,
    thr: Optional[float] = None,
    percentile: float = 10.0,
    smooth_sigma: tuple[float, float] = (1.0, 1.0),
    min_pixels: int = 200,
    min_area: Optional[float] = None,
    min_span_mm: Optional[float] = 5.0,
    min_duration_s: float = 4.0,
    area_threshold_median_fraction: float = 0.70,
    merge_max_gap_s: float = 1.0,
    merge_max_offset_mm: float = 5.0,
    merge_max_velocity_delta_mm_s: float = 1.0,
    pixel_to_mm_factor: Optional[float] = None,
    open_iters: int = 1,
    close_iters: int = 2,
) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """
    Detect contraction waves in a thickness heatmap.

    Args:
        thickness: Array of shape (Y, T) where Y is point-pair index and T is frame index
        dt: Seconds per frame
        dy: Physical distance per y-index in mm (if None, uses 1.0)
        thr: Manual threshold in normalized-thickness space
        percentile: Percentile for automatic threshold (0-100)
        smooth_sigma: Smoothing sigma in (y, t) index units
        min_pixels: Minimum pixels per seed component to keep
        min_area: Optional minimum connected area in mm²·s
        min_span_mm: Minimum merged contraction spatial span in mm
        min_duration_s: Minimum merged contraction duration in seconds
        area_threshold_median_fraction: Raw-thickness threshold as a fraction of global median
        merge_max_gap_s: Maximum gap in seconds for merging seed components
        merge_max_offset_mm: Maximum offset in mm for merging seed components
        merge_max_velocity_delta_mm_s: Maximum velocity delta in mm/s for merging seed components
        pixel_to_mm_factor: Pixels per millimeter for thickness conversion
        open_iters: Binary opening iterations
        close_iters: Binary closing iterations

    Returns:
        Tuple of (events_list, cleaned_mask, labeled_array)
    """
    Y, T = thickness.shape
    logger.info(
        "Starting contraction detection: input shape (%s, %s) = %s points x %s frames",
        Y,
        T,
        Y,
        T,
    )

    if dy is None:
        dy = 1.0

    mm_factor = (
        float(pixel_to_mm_factor)
        if pixel_to_mm_factor is not None and pixel_to_mm_factor > 0
        else PIXEL_TO_MM_FACTOR
    )

    logger.info("Preprocessing: applying Gaussian smoothing and baseline correction...")
    _, _, normalized_thickness = preprocess(thickness, sigma=smooth_sigma)
    logger.info(
        "Preprocessing complete: smoothed with sigma=(%.2f, %.2f)",
        smooth_sigma[0],
        smooth_sigma[1],
    )

    logger.info(
        "Thresholding: using %s threshold...",
        "manual" if thr is not None else f"{percentile}th percentile",
    )
    mask, used_thr = contraction_mask(normalized_thickness, thr=thr, percentile=percentile)
    mask_pixels = int(np.sum(mask))
    mask_percent = 100.0 * mask_pixels / mask.size if mask.size else 0.0
    logger.info(
        "Thresholding complete: threshold=%.4f, %s pixels (%.1f%%) below threshold",
        used_thr,
        mask_pixels,
        mask_percent,
    )

    logger.info(
        "Cleaning and labeling: opening iterations=%s, closing iterations=%s...",
        open_iters,
        close_iters,
    )
    cleaned_mask, labeled_mask, component_count = clean_and_label(
        mask,
        open_iters=open_iters,
        close_iters=close_iters,
    )
    logger.info("Labeling complete: found %s connected components", component_count)

    seed_components, filtered_by_pixels = _build_seed_components(
        labeled_mask,
        component_count,
        dt=dt,
        dy=dy,
        min_pixels=min_pixels,
        threshold_used=used_thr,
    )

    merged_groups = _merge_seed_components(
        seed_components,
        dt=dt,
        dy=dy,
        merge_max_gap_s=merge_max_gap_s,
        merge_max_offset_mm=merge_max_offset_mm,
        merge_max_velocity_delta_mm_s=merge_max_velocity_delta_mm_s,
    )

    thickness_mm = thickness.astype(np.float32, copy=False) / mm_factor
    global_median_mm = float(np.median(thickness_mm))
    area_threshold_mm = global_median_mm * area_threshold_median_fraction

    events: list[dict] = []
    filtered_by_duration = 0
    filtered_by_span = 0
    filtered_by_area = 0

    for group in merged_groups:
        group_coords_y = np.concatenate([component.coords_y for component in group])
        group_coords_t = np.concatenate([component.coords_t for component in group])

        t0, t1 = int(group_coords_t.min()), int(group_coords_t.max())
        y0, y1 = int(group_coords_y.min()), int(group_coords_y.max())
        duration_s = (t1 - t0 + 1) * dt
        span_mm = (y1 - y0 + 1) * dy

        if duration_s < min_duration_s:
            filtered_by_duration += 1
            continue
        if min_span_mm is not None and span_mm < min_span_mm:
            filtered_by_span += 1
            continue

        event = _build_merged_event(
            group,
            event_label=len(events) + 1,
            thickness_mm=thickness_mm,
            threshold_used=used_thr,
            area_threshold_mm=area_threshold_mm,
            min_area=min_area,
            dt=dt,
            dy=dy,
            merge_max_gap_s=merge_max_gap_s,
            merge_max_offset_mm=merge_max_offset_mm,
        )
        if event is None:
            filtered_by_area += 1
            continue
        events.append(event)

    total_filtered = filtered_by_pixels + filtered_by_duration + filtered_by_span + filtered_by_area
    if total_filtered > 0:
        filtered_parts = []
        if filtered_by_pixels > 0:
            filtered_parts.append(f"{filtered_by_pixels} by min_pixels (<{min_pixels})")
        if filtered_by_duration > 0:
            filtered_parts.append(
                f"{filtered_by_duration} by min_duration_s (<{min_duration_s:.2f} s)"
            )
        if filtered_by_span > 0 and min_span_mm is not None:
            filtered_parts.append(
                f"{filtered_by_span} by min_span_mm (<{min_span_mm:.2f} mm)"
            )
        if filtered_by_area > 0 and min_area is not None:
            filtered_parts.append(f"{filtered_by_area} by min_area (<{min_area:.2f} mm^2*s)")
        logger.info("Filtered out %s components/groups: %s", total_filtered, ", ".join(filtered_parts))

    if seed_components:
        logger.info(
            "Merged %s seed components into %s final contraction group(s)",
            len(seed_components),
            len(merged_groups),
        )

    events.sort(key=lambda event: event["t_range_frames"][0])
    logger.info(
        "Contraction detection complete: detected %s contraction event(s), area threshold %.3f mm",
        len(events),
        area_threshold_mm,
    )

    return events, cleaned_mask, labeled_mask


def detect_contractions_with_parameters(
    thickness: np.ndarray,
    dt: float,
    parameters: ContractionDetectionParameters,
    *,
    dy: Optional[float] = None,
    pixel_to_mm_factor: Optional[float] = None,
) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """Run contraction detection using a single parameter model."""
    min_span_mm = parameters.min_span_mm
    if min_span_mm is None and parameters.min_height is not None:
        min_span_mm = parameters.min_height

    return detect_contractions(
        thickness=thickness,
        dt=dt,
        dy=dy,
        thr=parameters.threshold,
        percentile=parameters.threshold_percentile,
        smooth_sigma=(parameters.smooth_sigma_y, parameters.smooth_sigma_t),
        min_pixels=parameters.min_pixels,
        min_area=parameters.min_area,
        min_span_mm=min_span_mm,
        min_duration_s=parameters.min_duration_s,
        area_threshold_median_fraction=parameters.area_threshold_median_fraction,
        merge_max_gap_s=parameters.merge_max_gap_s,
        merge_max_offset_mm=parameters.merge_max_offset_mm,
        merge_max_velocity_delta_mm_s=parameters.merge_max_velocity_delta_mm_s,
        pixel_to_mm_factor=pixel_to_mm_factor,
        open_iters=parameters.open_iters,
        close_iters=parameters.close_iters,
    )
