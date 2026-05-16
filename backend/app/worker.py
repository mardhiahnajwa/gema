"""
Gema Celery Worker
Handles background AI task execution and scheduling.
"""

import os
from datetime import datetime

from celery import Celery
from celery.utils.log import get_task_logger

from app.config import settings

logger = get_task_logger(__name__)

# ── Celery app ────────────────────────────────────────────────────────────────
celery_app = Celery(
    "gema",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
)


# ── Helper: set AI provider env keys ─────────────────────────────────────────
def _set_keys() -> None:
    key_map = {
        "OPENAI_API_KEY": settings.OPENAI_API_KEY,
        "ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY,
        "GEMINI_API_KEY": settings.GOOGLE_API_KEY,
        "MISTRAL_API_KEY": settings.MISTRAL_API_KEY,
        "COHERE_API_KEY": settings.COHERE_API_KEY,
        "GROQ_API_KEY": settings.GROQ_API_KEY,
        "TOGETHERAI_API_KEY": settings.TOGETHER_API_KEY,
        "HUGGINGFACE_API_KEY": settings.HUGGINGFACE_API_KEY,
    }
    for var, val in key_map.items():
        if val:
            os.environ[var] = val


# ── Tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="gema.execute_task", bind=True, max_retries=2)
def execute_task(self, task_id: str) -> dict:
    """
    Run an AI task:
    1. Load task + agent from DB
    2. Render prompt template with input_data
    3. Call litellm for completion
    4. Save result
    """
    import litellm
    from sqlalchemy.orm import Session, joinedload

    from app.database import SyncSessionLocal
    from app.models.task import Task

    _set_keys()

    with SyncSessionLocal() as db:
        task: Task = (
            db.query(Task)
            .options(joinedload(Task.agent))
            .filter(Task.id == task_id)
            .first()
        )

        if not task:
            return {"error": f"Task {task_id} not found"}

        task.status = "running"
        db.commit()

        try:
            # Build prompt from template + input_data
            prompt = task.prompt_template
            for key, value in (task.input_data or {}).items():
                prompt = prompt.replace(f"{{{{{key}}}}}", str(value))

            messages = []
            model = "gpt-4o"
            temperature = 0.7
            max_tokens = 4096

            if task.agent:
                model = task.agent.model
                temperature = task.agent.temperature
                max_tokens = task.agent.max_tokens
                if task.agent.system_prompt:
                    messages.append({"role": "system", "content": task.agent.system_prompt})

            messages.append({"role": "user", "content": prompt})

            kwargs: dict = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            response = litellm.completion(**kwargs)
            output = response.choices[0].message.content

            task.status = "completed"
            task.output = output
            task.completed_at = datetime.utcnow()
            db.commit()

            logger.info("Task %s completed successfully", task_id)
            return {"status": "completed", "output": output}

        except Exception as exc:
            logger.exception("Task %s failed: %s", task_id, exc)
            task.status = "failed"
            task.error_message = str(exc)
            task.completed_at = datetime.utcnow()
            db.commit()

            # Retry on transient errors
            try:
                raise self.retry(exc=exc, countdown=30)
            except self.MaxRetriesExceededError:
                return {"status": "failed", "error": str(exc)}


@celery_app.task(name="gema.execute_pipeline", bind=True, max_retries=1)
def execute_pipeline(self, run_id: str) -> dict:
    """
    Run all steps in a Pipeline sequentially, passing outputs forward.
    """
    from app.database import SyncSessionLocal
    from app.services.pipeline_service import execute_pipeline_run

    _set_keys()

    with SyncSessionLocal() as db:
        try:
            execute_pipeline_run(run_id, db)
            return {"status": "completed", "run_id": run_id}
        except Exception as exc:
            logger.exception("Pipeline run %s failed: %s", run_id, exc)
            try:
                raise self.retry(exc=exc, countdown=10)
            except self.MaxRetriesExceededError:
                return {"status": "failed", "error": str(exc)}
