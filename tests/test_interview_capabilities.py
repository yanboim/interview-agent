"""模拟面试能力维度的测试。"""

from app.application.interview_capabilities import (
    ASSESSMENT_DIMENSIONS,
    AnswerEvaluationRequestV1,
    AnswerEvaluationResultV1,
    QuestionGenerationRequestV1,
    QuestionGenerationResultV1,
)
from app import multi_agent
from app.interview_engine import ModelInterviewCapabilities


def test_question_contracts_are_versioned():
    request = QuestionGenerationRequestV1(
        topic="RAG", level="高级", turn_index=1
    )
    result = QuestionGenerationResultV1(question="如何评估召回质量？")

    assert request.schema_version == "question-request-v1"
    assert result.schema_version == "question-text-v1"
    assert result.prompt_version == "interview-question-v1"


def test_assessment_contract_has_one_authoritative_rubric():
    request = AnswerEvaluationRequestV1(
        topic="Python", level="高级", question="解释 GIL", answer="回答"
    )
    result = AnswerEvaluationResultV1(
        overall=7,
        dimensions={name: 7 for name in ASSESSMENT_DIMENSIONS},
        feedback="继续补充边界条件",
        reference_answer="参考回答",
    )

    assert request.schema_version == "assessment-request-v1"
    assert tuple(result.dimensions) == ASSESSMENT_DIMENSIONS
    assert result.schema_version == "assessment-v1"


def test_chat_specialists_reuse_authoritative_question_and_rubric_prompts():
    assert "一次只提出一个清晰、可评分" in multi_agent.INTERVIEWER_PROMPT
    for label in ("技术准确性", "原理深度", "表达结构", "工程实践"):
        assert label in multi_agent.EVALUATOR_PROMPT


def test_model_adapter_consumes_versioned_contracts(monkeypatch):
    from app import interview_engine

    monkeypatch.setattr(interview_engine, "_generate_question", lambda **_: "问题")
    monkeypatch.setattr(
        interview_engine,
        "_assess_answer",
        lambda **_: {
            "overall": 8,
            "dimensions": {name: 8 for name in ASSESSMENT_DIMENSIONS},
            "strengths": [],
            "weaknesses": [],
            "feedback": "反馈",
            "reference_answer": "参考",
        },
    )
    capabilities = ModelInterviewCapabilities()

    question = capabilities.generate(
        QuestionGenerationRequestV1(topic="RAG", level="高级", turn_index=1)
    )
    assessment = capabilities.evaluate(
        AnswerEvaluationRequestV1(
            topic="RAG", level="高级", question="问题", answer="回答"
        )
    )

    assert question.question == "问题"
    assert assessment.overall == 8
