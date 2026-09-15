from app.schemas import LinkedInPost
from app.services.generators.base import BaseGenerator


class LinkedInGenerator(BaseGenerator):
    output_type = "linkedin_post"
    schema = LinkedInPost
    output_guidelines = [
        "Generate a natural professional LinkedIn post for decision makers and cybersecurity peers.",
        "Structure naturally: opening/context, important development, significance/lesson, concise conclusion, and hashtags.",
        "Do NOT use mechanical labels such as 'Statistics:', 'Dates:', or 'Recommendations:'.",
        "Do NOT dump raw extracted text fragments or bullet lists.",
        "Do NOT include citation metadata like [c1...].",
        "Only include claims supported by canonical knowledge.",
    ]

    def to_markdown(self, payload: LinkedInPost) -> str:
        parts = []
        if payload.hook:
            parts.append(payload.hook)
        if payload.body:
            parts.append(payload.body)
        if payload.cta:
            parts.append(payload.cta)
        if payload.hashtags:
            parts.append(" ".join(payload.hashtags))
        return "\n\n".join(parts).strip() + "\n"
