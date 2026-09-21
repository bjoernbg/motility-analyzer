"""Regression tests for the frozen-build path and ffmpeg resolution rules.

Both failures these cover are silent on a developer machine: user data written
inside a PyInstaller bundle disappears when the process exits, and a Git LFS
pointer file is named exactly like the binary it stands in for.
"""

from __future__ import annotations

import sys

import pytest

from server import ffmpeg_tools, paths


@pytest.fixture(autouse=True)
def _clear_resolver_cache():
    ffmpeg_tools._resolve.cache_clear()
    yield
    ffmpeg_tools._resolve.cache_clear()


def test_source_checkout_keeps_data_beside_the_package(monkeypatch):
    monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert paths.data_dir() == paths._SOURCE_DIR
    assert paths.resource_dir() == paths._SOURCE_DIR


def test_frozen_data_dir_is_outside_the_bundle(monkeypatch, tmp_path):
    """The bundle directory is deleted on exit, so nothing writable may live there."""
    monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)

    data = paths.data_dir()
    resource = paths.resource_dir()

    assert resource == tmp_path / "bundle"
    assert not data.is_relative_to(resource)
    assert data.name == paths.APP_NAME


def test_data_dir_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path / "elsewhere"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert paths.data_dir() == (tmp_path / "elsewhere").resolve()


def _write_fake_binary(root, platform_dir: str, name: str, size: int):
    binary = root / platform_dir / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"\0" * size)
    binary.chmod(0o755)
    return binary


def test_lfs_pointer_is_not_mistaken_for_a_binary(monkeypatch, tmp_path):
    """A 130-byte pointer file is named ffmpeg.exe and would otherwise be bundled."""
    monkeypatch.setattr(ffmpeg_tools, "FFMPEG_BIN_DIR", tmp_path)
    monkeypatch.setattr(ffmpeg_tools, "_platform_dir", lambda: "windows")
    monkeypatch.setattr(sys, "platform", "win32")
    _write_fake_binary(tmp_path, "windows", "ffmpeg.exe", 130)
    monkeypatch.setattr(ffmpeg_tools.shutil, "which", lambda _tool: None)

    assert ffmpeg_tools._bundled_path("ffmpeg") is None
    with pytest.raises(ffmpeg_tools.FFmpegNotFoundError):
        ffmpeg_tools.ffmpeg_executable()


def test_bundled_binary_wins_over_path(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_tools, "FFMPEG_BIN_DIR", tmp_path)
    monkeypatch.setattr(ffmpeg_tools, "_platform_dir", lambda: "linux")
    monkeypatch.setattr(sys, "platform", "linux")
    binary = _write_fake_binary(tmp_path, "linux", "ffmpeg", 2 * 1024 * 1024)
    monkeypatch.setattr(ffmpeg_tools.shutil, "which", lambda _tool: "/usr/bin/ffmpeg")

    assert ffmpeg_tools.ffmpeg_executable() == str(binary)


def test_falls_back_to_path_without_a_bundled_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_tools, "FFMPEG_BIN_DIR", tmp_path)
    monkeypatch.setattr(ffmpeg_tools.shutil, "which", lambda _tool: "/usr/bin/ffprobe")

    assert ffmpeg_tools.ffprobe_executable() == "/usr/bin/ffprobe"


def test_readable_error_when_nothing_is_available(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_tools, "FFMPEG_BIN_DIR", tmp_path)
    monkeypatch.setattr(ffmpeg_tools.shutil, "which", lambda _tool: None)

    with pytest.raises(
        ffmpeg_tools.FFmpegNotFoundError, match="ffprobe is not available"
    ):
        ffmpeg_tools.ffprobe_executable()
