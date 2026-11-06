"""Pipeline step runner with status tracking and error isolation.

Wraps each pipeline step, saves status (running → success/failed) and error
message to DB. Never deletes previous data on failure.
"""

import logging
import traceback
from datetime import datetime, timezone
from typing import Callable, Any

from backend.schemas import LessonRun, StepName, StepStatus
from backend.db import get_db

logger = logging.getLogger(__name__)


class StepRunner:
    """Executes a pipeline step with status tracking and error handling."""

    def __init__(self, run: LessonRun):
        self.run = run
        self.db = get_db()

    async def execute(
        self,
        step_name: StepName,
        func: Callable[..., Any],
        *args,
        **kwargs,
    ) -> Any:
        """Execute a step function with status tracking.

        Args:
            step_name: Which pipeline step this is.
            func: The async or sync function to run.
            *args, **kwargs: Arguments to pass to the function.

        Returns:
            The result of the function.

        Raises:
            The original exception if the step fails (after saving status).
        """
        step = self.run.get_step(step_name)
        if step is None:
            raise ValueError(f"Unknown step: {step_name}")

        # Mark as running
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc)
        step.error_message = ""
        self.run.status = step_name
        self._save()

        logger.info(f"Step {step_name.value} started for run {self.run.id}")

        try:
            # Execute the step
            import asyncio
            if asyncio.iscoroutinefunction(func):
                result = await func(self.run, *args, **kwargs)
            else:
                result = func(self.run, *args, **kwargs)

            # Mark as success
            step.status = StepStatus.SUCCESS
            step.completed_at = datetime.now(timezone.utc)
            self._save()

            elapsed = (step.completed_at - step.started_at).total_seconds()
            logger.info(f"Step {step_name.value} completed in {elapsed:.1f}s for run {self.run.id}")

            return result

        except Exception as e:
            # Mark as failed but NEVER delete previous data
            step.status = StepStatus.FAILED
            step.completed_at = datetime.now(timezone.utc)
            step.error_message = str(e)
            self.run.error_log.append(
                f"[{datetime.now(timezone.utc).isoformat()}] {step_name.value}: {str(e)}"
            )
            self._save()

            logger.error(
                f"Step {step_name.value} failed for run {self.run.id}: {e}\n"
                f"{traceback.format_exc()}"
            )
            raise

    def _save(self):
        """Persist current run state to database."""
        self.run.updated_at = datetime.now(timezone.utc)
        self.db.save_run(self.run)

