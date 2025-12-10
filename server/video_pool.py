"""Video handle pool for efficient frame extraction."""
import cv2
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional
import time


class VideoHandlePool:
    """Pool of open cv2.VideoCapture handles for fast frame access.
    
    Keeps video files open to avoid the expensive file open/seek overhead
    on every frame request. Handles are automatically closed after idle timeout
    or when the pool reaches max capacity (LRU eviction).
    """
    
    def __init__(self, max_handles: int = 5, idle_timeout: float = 60.0):
        """Initialize the video handle pool.
        
        Args:
            max_handles: Maximum number of open video handles to keep
            idle_timeout: Seconds of inactivity before closing a handle
        """
        self.max_handles = max_handles
        self.idle_timeout = idle_timeout
        # OrderedDict: key=video_path, value=(VideoCapture, last_access_time)
        self._handles: OrderedDict[str, tuple[cv2.VideoCapture, float]] = OrderedDict()
        self._lock = threading.Lock()
    
    def _get_handle(self, video_path: str) -> Optional[cv2.VideoCapture]:
        """Get or create a video handle for the given path.
        
        Returns None if the video file cannot be opened.
        """
        video_path_str = str(video_path)
        current_time = time.time()
        
        # Check if handle already exists
        if video_path_str in self._handles:
            cap, _ = self._handles[video_path_str]
            # Move to end (most recently used)
            self._handles.move_to_end(video_path_str)
            # Update access time
            self._handles[video_path_str] = (cap, current_time)
            return cap
        
        # Clean up idle handles first
        self._cleanup_idle_handles(current_time)
        
        # If at capacity, evict least recently used
        if len(self._handles) >= self.max_handles:
            # Remove oldest (first) entry
            oldest_path, (old_cap, _) = self._handles.popitem(last=False)
            old_cap.release()
        
        # Open new handle
        cap = cv2.VideoCapture(video_path_str)
        if not cap.isOpened():
            return None
        
        # Add to pool (at end, most recently used)
        self._handles[video_path_str] = (cap, current_time)
        return cap
    
    def _cleanup_idle_handles(self, current_time: float) -> None:
        """Close handles that have been idle for too long."""
        idle_paths = []
        for path, (cap, last_access) in list(self._handles.items()):
            if current_time - last_access > self.idle_timeout:
                idle_paths.append(path)
        
        for path in idle_paths:
            cap, _ = self._handles.pop(path)
            cap.release()
    
    def get_frame(self, video_path: str | Path, frame_number: int, frame_multiplier: float = 1.0) -> Optional[bytes]:
        """Get a frame as JPEG bytes, using pooled handle.
        
        Args:
            video_path: Path to the video file
            frame_number: Frame number to extract
            frame_multiplier: Multiplier for frame position (from metadata)
        
        Returns:
            JPEG-encoded frame bytes, or None if extraction fails
        """
        with self._lock:
            # Get or create handle
            cap = self._get_handle(video_path)
            if cap is None:
                return None
            
            # Seek to the requested frame using multiplier from metadata
            target_frame = int(frame_number * frame_multiplier)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            if not ret:
                return None
            
            # Encode as JPEG (quality 92 is a good balance)
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 92]
            success, encoded = cv2.imencode('.jpg', frame, encode_params)
            if not success:
                return None
            
            return encoded.tobytes()
    
    def close_all(self) -> None:
        """Close all handles in the pool (for cleanup/shutdown)."""
        with self._lock:
            for cap, _ in self._handles.values():
                cap.release()
            self._handles.clear()
    
    def close_video(self, video_path: str | Path) -> None:
        """Close handle for a specific video (e.g., when video is deleted)."""
        video_path_str = str(video_path)
        with self._lock:
            if video_path_str in self._handles:
                cap, _ = self._handles.pop(video_path_str)
                cap.release()

