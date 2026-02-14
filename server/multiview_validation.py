"""Validation logic for multi-view analysis sessions."""

from server.models import Analysis, MultiViewValidationResult, VideoMetadata

MAX_DURATION_DIFF_SECONDS = 3.0
MAX_FRAME_DIFF = 90


def validate_multi_view_pair(
    left_analysis: Analysis,
    right_analysis: Analysis,
    left_video_metadata: VideoMetadata,
    right_video_metadata: VideoMetadata,
) -> MultiViewValidationResult:
    """Validate whether two completed analyses can be used in one multi-view session."""
    errors: list[str] = []
    details: dict[str, int | float | str | None] = {}

    if left_analysis.video_id == right_analysis.video_id:
        errors.append(
            "Please choose analyses from two different videos (different camera angles)."
        )

    if left_analysis.status != "completed" or right_analysis.status != "completed":
        errors.append("Both analyses must be completed before creating a session.")

    left_params = left_analysis.parameters
    right_params = right_analysis.parameters

    left_tracking_points = left_params.get("num_tracking_points")
    right_tracking_points = right_params.get("num_tracking_points")

    if left_tracking_points != right_tracking_points:
        errors.append(
            f"Tracking points must match ({left_tracking_points} vs {right_tracking_points})."
        )

    frame_diff = abs(left_video_metadata.total_frames - right_video_metadata.total_frames)
    duration_diff = abs(left_video_metadata.duration - right_video_metadata.duration)

    if frame_diff > MAX_FRAME_DIFF:
        errors.append(
            f"Frame count difference is too large ({frame_diff} > {MAX_FRAME_DIFF})."
        )

    if duration_diff > MAX_DURATION_DIFF_SECONDS:
        errors.append(
            "Duration difference is too large "
            f"({duration_diff:.2f}s > {MAX_DURATION_DIFF_SECONDS:.2f}s)."
        )

    details["left_frame_count"] = left_video_metadata.total_frames
    details["right_frame_count"] = right_video_metadata.total_frames
    details["frame_count_diff"] = frame_diff
    details["left_duration"] = left_video_metadata.duration
    details["right_duration"] = right_video_metadata.duration
    details["duration_diff"] = duration_diff
    details["num_tracking_points"] = left_tracking_points

    return MultiViewValidationResult(
        compatible=len(errors) == 0,
        errors=errors,
        details=details,
    )
