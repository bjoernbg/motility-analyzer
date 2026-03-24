"""Helpers for loading and saving per-video display settings."""

from __future__ import annotations

import json
from pathlib import Path

from .config import PIXEL_TO_MM_FACTOR
from .models import DisplaySettings


def load_video_display_settings(video_path: Path) -> DisplaySettings:
    """Load display settings from the per-video JSON file."""
    settings_path = video_path.with_suffix(".json")
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                all_data = json.load(f)
                if "display_settings" in all_data:
                    return DisplaySettings(**all_data["display_settings"])
        except (json.JSONDecodeError, IOError, ValueError):
            pass

    return DisplaySettings(
        pixel_to_mm_factor=PIXEL_TO_MM_FACTOR,
        heatmap_min_mm=3.0,
        heatmap_max_mm=30.0,
    )


def save_video_display_settings(video_path: Path, settings: DisplaySettings) -> None:
    """Save display settings to the per-video JSON file while preserving other keys."""
    settings_path = video_path.with_suffix(".json")
    existing_data: dict[str, object] = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                existing_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing_data = {}

    existing_data["display_settings"] = settings.model_dump()
    with open(settings_path, "w") as f:
        json.dump(existing_data, f, indent=2, default=str)
