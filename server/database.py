"""Database module for storing analysis data."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .config import DATABASE_PATH
from .models import Analysis, AnalysisResult, FrameData


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(row[1] == column_name for row in columns)


def migrate_database_for_multi_view_sessions() -> None:
    """Create multi_view_sessions table and remove legacy combined_analyses table."""
    db_path = Path(DATABASE_PATH)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        # Drop legacy table from removed combination feature.
        cursor.execute("DROP TABLE IF EXISTS combined_analyses")

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='multi_view_sessions'"
        )
        if cursor.fetchone():
            # Table already exists
            conn.commit()
            return

        # Create table
        cursor.execute("""
            CREATE TABLE multi_view_sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                left_analysis_id TEXT NOT NULL,
                right_analysis_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT
            )
        """)

        # Create indexes
        cursor.execute(
            "CREATE INDEX idx_multi_view_sessions_created_at ON multi_view_sessions(created_at)"
        )
        cursor.execute(
            "CREATE INDEX idx_multi_view_sessions_name ON multi_view_sessions(name)"
        )

        conn.commit()
    finally:
        conn.close()


def migrate_database_for_display_names() -> None:
    """Add display-name persistence schema for videos and analyses."""
    db_path = Path(DATABASE_PATH)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        if _table_exists(cursor, "analyses") and not _column_exists(
            cursor, "analyses", "display_name"
        ):
            cursor.execute("ALTER TABLE analyses ADD COLUMN display_name TEXT")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_labels (
                video_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_video_labels_updated_at ON video_labels(updated_at)"
        )

        conn.commit()
    finally:
        conn.close()


def init_database() -> None:
    """Initialize the database and create tables if they don't exist."""
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    # Favor throughput for frequent incremental writes during analysis.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    cursor = conn.cursor()

    # Create analyses table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            display_name TEXT,
            parameters TEXT NOT NULL,
            status TEXT NOT NULL,
            progress REAL NOT NULL DEFAULT 0.0,
            global_data TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            error_message TEXT
        )
    """)

    # Create frames table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS frames (
            analysis_id TEXT NOT NULL,
            frame_number INTEGER NOT NULL,
            frame_data TEXT NOT NULL,
            PRIMARY KEY (analysis_id, frame_number),
            FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
        )
    """)

    # Create contraction_events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contraction_events (
            id TEXT PRIMARY KEY,
            analysis_id TEXT NOT NULL,
            event_label INTEGER NOT NULL,
            n_pixels INTEGER NOT NULL,
            threshold_used REAL NOT NULL,
            t_range_start INTEGER NOT NULL,
            t_range_end INTEGER NOT NULL,
            y_range_start INTEGER NOT NULL,
            y_range_end INTEGER NOT NULL,
            duration_s REAL NOT NULL,
            height_phys REAL NOT NULL,
            velocity_phys_per_s REAL NOT NULL,
            line_fit_a REAL NOT NULL,
            line_fit_b REAL NOT NULL,
            area_exact REAL NOT NULL,
            area_triangle REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_labels (
            video_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Create indexes for efficient queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_id ON analyses(video_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON analyses(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON analyses(created_at)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_frames_analysis_id ON frames(analysis_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_contraction_events_analysis_id ON contraction_events(analysis_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_labels_updated_at ON video_labels(updated_at)"
    )

    conn.commit()
    conn.close()

    # Run migration for multi-view sessions table
    migrate_database_for_multi_view_sessions()
    migrate_database_for_display_names()


def clear_all_data() -> None:
    """Drop all tables and reinitialize the database (factory reset).

    This reclaims disk space via VACUUM after dropping tables.
    """
    db_path = Path(DATABASE_PATH)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE IF EXISTS contraction_events")
        conn.execute("DROP TABLE IF EXISTS frames")
        conn.execute("DROP TABLE IF EXISTS multi_view_sessions")
        conn.execute("DROP TABLE IF EXISTS combined_analyses")
        conn.execute("DROP TABLE IF EXISTS video_labels")
        conn.execute("DROP TABLE IF EXISTS analyses")
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()

    # Recreate all tables and indexes
    init_database()


class AnalysisDB:
    """Database operations for analyses."""

    def __init__(self, db_path: str = DATABASE_PATH):
        """Initialize with database path."""
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        # Keep per-connection settings aligned with init_database.
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def create_analysis(self, analysis: Analysis) -> None:
        """Insert a new analysis."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO analyses (id, video_id, display_name, parameters, status, progress, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    analysis.id,
                    analysis.video_id,
                    analysis.display_name,
                    json.dumps(analysis.parameters),
                    analysis.status,
                    analysis.progress,
                    analysis.created_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_analysis(self, analysis_id: str) -> Optional[Analysis]:
        """Retrieve an analysis by ID (without results)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT id, video_id, display_name, parameters, status, progress, created_at, completed_at, error_message, global_data
                FROM analyses
                WHERE id = ?
            """,
                (analysis_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            # Count processed frames
            cursor.execute(
                "SELECT COUNT(*) as count FROM frames WHERE analysis_id = ?",
                (analysis_id,),
            )
            frame_count_row = cursor.fetchone()
            processed_frames = int(frame_count_row["count"]) if frame_count_row else 0

            # Load global_data if present
            global_data = None
            if row["global_data"]:
                global_data = json.loads(row["global_data"])

            return Analysis(
                id=row["id"],
                video_id=row["video_id"],
                display_name=row["display_name"],
                parameters=json.loads(row["parameters"]),
                status=row["status"],
                progress=row["progress"],
                processed_frames=processed_frames if processed_frames > 0 else None,
                results_path=None,  # Not stored in DB anymore
                global_data=global_data,
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        finally:
            conn.close()

    def get_analysis_with_results(
        self, analysis_id: str
    ) -> tuple[Optional[Analysis], Optional[AnalysisResult]]:
        """Retrieve an analysis with its results."""
        analysis = self.get_analysis(analysis_id)
        if not analysis:
            return None, None

        results = self.load_results(analysis_id)
        return analysis, results

    def get_frame(self, analysis_id: str, frame_number: int) -> Optional[FrameData]:
        """Retrieve a single frame by analysis_id and frame_number."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT frame_data
                FROM frames
                WHERE analysis_id = ? AND frame_number = ?
            """,
                (analysis_id, frame_number),
            )

            row = cursor.fetchone()
            if not row:
                return None

            frame_data_dict = json.loads(row["frame_data"])
            return FrameData(**frame_data_dict)
        finally:
            conn.close()

    def update_analysis(self, analysis_id: str, **updates: Any) -> None:
        """Update analysis fields."""
        if not updates:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Build dynamic update query
            set_clauses = []
            values = []

            for key, value in updates.items():
                if key == "parameters":
                    set_clauses.append("parameters = ?")
                    values.append(json.dumps(value))
                elif key == "global_data":
                    set_clauses.append("global_data = ?")
                    values.append(
                        json.dumps(value, default=str) if value is not None else None
                    )
                elif key == "completed_at":
                    if value is None:
                        set_clauses.append("completed_at = NULL")
                    else:
                        set_clauses.append("completed_at = ?")
                        values.append(
                            value.isoformat() if isinstance(value, datetime) else value
                        )
                elif key == "created_at":
                    set_clauses.append("created_at = ?")
                    values.append(
                        value.isoformat() if isinstance(value, datetime) else value
                    )
                else:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)

            values.append(analysis_id)

            query = f"UPDATE analyses SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
        finally:
            conn.close()

    def save_results(self, analysis_id: str, results: AnalysisResult) -> None:
        """Store analysis results by saving global_data to analyses and frames to frames table."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Save global_data to analyses table
            global_data_json = json.dumps(results.global_data, default=str)
            cursor.execute(
                """
                UPDATE analyses
                SET global_data = ?
                WHERE id = ?
            """,
                (global_data_json, analysis_id),
            )

            # Insert or replace all frames
            for frame_data in results.per_frame:
                frame_data_json = json.dumps(frame_data.model_dump(), default=str)
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO frames (analysis_id, frame_number, frame_data)
                    VALUES (?, ?, ?)
                """,
                    (analysis_id, frame_data.f, frame_data_json),
                )

            conn.commit()
        finally:
            conn.close()

    def load_results(self, analysis_id: str) -> Optional[AnalysisResult]:
        """Load analysis results by querying frames table and reconstructing AnalysisResult."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get global_data from analyses table
            cursor.execute(
                "SELECT global_data FROM analyses WHERE id = ?", (analysis_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            # Load global_data (may be None if not set yet)
            global_data = {}
            if row["global_data"]:
                global_data = json.loads(row["global_data"])

            # Query all frames for this analysis, ordered by frame_number
            cursor.execute(
                """
                SELECT frame_data
                FROM frames
                WHERE analysis_id = ?
                ORDER BY frame_number
            """,
                (analysis_id,),
            )

            frame_rows = cursor.fetchall()

            # Reconstruct per_frame list
            per_frame = []
            for frame_row in frame_rows:
                frame_data_dict = json.loads(frame_row["frame_data"])
                frame_data = FrameData(**frame_data_dict)
                per_frame.append(frame_data)

            # Return None if no frames and no global_data (no results yet)
            if not per_frame and not global_data:
                return None

            return AnalysisResult(per_frame=per_frame, global_data=global_data)
        finally:
            conn.close()

    def list_analyses(
        self,
        video_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Analysis]:
        """List analyses with optional filters."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = """
                SELECT id, video_id, display_name, parameters, status, progress, created_at, completed_at, error_message, global_data
                FROM analyses
                WHERE 1=1
            """
            params = []

            if video_id:
                query += " AND video_id = ?"
                params.append(video_id)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            analyses = []
            for row in rows:
                # Count processed frames for this analysis
                cursor.execute(
                    "SELECT COUNT(*) as count FROM frames WHERE analysis_id = ?",
                    (row["id"],),
                )
                frame_count_row = cursor.fetchone()
                processed_frames = (
                    int(frame_count_row["count"]) if frame_count_row else 0
                )

                # Load global_data if present
                global_data = None
                if row["global_data"]:
                    global_data = json.loads(row["global_data"])

                analyses.append(
                    Analysis(
                        id=row["id"],
                        video_id=row["video_id"],
                        display_name=row["display_name"],
                        parameters=json.loads(row["parameters"]),
                        status=row["status"],
                        progress=row["progress"],
                        processed_frames=processed_frames
                        if processed_frames > 0
                        else None,
                        results_path=None,
                        global_data=global_data,
                        created_at=datetime.fromisoformat(row["created_at"]),
                    )
                )

            return analyses
        finally:
            conn.close()

    def delete_analysis(self, analysis_id: str) -> None:
        """Delete an analysis. Frames will be automatically deleted via CASCADE DELETE."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
            conn.commit()
        finally:
            conn.close()

    def results_exist(self, analysis_id: str) -> bool:
        """Check if results exist for an analysis (has frames or global_data)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Check if any frames exist for this analysis
            cursor.execute(
                "SELECT 1 FROM frames WHERE analysis_id = ? LIMIT 1", (analysis_id,)
            )
            if cursor.fetchone():
                return True

            # Check if global_data exists
            cursor.execute(
                "SELECT 1 FROM analyses WHERE id = ? AND global_data IS NOT NULL",
                (analysis_id,),
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def get_last_analyzed_frame(self, analysis_id: str) -> Optional[int]:
        """Get the last analyzed frame number for an analysis, or None if no frames exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT MAX(frame_number) as max_frame
                FROM frames
                WHERE analysis_id = ?
            """,
                (analysis_id,),
            )

            row = cursor.fetchone()
            if row and row["max_frame"] is not None:
                return int(row["max_frame"])
            return None
        finally:
            conn.close()

    def append_frame_to_results(
        self,
        analysis_id: str,
        frame_data: FrameData,
        total_frames: int,
        processed_count: int | None = None,
    ) -> None:
        """Append a frame to existing results by inserting into frames table."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Insert or replace frame in frames table
            frame_data_json = json.dumps(frame_data.model_dump(), default=str)
            cursor.execute(
                """
                INSERT OR REPLACE INTO frames (analysis_id, frame_number, frame_data)
                VALUES (?, ?, ?)
            """,
                (analysis_id, frame_data.f, frame_data_json),
            )

            # If caller already knows processed frame count, avoid extra COUNT(*) query.
            if processed_count is None:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM frames WHERE analysis_id = ?",
                    (analysis_id,),
                )
                processed_count = int(cursor.fetchone()["count"])

            # Update global_data in analyses table
            global_data = {
                "total_frames": total_frames,
                "processed_frames": processed_count,
            }
            global_data_json = json.dumps(global_data, default=str)
            cursor.execute(
                """
                UPDATE analyses
                SET global_data = ?
                WHERE id = ?
            """,
                (global_data_json, analysis_id),
            )

            conn.commit()
        finally:
            conn.close()

    def append_frames_to_results(
        self,
        analysis_id: str,
        frames: list[FrameData],
        total_frames: int,
        processed_count: int,
    ) -> None:
        """Append multiple frames in a single transaction for better throughput."""
        if not frames:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            frame_rows: list[tuple[str, int, str]] = []
            for frame_data in frames:
                frame_rows.append(
                    (
                        analysis_id,
                        frame_data.f,
                        json.dumps(frame_data.model_dump(), default=str),
                    )
                )

            cursor.executemany(
                """
                INSERT OR REPLACE INTO frames (analysis_id, frame_number, frame_data)
                VALUES (?, ?, ?)
                """,
                frame_rows,
            )

            global_data = {
                "total_frames": total_frames,
                "processed_frames": processed_count,
            }
            global_data_json = json.dumps(global_data, default=str)
            cursor.execute(
                """
                UPDATE analyses
                SET global_data = ?
                WHERE id = ?
                """,
                (global_data_json, analysis_id),
            )

            conn.commit()
        finally:
            conn.close()

    def finalize_results(
        self,
        analysis_id: str,
        results: AnalysisResult,
        skip_frame_upsert: bool = False,
    ) -> None:
        """Finalize results with complete global_data calculation."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Save global_data and completion metadata regardless of frame upsert mode.
            global_data_json = json.dumps(results.global_data, default=str)
            completed_at = datetime.now().isoformat()

            cursor.execute(
                """
                UPDATE analyses
                SET global_data = ?, completed_at = ?, status = 'completed', progress = 100.0
                WHERE id = ?
            """,
                (global_data_json, completed_at, analysis_id),
            )

            if skip_frame_upsert:
                conn.commit()
                return

            # Load existing frames to merge with final results
            # (in case finalize is called before all frames are appended)
            cursor.execute(
                """
                SELECT frame_data
                FROM frames
                WHERE analysis_id = ?
                ORDER BY frame_number
            """,
                (analysis_id,),
            )

            existing_frame_rows = cursor.fetchall()

            # Ensure all existing frames are in final results
            final_frame_nums = {f.f for f in results.per_frame}
            for frame_row in existing_frame_rows:
                frame_data_dict = json.loads(frame_row["frame_data"])
                if frame_data_dict["f"] not in final_frame_nums:
                    frame_data = FrameData(**frame_data_dict)
                    results.per_frame.append(frame_data)

            # Sort by frame number
            results.per_frame.sort(key=lambda f: f.f)

            # Insert or replace all frames
            for frame_data in results.per_frame:
                frame_data_json = json.dumps(frame_data.model_dump(), default=str)
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO frames (analysis_id, frame_number, frame_data)
                    VALUES (?, ?, ?)
                """,
                    (analysis_id, frame_data.f, frame_data_json),
                )

            conn.commit()
        finally:
            conn.close()

    def clear_analysis_frames(self, analysis_id: str) -> None:
        """Delete all frame data for an analysis."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Delete all frames for this analysis
            cursor.execute("DELETE FROM frames WHERE analysis_id = ?", (analysis_id,))
            # Clear global_data as well
            cursor.execute(
                """
                UPDATE analyses
                SET global_data = NULL, completed_at = NULL
                WHERE id = ?
            """,
                (analysis_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def get_frames_range(
        self, analysis_id: str, start: int, count: int
    ) -> list[FrameData]:
        """Efficiently fetch a range of frames."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Query frames in the specified range, ordered by frame_number
            cursor.execute(
                """
                SELECT frame_data
                FROM frames
                WHERE analysis_id = ? AND frame_number >= ?
                ORDER BY frame_number
                LIMIT ?
            """,
                (analysis_id, start, count),
            )

            frame_rows = cursor.fetchall()
            frames = []
            for frame_row in frame_rows:
                frame_data_dict = json.loads(frame_row["frame_data"])
                frame_data = FrameData(**frame_data_dict)
                frames.append(frame_data)

            return frames
        finally:
            conn.close()

    def get_available_frame_numbers(self, analysis_id: str) -> list[int]:
        """Return all frame numbers that have data."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT frame_number
                FROM frames
                WHERE analysis_id = ?
                ORDER BY frame_number
            """,
                (analysis_id,),
            )

            rows = cursor.fetchall()
            return [int(row["frame_number"]) for row in rows]
        finally:
            conn.close()

    def build_heatmap_matrix(self, analysis_id: str) -> tuple[np.ndarray, float, float]:
        """Extract distances from mpp field across all frames, return (matrix, min, max).

        The matrix is row-major: [frame0: pt0..ptN, frame1: pt0..ptN, ...]
        Each mpp entry is [cx, cy, tx, ty, bx, by, distance] where distance is at index 6.

        Returns:
            Tuple of (matrix as np.ndarray with shape (frame_count, point_count), min_value, max_value)
        """

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Query all frames ordered by frame number
            cursor.execute(
                """
                SELECT frame_number, frame_data
                FROM frames
                WHERE analysis_id = ?
                ORDER BY frame_number
            """,
                (analysis_id,),
            )

            frame_rows = cursor.fetchall()

            if not frame_rows:
                # Return empty matrix
                return np.array([], dtype=np.float32).reshape(0, 0), 0.0, 0.0

            # Find the number of measurement points in the first frame
            first_frame_data = json.loads(frame_rows[0]["frame_data"])
            mpp = first_frame_data.get("mpp")
            num_points = len(mpp) if mpp else 0

            if num_points == 0:
                # No measurement points found
                return np.array([], dtype=np.float32).reshape(0, 0), 0.0, 0.0

            num_frames = len(frame_rows)

            # Initialize matrix: (num_frames, num_points)
            matrix = np.zeros((num_frames, num_points), dtype=np.float32)

            # Extract distance values (index 6) from each frame's mpp
            for row_idx, frame_row in enumerate(frame_rows):
                frame_data_dict = json.loads(frame_row["frame_data"])
                mpp = frame_data_dict.get("mpp")

                if mpp:
                    for point_idx, point_pair in enumerate(mpp):
                        if len(point_pair) >= 7:
                            # Distance is at index 6
                            distance = float(point_pair[6])
                            matrix[row_idx, point_idx] = distance

            # Calculate min and max
            if matrix.size > 0:
                min_val = float(np.min(matrix))
                max_val = float(np.max(matrix))
            else:
                min_val = 0.0
                max_val = 0.0

            return matrix, min_val, max_val
        finally:
            conn.close()

    def save_contraction_events(self, analysis_id: str, events: list[dict]) -> None:
        """Store contraction events for an analysis."""
        from uuid import uuid4

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Clear existing events for this analysis
            cursor.execute(
                "DELETE FROM contraction_events WHERE analysis_id = ?", (analysis_id,)
            )

            # Insert new events
            created_at = datetime.now().isoformat()
            for event in events:
                event_id = str(uuid4())
                t_range = event.get("t_range_frames", (0, 0))
                y_range = event.get("y_range_idx", (0, 0))
                line_fit = event.get("line_fit", {})

                cursor.execute(
                    """
                    INSERT INTO contraction_events (
                        id, analysis_id, event_label, n_pixels, threshold_used,
                        t_range_start, t_range_end, y_range_start, y_range_end,
                        duration_s, height_phys, velocity_phys_per_s,
                        line_fit_a, line_fit_b, area_exact, area_triangle, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        event_id,
                        analysis_id,
                        event.get("label", 0),
                        event.get("n_pixels", 0),
                        event.get("threshold_used", 0.0),
                        t_range[0],
                        t_range[1],
                        y_range[0],
                        y_range[1],
                        event.get("duration_s", 0.0),
                        event.get("height_phys", 0.0),
                        event.get("velocity_phys_per_s", 0.0),
                        line_fit.get("a_idx_per_frame", 0.0),
                        line_fit.get("b", 0.0),
                        event.get("area_exact", 0.0),
                        event.get("area_triangle", 0.0),
                        created_at,
                    ),
                )

            conn.commit()
        finally:
            conn.close()

    def get_contraction_events(self, analysis_id: str) -> list[dict]:
        """Retrieve contraction events for an analysis."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT 
                    id, event_label, n_pixels, threshold_used,
                    t_range_start, t_range_end, y_range_start, y_range_end,
                    duration_s, height_phys, velocity_phys_per_s,
                    line_fit_a, line_fit_b, area_exact, area_triangle, created_at
                FROM contraction_events
                WHERE analysis_id = ?
                ORDER BY t_range_start
            """,
                (analysis_id,),
            )

            rows = cursor.fetchall()
            events = []
            for row in rows:
                events.append(
                    {
                        "id": row["id"],
                        "label": int(row["event_label"]),
                        "n_pixels": int(row["n_pixels"]),
                        "threshold_used": float(row["threshold_used"]),
                        "t_range_frames": (
                            int(row["t_range_start"]),
                            int(row["t_range_end"]),
                        ),
                        "y_range_idx": (
                            int(row["y_range_start"]),
                            int(row["y_range_end"]),
                        ),
                        "duration_s": float(row["duration_s"]),
                        "height_phys": float(row["height_phys"]),
                        "velocity_phys_per_s": float(row["velocity_phys_per_s"]),
                        "line_fit": {
                            "a_idx_per_frame": float(row["line_fit_a"]),
                            "b": float(row["line_fit_b"]),
                        },
                        "area_exact": float(row["area_exact"]),
                        "area_triangle": float(row["area_triangle"]),
                        "created_at": row["created_at"],
                    }
                )

            return events
        finally:
            conn.close()

    def clear_contraction_events(self, analysis_id: str) -> None:
        """Clear contraction events for an analysis."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM contraction_events WHERE analysis_id = ?", (analysis_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def contraction_events_exist(self, analysis_id: str) -> bool:
        """Check if contraction events exist for an analysis."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT 1 FROM contraction_events WHERE analysis_id = ? LIMIT 1",
                (analysis_id,),
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()


class VideoLabelDB:
    """Database operations for persisted video display names."""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def set_display_name(self, video_id: str, display_name: Optional[str]) -> None:
        """Set or clear a custom display name for a video."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            if display_name is None:
                cursor.execute("DELETE FROM video_labels WHERE video_id = ?", (video_id,))
            else:
                cursor.execute(
                    """
                    INSERT INTO video_labels (video_id, display_name, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        display_name = excluded.display_name,
                        updated_at = excluded.updated_at
                """,
                    (video_id, display_name, datetime.now().isoformat()),
                )
            conn.commit()
        finally:
            conn.close()

    def get_display_name(self, video_id: str) -> Optional[str]:
        """Get custom display name for one video."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT display_name FROM video_labels WHERE video_id = ?",
                (video_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return str(row["display_name"])
        finally:
            conn.close()

    def list_display_names(self, video_ids: list[str]) -> dict[str, str]:
        """Get display names for the provided video IDs."""
        if not video_ids:
            return {}

        placeholders = ",".join("?" for _ in video_ids)
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT video_id, display_name FROM video_labels WHERE video_id IN ({placeholders})",
                tuple(video_ids),
            )
            rows = cursor.fetchall()
            return {str(row["video_id"]): str(row["display_name"]) for row in rows}
        finally:
            conn.close()


class MultiViewSessionDB:
    """Database operations for persisted multi-view sessions."""

    def __init__(self, db_path: str = DATABASE_PATH):
        """Initialize with database path."""
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def create_session(self, session: dict) -> None:
        """Insert a new multi-view session."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO multi_view_sessions
                (id, name, left_analysis_id, right_analysis_id, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    session["id"],
                    session["name"],
                    session["left_analysis_id"],
                    session["right_analysis_id"],
                    session["created_at"],
                    json.dumps(session.get("metadata"))
                    if session.get("metadata")
                    else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_session(self, session_id: str) -> Optional[dict]:
        """Retrieve a multi-view session by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT id, name, left_analysis_id, right_analysis_id, created_at, metadata
                FROM multi_view_sessions
                WHERE id = ?
            """,
                (session_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            return {
                "id": row["id"],
                "name": row["name"],
                "left_analysis_id": row["left_analysis_id"],
                "right_analysis_id": row["right_analysis_id"],
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
            }
        finally:
            conn.close()

    def list_sessions(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List all multi-view sessions."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT id, name, left_analysis_id, right_analysis_id, created_at, metadata
                FROM multi_view_sessions
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """,
                (limit, offset),
            )

            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "left_analysis_id": row["left_analysis_id"],
                    "right_analysis_id": row["right_analysis_id"],
                    "created_at": row["created_at"],
                    "metadata": json.loads(row["metadata"])
                    if row["metadata"]
                    else None,
                }
                for row in rows
            ]
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> None:
        """Delete a multi-view session."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM multi_view_sessions WHERE id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    def update_session_name(self, session_id: str, name: str) -> bool:
        """Update a persisted session name."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "UPDATE multi_view_sessions SET name = ? WHERE id = ?",
                (name, session_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
