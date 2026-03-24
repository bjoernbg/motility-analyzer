from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from server.contraction_detection import (
    CONTRACTION_DETECTION_VERSION_V2,
    detect_contractions,
)
from server.database import AnalysisDB
from server.models import ContractionDetectionParameters


def _baseline_heatmap(height: int = 24, width: int = 64, baseline: float = 10.0) -> np.ndarray:
    return np.full((height, width), baseline, dtype=np.float32)


def _draw_segment(
    heatmap: np.ndarray,
    *,
    start_t: int,
    end_t: int,
    start_y: int,
    slope: float,
    value: float,
    thickness: int = 1,
) -> None:
    for frame_index in range(start_t, end_t + 1):
        center_y = int(round(start_y + ((frame_index - start_t) * slope)))
        for offset in range(thickness):
            y_index = center_y + offset
            if 0 <= y_index < heatmap.shape[0]:
                heatmap[y_index, frame_index] = value


def test_merges_seed_fragments_from_same_wave() -> None:
    heatmap = _baseline_heatmap()
    _draw_segment(heatmap, start_t=10, end_t=18, start_y=4, slope=0.5, value=1.5, thickness=2)
    _draw_segment(heatmap, start_t=20, end_t=28, start_y=9, slope=0.5, value=1.5, thickness=2)

    events, _, _ = detect_contractions(
        heatmap,
        dt=1.0,
        dy=1.0,
        thr=-6.0,
        smooth_sigma=(0.0, 0.0),
        min_pixels=4,
        min_duration_s=0.0,
        min_span_mm=0.0,
        merge_max_gap_s=2.0,
        merge_max_offset_mm=2.5,
        merge_max_velocity_delta_mm_s=0.75,
        pixel_to_mm_factor=1.0,
        open_iters=0,
        close_iters=0,
    )

    assert len(events) == 1
    assert events[0]["t_range_frames"] == (10, 28)


def test_keeps_distinct_waves_separate_when_offset_is_too_large() -> None:
    heatmap = _baseline_heatmap()
    _draw_segment(heatmap, start_t=10, end_t=18, start_y=4, slope=0.5, value=1.5, thickness=2)
    _draw_segment(heatmap, start_t=20, end_t=28, start_y=16, slope=0.5, value=1.5, thickness=2)

    events, _, _ = detect_contractions(
        heatmap,
        dt=1.0,
        dy=1.0,
        thr=-6.0,
        smooth_sigma=(0.0, 0.0),
        min_pixels=4,
        min_duration_s=0.0,
        min_span_mm=0.0,
        merge_max_gap_s=2.0,
        merge_max_offset_mm=2.5,
        merge_max_velocity_delta_mm_s=0.75,
        pixel_to_mm_factor=1.0,
        open_iters=0,
        close_iters=0,
    )

    assert len(events) == 2


def test_filters_small_events_after_merging() -> None:
    heatmap = _baseline_heatmap()
    _draw_segment(heatmap, start_t=8, end_t=10, start_y=6, slope=0.0, value=1.0, thickness=2)

    events, _, _ = detect_contractions(
        heatmap,
        dt=1.0,
        dy=1.0,
        thr=-6.0,
        smooth_sigma=(0.0, 0.0),
        min_pixels=3,
        min_duration_s=4.0,
        min_span_mm=5.0,
        pixel_to_mm_factor=1.0,
        open_iters=0,
        close_iters=0,
    )

    assert events == []


def test_connected_area_uses_thresholded_region_beyond_seed_mask() -> None:
    heatmap = _baseline_heatmap(height=20, width=30)
    heatmap[8:12, 10:14] = 6.0
    _draw_segment(heatmap, start_t=10, end_t=12, start_y=9, slope=1.0, value=1.0, thickness=1)

    events, _, _ = detect_contractions(
        heatmap,
        dt=1.0,
        dy=1.0,
        thr=-8.5,
        smooth_sigma=(0.0, 0.0),
        min_pixels=3,
        min_duration_s=0.0,
        min_span_mm=0.0,
        area_threshold_median_fraction=0.7,
        pixel_to_mm_factor=1.0,
        open_iters=0,
        close_iters=0,
    )

    assert len(events) == 1
    assert events[0]["area_exact"] > 3.0


def test_contraction_detection_metadata_round_trips_and_supports_empty_runs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "analyses.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE analyses (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                display_name TEXT,
                parameters TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0.0,
                global_data TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                error_message TEXT
            );
            CREATE TABLE contraction_events (
                id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL,
                event_label INTEGER NOT NULL,
                n_pixels INTEGER NOT NULL,
                threshold_used REAL NOT NULL,
                t_range_start INTEGER NOT NULL,
                t_range_end INTEGER NOT NULL,
                y_range_start INTEGER NOT NULL,
                y_range_end INTEGER NOT NULL,
                duration_s REAL NOT NULL,
                height_phys REAL NOT NULL,
                velocity_phys_per_s REAL NOT NULL,
                line_fit_a REAL NOT NULL,
                line_fit_b REAL NOT NULL,
                area_exact REAL NOT NULL,
                area_triangle REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
            );
            CREATE TABLE contraction_detection_runs (
                analysis_id TEXT PRIMARY KEY,
                parameters_json TEXT NOT NULL,
                detection_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
            );
        """
        )
        conn.execute(
            """
            INSERT INTO analyses (id, video_id, parameters, status, progress, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            ("analysis-1", "video-1", "{}", "completed", 100.0, "2026-03-16T12:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    db = AnalysisDB(db_path=str(db_path))
    parameters = ContractionDetectionParameters()

    db.save_contraction_events(
        "analysis-1",
        [],
        parameters_used=parameters,
        detection_version=CONTRACTION_DETECTION_VERSION_V2,
    )

    run = db.get_contraction_detection_run("analysis-1")
    assert run is not None
    assert run["detection_version"] == CONTRACTION_DETECTION_VERSION_V2
    assert run["parameters_used"].min_duration_s == 4.0
    assert db.contraction_events_exist("analysis-1") is True
    assert db.get_contraction_events("analysis-1") == []


def test_v2_parameter_defaults_match_contract() -> None:
    parameters = ContractionDetectionParameters()

    assert parameters.min_duration_s == 4.0
    assert parameters.min_span_mm == 5.0
    assert parameters.area_threshold_median_fraction == 0.7
    assert parameters.merge_max_gap_s == 1.0
    assert parameters.merge_max_offset_mm == 5.0
    assert parameters.merge_max_velocity_delta_mm_s == 1.0
