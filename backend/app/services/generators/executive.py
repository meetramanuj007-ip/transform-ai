from app.schemas import ExecutiveSummary
from app.services.generators.base import BaseGenerator


class ExecutiveSummaryGenerator(BaseGenerator):
    output_type = "executive_summary"
    schema = ExecutiveSummary
    output_guidelines = [
        "Use exact structure: # Title, ## Executive Context, ## Key Findings, ## Impact, ## Current Status, ## Recommended Actions.",
        "Key Findings must contain ONLY factual observations and discoveries. NEVER place recommendations under Key Findings.",
        "Impact must contain only supported impact information.",
        "Current Status must contain only supported current containment or operational status.",
        "Recommended Actions must contain only source-supported actionable recommendations.",
        "Do not leak citation brackets like [c1...] into prose.",
    ]

    def to_markdown(self, payload: ExecutiveSummary) -> str:
        parts = [f"# {payload.headline}\n\n"]
        if payload.context:
            parts.append(f"## Executive Context\n{payload.context}\n\n")
        if payload.key_findings:
            findings = "\n".join(f"- {x}" for x in payload.key_findings)
            parts.append(f"## Key Findings\n{findings}\n\n")
        if payload.impact:
            impact_str = "\n".join(f"- {x}" for x in payload.impact)
            parts.append(f"## Impact\n{impact_str}\n\n")
        if payload.current_status:
            status_str = "\n".join(f"- {x}" for x in payload.current_status)
            parts.append(f"## Current Status\n{status_str}\n\n")
        recs = payload.recommended_actions or payload.implications
        if recs:
            recs_str = "\n".join(f"- {x}" for x in recs)
            parts.append(f"## Recommended Actions\n{recs_str}\n")
        return "".join(parts).strip() + "\n"
