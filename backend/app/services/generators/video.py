from app.schemas import VideoPackage
from app.services.generators.base import BaseGenerator


class VideoPackageGenerator(BaseGenerator):
    output_type = "video_package"
    schema = VideoPackage
    output_guidelines = [
        "Generate structured narrative video scenes.",
        "Each scene must contain: Scene number, Title, Duration, Visual, Narration, and On-screen text.",
        "Do not repeat the same source sentence across multiple scenes.",
        "Do not expose citation metadata like [c1...].",
        "Use canonical facts to build a progression: Detection -> Scope/Investigation -> Containment -> Impact/Status -> Recommendations.",
    ]

    def to_markdown(self, payload: VideoPackage) -> str:
        parts = [
            f"# {payload.title}",
            f"Audience: {payload.target_audience}",
            f"Duration: {payload.duration}",
            "",
            "## Scenes",
            "",
        ]
        for s in payload.scenes:
            scene_num = s.scene_number or s.index
            title = s.title or f"Scene {scene_num}"
            duration = s.duration or f"{s.duration_seconds} seconds"
            visual = s.visual or s.description
            parts.extend([
                f"Scene {scene_num}",
                f"Title: {title}",
                f"Duration: {duration}",
                f"Visual: {visual}",
                f"Narration: {s.narration}",
                f"On-screen text: {s.on_screen_text}",
                "",
            ])
        return "\n".join(parts).strip() + "\n"
