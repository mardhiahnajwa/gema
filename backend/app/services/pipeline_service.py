"""
Pipeline execution engine.

Each step can:
  - Reference a saved Agent (inherits model, system_prompt, temp, max_tokens)
  - Override any of those per-step
  - Use template variables in input_template:
      {{user_input}}            — original user input to the pipeline run
      {{previous_output}}       — output of the immediately preceding step
      {{step_<step_id>_output}} — output of any specific step by its id
      {{long_term_memories}}    — relevant memories retrieved from MongoDB
      {{short_term_summary}}    — summary of last N pipeline runs for this scope+user

Memory behaviour
  - memory_enabled=True  on the pipeline → memories are retrieved before step 1
    and stored after the run completes.
  - memory_scope='pipeline' → memories are scoped to this pipeline (isolated).
  - memory_scope='global'   → memories are shared across all pipelines for the user.
"""

from datetime import datetime
from typing import Dict, List, Optional

import litellm
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent import Agent
from app.models.pipeline import Pipeline, PipelineRun


def _set_keys(db: Session) -> None:
    """Apply API keys: DB-stored values take priority over env/config defaults."""
    import os
    # First, apply any keys already in env (from config / docker-compose)
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
    # Then override with keys saved through the Settings UI (higher priority)
    try:
        from app.services.settings_service import apply_all_settings_to_env_sync
        apply_all_settings_to_env_sync(db)
    except Exception:
        pass


def _render_template(
    template: str,
    user_input: str,
    step_outputs: Dict[str, str],
    long_term_block: str = "",
    short_term_block: str = "",
) -> str:
    """Replace all {{variable}} tokens in a step input_template."""
    result = template
    result = result.replace("{{user_input}}", user_input or "")
    previous = list(step_outputs.values())[-1] if step_outputs else ""
    result = result.replace("{{previous_output}}", previous)
    result = result.replace("{{long_term_memories}}", long_term_block)
    result = result.replace("{{short_term_summary}}", short_term_block)
    for step_id, output in step_outputs.items():
        result = result.replace(f"{{{{step_{step_id}_output}}}}", output)
    return result


def _get_memory_scope_id(pipeline: Pipeline) -> str:
    """Return the MongoDB agent_id key to use for this pipeline's memories."""
    scope = getattr(pipeline, "memory_scope", "pipeline") or "pipeline"
    if scope == "global":
        return "pipeline_global"
    return f"pipeline_{pipeline.id}"


def _fetch_short_term_summary(pipeline: Pipeline, user_id: str, db: Session) -> str:
    """
    Pull the last 3 completed runs for this pipeline+user and build a
    brief summary string that can be injected as {{short_term_summary}}.
    """
    try:
        runs: List[PipelineRun] = (
            db.query(PipelineRun)
            .filter(
                PipelineRun.pipeline_id == pipeline.id,
                PipelineRun.status == "completed",
                PipelineRun.user_id == (user_id or ""),
            )
            .order_by(PipelineRun.created_at.desc())
            .limit(3)
            .all()
        )
        if not runs:
            return ""
        parts = []
        for r in reversed(runs):
            snippet = (r.final_output or "")[:200].replace("\n", " ")
            parts.append(f"- Input: {(r.user_input or '')[:80]} → Output: {snippet}")
        return "Recent pipeline runs for this user:\n" + "\n".join(parts)
    except Exception:
        return ""


def execute_pipeline_run(run_id: str, db: Session) -> None:
    """
    Synchronous execution (called from Celery worker).
    Runs each step sequentially, passing outputs and memories forward.
    """
    _set_keys(db)

    run: Optional[PipelineRun] = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        return

    pipeline: Optional[Pipeline] = db.query(Pipeline).filter(Pipeline.id == run.pipeline_id).first()
    if not pipeline:
        run.status = "failed"
        run.error_message = "Pipeline not found"
        db.commit()
        return

    run.status = "running"
    db.commit()

    step_outputs: Dict[str, str] = {}

    # ── Memory retrieval (before first step) ──────────────────────────────────
    memory_enabled = getattr(pipeline, "memory_enabled", True)
    long_term_block = ""
    short_term_block = ""

    if memory_enabled:
        scope_id = _get_memory_scope_id(pipeline)
        user_id = run.user_id or ""
        query = run.user_input or ""

        try:
            from app.services.memory_service import (
                sync_retrieve_long_term_memories,
            )
            memories = sync_retrieve_long_term_memories(scope_id, user_id, query)
            if memories:
                formatted = "\n".join(f"- {m}" for m in memories)
                long_term_block = (
                    "## Long-Term Memory (recalled from past pipeline runs)\n"
                    + formatted
                )
        except Exception:
            pass

        short_term_block = _fetch_short_term_summary(pipeline, user_id, db)

    try:
        steps = pipeline.steps or []
        for i, step in enumerate(steps):
            step_id = step.get("id", f"step-{i}")

            # Resolve model/prompt — agent overrides take priority
            model = step.get("model", "gpt-4o")
            system_prompt = step.get("system_prompt", "")
            temperature = float(step.get("temperature", 0.7))
            max_tokens = int(step.get("max_tokens", 2048))

            agent_id = step.get("agent_id")
            if agent_id:
                agent: Optional[Agent] = db.query(Agent).filter(Agent.id == agent_id).first()
                if agent:
                    model = agent.model
                    system_prompt = agent.system_prompt or system_prompt
                    temperature = agent.temperature
                    max_tokens = agent.max_tokens

            # Inject long-term memories into system prompt of the first step
            # (subsequent steps already receive the enriched previous_output)
            effective_system = system_prompt
            if memory_enabled and i == 0 and long_term_block:
                effective_system = (
                    (effective_system + "\n\n" if effective_system else "")
                    + long_term_block
                    + "\n\nDraw on these memories when relevant but do not repeat them verbatim."
                )

            # Build messages
            input_template = step.get("input_template", "{{user_input}}")
            user_content = _render_template(
                input_template,
                run.user_input or "",
                step_outputs,
                long_term_block=long_term_block if memory_enabled else "",
                short_term_block=short_term_block if memory_enabled else "",
            )

            messages = []
            if effective_system:
                messages.append({"role": "system", "content": effective_system})
            messages.append({"role": "user", "content": user_content})

            # Call the model
            response = litellm.completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            output = response.choices[0].message.content or ""
            step_outputs[step_id] = output

            # Persist step output incrementally so UI can poll progress
            run.step_outputs = dict(step_outputs)
            db.commit()

        run.status = "completed"
        run.final_output = list(step_outputs.values())[-1] if step_outputs else ""
        run.completed_at = datetime.utcnow()

    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.utcnow()

    run.step_outputs = step_outputs
    db.commit()

    # ── Memory storage (after run completes) ──────────────────────────────────
    if memory_enabled and run.status == "completed" and run.final_output:
        try:
            from app.services.memory_service import sync_store_pipeline_memory
            sync_store_pipeline_memory(
                scope_id=_get_memory_scope_id(pipeline),
                user_id=run.user_id or "",
                run_id=str(run.id),
                user_input=run.user_input or "",
                final_output=run.final_output or "",
                step_outputs=step_outputs,
            )
        except Exception:
            pass

