"""Storage utilities for videos and analysis results."""
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import VIDEOS_DIR
from .database import AnalysisDB, init_database
from .models import Analysis, AnalysisResult, FrameData, Video

# Initialize database on module import
init_database()


class VideoStorage:
    """Manages video file storage."""
    
    @staticmethod
    def save_uploaded_file(file_content: bytes, filename: str) -> str:
        """Save uploaded video file and return the file path."""
        # Sanitize filename
        safe_filename = "".join(c for c in filename if c.isalnum() or c in ".-_")
        if not safe_filename:
            safe_filename = "video"
        
        file_path = VIDEOS_DIR / safe_filename
        # Ensure unique filename
        counter = 1
        while file_path.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            file_path = VIDEOS_DIR / f"{stem}_{counter}{suffix}"
            counter += 1
        
        file_path.write_bytes(file_content)
        return str(file_path)
    
    @staticmethod
    def list_videos() -> List[Video]:
        """List all available videos."""
        videos = []
        for file_path in VIDEOS_DIR.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
                video = Video(
                    id=file_path.stem,  # Use filename stem as ID
                    filename=file_path.name,
                    file_path=str(file_path),
                    upload_date=datetime.fromtimestamp(file_path.stat().st_mtime)
                )
                videos.append(video)
        return sorted(videos, key=lambda v: v.upload_date, reverse=True)
    
    @staticmethod
    def get_video(video_id: str) -> Optional[Video]:
        """Get a video by ID."""
        for video in VideoStorage.list_videos():
            if video.id == video_id:
                return video
        return None
    
    @staticmethod
    def get_video_path(video_id: str) -> Optional[Path]:
        """Get the file path for a video ID."""
        video = VideoStorage.get_video(video_id)
        if video:
            return Path(video.file_path)
        return None


class ResultsStorage:
    """Manages analysis results storage using database."""
    
    def __init__(self):
        """Initialize with database connection."""
        self.db = AnalysisDB()
    
    def save_results(self, analysis_id: str, results: AnalysisResult) -> str:
        """Save analysis results to database."""
        self.db.save_results(analysis_id, results)
        return analysis_id  # Return analysis_id instead of file path
    
    def load_results(self, analysis_id: str) -> Optional[AnalysisResult]:
        """Load analysis results from database."""
        return self.db.load_results(analysis_id)
    
    def results_exist(self, analysis_id: str) -> bool:
        """Check if results exist for an analysis."""
        return self.db.results_exist(analysis_id)
    
    def append_frame_to_results(self, analysis_id: str, frame_data: FrameData, total_frames: int) -> None:
        """Append a frame to existing results or create new results structure."""
        self.db.append_frame_to_results(analysis_id, frame_data, total_frames)
    
    def finalize_results(self, analysis_id: str, results: AnalysisResult) -> None:
        """Finalize results with complete global_data calculation."""
        self.db.finalize_results(analysis_id, results)
    
    def get_frame(self, analysis_id: str, frame_number: int):
        """Get a single frame by analysis_id and frame_number."""
        return self.db.get_frame(analysis_id, frame_number)
    
    def clear_results(self, analysis_id: str) -> None:
        """Clear all results for an analysis."""
        self.db.clear_analysis_frames(analysis_id)


class AnalysisStorage:
    """Manages analysis metadata storage using database."""
    
    def __init__(self):
        """Initialize with database connection."""
        self.db = AnalysisDB()
    
    def create_analysis(self, analysis: Analysis) -> None:
        """Create a new analysis."""
        self.db.create_analysis(analysis)
    
    def get_analysis(self, analysis_id: str) -> Optional[Analysis]:
        """Get an analysis by ID."""
        return self.db.get_analysis(analysis_id)
    
    def get_analysis_with_results(self, analysis_id: str) -> tuple[Optional[Analysis], Optional[AnalysisResult]]:
        """Get an analysis with its results."""
        return self.db.get_analysis_with_results(analysis_id)
    
    def update_analysis(self, analysis_id: str, **updates) -> None:
        """Update analysis fields."""
        self.db.update_analysis(analysis_id, **updates)
    
    def list_analyses(
        self,
        video_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Analysis]:
        """List analyses with optional filters."""
        return self.db.list_analyses(video_id=video_id, status=status, limit=limit, offset=offset)
    
    def delete_analysis(self, analysis_id: str) -> None:
        """Delete an analysis."""
        self.db.delete_analysis(analysis_id)
    
    def clear_results(self, analysis_id: str) -> None:
        """Clear all results for an analysis."""
        self.db.clear_analysis_frames(analysis_id)


def clear_heatmap_cache(analysis_id: str, video_id: str) -> None:
    """Clear cached heatmap files for an analysis.
    
    Args:
        analysis_id: ID of the analysis
        video_id: ID of the video associated with the analysis
    """
    video_path = VideoStorage.get_video_path(video_id)
    if not video_path or not video_path.exists():
        return
    
    # Clear all three cache files
    cache_files = [
        video_path.parent / f"{video_path.stem}_analysis_{analysis_id}_heatmap_meta.json",
        video_path.parent / f"{video_path.stem}_analysis_{analysis_id}_heatmap_raw.bin",
        video_path.parent / f"{video_path.stem}_analysis_{analysis_id}_heatmap_raw_meta.json",
    ]
    
    for cache_file in cache_files:
        try:
            if cache_file.exists():
                cache_file.unlink()
        except (IOError, OSError):
            # If deletion fails, continue (cache will be regenerated on next request)
            pass

