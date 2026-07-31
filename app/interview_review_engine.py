"""真实面试逐字稿解析与复盘分析，长文本按批处理后再做确定性聚合。"""

import json
import re
from collections.abc import Iterable
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent_contracts import invoke_structured
from app.config import Settings
from app.model_gateway import create_chat_model


class TranscriptSegment(BaseModel):
    segment_id: str = Field(min_length=1, max_length=128)
    speaker: Literal["interviewer", "candidate", "unknown"]
    text: str = Field(min_length=1, max_length=20_000)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)


class ReviewTurnAssessment(BaseModel):
    turn_index: int = Field(ge=1)
    score: float = Field(ge=0, le=10)
    dimensions: dict[str, float]
    strengths: list[str] = Field(default_factory=list, max_length=5)
    weaknesses: list[str] = Field(default_factory=list, max_length=5)
    feedback: str
    improved_answer: str


class InterviewReviewResult(BaseModel):
    overall_summary: str
    dimension_scores: dict[str, float]
    strengths: list[str] = Field(default_factory=list, max_length=10)
    weaknesses: list[str] = Field(default_factory=list, max_length=10)
    action_plan: list[str] = Field(default_factory=list, max_length=10)
    turns: list[ReviewTurnAssessment]


_PREFIX = re.compile(
    r"^(面试官|问|interviewer|候选人|答|candidate)\s*[：:]\s*",
    re.IGNORECASE,
)
_CANDIDATE_DECLARATION = re.compile(
    r"^\s*候选人\s*[：:]\s*([^，,。；;\s：:]{2,30})(?:\s*[，,。；;]|\s*$)",
    re.MULTILINE,
)
_INTERVIEWER_LINE = re.compile(
    r"^\s*(面试官|问|interviewer)\s*[：:]\s*(.*)$",
    re.IGNORECASE,
)
_GENERIC_CANDIDATE_LINE = re.compile(
    r"^\s*(候选人|答|candidate)\s*[：:]\s*(.*)$",
    re.IGNORECASE,
)
_TIMESTAMP_LINE = re.compile(r"^\s*\[\d{1,2}:\d{2}(?::\d{2})?]\s*$")
_SECTION_LINE = re.compile(
    r"^\s*(?:#{1,6}\s+|[一二三四五六七八九十百]+、)\S"
)
_SEPARATOR_LINE = re.compile(r"^\s*[=\-—_]{4,}\s*$")


def parse_text_transcript(text: str) -> list[TranscriptSegment]:
    normalized = text.lstrip("\ufeff")
    aliases = {
        match.group(1).strip()
        for match in _CANDIDATE_DECLARATION.finditer(normalized)
        if re.search(
            rf"(?m)^\s*{re.escape(match.group(1).strip())}\s*[：:]\s*",
            normalized,
        )
    }
    structured = _parse_structured_transcript(normalized, aliases)
    if structured:
        return structured

    blocks = [
        block.strip()
        for block in re.split(
            r"\n\s*\n|\n(?=(?:面试官|问|候选人|答)[：:])",
            normalized,
        )
        if block.strip()
    ]
    segments = []
    for index, block in enumerate(blocks):
        match = _PREFIX.match(block)
        label = match.group(1).casefold() if match else ""
        if label in {"面试官", "问", "interviewer"}:
            speaker = "interviewer"
        elif label in {"候选人", "答", "candidate"}:
            speaker = "candidate"
        else:
            speaker = "unknown"
        content = _PREFIX.sub("", block, count=1).strip()
        if content:
            segments.append(
                TranscriptSegment(
                    segment_id=f"segment-{index + 1}",
                    speaker=speaker,
                    text=content,
                )
            )
    if not segments:
        raise ValueError("逐字稿不能为空")
    return segments


def _parse_structured_transcript(
    text: str,
    candidate_aliases: set[str],
) -> list[TranscriptSegment]:
    lines = text.splitlines()
    first_interviewer = next(
        (
            index
            for index, line in enumerate(lines)
            if _INTERVIEWER_LINE.match(line)
        ),
        None,
    )
    if first_interviewer is None:
        return []

    segments: list[TranscriptSegment] = []
    current_speaker: Literal["interviewer", "candidate"] | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        content = "\n".join(current_lines).strip()
        if current_speaker and content:
            segments.append(
                TranscriptSegment(
                    segment_id=f"segment-{len(segments) + 1}",
                    speaker=current_speaker,
                    text=content,
                )
            )
        current_lines = []

    for line_index, line in enumerate(
        lines[first_interviewer:],
        start=first_interviewer,
    ):
        stripped = line.strip()
        if (
            current_speaker
            and _SECTION_LINE.match(stripped)
            and "面试后复盘" in stripped
        ):
            flush()
            break

        speaker: Literal["interviewer", "candidate"] | None = None
        content = ""
        interviewer_match = _INTERVIEWER_LINE.match(line)
        candidate_match = _GENERIC_CANDIDATE_LINE.match(line)
        if interviewer_match:
            speaker = "interviewer"
            content = interviewer_match.group(2).strip()
        elif candidate_match:
            speaker = "candidate"
            content = candidate_match.group(2).strip()
        else:
            for alias in candidate_aliases:
                alias_match = re.match(
                    rf"^\s*{re.escape(alias)}\s*[：:]\s*(.*)$",
                    line,
                )
                if alias_match:
                    speaker = "candidate"
                    content = alias_match.group(1).strip()
                    break

        if speaker:
            flush()
            current_speaker = speaker
            if content:
                current_lines.append(content)
            continue
        if (
            not stripped
            or _TIMESTAMP_LINE.match(stripped)
            or _is_document_heading(lines, line_index)
            or _SEPARATOR_LINE.match(stripped)
        ):
            continue
        if current_speaker:
            current_lines.append(stripped)
    flush()
    return segments


def _is_document_heading(lines: list[str], index: int) -> bool:
    if not _SECTION_LINE.match(lines[index].strip()):
        return False
    for following in lines[index + 1 :]:
        if not following.strip():
            continue
        return bool(
            _TIMESTAMP_LINE.match(following)
            or _INTERVIEWER_LINE.match(following)
            or _SEPARATOR_LINE.match(following)
        )
    return True


def pair_confirmed_turns(
    segments: list[TranscriptSegment],
) -> list[dict[str, str]]:
    if any(segment.speaker == "unknown" for segment in segments):
        raise ValueError("请先确认所有片段的说话人")
    turns: list[dict[str, str]] = []
    question = ""
    answers: list[str] = []
    for segment in segments:
        if segment.speaker == "interviewer":
            if question and answers:
                turns.append(
                    {"question": question, "answer": "\n".join(answers)}
                )
            question = segment.text
            answers = []
        elif question:
            answers.append(segment.text)
    if question and answers:
        turns.append({"question": question, "answer": "\n".join(answers)})
    if not turns:
        raise ValueError("至少需要一组面试官问题和候选人回答")
    return turns


def analyze_interview_review(
    *,
    turns: list[dict[str, str]],
    settings: Settings,
) -> InterviewReviewResult:
    if not turns:
        raise ValueError("至少需要一组面试官问题和候选人回答")
    model = create_chat_model(
        "interview_review",
        temperature=0.2,
        max_tokens=min(3000, settings.llm_max_output_tokens),
        timeout_seconds=settings.review_analysis_timeout_seconds,
        max_retries=settings.review_analysis_max_retries,
        settings=settings,
    )
    batch_size = max(1, settings.review_analysis_batch_size)
    batches: list[tuple[int, InterviewReviewResult]] = []
    for offset in range(0, len(turns), batch_size):
        indexed_turns = [
            {
                "turn_index": index,
                "interviewer_question": turn["question"],
                "candidate_answer": turn["answer"],
            }
            for index, turn in enumerate(
                turns[offset : offset + batch_size],
                start=offset + 1,
            )
        ]
        result = _analyze_review_batch(model, indexed_turns)
        expected = {
            item["turn_index"]
            for item in indexed_turns
        }
        if {turn.turn_index for turn in result.turns} != expected:
            raise ValueError("复盘结果与确认的问答回合不一致")
        batches.append((len(indexed_turns), result))

    if len(batches) == 1:
        return batches[0][1]
    return _aggregate_review_batches(batches)


def _analyze_review_batch(
    model: object,
    indexed_turns: list[dict[str, object]],
) -> InterviewReviewResult:
    return invoke_structured(
        model,
        [
            SystemMessage(
                content=(
                    "你是面试复盘教练，只评价candidate_answer，不评价面试官。"
                    "只输出JSON，不作招聘结论。四维为accuracy、depth、"
                    "communication、practicality，均为0到10。当前输入可能只是"
                    "整场面试的一个批次；摘要和总体项只概括当前批次。turns必须"
                    "按输入turn_index原样返回。格式："
                    '{"overall_summary":"","dimension_scores":{},'
                    '"strengths":[],"weaknesses":[],"action_plan":[],'
                    '"turns":[{"turn_index":1,"score":0,"dimensions":{},'
                    '"strengths":[],"weaknesses":[],"feedback":"",'
                    '"improved_answer":""}]}'
                )
            ),
            HumanMessage(
                content=json.dumps(indexed_turns, ensure_ascii=False)
            ),
        ],
        InterviewReviewResult,
    )


def _unique(items: Iterable[str], *, limit: int = 10) -> list[str]:
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in result:
            result.append(normalized)
        if len(result) == limit:
            break
    return result


def _aggregate_review_batches(
    batches: list[tuple[int, InterviewReviewResult]],
) -> InterviewReviewResult:
    total_turns = sum(size for size, _ in batches)
    dimensions = {
        dimension: round(
            sum(
                result.dimension_scores.get(dimension, 0.0) * size
                for size, result in batches
            )
            / total_turns,
            2,
        )
        for dimension in {
            key
            for _, result in batches
            for key in result.dimension_scores
        }
    }
    summaries = [
        f"第{result.turns[0].turn_index}–{result.turns[-1].turn_index}题："
        f"{result.overall_summary.strip()}"
        for _, result in batches
        if result.turns and result.overall_summary.strip()
    ]
    return InterviewReviewResult(
        overall_summary="\n".join(summaries),
        dimension_scores=dimensions,
        strengths=_unique(
            item
            for _, result in batches
            for item in result.strengths
        ),
        weaknesses=_unique(
            item
            for _, result in batches
            for item in result.weaknesses
        ),
        action_plan=_unique(
            item
            for _, result in batches
            for item in result.action_plan
        ),
        turns=[
            turn
            for _, result in batches
            for turn in result.turns
        ],
    )
