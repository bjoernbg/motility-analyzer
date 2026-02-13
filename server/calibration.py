"""Tube-based calibration: measure tube width in pixels to compute pixel-to-mm factor."""

import numpy as np

from .edge_detection_silhouette import detect_mask_edges_at_x, make_object_mask


def calibrate_tube_width(
    frame: np.ndarray,
    tube_known_width_mm: float = 11.0,
) -> dict:
    """Measure the tube at the right edge of the frame and compute pixel_to_mm_factor.

    The tube is expected to be a bright object at the rightmost ~10 px columns
    of the frame with clear parallel edges.

    Args:
        frame: BGR or grayscale image (numpy array).
        tube_known_width_mm: Known physical width of the tube in mm.

    Returns:
        Dict with keys: pixel_to_mm_factor, tube_width_px,
        x_start, x_end, y_top, y_bottom.

    Raises:
        ValueError: If tube edges cannot be detected.
    """
    # Convert to grayscale
    if frame.ndim == 3:
        import cv2
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = frame

    H, W = img_gray.shape

    # Create mask of the full frame
    mask, _ = make_object_mask(img_gray)

    # Sample the rightmost columns (W-15 to W-5) to avoid edge artifacts
    x_start = max(0, W - 15)
    x_end = max(x_start + 1, W - 5)

    distances = []
    y_tops = []
    y_bottoms = []

    for x in range(x_start, x_end):
        y_top, y_bottom = detect_mask_edges_at_x(mask=mask, x=x)
        if y_top is not None and y_bottom is not None:
            dist = y_bottom - y_top
            if dist > 0:
                distances.append(dist)
                y_tops.append(y_top)
                y_bottoms.append(y_bottom)

    if not distances:
        raise ValueError(
            "Could not detect tube edges in the rightmost columns of the frame."
        )

    tube_width_px = float(np.median(distances))
    y_top_median = float(np.median(y_tops))
    y_bottom_median = float(np.median(y_bottoms))
    pixel_to_mm_factor = tube_width_px / tube_known_width_mm

    return {
        "pixel_to_mm_factor": round(pixel_to_mm_factor, 3),
        "tube_width_px": round(tube_width_px, 1),
        "x_start": x_start,
        "x_end": x_end,
        "y_top": round(y_top_median, 1),
        "y_bottom": round(y_bottom_median, 1),
    }
