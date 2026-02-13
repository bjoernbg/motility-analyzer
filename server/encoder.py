"""Video re-encoding utilities using ffmpeg."""

import logging
import subprocess
import time
from contextlib import suppress
from pathlib import Path

logger = logging.getLogger(__name__)


def reencode_video(video_path: Path) -> tuple[Path, dict]:
    """
    Re-encode video using ffmpeg with optimized settings.

    The re-encoded video replaces the original file and is converted to MP4 format.

    Settings:
    - Codec: libx264 (H.264)
    - Preset: slow (better compression)
    - CRF: 24 (quality level)
    - Pixel format: yuv420p (8-bit)
    - Audio: removed (-an)
    - Metadata: stripped (map_metadata -1, map_chapters -1)
    - Container: MP4 with faststart flag

    Args:
        video_path: Path to original video file

    Returns:
        Tuple of (path to re-encoded video, statistics dict)

    Raises:
        RuntimeError: If ffmpeg encoding fails
        FileNotFoundError: If input video doesn't exist
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Capture original file size
    original_size = video_path.stat().st_size

    # Create temporary output path (same directory, .tmp extension)
    temp_output = video_path.parent / f"{video_path.stem}_reencoding.tmp.mp4"

    # Final output path (always .mp4)
    final_output = video_path.parent / f"{video_path.stem}.mp4"

    try:
        logger.info(f"Starting re-encode of {video_path.name}")

        # Start timing
        start_time = time.time()

        # Build ffmpeg command exactly as specified
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(video_path),
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-crf",
            "24",
            "-preset",
            "slow",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-metadata",
            "encoder=",
            "-movflags",
            "+faststart",
            str(temp_output),
        ]

        logger.info(f"Executing ffmpeg command: {' '.join(cmd)}")

        # Execute encoding (blocking)
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            logger.error(f"FFmpeg failed with return code {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")
            raise RuntimeError(f"FFmpeg encoding failed: {result.stderr}")

        logger.info(f"Re-encoding completed: {temp_output.name}")

        # End timing
        end_time = time.time()
        duration_seconds = end_time - start_time

        # Get new file size
        new_size = temp_output.stat().st_size

        # Calculate statistics
        size_reduction_percent = (
            ((original_size - new_size) / original_size * 100)
            if original_size > 0
            else 0.0
        )

        statistics = {
            "duration_seconds": round(duration_seconds, 2),
            "original_size_bytes": original_size,
            "new_size_bytes": new_size,
            "size_reduction_percent": round(size_reduction_percent, 2),
        }

        # If original and final output are different files, delete original
        if video_path != final_output:
            logger.info(f"Removing original file: {video_path.name}")
            video_path.unlink()

        # Rename temp to final output
        logger.info(f"Renaming {temp_output.name} to {final_output.name}")
        temp_output.rename(final_output)

        logger.info(f"Successfully re-encoded video to {final_output.name}")
        logger.info(f"Statistics: {statistics}")

        return final_output, statistics

    except Exception as e:
        # Clean up temp file if it exists
        if temp_output.exists():
            logger.warning(f"Cleaning up temporary file: {temp_output.name}")
            with suppress(Exception):
                temp_output.unlink()

        # Re-raise the error
        error_msg = f"Failed to re-encode video: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
