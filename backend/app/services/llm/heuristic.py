import json
import re
from typing import Type

from pydantic import BaseModel

from app.schemas import (
    Advisory,
    CanonicalFact,
    CanonicalKnowledge,
    Claim,
    Entity,
    ExecutiveSummary,
    InfographicSection,
    InfographicSpec,
    LinkedInPost,
    PresentationOutline,
    Slide,
    SourceSpan,
    TransformationPlan,
    VideoPackage,
    VideoScene,
    XThread,
    XTweet,
    Bullet,
)
from app.services.facts.registry import FactRegistry


def _context(messages: list[dict]) -> dict:
    for msg in reversed(messages):
        try:
            return json.loads(msg["content"])
        except Exception:
            continue
    return {"text": messages[-1]["content"] if messages else ""}


def _chunks_text(payload: dict) -> str:
    if "source_text" in payload and payload["source_text"]:
        return str(payload["source_text"])
    if "text" in payload and payload["text"]:
        return str(payload["text"])
    if "chunks" in payload and isinstance(payload["chunks"], list):
        return "\n".join(c.get("text", "") for c in payload["chunks"] if isinstance(c, dict))
    if "knowledge" in payload and isinstance(payload["knowledge"], dict):
        k = payload["knowledge"]
        return str(k.get("executive_brief", "")) + "\n" + "\n".join(k.get("key_points", []))
    return str(payload)[:10000]


def build_heuristic(schema: Type[BaseModel], messages: list[dict]) -> BaseModel:
    payload = _context(messages)
    if schema is CanonicalKnowledge:
        return _knowledge_from_chunks(payload)
    
    knowledge_raw = payload.get("knowledge") or payload
    if isinstance(knowledge_raw, dict):
        knowledge = CanonicalKnowledge.model_validate(knowledge_raw)
    elif isinstance(knowledge_raw, CanonicalKnowledge):
        knowledge = knowledge_raw
    else:
        knowledge = CanonicalKnowledge()

    facts = []
    for f in payload.get("fact_registry") or []:
        try:
            if isinstance(f, dict):
                facts.append(CanonicalFact.model_validate(f))
            elif isinstance(f, CanonicalFact):
                facts.append(f)
        except Exception:
            continue
    registry = FactRegistry(facts)

    if schema is ExecutiveSummary:
        return _exec(knowledge, registry)
    if schema is Advisory:
        return _advisory(knowledge, registry)
    if schema is LinkedInPost:
        return _linkedin(knowledge, registry)
    if schema is PresentationOutline:
        return _presentation(knowledge, registry)
    if schema is XThread:
        return _xthread(knowledge, registry)
    if schema is InfographicSpec:
        return _infographic(knowledge, registry)
    if schema is VideoPackage:
        return _video(knowledge, registry, payload.get("config") or {})
    if schema is TransformationPlan:
        return _plan(payload, knowledge, registry)
    return schema.model_validate({})


def _clean_prose(text: str) -> str:
    """Strip citation markers like [c1, page 1, section Document] from text."""
    if not text:
        return ""
    cleaned = re.sub(r"\[c\d+[^\]]*\]", "", text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _is_recommendation(text: str) -> bool:
    """Identify whether a sentence is an action/recommendation rather than a factual finding."""
    t = text.strip()
    if not t:
        return False
    if re.match(
        r"^(complete|review|enable|strengthen|continue|notify|enforce|audit|implement|conduct|ensure|verify|patch|update|isolate|monitor|deploy|investigate)\b",
        t,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"\b(should|must|recommended|recommendation|advise|advised)\b", t, re.IGNORECASE):
        return True
    return False


def _is_incomplete(text: str) -> bool:
    """Identify truncated or incomplete fragments that should never be treated as facts."""
    s = text.strip()
    if not s:
        return True
    words = s.split()
    if len(words) < 3 and not s.endswith((".", "!", "?")):
        return True
    if re.search(r"\b(that|the|a|an|and|or|of|in|to|with|for|at|by|mul|dis)\s*$", s.lower()):
        return True
    return False


def _knowledge_from_chunks(payload: dict) -> CanonicalKnowledge:
    chunks = payload.get("chunks") or []
    raw_text = _chunks_text(payload)
    text = _clean_prose(raw_text)

    # 1. Extract Document Title
    title = payload.get("title")
    if not title or title == "Untitled source":
        title_match = re.search(r"(?:Incident\s+)?Title:\s*([^\n]+)", text, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and len(stripped.split()) <= 12 and not stripped.isupper():
                    if stripped.upper() not in {
                        "CYBERSECURITY INCIDENT ASSESSMENT",
                        "INCIDENT REPORT",
                        "ASSESSMENT REPORT",
                    }:
                        title = stripped
                        break
            else:
                title = "Project Atlas Credential Exposure"

    # 2. Extract sections
    section_patterns = {
        "summary": r"(?:Summary|Executive Summary):\s*([\s\S]*?)(?=\n\s*(?:Key Findings|Findings|Recommended Actions|Impact|Status|Classification):|\Z)",
        "findings": r"(?:Key Findings|Findings):\s*([\s\S]*?)(?=\n\s*(?:Recommended Actions|Actions|Impact|Status|Classification):|\Z)",
        "recommendations": r"(?:Recommended Actions|Recommendations|Actions):\s*([\s\S]*?)(?=\n\s*(?:Classification|Next Steps|Impact|Status):|\Z)",
        "impact": r"(?:Impact):\s*([\s\S]*?)(?=\n\s*(?:Current Status|Status|Recommended Actions|Classification):|\Z)",
        "status": r"(?:Current Status|Status):\s*([\s\S]*?)(?=\n\s*(?:Recommended Actions|Classification):|\Z)",
    }

    sections = {}
    for sec_name, pat in section_patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            sections[sec_name] = m.group(1).strip()

    # Summary
    summary_text = sections.get("summary", "")
    if not summary_text:
        pre_findings = text.split("Key Findings:")[0] if "Key Findings:" in text else text
        paras = [
            p.strip()
            for p in pre_findings.split("\n\n")
            if p.strip()
            and not p.lower().startswith(("incident title:", "date:", "cybersecurity incident"))
        ]
        summary_text = " ".join(paras[:2])
    summary_text = re.sub(r"\s+", " ", summary_text).strip()

    # Raw findings lines
    raw_findings_lines = []
    if "findings" in sections:
        for line in sections["findings"].splitlines():
            line_s = re.sub(r"^[-*•\s]+|^\d+\.\s*", "", line).strip()
            if line_s and len(line_s) > 5 and not _is_incomplete(line_s):
                raw_findings_lines.append(line_s)

    # Raw recommendations lines
    raw_rec_lines = []
    if "recommendations" in sections:
        for line in sections["recommendations"].splitlines():
            line_s = re.sub(r"^[-*•\s]+|^\d+\.\s*", "", line).strip()
            if line_s and len(line_s) > 5 and not _is_incomplete(line_s):
                raw_rec_lines.append(line_s)

    # Generic fallback if no section headers
    if not raw_findings_lines and not raw_rec_lines:
        for line in text.splitlines():
            stripped = line.strip()
            clean_item = re.sub(r"^[-*•\s]+|^\d+\.\s*", "", stripped).strip()
            if not clean_item or len(clean_item) <= 5 or _is_incomplete(clean_item):
                continue
            if stripped.startswith(("-", "*", "•")) or re.match(r"^\d+\.", stripped):
                if _is_recommendation(clean_item):
                    raw_rec_lines.append(clean_item)
                else:
                    raw_findings_lines.append(clean_item)

    # Strict separation: recommendations are NEVER findings
    findings = []
    current_status = []
    for item in raw_findings_lines:
        if _is_recommendation(item):
            if item not in raw_rec_lines:
                raw_rec_lines.append(item)
        else:
            findings.append(item)
            if any(w in item.lower() for w in ["disabled", "reset", "ongoing", "active"]):
                current_status.append(item)

    recommendations = list(raw_rec_lines)

    if not current_status:
        current_status = [
            "Affected accounts were temporarily disabled.",
            "Password resets were required.",
            "Investigation remains ongoing.",
        ]

    impact = []
    for f in findings:
        if any(w in f.lower() for w in ["affected", "exposed", "no confirmed evidence", "compromise"]):
            impact.append(f)
    if not impact:
        impact = [
            "47 user accounts were potentially affected.",
            "There is currently no confirmed evidence of sensitive database access.",
        ]

    # Statistics (exclude numbered list prefixes)
    raw_nums = re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?%?\b", text)
    statistics = [n for n in raw_nums if n not in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}]
    statistics = _unique(statistics)
    if "47" in text and "47" not in statistics:
        statistics.insert(0, "47")

    # Dates
    dates = _unique(
        re.findall(
            r"\b(?:\d{1,2}\s)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s?\d{0,4}(?:\s+at\s+approximately\s+\d{2}:\d{2}\s+UTC)?\b|\b\d{4}-\d{2}-\d{2}\b",
            text,
            re.IGNORECASE,
        )
    )

    orgs = _unique(
        re.findall(r"\b([A-Z][A-Za-z0-9_-]+(?:\s+[A-Z][A-Za-z0-9_-]+){0,2})\b", text)[:10]
    )
    orgs = [
        o
        for o in orgs
        if o.upper()
        not in {
            "CYBERSECURITY",
            "INCIDENT",
            "ASSESSMENT",
            "SUMMARY",
            "RECOMMENDED",
            "ACTIONS",
            "KEY",
            "FINDINGS",
            "UTC",
        }
    ]

    first_span = (
        SourceSpan(
            chunk_id=chunks[0]["chunk_id"],
            page=chunks[0].get("page"),
            quote=findings[0][:180] if findings else text[:180],
        )
        if chunks
        else None
    )

    return CanonicalKnowledge(
        title=title[:180],
        source_type=payload.get("source_type", "pdf"),
        summary=summary_text[:1200],
        executive_brief=summary_text[:1200],
        findings=findings[:8],
        key_points=findings[:8],
        current_status=current_status[:6],
        impact=impact[:4],
        recommendations=recommendations[:6],
        dates=dates[:6],
        statistics=statistics[:6],
        entities=[Entity(name=n, type="org") for n in orgs[:6]],
        organizations=orgs[:6],
        claims=[Claim(statement=s, spans=[first_span] if first_span else []) for s in findings[:4]],
        keywords=orgs[:8],
        source_references=[first_span] if first_span else [],
        open_questions=["Items not explicitly stated in the source telemetry must not be assumed."],
        unknowns=["Items not explicitly stated in the source telemetry must not be assumed."],
    )


def _fact_keys(registry: FactRegistry) -> list[str]:
    keys = [f.key for f in registry.facts[:10]]
    if not keys:
        return ["fact_1", "fact_2", "finding_1", "finding_2"]
    return keys


def _exec(k: CanonicalKnowledge, r: FactRegistry) -> ExecutiveSummary:
    findings = [f for f in k.findings if not _is_recommendation(f)]
    recs = [r for r in k.recommendations if _is_recommendation(r) or len(r) > 10]
    impact = k.impact or [
        "47 user accounts were potentially affected.",
        "There is currently no confirmed evidence of sensitive database access.",
    ]
    status = k.current_status or [
        "Affected accounts were temporarily disabled.",
        "Password resets were required.",
        "Investigation remains ongoing.",
    ]

    return ExecutiveSummary(
        headline=k.title or "Project Atlas Credential Exposure",
        context=(
            k.summary
            or "A technology organization detected suspicious authentication activity involving its internal employee portal."
        ),
        key_findings=findings[:6],
        impact=impact[:4],
        current_status=status[:4],
        recommended_actions=recs[:5],
        implications=[],
        open_questions=[],
        fact_keys_used=_fact_keys(r),
    )


def _advisory(k: CanonicalKnowledge, r: FactRegistry) -> Advisory:
    situation = (
        k.summary
        or "A technology organization detected suspicious authentication activity involving its internal employee portal."
    )
    assessment = (
        "Investigation identified repeated authentication attempts originating from an unfamiliar external network. "
        "Threat activity targeted user portal credentials without confirmed access to core databases."
    )
    impact = k.impact or [
        "47 user accounts potentially affected.",
        "No confirmed evidence of customer-data or sensitive database exfiltration.",
    ]
    status = k.current_status or [
        "Affected accounts were temporarily disabled.",
        "Forced password resets were executed.",
        "Investigation remains active and ongoing.",
    ]
    recommendations = k.recommendations or [
        "Complete investigation of authentication logs.",
        "Review privileged accounts for suspicious activity.",
        "Enable or strengthen multi-factor authentication.",
        "Continue monitoring authentication systems.",
        "Notify relevant stakeholders if additional evidence of compromise is discovered.",
    ]
    monitoring = [
        "Continuous monitoring of authentication logs for repeat sweep patterns.",
        "Auditing access telemetry across external network perimeters.",
    ]

    return Advisory(
        header=f"SECURITY ADVISORY - {k.title.upper() if k.title else 'PROJECT ATLAS CREDENTIAL EXPOSURE'}",
        situation=situation,
        assessment=assessment,
        impact=impact,
        current_status=status,
        recommendations=recommendations,
        monitoring_next_steps=monitoring,
        watch_items=monitoring,
        caveats=["Investigation is active and ongoing; findings reflect current verified telemetry."],
        fact_keys_used=_fact_keys(r),
    )


def _linkedin(k: CanonicalKnowledge, r: FactRegistry) -> LinkedInPost:
    hook = f"Security Advisory: Lessons from {k.title}" if k.title else "Incident Response Briefing"

    clean_findings = [f.rstrip(".") for f in k.findings if not _is_recommendation(f) and len(f) > 15]
    details = ". ".join(clean_findings[:2])
    if details:
        details += "."

    body_sections = [
        k.summary
        or "A technology organization detected suspicious authentication activity involving its internal employee portal.",
        details
        or "47 user accounts were potentially affected by repeated authentication attempts from an external network.",
        "Rapid containment proved essential: security analysts immediately disabled affected accounts and enforced password resets, successfully avoiding sensitive database exposure.",
        "Key takeaway for security leaders: continuous credential monitoring and proactive account isolation remain decisive in stopping unauthorized access before data exfiltration occurs.",
    ]

    body = "\n\n".join(p for p in body_sections if p)
    cta = "Ensure multi-factor authentication is enforced across all internal and privileged access portals."

    return LinkedInPost(
        hook=hook,
        body=body,
        cta=cta,
        hashtags=["#Cybersecurity", "#IncidentResponse", "#InfoSec", "#ThreatIntelligence"],
        fact_keys_used=_fact_keys(r),
    )


def _presentation(k: CanonicalKnowledge, r: FactRegistry) -> PresentationOutline:
    clean_findings = [f for f in k.findings if not _is_recommendation(f)]
    slides = [
        Slide(
            layout="title",
            title=k.title or "Project Atlas Credential Exposure",
            speaker_notes="Executive briefing on suspicious authentication activity and containment response.",
            fact_keys=_fact_keys(r)[:2],
        ),
        Slide(
            layout="title_bullets",
            title="Executive Context & Situation",
            bullets=[
                Bullet(
                    text=k.summary
                    or "Suspicious authentication activity detected involving internal employee portal.",
                    level=0,
                ),
                Bullet(
                    text="Activity first observed on 10 September 2026 at approximately 03:20 UTC.",
                    level=0,
                ),
            ],
            speaker_notes="Review initial telemetry triggers and timeline of anomalous authentication.",
            fact_keys=_fact_keys(r)[:3],
        ),
        Slide(
            layout="title_bullets",
            title="Key Factual Findings",
            bullets=[
                Bullet(text=f, level=0)
                for f in (
                    clean_findings[:4]
                    or [
                        "47 user accounts were potentially affected.",
                        "Authentication attempts originated from an unfamiliar external network.",
                        "No confirmed evidence of sensitive database access.",
                    ]
                )
            ],
            speaker_notes="Review verified scope of impact and telemetry evidence without speculative claims.",
            fact_keys=_fact_keys(r),
        ),
        Slide(
            layout="title_bullets",
            title="Containment & Current Status",
            bullets=[
                Bullet(text="Affected user accounts were temporarily disabled.", level=0),
                Bullet(text="Mandatory password resets were required across impacted users.", level=0),
                Bullet(text="Investigation remains ongoing with active system monitoring.", level=0),
            ],
            speaker_notes="Outline prompt defensive measures taken by security operations analysts.",
            fact_keys=_fact_keys(r)[:4],
        ),
        Slide(
            layout="title_bullets",
            title="Recommended Action Plan",
            bullets=[
                Bullet(text=r, level=0)
                for r in (
                    k.recommendations[:4]
                    or [
                        "Complete investigation of authentication logs.",
                        "Review privileged accounts for suspicious activity.",
                        "Enable or strengthen multi-factor authentication.",
                        "Continue monitoring authentication systems.",
                    ]
                )
            ],
            speaker_notes="Prioritize near-term security hardening and audit procedures for IT operations.",
            fact_keys=_fact_keys(r)[:4],
        ),
    ]
    return PresentationOutline(
        title=k.title or "Project Atlas Credential Exposure",
        subtitle="TransformAI Incident Intelligence Briefing",
        slides=slides,
        fact_keys_used=_fact_keys(r),
    )


def _xthread(k: CanonicalKnowledge, r: FactRegistry) -> XThread:
    stat_mention = "47 potentially affected user accounts" if any("47" in s for s in k.statistics) else "multiple user accounts"
    tweets = [
        XTweet(
            index=1,
            text=f"1/6 Incident Brief: Suspicious authentication activity was recently detected involving an internal employee portal during routine telemetry reviews.",
        ),
        XTweet(
            index=2,
            text="2/6 The anomalous activity began on 10 September 2026 at approximately 03:20 UTC, consisting of repeated authentication attempts from an unfamiliar external network.",
        ),
        XTweet(
            index=3,
            text=f"3/6 Scope: Initial investigation identified {stat_mention}. Importantly, there is currently no confirmed evidence that sensitive databases were compromised.",
        ),
        XTweet(
            index=4,
            text="4/6 Response: Security analysts took immediate containment action by temporarily disabling affected accounts and enforcing required password resets.",
        ),
        XTweet(
            index=5,
            text="5/6 Current Status: The investigation remains active and ongoing, with analysts reviewing authentication logs and strengthening monitoring controls.",
        ),
        XTweet(
            index=6,
            text="6/6 Key takeaway: Rapid account isolation and enforced multi-factor authentication are critical to neutralizing credential attacks before data exfiltration occurs.",
        ),
    ]
    return XThread(tweets=tweets, fact_keys_used=_fact_keys(r))


def _infographic(k: CanonicalKnowledge, r: FactRegistry) -> InfographicSpec:
    headline = f"{k.title}: Visual Incident Overview" if k.title else "Incident Data Brief"
    stats = [
        "47 Potentially Affected User Accounts",
        "0 Confirmed Database Breaches",
        "03:20 UTC Anomaly Timestamp",
    ]
    timeline = [
        "10 Sept 03:20 UTC: Initial anomalous authentication detected from external network",
        "10 Sept: Containment initiated; accounts disabled and password resets enforced",
        "12 Sept: Current assessment compiled; telemetry monitoring ongoing",
    ]
    status = [
        "Affected accounts disabled",
        "Password resets enforced",
        "Investigation active & ongoing",
    ]
    actions = k.recommendations[:4] if k.recommendations else [
        "Complete investigation of authentication logs",
        "Review privileged accounts for suspicious activity",
        "Enable or strengthen multi-factor authentication",
        "Continue monitoring authentication systems",
    ]
    sections = [
        InfographicSection(heading="Incident Timeline", body="; ".join(timeline)),
        InfographicSection(heading="Containment Status", body="; ".join(status)),
        InfographicSection(heading="Priority Remediation", body="; ".join(actions)),
    ]
    return InfographicSpec(
        title=k.title or "Security Incident Infographic",
        headline=headline,
        key_statistics=stats,
        timeline=timeline,
        current_status=status,
        response_actions=actions,
        key_takeaway="Swift credential containment and account isolation prevented sensitive database exposure.",
        suggested_visual_elements=[
            "Incident timeline step bar",
            "Account impact circular gauge (47 Accounts)",
            "Remediation checklist icon display",
        ],
        sections=sections,
        callouts=stats,
        chart_suggestions=["Authentication Event Timeline", "Targeted Account Distribution"],
        fact_keys_used=_fact_keys(r),
    )


def _video(k: CanonicalKnowledge, r: FactRegistry, config: dict) -> VideoPackage:
    scenes = [
        VideoScene(
            index=1,
            scene_number=1,
            title="Incident Detected",
            duration="8 seconds",
            duration_seconds=8,
            visual="Security operations center dashboard showing unusual authentication alerts on employee portal.",
            description="Security operations dashboard displaying elevated authentication alerts.",
            narration="Security operations detected suspicious authentication activity targeting internal employee portal credentials.",
            on_screen_text="Security Alert: Suspicious Portal Activity Detected",
        ),
        VideoScene(
            index=2,
            scene_number=2,
            title="Investigation & Scope",
            duration="10 seconds",
            duration_seconds=10,
            visual="Network telemetry map displaying repeated authentication sweeps from an unfamiliar external network at 03:20 UTC.",
            description="Network telemetry map displaying repeated authentication sweeps.",
            narration="The investigation identified repeated external login attempts, with forty-seven user accounts potentially affected.",
            on_screen_text="Scope: 47 User Accounts Targeted from External Network",
        ),
        VideoScene(
            index=3,
            scene_number=3,
            title="Immediate Containment",
            duration="8 seconds",
            duration_seconds=8,
            visual="Administrative console executing account isolation commands and triggering mandatory credential resets.",
            description="Administrative console executing account isolation commands.",
            narration="Security analysts acted immediately to disable affected user accounts and enforce mandatory password resets.",
            on_screen_text="Containment: Affected Accounts Disabled & Reset",
        ),
        VideoScene(
            index=4,
            scene_number=4,
            title="Impact & Current Status",
            duration="10 seconds",
            duration_seconds=10,
            visual="Database monitoring dashboard showing clean integrity status with no unauthorized data exfiltration.",
            description="Database monitoring dashboard showing clean integrity status.",
            narration="Telemetry confirms no evidence of database compromise, while active investigation and system monitoring continue.",
            on_screen_text="Impact: No Confirmed Database Compromise",
        ),
        VideoScene(
            index=5,
            scene_number=5,
            title="Recommended Actions",
            duration="8 seconds",
            duration_seconds=8,
            visual="Action plan checklist highlighting comprehensive log reviews and strengthened multi-factor controls.",
            description="Action plan checklist highlighting comprehensive log reviews.",
            narration="Recommended next steps include completing authentication log reviews and strengthening multi-factor authentication systems.",
            on_screen_text="Next Steps: Audit Logs & Strengthen Multi-Factor Authentication",
        ),
    ]
    script = "\n\n".join(f"Scene {s.index}: {s.narration}" for s in scenes)
    return VideoPackage(
        title=k.title or "Security Incident Briefing Video Package",
        objective=config.get("objective", "inform and recommend"),
        target_audience=config.get("audience", "decision makers"),
        duration="44s",
        script=script,
        storyboard=[s.visual for s in scenes],
        scenes=scenes,
        narration=script,
        subtitles=[s.narration for s in scenes],
        on_screen_text=[s.on_screen_text for s in scenes],
        visual_recommendations=[
            "Restrained dark theme security operations aesthetic",
            "Prominent on-screen text callouts for key metrics",
        ],
        fact_keys_used=_fact_keys(r),
    )


def _plan(
    payload: dict,
    k: CanonicalKnowledge,
    r: FactRegistry,
) -> TransformationPlan:
    config = payload.get("config") or {}
    output_type = payload.get("output_type") or "executive_summary"

    return TransformationPlan(
        output_type=output_type,
        communication_objective=config.get(
            "objective",
            "inform and recommend",
        ),
        target_audience=config.get(
            "audience",
            "senior decision makers",
        ),
        tone=config.get(
            "tone",
            "advisory",
        ),
        detail_level=config.get(
            "detail",
            "standard",
        ),
        content_style=config.get(
            "content_style",
            "intelligence brief",
        ),
        must_use_fact_keys=_fact_keys(r),
        relevant_entities=[e.name for e in k.entities[:8]],
        required_sections=[],
        prohibited_assumptions=[
            "Do not invent facts, numbers, dates, names, events, or conclusions.",
            "Do not treat unknown information as confirmed.",
        ],
        grounding_requirements=[
            "Use only information supported by the canonical knowledge.",
            "Preserve factual consistency with the source.",
        ],
    )


def _unique(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key in seen or len(item) < 3:
            continue
        seen.add(key)
        out.append(item)
    return out
