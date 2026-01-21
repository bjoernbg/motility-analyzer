"""Data models for video analysis."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class Video(BaseModel):
    """Video model."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    upload_date: datetime = Field(default_factory=datetime.now)
    file_path: str


class VideoMetadata(BaseModel):
    """Video metadata model."""
    total_frames: int = Field(description="Total number of frames")
    fps: float = Field(description="Frames per second")
    frame_multiplier: float = Field(description="Frame multiplier for the video")
    width: int = Field(description="Video width in pixels")
    height: int = Field(description="Video height in pixels")
    display_aspect_ratio: Optional[float] = Field(None, description="Display aspect ratio (width/height) accounting for non-square pixels")
    duration: float = Field(description="Duration in seconds")
    file_size: int = Field(description="File size in bytes")
    codec: Optional[str] = Field(None, description="Video codec")

    def needs_reencoding(self) -> bool:
        """Check if video needs re-encoding based on codec and format."""
        # Re-encode if codec is not AV1 (libsvtav1, av1, etc.)
        # Common codecs that should be re-encoded: h264, h265, mpeg4, etc.
        if not self.codec:
            return True  # Unknown codec, assume it needs re-encoding

        codec_lower = self.codec.lower().strip()
        # Check if already using AV1
        if 'av1' in codec_lower or 'av01' in codec_lower:
            return False

        return True


class ReencodeStatistics(BaseModel):
    """Statistics from video re-encoding operation."""
    duration_seconds: float = Field(description="Time taken to re-encode in seconds")
    original_size_bytes: int = Field(description="Original file size in bytes")
    new_size_bytes: int = Field(description="New file size in bytes")
    size_reduction_percent: float = Field(description="Percentage reduction in file size")
    original_codec: Optional[str] = Field(None, description="Original video codec")
    new_codec: str = Field(default="libsvtav1", description="New video codec")


class ReencodeResult(BaseModel):
    """Result of video re-encoding operation."""
    video: Video = Field(description="Updated video object")
    statistics: ReencodeStatistics = Field(description="Re-encoding statistics")


class AnalysisParameters(BaseModel):
    """Analysis parameters."""
    # Edge detection method selection
    edge_detection_method: Literal["costmap", "signal_1d", "canny", "silhouette"] = Field(
        default="silhouette",
        description="Edge detection method: 'costmap' (original), 'signal_1d' (1D signal-based), 'canny' (Canny edge detection), or 'silhouette' (mask-based segmentation)"
    )
    # Costmap parameters (only used when edge_detection_method="costmap")
    alpha: float = Field(default=1.5, ge=0.0, le=5.0, description="Contrast enhancement factor for costmap")
    band: int = Field(default=20, ge=1, le=100, description="Width of the search band around the current path position (in pixels)")
    threshold_percentile: float = Field(default=80.0, ge=0.0, le=100.0, description="Percentile threshold for keeping brightest pixels (0-100)")
    # Subsequent frame optimization (costmap method)
    subsequent_frame_band: Optional[int] = Field(default=None, ge=1, le=100, description="Band width for subsequent frames (if None, uses 'band' value)")
    # Smoothing factor (used by both methods)
    smoothing_factor: float = Field(default=0.2, ge=0.0, le=1.0, description="Smoothing factor for path following (0-1, higher = more smoothing)")
    # 1D Signal method parameters (only used when edge_detection_method="signal_1d")
    strip_width: int = Field(default=5, ge=1, le=20, description="Width of horizontal strip for 1D signal method (pixels)")
    band_height: int = Field(default=30, ge=10, le=100, description="Height of vertical band for 1D signal method (pixels)")
    sigma: float = Field(default=2.0, ge=0.5, le=10.0, description="Gaussian sigma parameter for 1D signal smoothing")
    # Canny method parameters (only used when edge_detection_method="canny")
    canny_threshold1: float = Field(default=50.0, ge=0.0, le=255.0, description="Lower threshold for Canny edge detection")
    canny_threshold2: float = Field(default=150.0, ge=0.0, le=255.0, description="Upper threshold for Canny edge detection")
    canny_aperture_size: int = Field(default=3, ge=3, le=7, description="Aperture size for Canny edge detection (must be 3, 5, or 7)")
    # Silhouette method parameters (only used when edge_detection_method="silhouette")
    silhouette_blur_ksize_x: int = Field(default=7, ge=1, le=50, description="Gaussian blur kernel width for silhouette method")
    silhouette_blur_ksize_y: int = Field(default=7, ge=1, le=50, description="Gaussian blur kernel height for silhouette method")
    silhouette_blur_sigma: float = Field(default=1.6, ge=0.1, le=10.0, description="Gaussian blur sigma for silhouette method")
    silhouette_close_k: int = Field(default=5, ge=1, le=50, description="Morphology kernel size for silhouette method")
    silhouette_x_step: int = Field(default=7, ge=1, le=20, description="Step size for x-coordinate sampling in silhouette method")
    silhouette_band: int = Field(default=60, ge=1, le=200, description="Vertical band width around previous paths for silhouette method")
    silhouette_median_k: int = Field(default=3, ge=3, le=101, description="Median filter kernel size for 1D smoothing in silhouette method (must be odd)")
    # Horizontal window parameters
    horizontal_window_x_left: Optional[int] = Field(default=None, description="Left x-coordinate for horizontal window (pixels)")
    horizontal_window_x_right: Optional[int] = Field(default=None, description="Right x-coordinate for horizontal window (pixels)")
    # Measurement configuration
    num_tracking_points: int = Field(default=30, ge=5, le=200, description="Number of tracking points for measurement")
    distribution_method: Literal["center_line_projection", "x_axis_even"] = Field(default="center_line_projection", description="Method for distributing measurement points")


class Analysis(BaseModel):
    """Analysis model."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    video_id: str
    parameters: Dict[str, Any]
    status: str = "pending"  # pending, processing, completed, failed
    progress: float = 0.0  # 0.0 to 100.0
    processed_frames: Optional[int] = Field(default=None, description="Number of frames processed so far")
    results_path: Optional[str] = None
    global_data: Optional[Dict[str, Any]] = Field(default=None, description="Global statistics and aggregated data")
    created_at: datetime = Field(default_factory=datetime.now)


class FrameData(BaseModel):
    """Data for a single frame."""
    f: int = Field(description="Frame number")
    pt: List[List[int]] = Field(description="Top boundary path: [[x, y], ...]")
    pb: List[List[int]] = Field(description="Bottom boundary path: [[x, y], ...]")
    pc: List[List[int]] = Field(description="Center path: [[x, y], ...]")
    colored_regions: List[Dict[str, Any]]  # List of colored region data
    mpp: Optional[List[List[float]]] = Field(default=None, description="Measurement point pairs: [[cx, cy, tx, ty, bx, by, distance], ...]")


class AnalysisResult(BaseModel):
    """Analysis result model."""
    per_frame: List[FrameData]
    global_data: Dict[str, Any]


class AnalysisProgress(BaseModel):
    """Progress update model."""
    analysis_id: str
    progress: float
    status: str
    current_frame: Optional[int] = None
    total_frames: Optional[int] = None


class HeatmapMeta(BaseModel):
    """Heatmap metadata model."""
    width: int = Field(description="Number of frames (x-axis)")
    height: int = Field(description="Number of tracking points (y-axis)")
    dtype: str = Field(default="float32", description="Data type")
    min: float = Field(description="Minimum distance value")
    max: float = Field(description="Maximum distance value")
    fps: float = Field(description="Frames per second for time conversion")
    display_settings: Optional["DisplaySettings"] = Field(default=None, description="Display settings for visualization")


class DisplaySettings(BaseModel):
    """Display settings for measurement visualization."""
    pixel_to_mm_factor: float = Field(default=11.0, gt=0.0, description="Pixels per millimeter")
    heatmap_min_mm: float = Field(default=3.0, ge=0.0, description="Minimum value for heatmap color scale (mm)")
    heatmap_max_mm: float = Field(default=30.0, gt=0.0, description="Maximum value for heatmap color scale (mm)")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp")

    @validator('heatmap_max_mm')
    def validate_max_greater_than_min(cls, v, values):
        if 'heatmap_min_mm' in values and v <= values['heatmap_min_mm']:
            raise ValueError('heatmap_max_mm must be greater than heatmap_min_mm')
        return v


class SuggestedDisplaySettings(BaseModel):
    """Auto-calculated suggestions for display settings."""
    pixel_to_mm_factor: float = Field(description="Current or default pixel-to-mm factor")
    heatmap_min_mm: float = Field(description="Suggested minimum (5th percentile)")
    heatmap_max_mm: float = Field(description="Suggested maximum (95th percentile)")
    data_min_mm: float = Field(description="Actual data minimum in mm")
    data_max_mm: float = Field(description="Actual data maximum in mm")
    data_median_mm: float = Field(description="Actual data median in mm")


class ContractionDetectionParameters(BaseModel):
    """Parameters for contraction detection algorithm."""
    smooth_sigma_y: float = Field(default=1.0, ge=0.0, description="Gaussian smoothing sigma for y-axis (point-pair index)")
    smooth_sigma_t: float = Field(default=1.0, ge=0.0, description="Gaussian smoothing sigma for t-axis (frame index)")
    threshold_percentile: float = Field(default=10.0, ge=0.0, le=100.0, description="Percentile for automatic threshold (0-100)")
    threshold: Optional[float] = Field(default=None, description="Manual threshold override (if None, uses percentile)")
    open_iters: int = Field(default=1, ge=0, description="Binary opening iterations (removes speckles)")
    close_iters: int = Field(default=2, ge=0, description="Binary closing iterations (fills holes)")
    min_pixels: int = Field(default=200, ge=1, description="Minimum pixels per event to keep")
    min_area: Optional[float] = Field(default=None, ge=0.0, description="Minimum area in mm²·s (exact calculation)")
    min_height: Optional[float] = Field(default=None, ge=0.0, description="Minimum height in mm (spatial extent)")
    dy: Optional[float] = Field(default=None, ge=0.0, description="Physical spacing between point pairs in mm (auto-calculated if None)")


class ContractionEventLineFit(BaseModel):
    """Line fit parameters for a contraction event."""
    a_idx_per_frame: float = Field(description="Slope in y-indices per frame")
    b: float = Field(description="Intercept in y-indices")


class ContractionEvent(BaseModel):
    """Single contraction event result."""
    id: str = Field(description="Unique event ID")
    label: int = Field(description="Component label from connected components")
    n_pixels: int = Field(description="Number of pixels in the event")
    threshold_used: float = Field(description="Threshold value used for detection")
    t_range_frames: tuple[int, int] = Field(description="Frame range (start, end)")
    y_range_idx: tuple[int, int] = Field(description="Point-pair index range (start, end)")
    duration_s: float = Field(description="Duration in seconds")
    height_phys: float = Field(description="Height in physical units (mm)")
    velocity_phys_per_s: float = Field(description="Velocity in mm/s (positive = moving to higher y)")
    line_fit: ContractionEventLineFit = Field(description="Fitted line parameters")
    area_exact: float = Field(description="Exact area below threshold in mm²·s")
    area_triangle: float = Field(description="Triangle approximation area in mm²·s")
    created_at: str = Field(description="Creation timestamp")


class ContractionDetectionResult(BaseModel):
    """Contraction detection result with all events."""
    events: List[ContractionEvent] = Field(description="List of detected contraction events")
    parameters_used: ContractionDetectionParameters = Field(description="Parameters used for detection")
    total_events: int = Field(description="Total number of events detected")

