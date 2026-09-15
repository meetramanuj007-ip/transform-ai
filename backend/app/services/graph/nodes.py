from __future__ import annotations

import importlib
import json
from typing import Any
import asyncio
import logging
logger = logging.getLogger(__name__)

from sqlalchemy import select

from app.db.models import (
    CanonicalKnowledgeRow,
    FactRow,
    GeneratedOutput,
    Source,
    SourceChunk,
    TransformationJob,
    ValidationResult,
)
from app.db.models import SessionLocal
from app.schemas import (
    CanonicalFact,
    CanonicalKnowledge,
    Citation,
    GeneratedArtifact,
    TransformationPlan,
    ValidationReport,
)
from app.services.facts.registry import FactRegistry
from app.services.ingestion.store import extract_source
from app.services.llm.provider import get_provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db():
    return SessionLocal()


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _get_source(db, source_id: str) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise ValueError(f"Source not found: {source_id}")
    return source


def _get_job(db, job_id: str) -> TransformationJob:
    job = db.get(TransformationJob, job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    return job


def _update_job(db, job_id: str, **values):
    job = _get_job(db, job_id)
    for key, value in values.items():
        setattr(job, key, value)
    db.commit()


def _chunks_for_source(db, source_id: str) -> list[SourceChunk]:
    return list(
        db.scalars(
            select(SourceChunk)
            .where(SourceChunk.source_id == source_id)
            .order_by(SourceChunk.id)
        )
    )


def _chunks_text(chunks: list[SourceChunk], max_chars: int = 50000) -> str:
    parts = []

    for chunk in chunks:
        header = f"[{chunk.chunk_id}"
        if chunk.page is not None:
            header += f", page {chunk.page}"
        if chunk.section:
            header += f", section {chunk.section}"
        header += "]"

        parts.append(f"{header}\n{chunk.text}")

    return "\n\n".join(parts)[:max_chars]


def _registry_from_state(state) -> FactRegistry:
    facts = []

    for item in state.get("fact_registry") or []:
        try:
            facts.append(CanonicalFact.model_validate(item))
        except Exception:
            continue

    return FactRegistry(facts)


def _save_facts(db, job_id: str, registry: FactRegistry):
    existing = {
        fact.key: fact
        for fact in db.scalars(
            select(FactRow).where(FactRow.job_id == job_id)
        )
    }

    for fact in registry.facts:
        row = existing.get(fact.key)

        if row is None:
            row = FactRow(
                job_id=job_id,
                key=fact.key,
            )
            db.add(row)

        row.label = fact.label
        row.value_json = fact.value
        row.value_type = fact.value_type
        row.unit = fact.unit
        row.confidence = fact.confidence
        row.importance = fact.importance
        row.severity = fact.severity
        row.spans_json = [span.model_dump() for span in fact.spans]

    db.commit()


def _save_knowledge(db, job_id: str, knowledge: CanonicalKnowledge):
    row = db.scalar(
        select(CanonicalKnowledgeRow).where(
            CanonicalKnowledgeRow.job_id == job_id
        )
    )

    if row is None:
        row = CanonicalKnowledgeRow(
            job_id=job_id,
            knowledge_json=knowledge.model_dump(),
        )
        db.add(row)
    else:
        row.knowledge_json = knowledge.model_dump()

    db.commit()


def _load_knowledge(db, job_id: str) -> CanonicalKnowledge | None:
    row = db.scalar(
        select(CanonicalKnowledgeRow).where(
            CanonicalKnowledgeRow.job_id == job_id
        )
    )

    if not row:
        return None

    return CanonicalKnowledge.model_validate(row.knowledge_json)


def _generator_for(output_type: str):
    """
    Dynamically locate the generator class.

    This avoids hard-coding class names and keeps this layer compatible
    with the generator modules already created by Cursor.
    """
    module_map = {
        "executive_summary": "app.services.generators.executive",
        "advisory": "app.services.generators.advisory",
        "linkedin_post": "app.services.generators.linkedin",
        "presentation": "app.services.generators.presentation",
        "x_thread": "app.services.generators.x_thread",
        "infographic": "app.services.generators.infographic",
        "video_package": "app.services.generators.video",
    }

    module_name = module_map.get(output_type)

    if not module_name:
        raise ValueError(f"Unsupported output type: {output_type}")

    module = importlib.import_module(module_name)

    from app.services.generators.base import BaseGenerator

    candidates = []

    for name in dir(module):
        obj = getattr(module, name)

        if (
            isinstance(obj, type)
            and issubclass(obj, BaseGenerator)
            and obj is not BaseGenerator
        ):
            candidates.append(obj)

    if not candidates:
        raise ValueError(
            f"No BaseGenerator implementation found for {output_type}"
        )

    return candidates[0]()


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

async def ingest(state: dict) -> dict:
    job_id = state["job_id"]
    source_id = state["source_id"]

    db = _db()

    try:
        source = _get_source(db, source_id)

        _update_job(
            db,
            job_id,
            status="running",
            current_node="ingest",
        )

        return {
            "status": "running",
            "current_node": "ingest",
        }

    finally:
        db.close()


async def extract(state: dict) -> dict:
    job_id = state["job_id"]
    source_id = state["source_id"]

    db = _db()

    try:
        source = _get_source(db, source_id)

        _update_job(
            db,
            job_id,
            current_node="extract",
        )

        # Avoid duplicating chunks if extraction has already happened.
        existing = _chunks_for_source(db, source_id)

        if not existing:
            chunks, warnings = extract_source(source)

            db.add_all(chunks)
            db.commit()
        else:
            warnings = []

        return {
            "current_node": "extract",
            "warnings": warnings,
        }

    finally:
        db.close()


async def analyze(state: dict) -> dict:
    job_id = state["job_id"]
    source_id = state["source_id"]

    db = _db()

    try:
        chunks = _chunks_for_source(db, source_id)

        if not chunks:
            raise ValueError("No extracted source chunks available")

        _update_job(
            db,
            job_id,
            current_node="analyze",
        )

        source_text = _chunks_text(chunks)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an intelligence document analyst. "
                    "Analyze the supplied source carefully. "
                    "Do not invent facts. "
                    "Use chunk IDs when referring to source evidence. "
                    "Return only structured JSON matching the requested schema."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": (
                            "Analyze this source and create canonical structured "
                            "knowledge for downstream content transformation."
                        ),
                        "source_text": source_text,
                    }
                ),
            },
        ]

        provider = get_provider()

        knowledge = await asyncio.wait_for(
            provider.structured(messages, CanonicalKnowledge, temperature=0.1),
            timeout=120,
        )

        knowledge.source_type = db.get(Source, source_id).source_type

        _save_knowledge(db, job_id, knowledge)

        return {
            "current_node": "analyze",
            "knowledge": knowledge.model_dump(),
        }

    finally:
        db.close()


async def structure_knowledge(state: dict) -> dict:
    job_id = state["job_id"]

    knowledge = CanonicalKnowledge.model_validate(
        state.get("knowledge") or {}
    )

    db = _db()

    try:
        _update_job(
            db,
            job_id,
            current_node="structure_knowledge",
        )

        registry = FactRegistry()

        # Convert important canonical information into explicit facts.
        for index, value in enumerate(knowledge.key_points):
            registry.add(
                CanonicalFact(
                    key=f"fact_{index + 1}",
                    label=f"Key Point {index + 1}",
                    value=value,
                    value_type="string",
                    confidence=0.85,
                    importance="high",
                    spans=knowledge.source_references[:1],
                )
            )

        for index, value in enumerate(knowledge.dates):
            registry.add(
                CanonicalFact(
                    key=f"date_{index + 1}",
                    label="Date",
                    value=value,
                    value_type="string",
                    confidence=0.8,
                    importance="normal",
                    spans=knowledge.source_references[:1],
                )
            )

        for index, value in enumerate(knowledge.statistics):
            registry.add(
                CanonicalFact(
                    key=f"statistic_{index + 1}",
                    label="Statistic",
                    value=value,
                    value_type="string",
                    confidence=0.75,
                    importance="normal",
                    spans=knowledge.source_references[:1],
                )
            )

        for index, value in enumerate(knowledge.organizations):
            registry.add(
                CanonicalFact(
                    key=f"organization_{index + 1}",
                    label="Organization",
                    value=value,
                    value_type="string",
                    confidence=0.8,
                    importance="normal",
                    spans=knowledge.source_references[:1],
                )
            )

        for index, value in enumerate(knowledge.locations):
            registry.add(
                CanonicalFact(
                    key=f"location_{index + 1}",
                    label="Location",
                    value=value,
                    value_type="string",
                    confidence=0.8,
                    importance="normal",
                    spans=knowledge.source_references[:1],
                )
            )

        for index, value in enumerate(knowledge.technologies):
            registry.add(
                CanonicalFact(
                    key=f"technology_{index + 1}",
                    label="Technology",
                    value=value,
                    value_type="string",
                    confidence=0.8,
                    importance="normal",
                    spans=knowledge.source_references[:1],
                )
            )

        _save_facts(db, job_id, registry)

        return {
            "current_node": "structure_knowledge",
            "fact_registry": registry.as_dicts(),
        }

    finally:
        db.close()


async def plan_outputs(state: dict) -> dict:
    job_id = state["job_id"]

    knowledge = CanonicalKnowledge.model_validate(
        state.get("knowledge") or {}
    )

    config = state.get("config") or {}
    selected = state.get("selected_outputs") or []

    db = _db()

    try:
        _update_job(
            db,
            job_id,
            current_node="plan_outputs",
            selected_outputs=selected,
            config=config,
        )

        provider = get_provider()
        plans = {}

        for output_type in selected:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a transformation planner. "
                        "Create a strict production plan for the requested "
                        "communication artifact. "
                        "The plan must identify facts that must be preserved, "
                        "relevant entities, sections, length limits, "
                        "prohibited assumptions and grounding requirements. "
                        "Never introduce unsupported facts."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "output_type": output_type,
                            "configuration": config,
                            "knowledge": knowledge.model_dump(),
                            "fact_registry": state.get("fact_registry") or [],
                        }
                    ),
                },
            ]

            plan = await provider.structured(
                messages,
                TransformationPlan,
                temperature=0.1,
            )

            plan.output_type = output_type
            plan.communication_objective = config.get(
                "objective",
                plan.communication_objective,
            )
            plan.target_audience = config.get(
                "audience",
                plan.target_audience,
            )
            plan.tone = config.get("tone", plan.tone)
            plan.detail_level = config.get(
                "detail_level",
                plan.detail_level,
            )
            plan.content_style = config.get(
                "content_style",
                plan.content_style,
            )

            plans[output_type] = plan.model_dump()

        _update_job(
            db,
            job_id,
            output_plans=plans,
        )

        return {
            "current_node": "plan_outputs",
            "output_plans": plans,
        }

    finally:
        db.close()


async def generate_output(state: dict) -> dict:
    job_id = state["job_id"]
    output_type = state["target_output_type"]

    knowledge = CanonicalKnowledge.model_validate(
        state.get("knowledge") or {}
    )

    registry = _registry_from_state(state)

    plan_data = (state.get("output_plans") or {}).get(output_type)

    if not plan_data:
        raise ValueError(f"No transformation plan for {output_type}")

    plan = TransformationPlan.model_validate(plan_data)

    generator = _generator_for(output_type)

    repair_issues = state.get("repair_issues")

    artifact = await generator.generate(
        knowledge,
        registry,
        plan,
        repair_issues=repair_issues,
    )

    artifact_dict = (
        artifact.model_dump()
        if hasattr(artifact, "model_dump")
        else artifact
    )

    return {
        "generated": [artifact_dict],
    }


async def fan_in(state: dict) -> dict:
    return {
        "current_node": "fan_in",
    }


def _artifact_val(artifact: Any, key: str, default: Any = None) -> Any:
    if isinstance(artifact, dict):
        return artifact.get(key, default)
    return getattr(artifact, key, default)


def _artifact_text(artifact: Any) -> str:
    payload = _artifact_val(artifact, "payload", {}) or {}

    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return str(payload)


async def consistency_check(state: dict) -> dict:
    artifacts = state.get("generated") or []
    registry = _registry_from_state(state)

    reports = []

    for artifact in artifacts:
        output_type = _artifact_val(artifact, "output_type")
        status = _artifact_val(artifact, "status")

        if status == "failed":
            reports.append(
                ValidationReport(
                    output_type=output_type,
                    check_type="consistency",
                    passed=False,
                    issues=[
                        {
                            "code": "generation_failed",
                            "message": _artifact_val(
                                artifact,
                                "error",
                                "Generation failed",
                            ),
                        }
                    ],
                ).model_dump()
            )
            continue

        text = _artifact_text(artifact)
        conflicts = registry.conflicts_with(text)

        issues = [
            {
                "code": "fact_conflict",
                "message": (
                    f"Possible conflict for fact "
                    f"'{fact.key}': generated value '{value}' "
                    f"does not match canonical value '{fact.value}'."
                ),
            }
            for fact, value in conflicts
        ]

        reports.append(
            ValidationReport(
                output_type=output_type,
                check_type="consistency",
                passed=not issues,
                issues=issues,
            ).model_dump()
        )

    return {
        "validations": reports,
        "current_node": "consistency_check",
    }


async def grounding_check(state: dict) -> dict:
    artifacts = state.get("generated") or []
    knowledge = CanonicalKnowledge.model_validate(
        state.get("knowledge") or {}
    )

    known_text = json.dumps(
        knowledge.model_dump(),
        ensure_ascii=False,
    ).lower()

    reports = []

    for artifact in artifacts:
        output_type = _artifact_val(artifact, "output_type")
        text = _artifact_text(artifact)

        fact_keys = _artifact_val(artifact, "fact_keys_used") or []

        issues = []

        if not text.strip():
            issues.append(
                {
                    "code": "empty_output",
                    "message": "Generated artifact is empty.",
                }
            )

        # Check that claimed fact keys actually exist.
        registry = _registry_from_state(state)

        for key in fact_keys:
            if registry.facts and not registry.get(key):
                issues.append(
                    {
                        "code": "unknown_fact_key",
                        "message": f"Unknown fact key used: {key}",
                    }
                )

        # Basic grounding signal.
        if text.strip() and not fact_keys and known_text:
            issues.append(
                {
                    "code": "missing_fact_traceability",
                    "message": (
                        "Artifact does not expose any fact keys for "
                        "traceability."
                    ),
                }
            )

        reports.append(
            ValidationReport(
                output_type=output_type,
                check_type="grounding",
                passed=not issues,
                issues=issues,
            ).model_dump()
        )

    return {
        "validations": reports,
        "current_node": "grounding_check",
    }


async def quality_check(state: dict) -> dict:
    artifacts = state.get("generated") or []

    reports = []
    failed = []

    for artifact in artifacts:
        output_type = _artifact_val(artifact, "output_type")
        status = _artifact_val(artifact, "status")
        payload = _artifact_val(artifact, "payload")
        markdown = _artifact_val(artifact, "markdown", "")

        issues = []

        if status == "failed":
            issues.append(
                {
                    "code": "generation_failed",
                    "message": _artifact_val(
                        artifact,
                        "error",
                        "Generator failed.",
                    ),
                }
            )

        if not payload:
            issues.append(
                {
                    "code": "missing_payload",
                    "message": "Artifact has no structured payload.",
                }
            )

        if not markdown.strip():
            issues.append(
                {
                    "code": "missing_markdown",
                    "message": "Artifact has no rendered content.",
                }
            )

        passed = not issues

        reports.append(
            ValidationReport(
                output_type=output_type,
                check_type="quality",
                passed=passed,
                issues=issues,
            ).model_dump()
        )

        if not passed:
            failed.append(output_type)

    # Merge failures using only the latest validation report for each (output_type, check_type)
    latest_reports = {}
    for r in (state.get("validations") or []) + reports:
        out_type = _artifact_val(r, "output_type")
        chk_type = _artifact_val(r, "check_type")
        if out_type and chk_type:
            latest_reports[(out_type, chk_type)] = r

    for (out_type, chk_type), report in latest_reports.items():
        if not _artifact_val(report, "passed", True) and out_type not in failed:
            failed.append(out_type)

    return {
        "validations": reports,
        "failed_output_types": failed,
        "current_node": "quality_check",
    }


async def repair_output(state: dict) -> dict:
    output_type = state["target_output_type"]

    attempts = dict(state.get("repair_attempts") or {})
    attempts[output_type] = attempts.get(output_type, 0) + 1

    knowledge = CanonicalKnowledge.model_validate(
        state.get("knowledge") or {}
    )

    registry = _registry_from_state(state)

    plan_data = (state.get("output_plans") or {}).get(output_type)

    if not plan_data:
        return {
            "repair_attempts": attempts,
            "current_node": "repair_output",
        }

    plan = TransformationPlan.model_validate(plan_data)

    generator = _generator_for(output_type)

    issues = state.get("repair_issues") or []

    artifact = await generator.generate(
        knowledge,
        registry,
        plan,
        repair_issues=issues,
    )

    artifact_dict = (
        artifact.model_dump()
        if hasattr(artifact, "model_dump")
        else artifact
    )

    return {
        "generated": [artifact_dict],
        "repair_attempts": attempts,
        "current_node": "repair_output",
    }


async def finalize(state: dict) -> dict:
    job_id = state["job_id"]
    artifacts = state.get("generated") or []

    db = _db()

    try:
        _update_job(
            db,
            job_id,
            status="completed",
            current_node="finalize",
        )

        # Persist generated outputs.
        for artifact in artifacts:
            output_type = _artifact_val(artifact, "output_type")
            status = _artifact_val(artifact, "status", "succeeded")
            payload = _artifact_val(artifact, "payload") or {}
            markdown = _artifact_val(artifact, "markdown", "")
            fact_keys = _artifact_val(artifact, "fact_keys_used") or []

            existing = db.scalar(
                select(GeneratedOutput)
                .where(
                    GeneratedOutput.job_id == job_id,
                    GeneratedOutput.output_type == output_type,
                )
                .order_by(GeneratedOutput.version.desc())
            )

            if existing:
                existing.version += 1
                existing.status = status
                existing.content_json = payload
                existing.content_markdown = markdown
                existing.fact_keys_used = fact_keys
            else:
                db.add(
                    GeneratedOutput(
                        job_id=job_id,
                        output_type=output_type,
                        status=status,
                        content_json=payload,
                        content_markdown=markdown,
                        fact_keys_used=fact_keys,
                    )
                )

        db.commit()

        return {
            "status": "completed",
            "current_node": "finalize",
        }

    finally:
        db.close()