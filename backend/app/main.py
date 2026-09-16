import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Base,
    CanonicalKnowledgeRow,
    FactRow,
    GeneratedOutput,
    SessionLocal,
    Source,
    SourceChunk,
    TransformationJob,
    ValidationResult,
    engine,
    get_db,
)
from app.schemas import (
    JobCreate,
    OutputEdit,
    PresentationOutline,
    TextSourceCreate,
    UrlSourceCreate,
)
from app.services.export.pptx import render_pptx
from app.services.graph.graph import get_graph
from app.services.ingestion.store import save_upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database tables exist
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="TransformAI API",
    description="Multi-Deliverable Canonical Knowledge Transformation Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS setup for local dev / production frontend
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "app_env": settings.app_env}


# ---------------------------------------------------------------------------
# Source Ingestion Routes
# ---------------------------------------------------------------------------

@app.post("/api/sources/upload")
async def upload_file_source(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        content = await file.read()
        source = save_upload(
            filename=file.filename or "uploaded_file",
            data=content,
            content_type=file.content_type or "application/octet-stream",
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return {
            "id": source.id,
            "filename": source.filename,
            "source_type": source.source_type,
            "size_bytes": source.size_bytes,
            "char_count": source.char_count,
            "extract_preview": source.extract_preview[:300],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload failed: {str(exc)}",
        )


@app.post("/api/sources/text")
def create_text_source(
    data: TextSourceCreate,
    db: Session = Depends(get_db),
):
    try:
        source = save_upload(
            filename=data.filename or "pasted.txt",
            data=data.text.encode("utf-8"),
            content_type="text/plain",
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return {
            "id": source.id,
            "filename": source.filename,
            "source_type": source.source_type,
            "size_bytes": source.size_bytes,
            "char_count": source.char_count,
            "extract_preview": source.extract_preview[:300],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create text source: {str(exc)}",
        )


@app.post("/api/sources/url")
def create_url_source(
    data: UrlSourceCreate,
    db: Session = Depends(get_db),
):
    try:
        source = save_upload(
            filename=data.url.split("/")[-1] or "url_source.txt",
            data=data.url.encode("utf-8"),
            content_type="text/plain",
            origin_url=data.url,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return {
            "id": source.id,
            "filename": source.filename,
            "source_type": source.source_type,
            "size_bytes": source.size_bytes,
            "char_count": source.char_count,
            "extract_preview": source.extract_preview[:300],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to ingest URL: {str(exc)}",
        )


@app.get("/api/sources/{source_id}")
def get_source_details(
    source_id: str,
    db: Session = Depends(get_db),
):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    chunks = db.scalars(
        select(SourceChunk)
        .where(SourceChunk.source_id == source_id)
        .order_by(SourceChunk.id)
    ).all()

    return {
        "id": source.id,
        "filename": source.filename,
        "source_type": source.source_type,
        "content_type": source.content_type,
        "size_bytes": source.size_bytes,
        "char_count": source.char_count,
        "page_count": source.page_count,
        "extract_preview": source.extract_preview,
        "chunk_count": len(chunks),
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "page": c.page,
                "section": c.section,
                "text_preview": c.text[:200],
            }
            for c in chunks
        ],
    }


# ---------------------------------------------------------------------------
# Transformation Job Runner
# ---------------------------------------------------------------------------

async def _run_transformation_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(TransformationJob, job_id)
        if not job:
            return

        graph = get_graph()
        initial_state = {
            "job_id": job.id,
            "source_id": job.source_id,
            "config": job.config or {},
            "selected_outputs": job.selected_outputs or [],
            "generated": [],
            "validations": [],
            "repair_attempts": {},
            "failed_output_types": [],
            "errors": [],
            "warnings": [],
        }

        # Execute LangGraph asynchronously
        await graph.ainvoke(initial_state)

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Job %s failed", job_id, exc_info=True)
        db_session = SessionLocal()
        try:
            j = db_session.get(TransformationJob, job_id)
            if j:
                j.status = "failed"
                # Some exceptions like TimeoutError evaluate to empty string
                err_msg = str(exc)
                j.error_message = err_msg if err_msg.strip() else repr(exc)
                db_session.commit()
        finally:
            db_session.close()

    finally:
        db.close()


@app.post("/api/jobs")
def create_job(
    data: JobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    source = db.get(Source, data.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    job = TransformationJob(
        id=str(uuid4()),
        source_id=source.id,
        status="queued",
        current_node="queued",
        selected_outputs=[t for t in data.selected_outputs],
        config=data.config.model_dump(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Spawn background execution
    background_tasks.add_task(_run_transformation_job, job.id)

    return {
        "id": job.id,
        "source_id": job.source_id,
        "status": job.status,
        "selected_outputs": job.selected_outputs,
        "config": job.config,
    }


@app.get("/api/jobs/{job_id}")
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
):
    job = db.get(TransformationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    knowledge_row = db.scalar(
        select(CanonicalKnowledgeRow).where(CanonicalKnowledgeRow.job_id == job_id)
    )
    facts = db.scalars(select(FactRow).where(FactRow.job_id == job_id)).all()
    outputs = db.scalars(
        select(GeneratedOutput).where(GeneratedOutput.job_id == job_id)
    ).all()
    validations = db.scalars(
        select(ValidationResult).where(ValidationResult.job_id == job_id)
    ).all()

    return {
        "id": job.id,
        "source_id": job.source_id,
        "status": job.status,
        "current_node": job.current_node,
        "selected_outputs": job.selected_outputs,
        "config": job.config,
        "output_plans": job.output_plans,
        "repair_attempts": job.repair_attempts,
        "error_message": job.error_message,
        "knowledge": knowledge_row.knowledge_json if knowledge_row else None,
        "facts": [
            {
                "key": f.key,
                "label": f.label,
                "value": f.value_json,
                "value_type": f.value_type,
                "unit": f.unit,
                "confidence": f.confidence,
                "importance": f.importance,
            }
            for f in facts
        ],
        "outputs": [
            {
                "id": o.id,
                "output_type": o.output_type,
                "version": o.version,
                "status": o.status,
                "content_json": o.content_json,
                "content_markdown": o.content_markdown,
                "fact_keys_used": o.fact_keys_used,
                "edited_by_human": o.edited_by_human,
            }
            for o in outputs
        ],
        "validations": [
            {
                "id": v.id,
                "output_id": v.output_id,
                "check_type": v.check_type,
                "severity": v.severity,
                "passed": v.passed,
                "attempt": v.attempt,
                "details": v.details_json,
            }
            for v in validations
        ],
    }


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_updates(job_id: str):
    """Server-Sent Events (SSE) live progress feed for job execution."""
    async def event_generator():
        last_node = None
        last_status = None
        attempts = 0

        while attempts < 300:  # Max 5 min stream polling
            db = SessionLocal()
            try:
                job = db.get(TransformationJob, job_id)
                if not job:
                    yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                    break

                if job.current_node != last_node or job.status != last_status:
                    last_node = job.current_node
                    last_status = job.status

                    outputs = db.scalars(
                        select(GeneratedOutput).where(GeneratedOutput.job_id == job_id)
                    ).all()

                    payload = {
                        "job_id": job.id,
                        "status": job.status,
                        "current_node": job.current_node,
                        "output_types": [o.output_type for o in outputs],
                        "error_message": job.error_message,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                if job.status in {"completed", "failed"}:
                    break

            finally:
                db.close()

            attempts += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/jobs/{job_id}/regenerate")
def regenerate_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = db.get(TransformationJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = "queued"
    job.current_node = "queued"
    job.error_message = None
    db.commit()

    background_tasks.add_task(_run_transformation_job, job.id)

    return {"id": job.id, "status": "queued"}


# ---------------------------------------------------------------------------
# Deliverable Output Edits & Export Routes
# ---------------------------------------------------------------------------

@app.put("/api/outputs/{output_id}")
def update_generated_output(
    output_id: str,
    edit: OutputEdit,
    db: Session = Depends(get_db),
):
    output = db.get(GeneratedOutput, output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output deliverable not found")

    if edit.content_markdown is not None:
        output.content_markdown = edit.content_markdown
        output.edited_by_human = True

    if edit.content_json is not None:
        output.content_json = edit.content_json
        output.edited_by_human = True

    db.commit()
    db.refresh(output)

    return {
        "id": output.id,
        "output_type": output.output_type,
        "version": output.version,
        "status": output.status,
        "content_markdown": output.content_markdown,
        "content_json": output.content_json,
        "edited_by_human": output.edited_by_human,
    }


@app.get("/api/outputs/{output_id}/export/pptx")
def export_output_pptx(
    output_id: str,
    db: Session = Depends(get_db),
):
    output = db.get(GeneratedOutput, output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output deliverable not found")

    if output.output_type != "presentation":
        raise HTTPException(
            status_code=400,
            detail="PPTX export is only available for presentation deliverables",
        )

    try:
        outline = PresentationOutline.model_validate(output.content_json)
        pptx_bytes = render_pptx(outline)

        filename = f"presentation_{output_id[:8]}.pptx"
        return Response(
            content=pptx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PPTX document: {str(exc)}",
        )
