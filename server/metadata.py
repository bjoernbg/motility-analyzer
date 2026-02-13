"""Video metadata detection and management."""

import json
import logging
from contextlib import suppress
from pathlib import Path

import cv2  # type: ignore[import-untyped]
from ffmpeg import FFmpeg

from .models import VideoMetadata

logger = logging.getLogger(__name__)


def load_metadata_from_json(video_path: Path) -> VideoMetadata | None:
    """Load video metadata from JSON file if it exists.

    Args:
        video_path: Path to the video file

    Returns:
        VideoMetadata if found, None otherwise
    """
    settings_path = video_path.with_suffix(".json")
    if not settings_path.exists():
        return None

    try:
        with open(settings_path, "r") as f:
            settings_data = json.load(f)
            if "metadata" in settings_data:
                metadata_dict = settings_data["metadata"]
                # Validate that we have the required fields
                required_fields = [
                    "total_frames",
                    "fps",
                    "width",
                    "height",
                    "duration",
                    "file_size",
                ]
                if all(field in metadata_dict for field in required_fields):
                    return VideoMetadata(**metadata_dict)
    except (json.JSONDecodeError, IOError, KeyError, ValueError) as e:
        logger.warning(f"Failed to load metadata from {settings_path}: {e}")

    return None


def save_metadata_to_json(video_path: Path, metadata: VideoMetadata) -> None:
    """Save video metadata to JSON file next to video file.

    Args:
        video_path: Path to the video file
        metadata: VideoMetadata to save
    """
    settings_path = video_path.with_suffix(".json")
    try:
        # Load existing settings if they exist
        existing_data = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r") as f:
                    existing_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                # If file is corrupted, start fresh
                existing_data = {}

        # Update metadata in the settings file
        existing_data["metadata"] = metadata.model_dump()

        # Write back to file
        with open(settings_path, "w") as f:
            json.dump(existing_data, f, indent=2, default=str)

        logger.info(f"Saved metadata to {settings_path}")
    except IOError as e:
        logger.warning(f"Failed to save metadata to {settings_path}: {e}")


def generate_metadata_from_video(video_path: Path) -> VideoMetadata:
    """Generate video metadata by analyzing the video file.

    This function uses ffprobe to get duration and OpenCV to analyze frames
    for accurate FPS calculation and other properties.

    Args:
        video_path: Path to the video file

    Returns:
        VideoMetadata with all properties

    Raises:
        ValueError: If video file cannot be opened or analyzed
    """
    # Open video with OpenCV
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Failed to open video file: {video_path}")

    try:
        # CAP_PROP_FRAME_COUNT and CAP_PROP_FPS are unreliable, so we use ffprobe
        ffprobe = FFmpeg(executable="ffprobe").input(
            video_path, print_format="json", show_streams=None
        )
        media = json.loads(ffprobe.execute())
        video_stream = media["streams"][0]
        duration = float(video_stream["duration"])

        # Extract display aspect ratio (e.g., "16:9" -> 16/9 = 1.778)
        display_aspect_ratio: float | None = None
        if "display_aspect_ratio" in video_stream:
            dar_str = video_stream["display_aspect_ratio"]
            if ":" in dar_str:
                w, h = dar_str.split(":")
                with suppress(ValueError, ZeroDivisionError):
                    display_aspect_ratio = float(w) / float(h)

        # Calculate FPS by reading frames and measuring time deltas
        prev_t = None
        deltas = []

        for _ in range(500):  # Check first ~500 frames
            ret, frame = cap.read()
            if not ret:
                break

            t = cap.get(cv2.CAP_PROP_POS_MSEC)  # time in ms
            if prev_t is not None:
                deltas.append(t - prev_t)
            prev_t = t

        if not deltas:
            raise ValueError(f"Could not calculate FPS from video: {video_path}")

        avg_dt = sum(deltas) / len(deltas)
        fps = round(1000.0 / avg_dt, 0)

        # Get video properties from OpenCV (needed for frame_multiplier before seeking)
        metadata_fps = cap.get(cv2.CAP_PROP_FPS)
        frame_multiplier = metadata_fps / fps if fps > 0 else 1.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        codec_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))

        # Calculate estimated total frames
        estimated_total = int(duration * fps)

        # Seek near estimated end and find actual last frame
        # Seek to approximately 100 frames before estimated end (or 95% through video)
        seek_to = max(0, estimated_total - 100)
        # OpenCV uses container frame numbering (based on metadata_fps), so multiply by frame_multiplier
        cap.set(cv2.CAP_PROP_POS_FRAMES, seek_to * frame_multiplier)

        # Get actual frame position after seeking (may differ due to keyframe seeking)
        # Convert back from container frame numbering to actual frame numbering
        container_frame_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
        actual_frame = (
            int(container_frame_pos / frame_multiplier)
            if frame_multiplier > 0
            else int(container_frame_pos)
        )

        # Read frames sequentially until we reach the end
        while True:
            ret, _ = cap.read()
            if not ret:
                break
            actual_frame += 1

        total_frames = actual_frame

        # Convert fourcc code to string
        codec = "".join([chr((codec_fourcc >> 8 * i) & 0xFF) for i in range(4)])

        # Get file size
        file_size = video_path.stat().st_size

        metadata = VideoMetadata(
            total_frames=total_frames,
            fps=fps,
            frame_multiplier=frame_multiplier,
            width=width,
            height=height,
            display_aspect_ratio=display_aspect_ratio,
            duration=duration,
            file_size=file_size,
            codec=codec if codec.strip() else None,
        )

        return metadata
    finally:
        cap.release()


def get_video_metadata(
    video_path: Path, force_regenerate: bool = False
) -> VideoMetadata:
    """Get video metadata, loading from cache if available, or generating if needed.

    This function automatically checks for pre-saved metadata JSON and uses it when available.
    If not found or force_regenerate is True, it generates new metadata and saves it.

    Args:
        video_path: Path to the video file
        force_regenerate: If True, regenerate metadata even if cached version exists

    Returns:
        VideoMetadata with all properties

    Raises:
        ValueError: If video file cannot be found, opened, or analyzed
    """
    if not video_path.exists():
        raise ValueError(f"Video file not found: {video_path}")

    # Try to load from cache first (unless forcing regeneration)
    if not force_regenerate:
        cached_metadata = load_metadata_from_json(video_path)
        if cached_metadata is not None:
            logger.info(f"Loaded cached metadata for {video_path.name}")
            return cached_metadata

    # Generate new metadata
    logger.info(f"Generating metadata for {video_path.name}")
    metadata = generate_metadata_from_video(video_path)

    # Save to cache for future use
    save_metadata_to_json(video_path, metadata)

    return metadata
