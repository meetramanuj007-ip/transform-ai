from app.schemas import XThread
from app.services.generators.base import BaseGenerator


class XThreadGenerator(BaseGenerator):
    output_type = "x_thread"
    schema = XThread
    output_guidelines = [
        "Create a coherent story-driven thread with exactly 5-6 tweets.",
        "Follow narrative arc: 1. What happened, 2. When/where it happened, 3. Scope/impact, 4. Response, 5. Current status, 6. Key takeaway.",
        "Do NOT turn the thread into a numbered list of recommendations.",
        "Do NOT repeat sentences across tweets.",
        "Keep each tweet under 280 characters.",
        "Never include citation metadata like [c1...].",
    ]

    def to_markdown(self, payload: XThread) -> str:
        total = len(payload.tweets)
        tweets = []
        for t in payload.tweets:
            prefix = f"{t.index}/{total}"
            text = t.text.strip()
            # If text doesn't already have index prefix, add it
            if not text.startswith(f"{t.index}/"):
                tweets.append(f"{prefix} {text}")
            else:
                tweets.append(text)
        return "\n\n".join(tweets).strip() + "\n"
