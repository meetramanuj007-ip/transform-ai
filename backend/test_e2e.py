import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.models import Base, engine, SessionLocal, Source, TransformationJob
from app.services.ingestion.store import save_upload
from app.services.graph.graph import get_graph


async def main():
    # Make sure tables exist
    Base.metadata.create_all(engine)

    report_path = Path(__file__).parent / "test_report.txt"
    report_text = report_path.read_text(encoding="utf-8")

    db = SessionLocal()

    try:
        # Create source
        source = save_upload(
            filename="test_report.txt",
            data=report_text.encode("utf-8"),
            content_type="text/plain",
        )

        db.add(source)
        db.flush()

        # Create transformation job
        job = TransformationJob(
            id=str(uuid4()),
            source_id=source.id,
            status="queued",
            selected_outputs=[
                "executive_summary",
                "advisory",
                "linkedin_post",
                "x_thread",
                "presentation",
                "infographic",
                "video_package",
            ],
            config={
                "audience": "senior decision makers",
                "tone": "advisory",
                "language": "en",
                "detail": "standard",
                "objective": "inform and recommend",
                "content_style": "intelligence brief",
            },
        )

        db.add(job)
        db.commit()

        print("=" * 60)
        print("TRANSFORMAI E2E TEST")
        print("=" * 60)
        print(f"Source ID : {source.id}")
        print(f"Job ID    : {job.id}")
        print()
        print("Starting LangGraph...")
        print()

        graph = get_graph()

        initial_state = {
            "job_id": job.id,
            "source_id": source.id,
            "config": job.config or {},
            "selected_outputs": job.selected_outputs or [],
            "generated": [],
            "validations": [],
            "repair_attempts": {},
            "failed_output_types": [],
            "errors": [],
            "warnings": [],
        }

        result = await graph.ainvoke(initial_state)

        print()
        print("=" * 60)
        print("GRAPH FINISHED")
        print("=" * 60)

        print(f"Status: {result.get('status')}")
        print(f"Current node: {result.get('current_node')}")

        print()
        print("GENERATED OUTPUTS:")
        print("-" * 60)

        for artifact in result.get("generated", []):
            print(f"\n[{artifact.get('output_type')}]")
            print(f"Status: {artifact.get('status')}")
            print(f"Fact keys: {artifact.get('fact_keys_used')}")

            markdown = artifact.get("markdown") or ""
            print("Preview:")
            print(markdown[:500])

        print()
        # Verify all expected outputs are present
        expected_outputs = {"executive_summary","advisory","linkedin_post","x_thread","presentation","infographic","video_package"}
        generated_outputs = {artifact.get('output_type') for artifact in result.get('generated', [])}
        missing = expected_outputs - generated_outputs
        assert not missing, f"Missing generated outputs: {missing}"

        # Verify each output passed consistency, grounding, quality
        validations = result.get('validations', [])
        for out_type in expected_outputs:
            checks = [v for v in validations if v.get('output_type') == out_type]
            assert checks, f"No validations found for {out_type}"
            for chk in checks:
                assert chk.get('passed') is True, f"{out_type} {chk.get('check_type')} failed"

        print("VALIDATIONS:")
        print("-" * 60)

        for validation in result.get("validations", []):
            print(
                f"{validation.get('output_type')} | "
                f"{validation.get('check_type')} | "
                f"passed={validation.get('passed')}"
            )

        print()
        print("ERRORS:")
        print(result.get("errors", []))

        print()
        print("=" * 60)
        print("E2E TEST COMPLETE")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())

def test_e2e():
    asyncio.run(main())