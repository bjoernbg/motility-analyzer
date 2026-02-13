"""Horizontal window detection for finding left and right boundaries."""

import cv2
import numpy as np


def horizontal_window_detection(*, frame: np.ndarray, y: int | None = None):
    """Detect two x coordinates at a specified y coordinate (or vertical middle).

    Constrains detection so that the first x coordinate is within the first 20%
    of the frame width and the second x coordinate is within the last 20%.

    Similar to starting_point_detection but works on the horizontal center line
    instead of the vertical center line.

    Args:
        frame: Input image as BGR or grayscale ndarray.
        y: Y coordinate to use for detection. If None, uses the vertical middle.

    Returns:
        Tuple of (x_left, x_right, y_mid) where:
        - x_left: Left x-coordinate of detected feature (within first 20% of width)
        - x_right: Right x-coordinate of detected feature (within last 20% of width)
        - y_mid: Y-coordinate used for detection
    """
    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = frame.copy()

    ksize = -1  # 3 for Sobel, -1 for Scharr
    gX = cv2.Sobel(img_gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=ksize)
    gY = cv2.Sobel(img_gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=ksize)

    # normalize the magnitude to 0-1
    mag = cv2.magnitude(gX, gY)
    mag = cv2.normalize(mag, None, 0.0, 1.0, cv2.NORM_MINMAX)

    # get the center line (horizontal)
    h, w = mag.shape
    y_mid = y if y is not None else h // 2
    center_line = mag[y_mid, :].copy()  # shape (w,)

    # Define search regions: first 20% and last 20%
    border = 10
    left_region_end = int(0.2 * w)
    right_region_start = int(0.8 * w)

    # Search for left peak in first 20%
    left_start = border
    left_end = min(left_region_end, w - border)
    if left_end <= left_start:
        x_left = -1
    else:
        left_sig = center_line[left_start:left_end]
        if len(left_sig) == 0:
            x_left = -1
        else:
            left_peak_idx = np.argmax(left_sig)
            x_left = int(left_start + left_peak_idx)

    # Search for right peak in last 20%
    right_start = max(right_region_start, border)
    right_end = w - border
    if right_end <= right_start:
        x_right = -1
    else:
        right_sig = center_line[right_start:right_end]
        if len(right_sig) == 0:
            x_right = -1
        else:
            right_peak_idx = np.argmax(right_sig)
            x_right = int(right_start + right_peak_idx)

    return int(x_left), int(x_right), int(y_mid)
