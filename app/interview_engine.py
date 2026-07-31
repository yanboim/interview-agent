"""模拟面试的提示词与结果整形；模型传输策略由 model_gateway 统一负责。"""

import json
from functools import lru_cache
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from app.agent_contracts import (
    AssessmentV1,
    invoke_structured,
    validate_structured_text,
)
from app.config import get_settings
from app.model_gateway import PolicyChatOpenAI, create_chat_model


DIMENSIONS = ("accuracy", "depth", "communication", "practicality")
DIMENSION_LABELS = {
    "accuracy": "技术准确性",
    "depth": "原理深度",
    "communication": "表达结构",
    "practicality": "工程实践",
}
STUDY_ACTIONS = {
    "accuracy": "回顾核心概念与边界条件，用知识库逐条校正错误表述。",
    "depth": "补充源码链路、关键数据结构和机制原理，并练习连续追问。",
    "communication": "使用“结论—原理—场景—权衡”四段式重新组织答案。",
    "practicality": "为每个主题补充真实项目案例、指标、故障与复盘数据。",
}


@lru_cache
def get_interviewer_model() -> PolicyChatOpenAI:
    settings = get_settings()
    if not settings.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，无法进行模拟面试。")
    return create_chat_model(
        "interviewer",
        temperature=0.3,
        max_tokens=1200,
        settings=settings,
    )


@lru_cache
def get_evaluator_model() -> PolicyChatOpenAI:
    settings = get_settings()
    if not settings.zhipu_api_key:
        raise RuntimeError("未配置 ZHIPU_API_KEY，无法进行模拟面试。")
    return create_chat_model(
        "evaluator", temperature=0.2, max_tokens=1200, settings=settings
    )


def _message_text(response: Any) -> str:
    if isinstance(response.content, str):
        return response.content.strip()
    return str(response.content).strip()


def generate_question(
    *,
    topic: str,
    level: str,
    turn_index: int,
    previous_turns: list[dict[str, object]],
    resume_context: dict[str, object] | None = None,
) -> str:
    history = "\n".join(
        (
            f"问题：{turn['question']}\n"
            f"候选人回答：{str(turn.get('answer') or '')[:600]}"
        )
        for turn in previous_turns[-3:]
    )
    resume_instruction = ""
    if resume_context:
        resume_instruction = (
            "\n这是基于简历的定向面试。优先轮换考察项目证据、技术决策、本人职责、"
            "量化成果、失败复盘和岗位差距。只能使用下方最小化上下文，不要询问"
            "姓名、联系方式、年龄、性别、婚育、住址等无关个人信息。\n"
            f"简历上下文：{json.dumps(resume_context, ensure_ascii=False)}\n"
        )
    response = get_interviewer_model().invoke(
        [
            SystemMessage(
                content=(
                    "你是一名高级软件工程师面试官。一次只提出一个清晰、可评分的"
                    "中文技术问题，不要给答案、提示或评分标准。避免与历史问题重复。"
                    "如有简历上下文，问题必须关联其中的项目证据或岗位差距。"
                )
            ),
            HumanMessage(
                content=(
                    f"面试主题：{topic}\n难度：{level}\n"
                    f"当前第 {turn_index} 题\n"
                    f"已有问答：\n{history or '无'}\n"
                    f"{resume_instruction}"
                    "请直接输出下一道面试题。"
                )
            ),
        ]
    )
    return _message_text(response)


def parse_assessment(content: str) -> dict[str, Any]:
    parsed = validate_structured_text(content, AssessmentV1)
    data = parsed.model_dump()
    dimensions = data["dimensions"]
    normalized_dimensions = {
        name: max(0.0, min(10.0, float(dimensions.get(name, 0))))
        for name in DIMENSIONS
    }
    overall = data.get("overall")
    if overall is None:
        overall = sum(normalized_dimensions.values()) / len(DIMENSIONS)
    return {
        "overall": max(0.0, min(10.0, float(overall))),
        "dimensions": normalized_dimensions,
        "strengths": [str(item) for item in data["strengths"]][:5],
        "weaknesses": [str(item) for item in data["weaknesses"]][:5],
        "feedback": str(data["feedback"]).strip(),
        "reference_answer": str(data["reference_answer"]).strip(),
    }


def assess_answer(
    *,
    topic: str,
    level: str,
    question: str,
    answer: str,
) -> dict[str, Any]:
    assessment = invoke_structured(
        get_evaluator_model(),
        [
            SystemMessage(
                content=(
                    "你是严格但建设性的高级工程师面试评分官。只输出 JSON，"
                    "不要使用 Markdown 代码块。评分范围 0 到 10。JSON 格式："
                    '{"overall":7.5,"dimensions":{"accuracy":8,'
                    '"depth":7,"communication":8,"practicality":7},'
                    '"strengths":["..."],"weaknesses":["..."],'
                    '"feedback":"包含改进建议的具体点评",'
                    '"reference_answer":"结构完整、可供复盘的参考回答"}。'
                    "reference_answer 使用 Markdown 组织内容；编号、标题和"
                    "列表项之间必须使用换行，并在 JSON 字符串中写成 \\n。"
                )
            ),
            HumanMessage(
                content=(
                    f"主题：{topic}\n难度：{level}\n"
                    f"问题：{question}\n候选人回答：{answer}\n"
                    "请基于技术正确性、原理深度、表达结构和工程实践评分。"
                )
            ),
        ],
        AssessmentV1,
    )
    return parse_assessment(assessment.model_dump_json())


def build_report(turns: list[dict[str, object]]) -> dict[str, Any]:
    assessed = [turn for turn in turns if turn.get("score") is not None]
    if not assessed:
        return {
            "average_score": 0.0,
            "dimension_scores": {name: 0.0 for name in DIMENSIONS},
            "weaknesses": [],
            "study_plan": [],
        }

    dimension_totals = {name: 0.0 for name in DIMENSIONS}
    weakness_counts: dict[str, int] = {}
    for turn in assessed:
        dimensions = json.loads(str(turn.get("dimensions_json") or "{}"))
        for name in DIMENSIONS:
            dimension_totals[name] += float(dimensions.get(name, 0))
        for weakness in json.loads(str(turn.get("weaknesses_json") or "[]")):
            weakness_counts[str(weakness)] = weakness_counts.get(str(weakness), 0) + 1

    dimension_scores = {
        name: round(total / len(assessed), 2)
        for name, total in dimension_totals.items()
    }
    weakest_dimensions = sorted(
        DIMENSIONS,
        key=lambda name: dimension_scores[name],
    )[:2]
    weaknesses = [
        item
        for item, _ in sorted(
            weakness_counts.items(),
            key=lambda pair: pair[1],
            reverse=True,
        )[:5]
    ]
    return {
        "average_score": round(
            sum(float(turn["score"]) for turn in assessed) / len(assessed),
            2,
        ),
        "dimension_scores": {
            DIMENSION_LABELS[name]: dimension_scores[name]
            for name in DIMENSIONS
        },
        "weaknesses": weaknesses,
        "study_plan": [
            {
                "dimension": DIMENSION_LABELS[name],
                "current_score": dimension_scores[name],
                "action": STUDY_ACTIONS[name],
            }
            for name in weakest_dimensions
        ],
    }
