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

# Physical measurement constants
# Pixel to millimeter conversion factor
# ⚠️ IMPORTANT: This constant is also defined in the frontend at client/src/lib/constants.ts
# If you change this value, you MUST also update it in client/src/lib/constants.ts to keep them in sync!
PIXEL_TO_MM_FACTOR = 11.0  # 11 pixels = 1 mm

