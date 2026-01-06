"""Hybrid edge detection method using sparse point tracking with optical flow."""
import logging

import cv2
import numpy as np

from .edge_detection_canny import edge_detection_canny_calculation
from .edge_utils import starting_point_detection

logger = logging.getLogger(__name__)


def compute_path_normals(
    path: list[tuple[int, int]],
    outward: bool = True,
) -> np.ndarray:
    """Compute outward normals for each point on a path.
    
    Args:
        path: List of (x, y) tuples representing the path.
        outward: If True, compute outward normals (for top path, upward; for bottom, downward).
    
    Returns:
        Array of shape (N, 2) with normalized normal vectors [nx, ny] for each point.
    """
    if len(path) < 2:
        return np.zeros((len(path), 2), dtype=np.float32)
    
    n = len(path)
    normals = np.zeros((n, 2), dtype=np.float32)
    
    for i in range(n):
        if i == 0:
            # First point: use forward difference
            dx = path[1][0] - path[0][0]
            dy = path[1][1] - path[0][1]
        elif i == n - 1:
            # Last point: use backward difference
            dx = path[n - 1][0] - path[n - 2][0]
            dy = path[n - 1][1] - path[n - 2][1]
        else:
            # Middle points: use central difference
            dx = path[i + 1][0] - path[i - 1][0]
            dy = path[i + 1][1] - path[i - 1][1]
        
        # Tangent vector
        tangent_len = np.sqrt(dx * dx + dy * dy)
        if tangent_len < 1e-6:
            # Degenerate case: use previous normal or default
            if i > 0:
                normals[i] = normals[i - 1]
            else:
                normals[i] = np.array([0.0, -1.0 if outward else 1.0])
            continue
        
        # Normal vector: rotate tangent 90 degrees
        # For outward normals on top path (y increases downward), we want upward normals
        # So for tangent (dx, dy), normal is (-dy, dx) for outward
        nx = -dy / tangent_len
        ny = dx / tangent_len
        
        # Flip if needed for outward direction
        if not outward:
            nx = -nx
            ny = -ny
        
        normals[i] = np.array([nx, ny], dtype=np.float32)
    
    return normals


def distribute_points_along_path(
    path: list[tuple[int, int]],
    num_points: int,
) -> list[tuple[float, float]]:
    """Distribute points evenly along a path based on arc length.
    
    Args:
        path: List of (x, y) tuples representing the path.
        num_points: Number of points to distribute.
    
    Returns:
        List of (x, y) tuples with evenly distributed points.
    """
    if len(path) < 2:
        return [(float(p[0]), float(p[1])) for p in path]
    
    if num_points <= 0:
        return []
    
    # Calculate cumulative arc lengths
    cumulative_lengths = [0.0]
    total_length = 0.0
    
    for i in range(len(path) - 1):
        dx = path[i + 1][0] - path[i][0]
        dy = path[i + 1][1] - path[i][1]
        segment_length = np.sqrt(dx * dx + dy * dy)
        total_length += segment_length
        cumulative_lengths.append(total_length)
    
    if total_length < 1e-6:
        # Path is degenerate, just return evenly spaced indices
        indices = np.linspace(0, len(path) - 1, num_points)
        result = []
        for idx in indices:
            i = int(np.round(idx))
            i = max(0, min(len(path) - 1, i))
            result.append((float(path[i][0]), float(path[i][1])))
        return result
    
    # Distribute points evenly along arc length
    result = []
    if num_points == 1:
        # Return midpoint
        target_length = total_length / 2.0
    else:
        # Distribute evenly
        for i in range(num_points):
            target_length = i * total_length / (num_points - 1)
            
            # Find segment containing target_length
            segment_idx = 0
            for j in range(len(cumulative_lengths) - 1):
                if cumulative_lengths[j] <= target_length <= cumulative_lengths[j + 1]:
                    segment_idx = j
                    break
            
            # Interpolate within segment
            if segment_idx < len(path) - 1:
                seg_start_len = cumulative_lengths[segment_idx]
                seg_end_len = cumulative_lengths[segment_idx + 1]
                if seg_end_len - seg_start_len > 1e-6:
                    t = (target_length - seg_start_len) / (seg_end_len - seg_start_len)
                else:
                    t = 0.0
                
                x0, y0 = path[segment_idx]
                x1, y1 = path[segment_idx + 1]
                x = x0 + t * (x1 - x0)
                y = y0 + t * (y1 - y0)
                result.append((float(x), float(y)))
            else:
                # Use last point
                result.append((float(path[-1][0]), float(path[-1][1])))
    
    return result


def snap_point_to_edge(
    point: tuple[float, float],
    normal: np.ndarray,
    edge_evidence: np.ndarray,
    snap_range: int = 10,
) -> tuple[float, float, float]:
    """Snap a point to the nearest strong edge along its normal direction.
    
    Args:
        point: Current point position (x, y).
        normal: Normal vector [nx, ny] (normalized).
        edge_evidence: Edge evidence image (gradient magnitude or binary edges).
        snap_range: Search range along normal (pixels).
    
    Returns:
        Tuple of (new_x, new_y, edge_response) where edge_response is the maximum response found.
    """
    H, W = edge_evidence.shape
    px, py = point
    nx, ny = normal
    
    # Sample positions along normal
    best_s = 0.0
    best_response = 0.0
    
    for s in np.linspace(-snap_range, snap_range, 2 * snap_range + 1):
        x = px + s * nx
        y = py + s * ny
        
        # Clamp to image bounds
        x = max(0, min(W - 1, x))
        y = max(0, min(H - 1, y))
        
        # Sample edge evidence (bilinear interpolation)
        x0, y0 = int(np.floor(x)), int(np.floor(y))
        x1, y1 = min(W - 1, x0 + 1), min(H - 1, y0 + 1)
        
        fx = x - x0
        fy = y - y0
        
        # Bilinear interpolation
        val = (
            edge_evidence[y0, x0] * (1 - fx) * (1 - fy) +
            edge_evidence[y0, x1] * fx * (1 - fy) +
            edge_evidence[y1, x0] * (1 - fx) * fy +
            edge_evidence[y1, x1] * fx * fy
        )
        
        if val > best_response:
            best_response = val
            best_s = s
    
    # Update point position
    new_x = px + best_s * nx
    new_y = py + best_s * ny
    
    # Clamp to image bounds
    new_x = max(0, min(W - 1, new_x))
    new_y = max(0, min(H - 1, new_y))
    
    return (new_x, new_y, best_response)


def smooth_contour(
    points: list[tuple[float, float]],
    window_size: int = 5,
) -> list[tuple[float, float]]:
    """Smooth a contour using moving average.
    
    Args:
        points: List of (x, y) tuples.
        window_size: Window size for moving average (must be odd).
    
    Returns:
        Smoothed list of (x, y) tuples.
    """
    if len(points) < 3:
        return points
    
    if window_size < 3:
        window_size = 3
    if window_size % 2 == 0:
        window_size += 1
    
    half_window = window_size // 2
    n = len(points)
    smoothed = []
    
    for i in range(n):
        # Calculate window boundaries
        start_idx = max(0, i - half_window)
        end_idx = min(n, i + half_window + 1)
        
        # Average x and y over window
        x_sum = 0.0
        y_sum = 0.0
        count = 0
        
        for j in range(start_idx, end_idx):
            x_sum += points[j][0]
            y_sum += points[j][1]
            count += 1
        
        if count > 0:
            smoothed.append((x_sum / count, y_sum / count))
        else:
            smoothed.append(points[i])
    
    return smoothed


def compute_edge_evidence(
    gray: np.ndarray,
    method: str = "sobel",
    canny_threshold1: float = 50.0,
    canny_threshold2: float = 150.0,
) -> np.ndarray:
    """Compute edge evidence image.
    
    Args:
        gray: Grayscale image.
        method: "sobel" for gradient magnitude, "canny" for binary edges.
        canny_threshold1: Lower threshold for Canny (if method="canny").
        canny_threshold2: Upper threshold for Canny (if method="canny").
    
    Returns:
        Edge evidence image (normalized to 0-1 range).
    """
    if method == "sobel":
        # Compute gradient magnitude
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=-1)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=-1)
        mag = cv2.magnitude(gx, gy)
        # Normalize to 0-1
        mag = cv2.normalize(mag, None, 0.0, 1.0, cv2.NORM_MINMAX)
        return mag
    elif method == "canny":
        # Binary edge image
        edges = cv2.Canny(
            gray,
            threshold1=int(canny_threshold1),
            threshold2=int(canny_threshold2),
        )
        # Convert to float and normalize
        return edges.astype(np.float32) / 255.0
    else:
        raise ValueError(f"Unknown edge method: {method}")


def reinitialize_from_contour(
    last_path: list[tuple[int, int]],
    frame: np.ndarray,
    num_points: int,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
) -> list[tuple[float, float]]:
    """Reinitialize tracking points from last known contour.
    
    Args:
        last_path: Last known path as list of (x, y) tuples.
        frame: Current frame.
        num_points: Number of points to extract.
        horizontal_window_x_left: Left boundary of horizontal window.
        horizontal_window_x_right: Right boundary of horizontal window.
    
    Returns:
        List of (x, y) tuples for reinitialized points.
    """
    if not last_path:
        return []
    
    # Filter path to horizontal window if specified
    if horizontal_window_x_left is not None and horizontal_window_x_right is not None:
        filtered_path = [
            (x, y) for x, y in last_path
            if horizontal_window_x_left <= x <= horizontal_window_x_right
        ]
        if filtered_path:
            last_path = filtered_path
    
    # Distribute points evenly along path
    return distribute_points_along_path(last_path, num_points)


def edge_detection_hybrid_calculation(
    *,
    frame: np.ndarray,
    hybrid_num_points: int = 50,
    hybrid_snap_range: int = 10,
    hybrid_lk_win_size: list[int] = [15, 15],
    hybrid_lk_max_level: int = 2,
    hybrid_edge_method: str = "sobel",
    hybrid_smoothing_window: int = 5,
    hybrid_reinit_threshold: float = 0.6,
    canny_threshold1: float = 50.0,
    canny_threshold2: float = 150.0,
    path_storage: dict | None = None,
    horizontal_window_x_left: int | None = None,
    horizontal_window_x_right: int | None = None,
    prev_path_top: list[tuple[int, int]] | None = None,
    prev_path_bottom: list[tuple[int, int]] | None = None,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Calculate edge paths using hybrid method (sparse points + optical flow + edge snapping).
    
    Args:
        frame: Input image as BGR or grayscale ndarray.
        hybrid_num_points: Number of sparse tracking points per path.
        hybrid_snap_range: Search range for edge snapping (pixels).
        hybrid_lk_win_size: Lucas-Kanade window size (width, height).
        hybrid_lk_max_level: Lucas-Kanade pyramid levels.
        hybrid_edge_method: Edge detection method for snapping ("sobel" or "canny").
        hybrid_smoothing_window: Window size for contour smoothing.
        hybrid_reinit_threshold: Fraction of valid points below which to reinitialize.
        canny_threshold1: Lower threshold for Canny (if edge_method="canny").
        canny_threshold2: Upper threshold for Canny (if edge_method="canny").
        path_storage: Optional dict to store paths and state in.
        horizontal_window_x_left: Left boundary for horizontal window (pixels).
        horizontal_window_x_right: Right boundary for horizontal window (pixels).
        prev_path_top: Previous frame's top path. If provided, uses for tracking.
        prev_path_bottom: Previous frame's bottom path. If provided, uses for tracking.
    
    Returns:
        Tuple of (path_top, path_bottom) where paths are lists of (x, y) tuples.
    """
    if frame is None or not isinstance(frame, np.ndarray):
        raise TypeError("'frame' must be a numpy ndarray")
    
    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = frame.copy()
    
    H, W = img_gray.shape
    
    # Initialize or retrieve state from path_storage
    if path_storage is None:
        path_storage = {}
    
    is_first_frame = (
        prev_path_top is None or
        prev_path_bottom is None or
        "prev_gray_top" not in path_storage or
        "prev_gray_bottom" not in path_storage or
        "pts_top" not in path_storage or
        "pts_bottom" not in path_storage
    )
    
    if is_first_frame:
        logger.info("First frame: initializing hybrid tracking")
        
        # Use starting point detection to get initial boundaries
        try:
            y_top, y_bottom, x_mid = starting_point_detection(frame=frame)
        except Exception as e:
            logger.error(f"Starting point detection failed: {e}", exc_info=True)
            return [], []
        
        if y_top < 0 or y_bottom < 0:
            logger.warning("Starting point detection failed, using Canny fallback")
            # Fallback to Canny method for initialization
            path_top, path_bottom = edge_detection_canny_calculation(
                frame=frame,
                canny_threshold1=canny_threshold1,
                canny_threshold2=canny_threshold2,
                horizontal_window_x_left=horizontal_window_x_left,
                horizontal_window_x_right=horizontal_window_x_right,
            )
            if not path_top or not path_bottom:
                return [], []
        else:
            # Use Canny to get full initial paths
            path_top, path_bottom = edge_detection_canny_calculation(
                frame=frame,
                canny_threshold1=canny_threshold1,
                canny_threshold2=canny_threshold2,
                horizontal_window_x_left=horizontal_window_x_left,
                horizontal_window_x_right=horizontal_window_x_right,
            )
            if not path_top or not path_bottom:
                return [], []
        
        # Filter paths to horizontal window if specified
        if horizontal_window_x_left is not None and horizontal_window_x_right is not None:
            path_top = [
                (x, y) for x, y in path_top
                if horizontal_window_x_left <= x <= horizontal_window_x_right
            ]
            path_bottom = [
                (x, y) for x, y in path_bottom
                if horizontal_window_x_left <= x <= horizontal_window_x_right
            ]
        
        # Distribute sparse points along paths
        pts_top = distribute_points_along_path(path_top, hybrid_num_points)
        pts_bottom = distribute_points_along_path(path_bottom, hybrid_num_points)
        
        # Compute normals (outward for top, inward for bottom)
        normals_top = compute_path_normals(path_top, outward=True)
        normals_bottom = compute_path_normals(path_bottom, outward=False)
        
        # Store state
        path_storage["prev_gray_top"] = img_gray.copy()
        path_storage["prev_gray_bottom"] = img_gray.copy()
        path_storage["pts_top"] = pts_top
        path_storage["pts_bottom"] = pts_bottom
        path_storage["normals_top"] = normals_top
        path_storage["normals_bottom"] = normals_bottom
        
        # Return initial paths
        return path_top, path_bottom
    
    # Subsequent frame: track with optical flow
    prev_gray_top = path_storage.get("prev_gray_top")
    prev_gray_bottom = path_storage.get("prev_gray_bottom")
    pts_top = path_storage.get("pts_top", [])
    pts_bottom = path_storage.get("pts_bottom", [])
    normals_top = path_storage.get("normals_top")
    normals_bottom = path_storage.get("normals_bottom")
    
    if not pts_top or not pts_bottom:
        logger.warning("No previous points found, reinitializing")
        return edge_detection_hybrid_calculation(
            frame=frame,
            hybrid_num_points=hybrid_num_points,
            hybrid_snap_range=hybrid_snap_range,
            hybrid_lk_win_size=hybrid_lk_win_size,
            hybrid_lk_max_level=hybrid_lk_max_level,
            hybrid_edge_method=hybrid_edge_method,
            hybrid_smoothing_window=hybrid_smoothing_window,
            hybrid_reinit_threshold=hybrid_reinit_threshold,
            canny_threshold1=canny_threshold1,
            canny_threshold2=canny_threshold2,
            path_storage={},  # Force reinit
            horizontal_window_x_left=horizontal_window_x_left,
            horizontal_window_x_right=horizontal_window_x_right,
        )
    
    # Convert points to LK format (Nx1x2 float32)
    pts_top_np = np.array(pts_top, dtype=np.float32).reshape(-1, 1, 2)
    pts_bottom_np = np.array(pts_bottom, dtype=np.float32).reshape(-1, 1, 2)
    
    # Track with Lucas-Kanade optical flow
    lk_params = dict(
        winSize=tuple(hybrid_lk_win_size),
        maxLevel=hybrid_lk_max_level,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
    )
    
    # Track top points
    next_pts_top, status_top, err_top = cv2.calcOpticalFlowPyrLK(
        prev_gray_top, img_gray, pts_top_np, None, **lk_params
    )
    
    # Track bottom points
    next_pts_bottom, status_bottom, err_bottom = cv2.calcOpticalFlowPyrLK(
        prev_gray_bottom, img_gray, pts_bottom_np, None, **lk_params
    )
    
    # Filter valid points
    valid_top = status_top.ravel() == 1
    valid_bottom = status_bottom.ravel() == 1
    
    # Check if too many points were lost
    valid_ratio_top = np.sum(valid_top) / len(valid_top) if len(valid_top) > 0 else 0.0
    valid_ratio_bottom = np.sum(valid_bottom) / len(valid_bottom) if len(valid_bottom) > 0 else 0.0
    
    if valid_ratio_top < hybrid_reinit_threshold or valid_ratio_bottom < hybrid_reinit_threshold:
        logger.warning(
            f"Too many points lost (top: {valid_ratio_top:.2f}, bottom: {valid_ratio_bottom:.2f}), "
            f"reinitializing from last paths"
        )
        # Reinitialize from last paths
        if prev_path_top and prev_path_bottom:
            pts_top = reinitialize_from_contour(
                prev_path_top, frame, hybrid_num_points,
                horizontal_window_x_left, horizontal_window_x_right
            )
            pts_bottom = reinitialize_from_contour(
                prev_path_bottom, frame, hybrid_num_points,
                horizontal_window_x_left, horizontal_window_x_right
            )
            # Update state and continue
            path_storage["pts_top"] = pts_top
            path_storage["pts_bottom"] = pts_bottom
            path_storage["prev_gray_top"] = img_gray.copy()
            path_storage["prev_gray_bottom"] = img_gray.copy()
            # Recompute normals
            path_top_temp = [(int(x), int(y)) for x, y in pts_top]
            path_bottom_temp = [(int(x), int(y)) for x, y in pts_bottom]
            path_storage["normals_top"] = compute_path_normals(path_top_temp, outward=True)
            path_storage["normals_bottom"] = compute_path_normals(path_bottom_temp, outward=False)
            # Return paths from reinitialized points
            return path_top_temp, path_bottom_temp
    
    # Extract valid tracked points
    tracked_pts_top = []
    tracked_pts_bottom = []
    valid_normals_top = []
    valid_normals_bottom = []
    
    for i in range(len(pts_top)):
        if valid_top[i]:
            pt = next_pts_top[i, 0]
            tracked_pts_top.append((float(pt[0]), float(pt[1])))
            valid_normals_top.append(normals_top[i])
    
    for i in range(len(pts_bottom)):
        if valid_bottom[i]:
            pt = next_pts_bottom[i, 0]
            tracked_pts_bottom.append((float(pt[0]), float(pt[1])))
            valid_normals_bottom.append(normals_bottom[i])
    
    # Compute edge evidence
    edge_evidence = compute_edge_evidence(
        img_gray,
        method=hybrid_edge_method,
        canny_threshold1=canny_threshold1,
        canny_threshold2=canny_threshold2,
    )
    
    # Snap points to edges
    snapped_pts_top = []
    snapped_pts_bottom = []
    edge_responses_top = []
    edge_responses_bottom = []
    
    for pt, normal in zip(tracked_pts_top, valid_normals_top):
        new_x, new_y, response = snap_point_to_edge(pt, normal, edge_evidence, hybrid_snap_range)
        snapped_pts_top.append((new_x, new_y))
        edge_responses_top.append(response)
    
    for pt, normal in zip(tracked_pts_bottom, valid_normals_bottom):
        new_x, new_y, response = snap_point_to_edge(pt, normal, edge_evidence, hybrid_snap_range)
        snapped_pts_bottom.append((new_x, new_y))
        edge_responses_bottom.append(response)
    
    # Smooth contours
    smoothed_pts_top = smooth_contour(snapped_pts_top, hybrid_smoothing_window)
    smoothed_pts_bottom = smooth_contour(snapped_pts_bottom, hybrid_smoothing_window)
    
    # Convert to integer paths
    path_top = [(int(np.round(x)), int(np.round(y))) for x, y in smoothed_pts_top]
    path_bottom = [(int(np.round(x)), int(np.round(y))) for x, y in smoothed_pts_bottom]
    
    # Update state for next frame
    path_storage["prev_gray_top"] = img_gray.copy()
    path_storage["prev_gray_bottom"] = img_gray.copy()
    path_storage["pts_top"] = smoothed_pts_top
    path_storage["pts_bottom"] = smoothed_pts_bottom
    
    # Recompute normals from smoothed paths
    path_storage["normals_top"] = compute_path_normals(path_top, outward=True)
    path_storage["normals_bottom"] = compute_path_normals(path_bottom, outward=False)
    
    # Store paths in path_storage
    if path_storage is not None:
        path_storage["path_top"] = path_top
        path_storage["path_bottom"] = path_bottom
    
    return path_top, path_bottom

