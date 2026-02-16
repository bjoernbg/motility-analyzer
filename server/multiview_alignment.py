"""Alignment helpers for multi-view sessions (window + time shift)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional
import logging

import cv2
import numpy as np

from .database import AnalysisDB
from .edge_detection_silhouette import make_object_mask
from .edge_detection_silhouette import detect_mask_edges_at_x
from .models import (
    Analysis,
    MultiViewAlignmentSuggestion,
    MultiViewTimeShiftSuggestion,
    MultiViewWindowSuggestion,
    VideoMetadata,
)

AUTO_APPLY_CONFIDENCE_THRESHOLD = 0.35
TARGET_SIGNAL_HZ = 20.0
logger = logging.getLogger("uvicorn.error")


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _median_or_none(values: Iterable[float]) -> float | None:
    values_list = [float(v) for v in values]
    if not values_list:
        return None
    return float(np.median(np.asarray(values_list, dtype=np.float64)))


def _quantile_sample_times(duration_sec: float, sample_count: int) -> list[float]:
    if duration_sec <= 0:
        return [0.0]

    count = max(1, int(sample_count))
    if count == 1:
        return [duration_sec * 0.5]

    qs = np.linspace(0.1, 0.9, count, dtype=np.float64)
    return [float(q * duration_sec) for q in qs]


def _frame_from_time(time_sec: float, fps: float, total_frames: int) -> int:
    if total_frames <= 0:
        return 0
    if fps <= 0:
        return _clamp_int(int(round(time_sec)), 0, total_frames - 1)
    return _clamp_int(int(round(time_sec * fps)), 0, total_frames - 1)


def _derive_window_bounds(
    analysis: Analysis,
    video_width: int,
    sampled_x_mins: list[float],
    sampled_x_maxs: list[float],
) -> tuple[int, int]:
    params = analysis.parameters
    raw_left = params.get("horizontal_window_x_left")
    raw_right = params.get("horizontal_window_x_right")

    if isinstance(raw_left, int) and isinstance(raw_right, int) and raw_right > raw_left:
        return (
            _clamp_int(raw_left, 0, max(0, video_width - 2)),
            _clamp_int(raw_right, 1, max(1, video_width - 1)),
        )

    if sampled_x_mins and sampled_x_maxs:
        median_min = float(np.median(np.asarray(sampled_x_mins, dtype=np.float64)))
        median_max = float(np.median(np.asarray(sampled_x_maxs, dtype=np.float64)))
        left = _clamp_int(int(round(median_min - 20)), 0, max(0, video_width - 2))
        right = _clamp_int(int(round(median_max + 20)), left + 1, max(1, video_width - 1))
        return left, right

    left = int(round(video_width * 0.1))
    right = int(round(video_width * 0.9))
    left = _clamp_int(left, 0, max(0, video_width - 2))
    right = _clamp_int(right, left + 1, max(1, video_width - 1))
    return left, right


def _best_high_occupancy_run(
    values: np.ndarray, *, threshold: float, min_len: int
) -> tuple[int, int, float] | None:
    if values.size == 0:
        return None

    mask = values >= threshold
    run_start: int | None = None
    runs: list[tuple[int, int, float]] = []
    for i, hit in enumerate(mask):
        if hit:
            if run_start is None:
                run_start = i
            continue
        if run_start is not None:
            run_len = i - run_start
            if run_len >= min_len:
                run_mean = float(np.mean(values[run_start:i]))
                runs.append((run_start, run_len, run_mean))
            run_start = None
    if run_start is not None:
        run_len = mask.size - run_start
        if run_len >= min_len:
            run_mean = float(np.mean(values[run_start:]))
            runs.append((run_start, run_len, run_mean))

    if not runs:
        return None
    runs.sort(key=lambda run: (run[2], run[0]))
    return runs[-1]


def _detect_tube_anchor_x(video_path: Path, frame_indices: list[int]) -> int | None:
    """Detect the left boundary of the bright tube holder in the right image region."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    detected: list[int] = []
    last_width: int | None = None
    try:
        for frame_idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_idx)))
            ret, frame = cap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            last_width = w

            mask, _ = make_object_mask(gray)
            col_fill = (mask > 0).mean(axis=0).astype(np.float32)
            smooth = np.convolve(
                col_fill, np.ones(9, dtype=np.float32) / 9.0, mode="same"
            )

            start = int(0.6 * w)
            focus = smooth[start:]
            if focus.size == 0:
                continue

            q75 = float(np.quantile(focus, 0.75))
            q90 = float(np.quantile(focus, 0.90))
            q95 = float(np.quantile(focus, 0.95))

            primary_threshold = max(0.22, q90, q75 + 0.07)
            run = _best_high_occupancy_run(
                focus,
                threshold=primary_threshold,
                min_len=max(6, int(round(0.004 * w))),
            )
            threshold_used = primary_threshold
            if run is None:
                secondary_threshold = max(0.20, q95)
                run = _best_high_occupancy_run(
                    focus,
                    threshold=secondary_threshold,
                    min_len=max(4, int(round(0.003 * w))),
                )
                threshold_used = secondary_threshold

            anchor: int | None = None
            if run is not None:
                anchor = start + int(run[0])
            else:
                gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
                grad = np.abs(gx).mean(axis=0)[start:]
                if grad.size > 0:
                    anchor = start + int(np.argmax(grad))

            if anchor is not None:
                detected.append(int(anchor))
                logger.info(
                    "Tube-anchor sample: frame=%s anchor_x=%s threshold=%.3f q90=%.3f q95=%.3f",
                    frame_idx,
                    anchor,
                    threshold_used,
                    q90,
                    q95,
                )
    finally:
        cap.release()

    if detected:
        return int(round(float(np.median(np.asarray(detected, dtype=np.float64)))))
    if last_width is not None:
        return max(0, last_width - 1)
    return None


def _detect_tube_vertical_bounds(
    video_path: Path, frame_indices: list[int]
) -> tuple[float, float] | None:
    """Detect median tube top/bottom near the right edge, matching calibration semantics."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    y_tops: list[float] = []
    y_bottoms: list[float] = []
    try:
        for frame_idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_idx)))
            ret, frame = cap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            if h <= 0 or w <= 0:
                continue

            mask, _ = make_object_mask(gray)
            x_start = max(0, w - 15)
            x_end = max(x_start + 1, w - 5)

            frame_tops: list[float] = []
            frame_bottoms: list[float] = []
            for x in range(x_start, x_end):
                y_top, y_bottom = detect_mask_edges_at_x(mask=mask, x=x)
                if y_top is None or y_bottom is None:
                    continue
                if y_bottom <= y_top:
                    continue
                frame_tops.append(float(y_top))
                frame_bottoms.append(float(y_bottom))

            if frame_tops and frame_bottoms:
                y_tops.append(float(np.median(np.asarray(frame_tops, dtype=np.float64))))
                y_bottoms.append(
                    float(np.median(np.asarray(frame_bottoms, dtype=np.float64)))
                )
    finally:
        cap.release()

    if not y_tops or not y_bottoms:
        return None
    return (
        float(np.median(np.asarray(y_tops, dtype=np.float64))),
        float(np.median(np.asarray(y_bottoms, dtype=np.float64))),
    )


def _compute_window_suggestion(
    *,
    db: AnalysisDB,
    left_analysis: Analysis,
    right_analysis: Analysis,
    left_metadata: VideoMetadata,
    right_metadata: VideoMetadata,
    left_video_path: Path,
    right_video_path: Path,
    left_pixel_to_mm_factor: float,
    right_pixel_to_mm_factor: float,
    sample_frames: int,
) -> MultiViewWindowSuggestion:
    logger.info(
        "Alignment window analysis: left=%s right=%s sample_frames=%s",
        left_analysis.id,
        right_analysis.id,
        sample_frames,
    )
    overlap_duration = max(
        0.0, min(float(left_metadata.duration), float(right_metadata.duration))
    )
    times = _quantile_sample_times(overlap_duration, sample_frames)

    sampled_frames: list[int] = []
    left_sample_frames: list[int] = []
    right_sample_frames: list[int] = []
    left_x_mins: list[float] = []
    right_x_mins: list[float] = []

    for t in times:
        left_frame = _frame_from_time(t, left_metadata.fps, left_metadata.total_frames)
        right_frame = _frame_from_time(
            t, right_metadata.fps, right_metadata.total_frames
        )

        sampled_frames.append(left_frame)
        left_sample_frames.append(left_frame)
        right_sample_frames.append(right_frame)

    left_anchor_x = _detect_tube_anchor_x(left_video_path, left_sample_frames)
    right_anchor_x = _detect_tube_anchor_x(right_video_path, right_sample_frames)
    left_tube_bounds = _detect_tube_vertical_bounds(left_video_path, left_sample_frames)
    right_tube_bounds = _detect_tube_vertical_bounds(
        right_video_path, right_sample_frames
    )
    if left_anchor_x is None:
        left_anchor_x = max(0, left_metadata.width - 1)
    if right_anchor_x is None:
        right_anchor_x = max(0, right_metadata.width - 1)

    logger.info(
        "Detected tube anchors: left_anchor_x=%s right_anchor_x=%s",
        left_anchor_x,
        right_anchor_x,
    )

    for i, t in enumerate(times):
        left_frame = left_sample_frames[i] if i < len(left_sample_frames) else _frame_from_time(t, left_metadata.fps, left_metadata.total_frames)
        right_frame = right_sample_frames[i] if i < len(right_sample_frames) else _frame_from_time(t, right_metadata.fps, right_metadata.total_frames)

        left_data = db.get_frame(left_analysis.id, left_frame)
        right_data = db.get_frame(right_analysis.id, right_frame)
        if not left_data or not right_data:
            continue

        left_pc = left_data.pc or []
        right_pc = right_data.pc or []
        if len(left_pc) == 0 or len(right_pc) == 0:
            continue

        left_x_values = np.asarray([float(p[0]) for p in left_pc], dtype=np.float64)
        right_x_values = np.asarray([float(p[0]) for p in right_pc], dtype=np.float64)
        if left_x_values.size == 0 or right_x_values.size == 0:
            continue

        left_x_mins.append(float(np.min(left_x_values)))
        right_x_mins.append(float(np.min(right_x_values)))

    left_x_left, left_x_right = _derive_window_bounds(
        left_analysis, left_metadata.width, left_x_mins, []
    )
    right_x_left, right_x_right = _derive_window_bounds(
        right_analysis, right_metadata.width, right_x_mins, []
    )

    left_window_width_px = max(10, left_x_right - left_x_left)
    right_window_width_px = max(10, right_x_right - right_x_left)

    left_margin = float(left_anchor_x - left_x_right)
    right_margin = float(right_anchor_x - right_x_right)
    margin_delta = float(left_margin - right_margin)

    left_offset_mm = (
        left_margin / left_pixel_to_mm_factor if left_pixel_to_mm_factor > 0 else None
    )
    right_offset_mm = (
        right_margin / right_pixel_to_mm_factor
        if right_pixel_to_mm_factor > 0
        else None
    )

    left_window_width_mm = (
        float(left_window_width_px / left_pixel_to_mm_factor)
        if left_pixel_to_mm_factor > 0
        else None
    )
    right_window_width_mm = (
        float(right_window_width_px / right_pixel_to_mm_factor)
        if right_pixel_to_mm_factor > 0
        else None
    )

    width_candidates_mm = [
        mm
        for mm in [left_window_width_mm, right_window_width_mm]
        if mm is not None and mm > 0
    ]
    target_window_width_mm = min(width_candidates_mm) if width_candidates_mm else None

    if target_window_width_mm is not None and left_pixel_to_mm_factor > 0:
        left_target_width_px = max(10, int(round(target_window_width_mm * left_pixel_to_mm_factor)))
    else:
        left_target_width_px = left_window_width_px
    if target_window_width_mm is not None and right_pixel_to_mm_factor > 0:
        right_target_width_px = max(10, int(round(target_window_width_mm * right_pixel_to_mm_factor)))
    else:
        right_target_width_px = right_window_width_px

    offset_list = [mm for mm in [left_offset_mm, right_offset_mm] if mm is not None]
    target_offset_mm = (
        float(np.median(np.asarray(offset_list, dtype=np.float64)))
        if offset_list
        else 0.0
    )

    left_target_right = (
        left_anchor_x - int(round(target_offset_mm * left_pixel_to_mm_factor))
        if left_pixel_to_mm_factor > 0
        else left_x_right
    )
    right_target_right = (
        right_anchor_x - int(round(target_offset_mm * right_pixel_to_mm_factor))
        if right_pixel_to_mm_factor > 0
        else right_x_right
    )

    left_suggested_x_right = _clamp_int(
        left_target_right, 1, max(1, left_metadata.width - 1)
    )
    left_suggested_x_left = _clamp_int(
        left_suggested_x_right - left_target_width_px,
        0,
        max(0, left_suggested_x_right - 1),
    )

    right_suggested_x_right = _clamp_int(
        right_target_right, 1, max(1, right_metadata.width - 1)
    )
    right_suggested_x_left = _clamp_int(
        right_suggested_x_right - right_target_width_px,
        0,
        max(0, right_suggested_x_right - 1),
    )

    left_delta_px = left_suggested_x_left - left_x_left
    right_delta_px = right_suggested_x_left - right_x_left

    scale_ratio = None
    if (
        left_window_width_mm is not None
        and right_window_width_mm is not None
        and left_window_width_mm > 1e-9
    ):
        scale_ratio = float(right_window_width_mm / left_window_width_mm)

    result = MultiViewWindowSuggestion(
        sample_frames=sampled_frames,
        left_right_margin_px=float(left_margin),
        right_right_margin_px=float(right_margin),
        right_margin_delta_px=float(margin_delta),
        left_window_delta_px=left_delta_px,
        right_window_delta_px=right_delta_px,
        left_suggested_x_left=left_suggested_x_left,
        left_suggested_x_right=left_suggested_x_right,
        right_suggested_x_left=right_suggested_x_left,
        right_suggested_x_right=right_suggested_x_right,
        left_span_mm=left_window_width_mm,
        right_span_mm=right_window_width_mm,
        scale_mismatch_ratio=scale_ratio,
        left_anchor_x_px=int(left_anchor_x),
        right_anchor_x_px=int(right_anchor_x),
        target_offset_mm=float(target_offset_mm),
        target_window_width_mm=(
            float(target_window_width_mm)
            if target_window_width_mm is not None
            else None
        ),
        left_tube_end_x_left_px=int(left_anchor_x),
        left_tube_end_x_right_px=max(int(left_anchor_x) + 1, int(left_metadata.width)),
        left_tube_end_y_top_px=(
            float(left_tube_bounds[0]) if left_tube_bounds is not None else None
        ),
        left_tube_end_y_bottom_px=(
            float(left_tube_bounds[1]) if left_tube_bounds is not None else None
        ),
        right_tube_end_x_left_px=int(right_anchor_x),
        right_tube_end_x_right_px=max(
            int(right_anchor_x) + 1, int(right_metadata.width)
        ),
        right_tube_end_y_top_px=(
            float(right_tube_bounds[0]) if right_tube_bounds is not None else None
        ),
        right_tube_end_y_bottom_px=(
            float(right_tube_bounds[1]) if right_tube_bounds is not None else None
        ),
    )
    logger.info(
        (
            "Alignment window result: margin_delta_px=%.2f "
            "left_anchor=%s right_anchor=%s left_margin=%.2f right_margin=%.2f "
            "target_offset_mm=%.3f target_width_mm=%s "
            "left_delta=%s right_delta=%s left_window=%s-%s right_window=%s-%s"
        ),
        result.right_margin_delta_px,
        left_anchor_x,
        right_anchor_x,
        result.left_right_margin_px,
        result.right_right_margin_px,
        target_offset_mm,
        f"{target_window_width_mm:.3f}" if target_window_width_mm is not None else "n/a",
        result.left_window_delta_px,
        result.right_window_delta_px,
        result.left_suggested_x_left,
        result.left_suggested_x_right,
        result.right_suggested_x_left,
        result.right_suggested_x_right,
    )
    return result


def _resample_signal(signal: np.ndarray, fps: float, target_hz: float) -> np.ndarray:
    if signal.size <= 1 or fps <= 0 or target_hz <= 0:
        return signal.astype(np.float64, copy=False)

    duration = (signal.size - 1) / fps
    if duration <= 0:
        return signal.astype(np.float64, copy=False)

    t_old = np.linspace(0.0, duration, signal.size, dtype=np.float64)
    t_new = np.arange(0.0, duration + (0.5 / target_hz), 1.0 / target_hz, dtype=np.float64)
    if t_new.size == 0:
        return signal.astype(np.float64, copy=False)

    return np.interp(t_new, t_old, signal).astype(np.float64, copy=False)


def _normalized(values: np.ndarray) -> np.ndarray:
    arr = values.astype(np.float64, copy=False)
    if arr.size == 0:
        return arr
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    if std <= 1e-9:
        return np.zeros_like(arr)
    return (arr - mean) / std


def _corr_for_lag(left: np.ndarray, right: np.ndarray, lag: int) -> float:
    if lag > 0:
        if lag >= min(left.size, right.size):
            return float("-inf")
        a = left[:-lag]
        b = right[lag:]
    elif lag < 0:
        pos = -lag
        if pos >= min(left.size, right.size):
            return float("-inf")
        a = left[pos:]
        b = right[:-pos]
    else:
        a = left
        b = right

    n = min(a.size, b.size)
    if n < 5:
        return float("-inf")
    a2 = a[:n]
    b2 = b[:n]
    a_std = float(np.std(a2))
    b_std = float(np.std(b2))
    if a_std <= 1e-9 or b_std <= 1e-9:
        return float("-inf")
    a_z = (a2 - float(np.mean(a2))) / a_std
    b_z = (b2 - float(np.mean(b2))) / b_std
    return float(np.mean(a_z * b_z))


def _lag_confidence(peak: float, prominence: float) -> float:
    strength = min(1.0, max(0.0, (peak - 0.20) / 0.75))
    sep = min(1.0, max(0.0, prominence) / 0.08)
    confidence = 0.8 * strength + 0.2 * sep
    if prominence < 0.015 and peak < 0.98:
        confidence -= 0.12
    if peak >= 0.85:
        confidence = max(confidence, 0.40)
    return float(max(0.0, min(1.0, confidence)))


def _match_time_shift(
    left_signal: np.ndarray, right_signal: np.ndarray, max_shift_sec: float
) -> tuple[float, float, float, float]:
    left_norm = _normalized(left_signal)
    right_norm = _normalized(right_signal)
    if left_norm.size < 8 or right_norm.size < 8:
        return 0.0, 0.0, 0.0, 0.0

    max_lag = max(1, int(round(max_shift_sec * TARGET_SIGNAL_HZ)))
    lags = np.arange(-max_lag, max_lag + 1, dtype=np.int32)
    corr_values = np.asarray(
        [_corr_for_lag(left_norm, right_norm, int(lag)) for lag in lags],
        dtype=np.float64,
    )

    finite_mask = np.isfinite(corr_values)
    if not finite_mask.any():
        return 0.0, 0.0, 0.0, 0.0

    finite_corr = corr_values[finite_mask]
    finite_lags = lags[finite_mask]
    best_idx = int(np.argmax(finite_corr))
    best_corr = float(finite_corr[best_idx])
    best_lag_samples = int(finite_lags[best_idx])

    if finite_corr.size > 1:
        others = np.delete(finite_corr, best_idx)
        second_best = float(np.max(others))
    else:
        second_best = -1.0

    prominence = float(best_corr - second_best)
    confidence = _lag_confidence(best_corr, prominence)
    best_shift_sec = float(best_lag_samples / TARGET_SIGNAL_HZ)
    return best_shift_sec, confidence, best_corr, prominence


def _analysis_signal(
    db: AnalysisDB, analysis_id: str, fps: float, pixel_to_mm_factor: float
) -> np.ndarray:
    matrix, _, _ = db.build_heatmap_matrix(analysis_id)
    if matrix.size == 0:
        return np.array([], dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] < 2:
        return np.array([], dtype=np.float64)
    signal_px = np.median(matrix, axis=1).astype(np.float64, copy=False)
    if pixel_to_mm_factor > 0:
        signal_mm = signal_px / pixel_to_mm_factor
    else:
        signal_mm = signal_px
    return _resample_signal(signal_mm, fps=fps, target_hz=TARGET_SIGNAL_HZ)


def _motion_energy_signal(
    video_path: Path,
    fps: float,
    x_left: Optional[int],
    x_right: Optional[int],
) -> np.ndarray:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return np.array([], dtype=np.float64)

    step = max(1, int(round(fps / TARGET_SIGNAL_HZ))) if fps > 0 else 1
    energies: list[float] = []
    prev_roi: np.ndarray | None = None
    frame_idx = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % step != 0:
                frame_idx += 1
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            width = gray.shape[1]
            if width <= 1:
                frame_idx += 1
                continue

            left = 0 if x_left is None else _clamp_int(int(x_left), 0, width - 2)
            right = (
                width - 1
                if x_right is None
                else _clamp_int(int(x_right), left + 1, width - 1)
            )
            roi = gray[:, left : right + 1]

            if prev_roi is not None and prev_roi.shape == roi.shape:
                diff = cv2.absdiff(roi, prev_roi)
                energies.append(float(np.mean(diff)))
            prev_roi = roi
            frame_idx += 1
    finally:
        cap.release()

    if not energies:
        return np.array([], dtype=np.float64)
    sampled_hz = fps / step if fps > 0 else TARGET_SIGNAL_HZ
    return _resample_signal(
        np.asarray(energies, dtype=np.float64),
        fps=sampled_hz,
        target_hz=TARGET_SIGNAL_HZ,
    )


def _time_shift_suggestion(
    *,
    db: AnalysisDB,
    left_analysis: Analysis,
    right_analysis: Analysis,
    left_metadata: VideoMetadata,
    right_metadata: VideoMetadata,
    left_pixel_to_mm_factor: float,
    right_pixel_to_mm_factor: float,
    left_video_path: Path,
    right_video_path: Path,
    max_shift_sec: float,
) -> tuple[MultiViewTimeShiftSuggestion, list[str]]:
    logger.info(
        "Alignment time-shift analysis: left=%s right=%s max_shift_sec=%.2f",
        left_analysis.id,
        right_analysis.id,
        max_shift_sec,
    )
    notes: list[str] = []
    left_signal = _analysis_signal(
        db, left_analysis.id, left_metadata.fps, left_pixel_to_mm_factor
    )
    right_signal = _analysis_signal(
        db, right_analysis.id, right_metadata.fps, right_pixel_to_mm_factor
    )

    analysis_valid = (
        left_signal.size >= 8
        and right_signal.size >= 8
        and float(np.std(left_signal)) > 1e-6
        and float(np.std(right_signal)) > 1e-6
    )

    if analysis_valid:
        shift_sec, confidence, peak, prominence = _match_time_shift(
            left_signal, right_signal, max_shift_sec
        )
        logger.info(
            "Analysis-signal shift candidate: shift=%.4fs confidence=%.3f peak=%.3f prominence=%.3f",
            shift_sec,
            confidence,
            peak,
            prominence,
        )
        if confidence >= AUTO_APPLY_CONFIDENCE_THRESHOLD:
            return (
                MultiViewTimeShiftSuggestion(
                    right_time_shift_sec=shift_sec,
                    confidence=confidence,
                    method="analysis",
                    peak_correlation=peak,
                    prominence=prominence,
                ),
                notes,
            )
        notes.append(
            "Analysis-based sync confidence is low; falling back to video motion signal."
        )
    else:
        notes.append("Analysis signal is insufficient; falling back to video motion signal.")
    logger.info("Using video fallback for time-shift estimation.")

    left_window_left = left_analysis.parameters.get("horizontal_window_x_left")
    left_window_right = left_analysis.parameters.get("horizontal_window_x_right")
    right_window_left = right_analysis.parameters.get("horizontal_window_x_left")
    right_window_right = right_analysis.parameters.get("horizontal_window_x_right")

    left_motion = _motion_energy_signal(
        left_video_path,
        left_metadata.fps,
        left_window_left if isinstance(left_window_left, int) else None,
        left_window_right if isinstance(left_window_right, int) else None,
    )
    right_motion = _motion_energy_signal(
        right_video_path,
        right_metadata.fps,
        right_window_left if isinstance(right_window_left, int) else None,
        right_window_right if isinstance(right_window_right, int) else None,
    )

    if (
        left_motion.size < 8
        or right_motion.size < 8
        or float(np.std(left_motion)) <= 1e-6
        or float(np.std(right_motion)) <= 1e-6
    ):
        notes.append("Video fallback signal is also weak; using zero shift.")
        return (
            MultiViewTimeShiftSuggestion(
                right_time_shift_sec=0.0,
                confidence=0.0,
                method="video_fallback",
                peak_correlation=0.0,
                prominence=0.0,
                warning="Could not derive a reliable time shift.",
            ),
            notes,
        )

    shift_sec, confidence, peak, prominence = _match_time_shift(
        left_motion, right_motion, max_shift_sec
    )
    logger.info(
        "Video-fallback shift candidate: shift=%.4fs confidence=%.3f peak=%.3f prominence=%.3f",
        shift_sec,
        confidence,
        peak,
        prominence,
    )

    warning = None
    if confidence < AUTO_APPLY_CONFIDENCE_THRESHOLD:
        warning = "Low-confidence shift suggestion. Not auto-applied."

    return (
        MultiViewTimeShiftSuggestion(
            right_time_shift_sec=shift_sec,
            confidence=confidence,
            method="video_fallback",
            peak_correlation=peak,
            prominence=prominence,
            warning=warning,
        ),
        notes,
    )


def compute_alignment_suggestion(
    *,
    db: AnalysisDB,
    left_analysis: Analysis,
    right_analysis: Analysis,
    left_metadata: VideoMetadata,
    right_metadata: VideoMetadata,
    left_pixel_to_mm_factor: float,
    right_pixel_to_mm_factor: float,
    left_video_path: Path,
    right_video_path: Path,
    sample_frames: int,
    max_shift_sec: float,
) -> MultiViewAlignmentSuggestion:
    logger.info(
        "Starting combined alignment computation: left=%s right=%s",
        left_analysis.id,
        right_analysis.id,
    )
    window = _compute_window_suggestion(
        db=db,
        left_analysis=left_analysis,
        right_analysis=right_analysis,
        left_metadata=left_metadata,
        right_metadata=right_metadata,
        left_video_path=left_video_path,
        right_video_path=right_video_path,
        left_pixel_to_mm_factor=left_pixel_to_mm_factor,
        right_pixel_to_mm_factor=right_pixel_to_mm_factor,
        sample_frames=sample_frames,
    )
    time_shift, notes = _time_shift_suggestion(
        db=db,
        left_analysis=left_analysis,
        right_analysis=right_analysis,
        left_metadata=left_metadata,
        right_metadata=right_metadata,
        left_pixel_to_mm_factor=left_pixel_to_mm_factor,
        right_pixel_to_mm_factor=right_pixel_to_mm_factor,
        left_video_path=left_video_path,
        right_video_path=right_video_path,
        max_shift_sec=max_shift_sec,
    )
    result = MultiViewAlignmentSuggestion(
        left_analysis_id=left_analysis.id,
        right_analysis_id=right_analysis.id,
        time_shift=time_shift,
        window=window,
        notes=notes,
    )
    logger.info(
        "Completed combined alignment computation: shift=%.4fs method=%s confidence=%.3f",
        result.time_shift.right_time_shift_sec,
        result.time_shift.method,
        result.time_shift.confidence,
    )
    return result
