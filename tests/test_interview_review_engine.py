import json

import pytest
from langchain_core.messages import AIMessage

from app.config import Settings
from app.interview_review_engine import (
    analyze_interview_review,
    pair_confirmed_turns,
    parse_text_transcript,
)


def test_parser_recognizes_declared_candidate_name_and_stops_at_appendix() -> None:
    transcript = """\
AI 应用开发工程师面试记录
候选人：测试同学，岗位：AI 应用开发

一、项目经验
[00:01]
面试官：
请介绍一个项目。

测试同学：
一、我先说明目标。
二、再说明实现。

面试官：如何验证效果？
测试同学：通过离线集和线上指标验证。

十四、面试后复盘记录
面试官：这行属于附录，不应再次解析。
测试同学：这行也属于附录。
"""

    segments = parse_text_transcript(transcript)
    turns = pair_confirmed_turns(segments)

    assert [segment.speaker for segment in segments] == [
        "interviewer",
        "candidate",
        "interviewer",
        "candidate",
    ]
    assert len(turns) == 2
    assert "AI 应用开发工程师面试记录" not in segments[0].text
    assert "一、我先说明目标" in turns[0]["answer"]
    assert all("附录" not in segment.text for segment in segments)


def test_parser_preserves_simple_generic_speaker_format() -> None:
    segments = parse_text_transcript(
        "面试官：问题一\n\n候选人：回答一\n\n问：问题二\n\n答：回答二"
    )

    assert len(pair_confirmed_turns(segments)) == 2
    assert all(segment.speaker != "unknown" for segment in segments)


class FakeReviewModel:
    def __init__(self) -> None:
        self.calls: list[list[int]] = []

    def invoke(self, messages):
        payload = json.loads(messages[-1].content)
        indexes = [item["turn_index"] for item in payload]
        self.calls.append(indexes)
        batch_number = len(self.calls)
        return AIMessage(
            content=json.dumps(
                {
                    "overall_summary": f"批次{batch_number}",
                    "dimension_scores": {
                        "accuracy": batch_number,
                        "depth": batch_number,
                        "communication": batch_number,
                        "practicality": batch_number,
                    },
                    "strengths": ["共同亮点", f"亮点{batch_number}"],
                    "weaknesses": [f"不足{batch_number}"],
                    "action_plan": [f"行动{batch_number}"],
                    "turns": [
                        {
                            "turn_index": index,
                            "score": 7,
                            "dimensions": {
                                "accuracy": 7,
                                "depth": 7,
                                "communication": 7,
                                "practicality": 7,
                            },
                            "strengths": ["清晰"],
                            "weaknesses": ["细节不足"],
                            "feedback": "补充依据。",
                            "improved_answer": "给出目标、实现与验证。",
                        }
                        for index in indexes
                    ],
                },
                ensure_ascii=False,
            )
        )


def test_long_review_is_batched_and_aggregated_with_global_indexes(
    monkeypatch,
) -> None:
    model = FakeReviewModel()
    captured = {}

    def create_model(name, **kwargs):
        captured.update({"name": name, **kwargs})
        return model

    monkeypatch.setattr(
        "app.interview_review_engine.create_chat_model",
        create_model,
    )
    settings = Settings(
        _env_file=None,
        zhipu_api_key="test",
        llm_max_output_tokens=2000,
        review_analysis_batch_size=6,
        review_analysis_timeout_seconds=180,
        review_analysis_max_retries=0,
    )
    turns = [
        {"question": f"问题{index}", "answer": f"回答{index}"}
        for index in range(1, 14)
    ]

    result = analyze_interview_review(turns=turns, settings=settings)

    assert model.calls == [
        [1, 2, 3, 4, 5, 6],
        [7, 8, 9, 10, 11, 12],
        [13],
    ]
    assert [turn.turn_index for turn in result.turns] == list(range(1, 14))
    assert result.dimension_scores["accuracy"] == 1.62
    assert result.strengths == ["共同亮点", "亮点1", "亮点2", "亮点3"]
    assert captured["timeout_seconds"] == 180
    assert captured["max_retries"] == 0


def test_review_batch_rejects_missing_global_turn(monkeypatch) -> None:
    model = FakeReviewModel()
    valid_invoke = model.invoke

    def invoke_with_missing(messages):
        response = valid_invoke(messages)
        payload = json.loads(response.content)
        payload["turns"].pop()
        return AIMessage(content=json.dumps(payload, ensure_ascii=False))

    model.invoke = invoke_with_missing
    monkeypatch.setattr(
        "app.interview_review_engine.create_chat_model",
        lambda *_args, **_kwargs: model,
    )

    with pytest.raises(ValueError, match="问答回合不一致"):
        analyze_interview_review(
            turns=[{"question": "问题", "answer": "回答"}],
            settings=Settings(_env_file=None, zhipu_api_key="test"),
        )
