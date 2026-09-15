from app.schemas import Advisory
from app.services.generators.base import BaseGenerator


class AdvisoryGenerator(BaseGenerator):
    output_type = "advisory"
    schema = Advisory
    output_guidelines = [
        "Use operational structure: Situation, Assessment, Impact, Current Status, Recommended Actions, Monitoring / Next Steps.",
        "Separate situation, assessment, and recommendations cleanly without duplication.",
        "Only include sections supported by the source.",
        "Never include citation metadata like [c1...].",
    ]

    def to_markdown(self, payload: Advisory) -> str:
        parts = [f"# {payload.header}\n\n"]
        if payload.situation:
            parts.append(f"## Situation\n{payload.situation}\n\n")
        if payload.assessment:
            parts.append(f"## Assessment\n{payload.assessment}\n\n")
        if payload.impact:
            impact_lines = "\n".join(f"- {x}" for x in payload.impact)
            parts.append(f"## Impact\n{impact_lines}\n\n")
        if payload.current_status:
            status_lines = "\n".join(f"- {x}" for x in payload.current_status)
            parts.append(f"## Current Status\n{status_lines}\n\n")
        if payload.recommendations:
            recs = "\n".join(f"1. {x}" for x in payload.recommendations)
            parts.append(f"## Recommended Actions\n{recs}\n\n")
        monitoring = payload.monitoring_next_steps or payload.watch_items
        if monitoring:
            mon_lines = "\n".join(f"- {x}" for x in monitoring)
            parts.append(f"## Monitoring / Next Steps\n{mon_lines}\n\n")
        if payload.caveats:
            cav_lines = "\n".join(f"- {x}" for x in payload.caveats)
            parts.append(f"## Operational Caveats\n{cav_lines}\n")
        return "".join(parts).strip() + "\n"
