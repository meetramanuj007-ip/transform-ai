from app.schemas import PresentationOutline
from app.services.generators.base import BaseGenerator


class PresentationGenerator(BaseGenerator):
    output_type = "presentation"
    schema = PresentationOutline
    output_guidelines = [
        "Generate slide-by-slide briefing structure (4-5 slides).",
        "Each slide must contain: Slide number, Title, Key points, and Speaker notes.",
        "Do not repeat the same bullet across slides.",
        "Speaker notes should provide executive speaking cues without merely reading the bullets.",
        "Never include citation metadata like [c1...].",
    ]

    def to_markdown(self, payload: PresentationOutline) -> str:
        parts = [f"# {payload.title}"]
        if payload.subtitle:
            parts.append(f"_{payload.subtitle}_")
        parts.append("")

        for i, slide in enumerate(payload.slides, start=1):
            parts.append(f"## Slide {i}: {slide.title}")
            # Use bullets from either field
            bullet_items = slide.bullets if getattr(slide, "bullets", None) else slide.right_column_bullets
            if bullet_items:
                parts.append("### Key Points")
                for b in bullet_items:
                    indent = "  " * getattr(b, "level", 0)
                    text = b.text if hasattr(b, "text") else str(b)
                    parts.append(f"{indent}- {text}")
            if slide.speaker_notes:
                parts.append(f"\n### Speaker Notes\n{slide.speaker_notes}")
            parts.append("")
        return "\n".join(parts).strip() + "\n"
