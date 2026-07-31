"""从已完成的简历评估构造有来源约束、长度受限的定向面试上下文。"""

import re

from pydantic import BaseModel, Field

from app.resume_engine import deserialize_json

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_PRIVATE_LABEL = re.compile(r"(?:姓名|电话|手机|邮箱|住址|地址|婚育|性别)[：:]")


def _safe_claim(value: object) -> str:
    text = str(value).strip()[:300]
    if _PRIVATE_LABEL.search(text):
        return ""
    return _PHONE.sub("[已隐藏电话]", _EMAIL.sub("[已隐藏邮箱]", text))


class ResumeInterviewContext(BaseModel):
    target_role: str = Field(default="", max_length=100)
    experience_level: str = Field(default="", max_length=30)
    job_description: str = Field(default="", max_length=4000)
    demonstrated_keywords: list[str] = Field(default_factory=list, max_length=20)
    keyword_gaps: list[str] = Field(default_factory=list, max_length=20)
    evidence_claims: list[str] = Field(default_factory=list, max_length=20)
    improvement_topics: list[str] = Field(default_factory=list, max_length=20)


def build_resume_interview_context(
    analysis: dict[str, object],
) -> ResumeInterviewContext:
    report = deserialize_json(analysis.get("report_json"), {})
    draft = deserialize_json(analysis.get("draft_json"), {})
    report = report if isinstance(report, dict) else {}
    draft = draft if isinstance(draft, dict) else {}
    issues = report.get("issues", [])
    sections = draft.get("sections", [])
    evidence_claims: list[str] = []
    improvement_topics: list[str] = []
    if isinstance(issues, list):
        for issue in issues[:20]:
            if not isinstance(issue, dict):
                continue
            evidence = _safe_claim(issue.get("evidence") or "")
            suggestion = _safe_claim(issue.get("suggestion") or "")
            if evidence:
                evidence_claims.append(evidence[:300])
            if suggestion:
                improvement_topics.append(suggestion[:300])
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            items = section.get("items", [])
            if isinstance(items, list):
                evidence_claims.extend(
                    safe
                    for item in items
                    if (safe := _safe_claim(item))
                )
    return ResumeInterviewContext(
        target_role=str(analysis.get("target_role") or ""),
        experience_level=str(analysis.get("experience_level") or ""),
        job_description=str(analysis.get("job_description") or "")[:4000],
        demonstrated_keywords=[
            str(item)[:100]
            for item in report.get("keyword_matches", [])
            if str(item).strip()
        ][:20],
        keyword_gaps=[
            str(item)[:100]
            for item in report.get("keyword_gaps", [])
            if str(item).strip()
        ][:20],
        evidence_claims=list(dict.fromkeys(evidence_claims))[:20],
        improvement_topics=list(dict.fromkeys(improvement_topics))[:20],
    )
