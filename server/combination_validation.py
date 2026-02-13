"""Validation logic for combining analyses."""
from server.models import Analysis, CompatibilityCheckResult, VideoMetadata


def validate_compatibility(
    analysis1: Analysis,
    analysis2: Analysis,
    video1_metadata: VideoMetadata,
    video2_metadata: VideoMetadata
) -> CompatibilityCheckResult:
    """Validate if two analyses can be combined.

    Compatibility Rules:
    - REQUIRED (errors if violated):
      1. Different video_id (no self-combination)
      2. Same num_tracking_points
      3. Same distribution_method
      4. Both analyses completed successfully

    - WARNINGS (allowed but warn user):
      1. Frame count difference >100 frames
      2. Duration difference >4 seconds

    Args:
        analysis1: First analysis to combine
        analysis2: Second analysis to combine
        video1_metadata: Metadata for first video
        video2_metadata: Metadata for second video

    Returns:
        CompatibilityCheckResult with validation outcome
    """
    errors = []
    warnings = []
    details = {}

    # Required checks - errors prevent combination
    if analysis1.video_id == analysis2.video_id:
        errors.append("Cannot combine analyses from the same video. Please select a different analysis.")

    if analysis1.status != 'completed' or analysis2.status != 'completed':
        incomplete = []
        if analysis1.status != 'completed':
            incomplete.append("Analysis 1")
        if analysis2.status != 'completed':
            incomplete.append("Analysis 2")
        errors.append(f"Both analyses must be completed before combining. {', '.join(incomplete)} is {analysis1.status if analysis1.status != 'completed' else analysis2.status}.")

    # Extract parameters
    params1 = analysis1.parameters
    params2 = analysis2.parameters

    num_tracking_points1 = params1.get('num_tracking_points')
    num_tracking_points2 = params2.get('num_tracking_points')

    if num_tracking_points1 != num_tracking_points2:
        errors.append(
            f"Incompatible: Analysis 1 uses {num_tracking_points1} tracking points, "
            f"Analysis 2 uses {num_tracking_points2}. Both analyses must use the same number of tracking points."
        )

    dist_method1 = params1.get('distribution_method')
    dist_method2 = params2.get('distribution_method')

    if dist_method1 != dist_method2:
        errors.append(
            f"Incompatible: Analysis 1 uses '{dist_method1}' distribution method, "
            f"Analysis 2 uses '{dist_method2}'. Both must use the same distribution method."
        )

    # Warning checks - don't prevent combination
    frame_diff = abs(video1_metadata.total_frames - video2_metadata.total_frames)
    duration_diff = abs(video1_metadata.duration - video2_metadata.duration)

    details['frame_count_1'] = video1_metadata.total_frames
    details['frame_count_2'] = video2_metadata.total_frames
    details['frame_count_diff'] = frame_diff
    details['duration_1'] = video1_metadata.duration
    details['duration_2'] = video2_metadata.duration
    details['duration_diff'] = duration_diff
    details['num_tracking_points'] = num_tracking_points1
    details['distribution_method'] = dist_method1

    if frame_diff > 100:
        warnings.append(
            f"Videos have different lengths ({video1_metadata.total_frames} vs {video2_metadata.total_frames} frames, "
            f"difference: {frame_diff} frames). Playback will be limited to the shorter video."
        )

    if duration_diff > 4.0:
        warnings.append(
            f"Videos have different durations ({video1_metadata.duration:.2f}s vs {video2_metadata.duration:.2f}s, "
            f"difference: {duration_diff:.2f}s). This may indicate different frame rates or capture times."
        )

    return CompatibilityCheckResult(
        compatible=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        details=details
    )
