"""Background task manager for video analysis."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from .analysis import process_video
from .models import Analysis, AnalysisParameters, FrameData
from .storage import AnalysisStorage, ResultsStorage


class TaskManager:
    """Manages background analysis tasks."""
    
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.analyses: Dict[str, Analysis] = {}
        self.analysis_storage = AnalysisStorage()
        self.results_storage = ResultsStorage()
        self.executor = ThreadPoolExecutor(max_workers=1)
    
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
        existing_results = None,
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
            
            async def progress_callback(progress: float, current_frame: int, total_frames: int, frame_data: FrameData):
                """Update progress and save frame data incrementally."""
                nonlocal total_frames_var
                analysis.progress = progress
                total_frames_var = total_frames
                
                # Persist progress to database (every frame for accurate polling)
                self.analysis_storage.update_analysis(analysis_id, progress=progress)
                
                # Save frame data incrementally to database
                self.results_storage.append_frame_to_results(analysis_id, frame_data, total_frames)
                
                # Check if analysis was cancelled
                if analysis.status == "cancelled":
                    raise asyncio.CancelledError()
            
            # Run the async process_video in this thread's event loop
            return loop.run_until_complete(
                process_video(video_id, parameters, progress_callback, start_frame, existing_results)
            )
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
        resume: bool = False,
    ):
        """Start background analysis task.
        
        Args:
            analysis_id: ID of the analysis
            video_id: ID of the video to process
            parameters: Analysis parameters
            resume: If True, resume from last analyzed frame if partial results exist
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
                    self.analysis_storage.update_analysis(analysis_id, status="completed", progress=100.0)
                    return
        
        # Determine if we should resume
        start_frame = 0
        existing_results = None
        if resume:
            # Get last analyzed frame
            last_frame = self.results_storage.db.get_last_analyzed_frame(analysis_id)
            if last_frame is not None:
                start_frame = last_frame + 1  # Start from next frame
                # Load existing results to get previous frame paths
                existing_results = self.results_storage.load_results(analysis_id)
        
        analysis.status = "processing"
        self.analysis_storage.update_analysis(analysis_id, status="processing")
        
        try:
            # Run analysis in a separate thread to avoid blocking the event loop
            results, total_frames_var = await asyncio.get_event_loop().run_in_executor(
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
            
            analysis.results_path = analysis_id  # Store analysis_id instead of file path
            analysis.status = "completed"
            analysis.progress = 100.0
            
            # Finalize results with global_data calculation (this also updates status and completed_at)
            self.results_storage.finalize_results(analysis_id, results)
            
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
                self.analysis_storage.update_analysis(analysis_id, status="failed", error_message=error_message)
        
        finally:
            # Clean up task
            if analysis_id in self.tasks:
                del self.tasks[analysis_id]


# Global task manager instance
task_manager = TaskManager()

