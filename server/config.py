"""Configuration settings for the video analysis server."""
from pathlib import Path

# Base directory for the server
BASE_DIR = Path(__file__).parent

# Storage directories
VIDEOS_DIR = BASE_DIR / "videos"
RESULTS_DIR = BASE_DIR / "results"

# Ensure directories exist
VIDEOS_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# Allowed video file extensions
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

# Maximum upload size (100MB)
MAX_UPLOAD_SIZE = 1000 * 1024 * 1024

# Database path
DATABASE_PATH = BASE_DIR / "analyses.db"

