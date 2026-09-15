from app.schemas import InfographicSpec
from app.services.generators.base import BaseGenerator


class InfographicGenerator(BaseGenerator):
    output_type = "infographic"
    schema = InfographicSpec
    output_guidelines = [
        "Create a clear visual information hierarchy.",
        "Sections: Headline, Key statistics, Timeline, Current status, Response actions, Key takeaway, Suggested visual elements.",
        "Ground statistics and actions strictly in canonical knowledge.",
        "Never include citation metadata like [c1...].",
    ]

    def to_markdown(self, payload: InfographicSpec) -> str:
        parts = [f"# {payload.title}\n"]

        if payload.headline:
            parts.append(f"## Headline\n{payload.headline}\n")

        stats = payload.key_statistics or payload.callouts
        if stats:
            stat_lines = "\n".join(f"- {s}" for s in stats)
            parts.append(f"## Key Statistics\n{stat_lines}\n")

        if payload.timeline:
            timeline_lines = "\n".join(f"- {t}" for t in payload.timeline)
            parts.append(f"## Timeline\n{timeline_lines}\n")

        if payload.current_status:
            status_lines = "\n".join(f"- {s}" for s in payload.current_status)
            parts.append(f"## Current Status\n{status_lines}\n")

        if payload.response_actions:
            action_lines = "\n".join(f"- {a}" for a in payload.response_actions)
            parts.append(f"## Response Actions\n{action_lines}\n")

        if payload.key_takeaway:
            parts.append(f"## Key Takeaway\n{payload.key_takeaway}\n")

        visuals = payload.suggested_visual_elements or payload.chart_suggestions
        if visuals:
            visual_lines = "\n".join(f"- {v}" for v in visuals)
            parts.append(f"## Suggested Visual Elements\n{visual_lines}\n")

        if payload.sections:
            sec_lines = "\n\n".join(f"### {s.heading}\n{s.body}" for s in payload.sections)
            parts.append(f"## Detail Sections\n{sec_lines}\n")

        return "\n".join(parts).strip() + "\n"
