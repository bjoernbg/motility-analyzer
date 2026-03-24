"""Background task manager for video analysis."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict
import logging

from .analysis import process_video
from .config import ANALYSIS_MAX_WORKERS, ANALYSIS_PERSIST_EVERY_N_FRAMES
from .models import (
    Analysis,
    AnalysisParameters,
    ContractionDetectionParameters,
    FrameData,
)
from .display_settings import load_video_display_settings
from .storage import AnalysisStorage, ResultsStorage, VideoStorage, clear_heatmap_cache
from .contraction_detection import (
    CONTRACTION_DETECTION_VERSION_V2,
    calculate_physical_spacing,
    detect_contractions_with_parameters,
)
from .metadata import get_video_metadata

logger = logging.getLogger("uvicorn.error")


class TaskManager:
    """Manages background analysis tasks."""

    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.analyses: Dict[str, Analysis] = {}
        self.analysis_storage = AnalysisStorage()
        self.results_storage = ResultsStorage()
        self.persist_every_n_frames = max(1, ANALYSIS_PERSIST_EVERY_N_FRAMES)
        self.executor = ThreadPoolExecutor(max_workers=ANALYSIS_MAX_WORKERS)
        logger.info(
            "TaskManager configured with %s workers and DB persist interval %s frames",
            ANALYSIS_MAX_WORKERS,
            self.persist_every_n_frames,
        )

    def register_analysis(self, analysis: Analysis):
        """Register a new analysis and persist to database."""
        self.analyses[analysis.id] = analysis
        # Persist to database
        self.analysis_storage.create_analysis(analysis)

    def get_analysis(self, analysis_id: str) -> Analysis | None:
        """Get analysis by ID, loading from database if not in memory."""
        # Check in-memory cache first
        if analysis_id in self.analyses:
            return self.analyses[analysis_id]

        # Load from database
        analysis = self.analysis_storage.get_analysis(analysis_id)
        if analysis:
            self.analyses[analysis_id] = analysis
        return analysis

    def _run_analysis_in_thread(
        self,
        video_id: str,
        parameters: AnalysisParameters,
        analysis: Analysis,
        analysis_id: str,
        start_frame: int = 0,
        existing_results=None,
    ) -> tuple:
        """Synchronous wrapper to run async process_video in a separate thread's event loop.

        This function runs in a thread pool executor and creates its own event loop
        to run the async process_video function.

        Args:
            video_id: ID of the video to process
            parameters: Analysis parameters
            analysis: Analysis object to update
            analysis_id: ID of the analysis
            start_frame: Frame number to start processing from (for resuming)
            existing_results: Existing results to load previous frame paths from (for resuming)

        Returns:
            Tuple of (AnalysisResult, total_frames) or raises exception
        """
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            total_frames_var: int | None = None
            pending_frames: list[FrameData] = []
            last_seen_frame = 0
            last_seen_progress = 0.0

            def flush_pending_frames(
                total_frames: int, current_frame: int, progress: float
            ) -> None:
                """Persist buffered frames and progress in one batched DB write."""
                nonlocal pending_frames
                if pending_frames:
                    self.results_storage.append_frames_to_results(
                        analysis_id=analysis_id,
                        frames=pending_frames,
                        total_frames=total_frames,
                        processed_count=current_frame,
                    )
                    pending_frames = []

                self.analysis_storage.update_analysis(analysis_id, progress=progress)

            async def progress_callback(
                progress: float,
                current_frame: int,
                total_frames: int,
                frame_data: FrameData,
            ):
                """Update progress and save frame data incrementally."""
                nonlocal total_frames_var, last_seen_frame, last_seen_progress
                analysis.progress = progress
                total_frames_var = total_frames

                if analysis.status == "cancelled":
                    raise asyncio.CancelledError()

                pending_frames.append(frame_data)
                last_seen_frame = current_frame
                last_seen_progress = progress

                if (
                    len(pending_frames) >= self.persist_every_n_frames
                    or current_frame >= total_frames
                ):
                    flush_pending_frames(total_frames, current_frame, progress)

                # Check if analysis was cancelled
                if analysis.status == "cancelled":
                    raise asyncio.CancelledError()

            # Run the async process_video in this thread's event loop
            result = loop.run_until_complete(
                process_video(
                    video_id,
                    parameters,
                    progress_callback,
                    start_frame,
                    existing_results,
                    collect_per_frame=False,
                )
            )
            if total_frames_var is not None and pending_frames:
                flush_pending_frames(
                    total_frames_var, last_seen_frame, last_seen_progress
                )
            return result
        except Exception:
            if (
                total_frames_var is not None
                and pending_frames
                and analysis.status != "cancelled"
            ):
                flush_pending_frames(
                    total_frames_var, last_seen_frame, last_seen_progress
                )
            raise
        finally:
            loop.close()

    async def stop_analysis(self, analysis_id: str) -> bool:
        """Stop a running analysis."""
        analysis = self.analyses.get(analysis_id)
        if not analysis:
            return False

        # Check if analysis is actually running
        if analysis.status != "processing":
            return False

        # Cancel the task if it exists
        if analysis_id in self.tasks:
            task = self.tasks[analysis_id]
            task.cancel()
            del self.tasks[analysis_id]

        # Update analysis status
        analysis.status = "cancelled"
        analysis.progress = analysis.progress  # Keep current progress

        # Persist to database
        self.analysis_storage.update_analysis(analysis_id, status="cancelled")

        return True

    async def start_analysis(
        self,
        analysis_id: str,
        video_id: str,
        parameters: AnalysisParameters,
    ):
        """Start background analysis task.

        Args:
            analysis_id: ID of the analysis
            video_id: ID of the video to process
            parameters: Analysis parameters
        """
        analysis = self.analyses.get(analysis_id)
        if not analysis:
            return

        # Check if results already exist and are complete
        if self.results_storage.results_exist(analysis_id):
            # Check if analysis is actually complete
            existing_results = self.results_storage.load_results(analysis_id)
            if existing_results and existing_results.global_data:
                total_frames = existing_results.global_data.get("total_frames", 0)
                processed_frames = len(existing_results.per_frame)
                if processed_frames >= total_frames and total_frames > 0:
                    analysis.status = "completed"
                    analysis.progress = 100.0
                    self.analysis_storage.update_analysis(
                        analysis_id, status="completed", progress=100.0
                    )
                    return

        # Always start from frame 0
        start_frame = 0
        existing_results = None

        analysis.status = "processing"
        self.analysis_storage.update_analysis(analysis_id, status="processing")

        try:
            # Run analysis in a separate thread to avoid blocking the event loop
            results, _total_frames = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._run_analysis_in_thread,
                video_id,
                parameters,
                analysis,
                analysis_id,
                start_frame,
                existing_results,
            )

            # Check if task was cancelled
            if analysis.status == "cancelled":
                return

            analysis.results_path = (
                analysis_id  # Store analysis_id instead of file path
            )
            analysis.status = "completed"
            analysis.progress = 100.0

            # Finalize results with global_data calculation (this also updates status and completed_at)
            self.results_storage.finalize_results(
                analysis_id, results, skip_frame_upsert=True
            )

            # Clear cached heatmap data to force regeneration with complete results
            clear_heatmap_cache(analysis_id, video_id)

            # Auto-run contraction detection with default parameters
            try:
                logger.info(
                    f"Auto-running contraction detection for analysis {analysis_id}..."
                )
                # Check if heatmap data exists
                db = self.results_storage.db
                matrix, _, _ = db.build_heatmap_matrix(analysis_id)

                if matrix.size > 0:
                    logger.info(f"Heatmap matrix shape: {matrix.shape}")
                    # Get video metadata for FPS
                    video_path = VideoStorage.get_video_path(video_id)
                    if video_path and video_path.exists():
                        try:
                            video_metadata = get_video_metadata(video_path)
                            fps = video_metadata.fps
                            dt = 1.0 / fps if fps > 0 else 1.0
                            display_settings = load_video_display_settings(video_path)

                            # Transpose matrix: (frames, points) -> (points, frames)
                            thickness = matrix.T

                            # Calculate physical spacing
                            dy = calculate_physical_spacing(
                                analysis_id,
                                self.results_storage,
                                pixel_to_mm_factor=display_settings.pixel_to_mm_factor,
                            )

                            # Run contraction detection with default parameters
                            default_params = ContractionDetectionParameters()
                            events, _, _ = detect_contractions_with_parameters(
                                thickness=thickness,
                                dt=dt,
                                parameters=default_params,
                                dy=dy,
                                pixel_to_mm_factor=display_settings.pixel_to_mm_factor,
                            )

                            # Store events in database
                            db.save_contraction_events(
                                analysis_id,
                                events,
                                parameters_used=default_params,
                                detection_version=CONTRACTION_DETECTION_VERSION_V2,
                            )
                            logger.info(
                                f"Auto-detected {len(events)} contraction events for analysis {analysis_id}"
                            )
                        except Exception as e:
                            # Log error but don't fail the analysis
                            logger.warning(
                                f"Auto contraction detection failed for analysis {analysis_id}: {str(e)}"
                            )
                else:
                    logger.info(
                        f"No heatmap data available for analysis {analysis_id}, skipping contraction detection"
                    )
            except Exception as e:
                # Log error but don't fail the analysis
                logger.warning(
                    f"Auto contraction detection check failed for analysis {analysis_id}: {str(e)}"
                )

        except asyncio.CancelledError:
            # Task was cancelled
            analysis.status = "cancelled"
            self.analysis_storage.update_analysis(analysis_id, status="cancelled")
            raise
        except Exception as e:
            # Only set to failed if not already cancelled
            if analysis.status != "cancelled":
                analysis.status = "failed"
                error_message = str(e)
                self.analysis_storage.update_analysis(
                    analysis_id, status="failed", error_message=error_message
                )

        finally:
            # Clean up task
            if analysis_id in self.tasks:
                del self.tasks[analysis_id]


# Global task manager instance
task_manager = TaskManager()
