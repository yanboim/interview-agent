import pytest
from langchain_core.messages import AIMessage

from app.agent_contracts import (
    AssessmentV1,
    SpecialistResultV1,
    StructuredOutputError,
    invoke_structured,
    validate_structured_text,
)


VALID_ASSESSMENT = (
    '{"overall":8,"dimensions":{"accuracy":8,"depth":8,'
    '"communication":8,"practicality":8},"strengths":[],'
    '"weaknesses":[],"feedback":"ok","reference_answer":"answer"}'
)


class RepairModel:
    def __init__(self, outputs: list[str]):
        self.outputs = outputs
        self.calls = 0

    def invoke(self, _messages):
        output = self.outputs[self.calls]
        self.calls += 1
        return AIMessage(content=output)


def test_single_object_parser_rejects_truncation_and_multiple_objects():
    for value in ('{"overall": 8', VALID_ASSESSMENT + " {}"):
        with pytest.raises(StructuredOutputError):
            validate_structured_text(value, AssessmentV1)


def test_structured_invocation_repairs_once():
    model = RepairModel(["not-json", VALID_ASSESSMENT])

    result = invoke_structured(model, [], AssessmentV1)

    assert result.overall == 8
    assert model.calls == 2


def test_structured_invocation_prefers_native_provider_schema():
    class NativeRunner:
        def invoke(self, _messages):
            return AssessmentV1.model_validate_json(VALID_ASSESSMENT)

    class NativeModel:
        profile = {"structured_output": True}

        def invoke(self, _messages):
            raise AssertionError("plain invocation must not be used")

        def with_structured_output(self, schema, method):
            assert schema is AssessmentV1
            assert method == "json_schema"
            return NativeRunner()

    result = invoke_structured(NativeModel(), [], AssessmentV1)

    assert result.overall == 8


def test_structured_invocation_fails_after_one_repair():
    model = RepairModel(["not-json", "still-not-json"])

    with pytest.raises(StructuredOutputError, match="after one repair"):
        invoke_structured(model, [], AssessmentV1)
    assert model.calls == 2


def test_specialist_result_rejects_unknown_citation():
    with pytest.raises(StructuredOutputError):
        validate_structured_text(
            '{"schema_version":"agent-schema-v1","answer":"结论",'
            '"citations":[{"claim":"结论","evidence_ids":["missing"],'
            '"support":"supported"}],"sources":[],"warnings":[]}',
            SpecialistResultV1,
        )
