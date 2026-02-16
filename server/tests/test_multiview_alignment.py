from __future__ import annotations

from pathlib import Path
import re

import numpy as np
from fastapi.testclient import TestClient

from server import main
from server.models import (
    Analysis,
    MultiViewAlignmentState,
    MultiViewSessionMetadata,
    MultiViewValidationResult,
    Video,
    VideoMetadata,
)
from server.multiview_alignment import (
    TARGET_SIGNAL_HZ,
    _match_time_shift,
    _time_shift_suggestion,
    _compute_window_suggestion,
)


def _video_metadata(*, total_frames: int = 200, fps: float = 20.0, width: int = 200) -> VideoMetadata:
    return VideoMetadata(
        total_frames=total_frames,
        fps=fps,
        frame_multiplier=1.0,
        width=width,
        height=100,
        display_aspect_ratio=None,
        duration=total_frames / fps,
        file_size=1,
        codec="h264",
    )


def test_match_time_shift_recovers_known_positive_lag() -> None:
    rng = np.random.default_rng(7)
    left = rng.normal(0.0, 1.0, size=800)
    left = np.convolve(left, np.ones(7) / 7, mode="same")

    true_shift_samples = 9
    right = np.concatenate([np.zeros(true_shift_samples), left[:-true_shift_samples]])

    shift_sec, confidence, _peak, _prominence = _match_time_shift(
        left, right, max_shift_sec=2.0
    )

    estimated_samples = int(round(shift_sec * TARGET_SIGNAL_HZ))
    assert estimated_samples == true_shift_samples
    assert confidence > 0.5


def test_time_shift_suggestion_falls_back_to_video_signal(monkeypatch) -> None:
    class EmptyDb:
        def build_heatmap_matrix(self, _analysis_id: str):
            return np.array([], dtype=np.float32).reshape(0, 0), 0.0, 0.0

    left_motion = np.linspace(0.0, 1.0, 200)
    right_motion = np.concatenate([np.zeros(6), left_motion[:-6]])

    def fake_motion_signal(
        _video_path: Path,
        _fps: float,
        _x_left: int | None,
        _x_right: int | None,
    ) -> np.ndarray:
        if "left" in str(_video_path):
            return left_motion
        return right_motion

    monkeypatch.setattr(main, "AUTO_APPLY_CONFIDENCE_THRESHOLD", 0.35, raising=False)
    monkeypatch.setattr(
        "server.multiview_alignment._motion_energy_signal",
        fake_motion_signal,
    )

    left_analysis = Analysis(
        id="left-a",
        video_id="left-v",
        parameters={"horizontal_window_x_left": 10, "horizontal_window_x_right": 180},
        status="completed",
    )
    right_analysis = Analysis(
        id="right-a",
        video_id="right-v",
        parameters={"horizontal_window_x_left": 10, "horizontal_window_x_right": 180},
        status="completed",
    )

    suggestion, notes = _time_shift_suggestion(
        db=EmptyDb(),
        left_analysis=left_analysis,
        right_analysis=right_analysis,
        left_metadata=_video_metadata(),
        right_metadata=_video_metadata(),
        left_pixel_to_mm_factor=11.0,
        right_pixel_to_mm_factor=11.0,
        left_video_path=Path("left.mp4"),
        right_video_path=Path("right.mp4"),
        max_shift_sec=2.0,
    )

    assert suggestion.method == "video_fallback"
    assert len(notes) >= 1


def test_window_suggestion_matches_known_right_margin_delta() -> None:
    class DbWithFrames:
        def __init__(self):
            from server.models import FrameData

            left_pc = [[40, 50], [160, 50]]
            right_pc = [[50, 50], [170, 50]]
            self.left = FrameData(f=0, pt=[], pb=[], pc=left_pc, colored_regions=[], mpp=None)
            self.right = FrameData(f=0, pt=[], pb=[], pc=right_pc, colored_regions=[], mpp=None)

        def get_frame(self, analysis_id: str, _frame_number: int):
            if analysis_id == "left-a":
                return self.left
            if analysis_id == "right-a":
                return self.right
            return None

    left_analysis = Analysis(
        id="left-a",
        video_id="left-v",
        parameters={"horizontal_window_x_left": 20, "horizontal_window_x_right": 180},
        status="completed",
    )
    right_analysis = Analysis(
        id="right-a",
        video_id="right-v",
        parameters={"horizontal_window_x_left": 30, "horizontal_window_x_right": 190},
        status="completed",
    )

    from server import multiview_alignment

    original_detect = multiview_alignment._detect_tube_anchor_x
    multiview_alignment._detect_tube_anchor_x = (
        lambda video_path, _frames: 190 if "left" in str(video_path) else 180
    )
    try:
        window = _compute_window_suggestion(
            db=DbWithFrames(),
            left_analysis=left_analysis,
            right_analysis=right_analysis,
            left_metadata=_video_metadata(width=200),
            right_metadata=_video_metadata(width=200),
            left_video_path=Path("left.mp4"),
            right_video_path=Path("right.mp4"),
            left_pixel_to_mm_factor=10.0,
            right_pixel_to_mm_factor=10.0,
            sample_frames=7,
        )
    finally:
        multiview_alignment._detect_tube_anchor_x = original_detect

    assert round(window.right_margin_delta_px, 1) == 20.0
    assert window.left_window_delta_px == 10
    assert window.right_window_delta_px == -10
    assert window.left_suggested_x_left == 30
    assert window.right_suggested_x_left == 20


def test_metadata_round_trip_supports_legacy_and_new_shapes() -> None:
    legacy = MultiViewSessionMetadata(
        validated=True,
        frame_count_diff=5,
        duration_diff=0.4,
    )
    dumped_legacy = legacy.model_dump()
    loaded_legacy = MultiViewSessionMetadata(**dumped_legacy)
    assert loaded_legacy.alignment is None

    enriched = MultiViewSessionMetadata(
        validated=True,
        frame_count_diff=0,
        duration_diff=0.0,
        alignment=MultiViewAlignmentState(right_time_shift_sec=0.25, source="manual"),
    )
    dumped_enriched = enriched.model_dump()
    loaded_enriched = MultiViewSessionMetadata(**dumped_enriched)
    assert loaded_enriched.alignment is not None
    assert loaded_enriched.alignment.right_time_shift_sec == 0.25


def test_put_sources_rejects_incomplete_analyses(monkeypatch) -> None:
    client = TestClient(main.app)

    session_row = {
        "id": "s1",
        "name": "session",
        "left_analysis_id": "old-left",
        "right_analysis_id": "old-right",
        "created_at": "2026-01-01T00:00:00",
        "metadata": {
            "validated": True,
            "frame_count_diff": 0,
            "duration_diff": 0.0,
        },
    }

    left_analysis = Analysis(
        id="left-a",
        video_id="left-v",
        parameters={"num_tracking_points": 30},
        status="processing",
    )
    right_analysis = Analysis(
        id="right-a",
        video_id="right-v",
        parameters={"num_tracking_points": 30},
        status="completed",
    )

    def fake_get_analysis(_self, analysis_id: str):
        if analysis_id == "left-a":
            return left_analysis
        if analysis_id == "right-a":
            return right_analysis
        return None

    monkeypatch.setattr(main.multi_view_session_db, "get_session", lambda _id: session_row)
    monkeypatch.setattr(main.AnalysisStorage, "get_analysis", fake_get_analysis)
    monkeypatch.setattr(main.VideoStorage, "get_video", lambda _self, _id: Video(
        id=_id,
        filename=f"{_id}.mp4",
        file_path=f"/tmp/{_id}.mp4",
    ))
    monkeypatch.setattr(main, "get_video_metadata", lambda _path: _video_metadata())
    monkeypatch.setattr(
        main,
        "validate_multi_view_pair",
        lambda *args, **kwargs: MultiViewValidationResult(compatible=True, errors=[], details={}),
    )

    response = client.put(
        "/api/multi-view/sessions/s1/sources",
        json={"left_analysis_id": "left-a", "right_analysis_id": "right-a"},
    )
    assert response.status_code == 400
    assert "Both analyses must be completed" in response.text


def test_auto_reanalyze_assigns_timestamped_display_names(monkeypatch) -> None:
    client = TestClient(main.app)

    session_row = {
        "id": "s1",
        "name": "session",
        "left_analysis_id": "old-left",
        "right_analysis_id": "old-right",
        "created_at": "2026-01-01T00:00:00",
        "metadata": {
            "validated": True,
            "frame_count_diff": 0,
            "duration_diff": 0.0,
        },
    }

    left_analysis = Analysis(
        id="old-left",
        video_id="left-v",
        parameters={"horizontal_window_x_left": 20, "horizontal_window_x_right": 180},
        status="completed",
    )
    right_analysis = Analysis(
        id="old-right",
        video_id="right-v",
        parameters={"horizontal_window_x_left": 30, "horizontal_window_x_right": 190},
        status="completed",
    )

    created_names: list[str] = []

    def fake_get_analysis(_self, analysis_id: str):
        if analysis_id == "old-left":
            return left_analysis
        if analysis_id == "old-right":
            return right_analysis
        return None

    def fake_start_background(
        video_id: str, parameters_dict: dict, display_name: str | None = None
    ) -> Analysis:
        created_names.append(display_name or "")
        suffix = "left" if video_id == "left-v" else "right"
        return Analysis(
            id=f"new-{suffix}",
            video_id=video_id,
            display_name=display_name,
            parameters=parameters_dict,
            status="processing",
        )

    monkeypatch.setattr(main.multi_view_session_db, "get_session", lambda _id: session_row)
    monkeypatch.setattr(main.AnalysisStorage, "get_analysis", fake_get_analysis)
    monkeypatch.setattr(main, "_start_background_analysis_for_video", fake_start_background)
    monkeypatch.setattr(main, "_persist_session_metadata", lambda *_args, **_kwargs: None)

    response = client.post(
        "/api/multi-view/sessions/s1/alignment/auto-reanalyze",
        json={"use_latest_suggestion": False},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["left_analysis_id"] == "new-left"
    assert payload["right_analysis_id"] == "new-right"

    assert len(created_names) == 2
    assert re.match(r"^AutoAlign L · \d{2}:\d{2}$", created_names[0]) is not None
    assert re.match(r"^AutoAlign R · \d{2}:\d{2}$", created_names[1]) is not None
