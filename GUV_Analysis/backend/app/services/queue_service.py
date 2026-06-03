import uuid
import logging
import os
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Task, TaskRun
from app.worker.tasks import run_analysis_task, run_video_task
from app.services.autoexp_callback_service import maybe_send_autoexp_callback
from app.core.config import settings

logger = logging.getLogger(__name__)

class QueueService:
    """
    Service module for managing the task queue.
    Ensures FIFO execution order by leveraging the underlying Celery worker configuration (concurrency=1).
    Provides methods for task submission, status tracking, and queue monitoring.
    """

    @staticmethod
    def _cleanup_cancel_markers(task_id: str) -> None:
        images_dir = os.path.join(settings.RUN_BASE_DIR, str(task_id), "images")
        try:
            if not os.path.isdir(images_dir):
                return
            for name in os.listdir(images_dir):
                if name == "cancel.global" or name.startswith("cancel."):
                    marker_path = os.path.join(images_dir, name)
                    try:
                        os.remove(marker_path)
                        logger.info("Removed stale cancel marker: %s", marker_path)
                    except FileNotFoundError:
                        continue
                    except Exception as exc:
                        logger.warning("Failed to remove cancel marker %s: %s", marker_path, exc)
        except Exception as exc:
            logger.warning("Failed to scan cancel markers for task %s: %s", task_id, exc)

    @staticmethod
    def submit_task(
        db: Session, 
        task: Task, 
        mode: str, 
        params_snapshot: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Submits a task to the execution queue.
        If no task is running, it will be picked up immediately by the worker.
        If a task is running, it stays in the queue (FIFO).
        
        Args:
            db: Database session
            task: Task model instance
            mode: 'debug', 'final' or 'video'
            params_snapshot: Snapshot of parameters for this run
            
        Returns:
            run_id: The UUID string of the created run
        """
        
        # 1. Create TaskRun record (Status: QUEUED)
        run_id = uuid.uuid4()
        new_run = TaskRun(
            id=run_id,
            task_id=task.id,
            run_mode=mode,
            status="QUEUED",
            params_snapshot=params_snapshot or {}
        )
        db.add(new_run)
        
        # 2. Update Task Status
        task.run_id_current = run_id
        task.status = "QUEUED"
        task.cancel_requested = False
        task.last_error = None # Clear previous error
        QueueService._cleanup_cancel_markers(str(task.id))
        
        db.commit()
        
        logger.info(f"Task {task.id} submitted to queue. RunID: {run_id}, Mode: {mode}")

        # 3. Dispatch to Celery (Async)
        # Celery handles the FIFO queueing mechanism.
        try:
            if mode == "video":
                run_video_task.delay(str(task.id), str(run_id))
            else:
                run_analysis_task.delay(str(task.id), mode, str(run_id))
        except Exception as e:
            logger.error(f"Failed to dispatch task {task.id} to Celery: {e}")
            new_run.status = "FAILED"
            task.status = "FAILED"
            task.last_error = f"Queue Dispatch Error: {str(e)}"
            db.commit()
            maybe_send_autoexp_callback(
                db=db,
                task=task,
                task_run=new_run,
                mode=mode,
                run_dir=None,
                error_code="GUV_QUEUE_DISPATCH_ERROR",
                error_message=task.last_error,
            )
            raise e

        return str(run_id)

    @staticmethod
    def get_queue_status(db: Session) -> Dict[str, Any]:
        """
        Returns the current state of the task queue.
        - queued: Number of tasks waiting to start
        - running: Number of tasks currently executing
        - total_active: Sum of queued and running
        """
        queued_count = db.query(Task).filter(Task.status == "QUEUED").count()
        
        # Running tasks might be RUNNING_DEBUG or RUNNING_FINAL
        running_count = db.query(Task).filter(Task.status.like("RUNNING%")).count()
        
        return {
            "queued": queued_count,
            "running": running_count,
            "total_active": queued_count + running_count
        }

    @staticmethod
    def get_next_queued_task(db: Session) -> Optional[Task]:
        """
        Preview the next task in the queue (based on creation time of the active run).
        This is mainly for monitoring/UI, as Celery manages the actual pop order.
        """
        # Find the oldest task with status QUEUED
        # We use Task.updated_at or we should look at the associated TaskRun.created_at
        # Ideally, we look at TaskRun where status='QUEUED' order by created_at asc
        next_run = db.query(TaskRun).filter(TaskRun.status == "QUEUED")\
            .order_by(TaskRun.created_at.asc()).first()
            
        if next_run:
            return db.query(Task).filter(Task.id == next_run.task_id).first()
        return None

    @staticmethod
    def get_queue_position(db: Session, task_id: str) -> Dict[str, Any]:
        """
        Get the position of a specific task in the queue.
        Returns:
            {
                "status": "QUEUED" | "RUNNING" | "NOT_QUEUED",
                "position": int (1-based index, 0 if running or not queued),
                "total_queued": int
            }
        """
        # 1. Get the current active run for this task
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or not task.run_id_current:
            return {"status": "NOT_QUEUED", "position": 0, "total_queued": 0}
            
        current_run = db.query(TaskRun).filter(TaskRun.id == task.run_id_current).first()
        if not current_run:
            return {"status": "NOT_QUEUED", "position": 0, "total_queued": 0}
            
        # 2. Check status
        if current_run.status.startswith("RUNNING"):
            return {"status": "RUNNING", "position": 0, "total_queued": 0}
            
        if current_run.status != "QUEUED":
            return {"status": "NOT_QUEUED", "position": 0, "total_queued": 0}
            
        # 3. Calculate position
        # Count how many QUEUED runs have created_at < current_run.created_at
        position = db.query(TaskRun).filter(
            TaskRun.status == "QUEUED",
            TaskRun.created_at < current_run.created_at
        ).count() + 1
        
        total_queued = db.query(TaskRun).filter(TaskRun.status == "QUEUED").count()
        
        return {
            "status": "QUEUED", 
            "position": position, 
            "total_queued": total_queued
        }
