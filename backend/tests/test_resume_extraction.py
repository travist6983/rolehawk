"""Reading a resume with Claude, end to end through the real SDK (mocked HTTP, no network).

The first install test failed here: "Read with Claude" on a PDF or a .docx showed only "The AI
request failed." The structured-output schema (Profile + Preferences) had 44 optional and 24
nullable fields, over the API's limits of 24 and 16, so every call got a 400 "Schema is too
complex for compilation". The all-required wire schema that fixed it was still too big as one
grammar (400 "The compiled grammar is too large"), so profile and preferences are now two
requests. These tests send the requests the way the app does and check each schema against the
limits, using the fictional fixture resumes.
"""

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel

from rolehawk.apply.drafts import ApplicationDraft
from rolehawk.apply.followup import FollowUpDraftOut
from rolehawk.apply.review import ReviewResult
from rolehawk.fit.rubric import FitBatch
from rolehawk.insights.calibration import CalibrationOut
from rolehawk.llm.anthropic_provider import AnthropicProvider
from rolehawk.llm.errors import LLMRequestError, LLMSchemaError
from rolehawk.llm.schema import (
    MAX_OPTIONAL_FIELDS,
    MAX_PROPERTIES,
    MAX_UNION_FIELDS,
    check_output_schema,
    schema_complexity,
)
from rolehawk.memory.extraction import ExtractedProposals
from rolehawk.memory.sessions import SessionSummary
from rolehawk.paths import DataPaths
from rolehawk.portals.custom.generate import AiDraft
from rolehawk.profile.extraction import ExtractedSetup, ExtractionOut, WirePreferences, WireProfile
from rolehawk.profile.model import RemotePreference
from rolehawk.services.runtime import Runtime, open_runtime

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"

Handler = Callable[[httpx2.Request], httpx2.Response]

# Every schema the app asks Claude to fill with structured outputs.
STRUCTURED_SCHEMAS: list[type[BaseModel]] = [
    WireProfile,
    WirePreferences,
    FitBatch,
    ApplicationDraft,
    ReviewResult,
    FollowUpDraftOut,
    ExtractedProposals,
    SessionSummary,
    CalibrationOut,
    AiDraft,
]


@pytest.mark.parametrize("schema", STRUCTURED_SCHEMAS, ids=lambda s: s.__name__)
def test_every_structured_schema_is_within_the_api_limits(schema: type[BaseModel]) -> None:
    found = check_output_schema(schema)
    assert found.optional <= MAX_OPTIONAL_FIELDS
    assert found.unions <= MAX_UNION_FIELDS
    assert found.properties <= MAX_PROPERTIES


def test_the_profile_model_itself_is_too_complex_to_send() -> None:
    found = schema_complexity(ExtractedSetup.model_json_schema())
    assert not found.ok  # why extraction uses the ExtractionOut wire schema
    with pytest.raises(ValueError, match="too complex"):
        check_output_schema(ExtractedSetup)


def test_profile_and_preferences_are_too_big_to_send_together() -> None:
    # 49 properties as one schema: the API said "The compiled grammar is too large".
    found = schema_complexity(ExtractionOut.model_json_schema())
    assert found.optional == found.unions == 0
    assert found.properties > MAX_PROPERTIES
    with pytest.raises(ValueError, match="49 properties"):
        check_output_schema(ExtractionOut)


def _wire_reply() -> dict[str, Any]:
    """A reply Claude could give for the fixture resume (fictional person)."""
    return {
        "profile": {
            "contact": {
                "name": "Ada Example",
                "email": "ada@example.com",
                "phone": "+1 555 0100",
                "location": "Austin, TX",
                "links": ["github.com/ada-example", ""],
            },
            "headline": "Senior Frontend Engineer",
            "summary": "",
            "experience": [
                {
                    "title": "Senior Frontend Engineer",
                    "company": "Northwind Payments",
                    "location": "Remote",
                    "start": "2021-03",
                    "end": "",
                    "current": True,
                    "highlights": ["Led the checkout redesign, lifting conversion 12%"],
                },
                {
                    "title": "Frontend Engineer",
                    "company": "Contoso Health",
                    "location": "Austin, TX",
                    "start": "2017-06",
                    "end": "2021-02",
                    "current": False,
                    "highlights": ["Mentored four junior engineers"],
                },
            ],
            "education": [
                {
                    "institution": "University of Texas at Austin",
                    "degree": "BSc",
                    "field": "Computer Science",
                    "start": "2013",
                    "end": "2017",
                    "notes": "",
                }
            ],
            "skills": ["TypeScript", "React"],
            "projects": [],
            "certifications": [],
            "achievements": [],
            "languages": [],
        },
        "preferences": {
            "target_titles": [],
            "seniority": "",
            "locations": [],
            "remote": "remote",
            "country": "",
            "salary_amount": 0,
            "salary_currency": "",
            "salary_period": "year",
            "work_authorization": "",
            "deal_breakers": [],
            "energizing": [],
            "draining": [],
        },
    }


def _message(text: str) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 400},
    }


class FakeAnthropic:
    """Plays the Messages API: refuses over-limit schemas the way the real one does."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body: dict[str, Any] = json.loads(request.content)
        self.bodies.append(body)
        schema = body["output_config"]["format"]["schema"]
        found = schema_complexity(schema)
        refusal = None
        if found.optional > MAX_OPTIONAL_FIELDS or found.unions > MAX_UNION_FIELDS:
            refusal = "Schema is too complex for compilation."
        elif found.properties > MAX_PROPERTIES:
            refusal = (
                "The compiled grammar is too large, which would cause performance issues. "
                "Simplify your tool schemas or reduce the number of strict tools."
            )
        if refusal is not None:
            error = {"type": "invalid_request_error", "message": refusal}
            return httpx2.Response(400, json={"type": "error", "error": error})
        half = "profile" if "contact" in schema["properties"] else "preferences"
        return httpx2.Response(200, json=_message(json.dumps(_wire_reply()[half])))


@pytest.fixture
def api() -> FakeAnthropic:
    return FakeAnthropic()


@pytest.fixture
async def real_sdk_runtime(paths: DataPaths, api: FakeAnthropic) -> AsyncIterator[Runtime]:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(api))
    provider = AnthropicProvider("sk-ant-test-key", http_client=client, max_retries=0)
    rt = open_runtime(paths, provider=provider)
    yield rt
    await rt.aclose()


@pytest.mark.parametrize("filename", ["ada_example.pdf", "ada_example.docx"])
async def test_read_with_claude_works_for_pdf_and_docx(
    real_sdk_runtime: Runtime, api: FakeAnthropic, filename: str
) -> None:
    doc = real_sdk_runtime.setup.add_document(filename, (FIXTURES / filename).read_bytes())
    draft = await real_sdk_runtime.setup.extract([doc.id], task_id=None)

    profile_body, preferences_body = api.bodies
    for body in api.bodies:
        assert "Northwind Payments" in body["messages"][0]["content"]  # the document's text went
        assert schema_complexity(body["output_config"]["format"]["schema"]).ok
    assert "contact" in profile_body["output_config"]["format"]["schema"]["properties"]
    assert "remote" in preferences_body["output_config"]["format"]["schema"]["properties"]

    profile = draft.profile
    assert profile.contact.name == "Ada Example"
    assert profile.contact.links == ["github.com/ada-example"]  # blanks dropped
    assert profile.summary is None  # "" on the wire means not stated
    current, past = profile.experience
    assert current.current is True
    assert current.end is None
    assert past.end == "2021-02"
    assert profile.education[0].notes is None
    assert draft.preferences.remote is RemotePreference.REMOTE
    assert draft.preferences.salary_floor is None  # amount 0 means not stated


async def test_a_rejected_request_says_what_claude_said(
    real_sdk_runtime: Runtime, api: FakeAnthropic, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pretend a future schema slipped past the local check: the message names the cause.
    import rolehawk.llm.service as service

    monkeypatch.setattr(service, "check_output_schema", lambda _schema: None)
    monkeypatch.setattr("rolehawk.profile.extraction.WireProfile", ExtractedSetup)
    doc = real_sdk_runtime.setup.add_document(
        "cv.docx", (FIXTURES / "ada_example.docx").read_bytes()
    )
    with pytest.raises(LLMRequestError) as caught:
        await real_sdk_runtime.setup.extract([doc.id], task_id=None)
    message = caught.value.user_message
    assert "Schema is too complex for compilation." in message
    assert "RoleHawk bug" in message
    assert "github.com/travist6983/rolehawk/issues" in message


async def test_a_grammar_too_large_refusal_is_reported_the_same_way(
    real_sdk_runtime: Runtime, api: FakeAnthropic, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The 0.2.1 failure: all fields required, but too many of them for one grammar.
    import rolehawk.llm.service as service

    monkeypatch.setattr(service, "check_output_schema", lambda _schema: None)
    monkeypatch.setattr("rolehawk.profile.extraction.WireProfile", ExtractionOut)
    doc = real_sdk_runtime.setup.add_document(
        "cv.docx", (FIXTURES / "ada_example.docx").read_bytes()
    )
    with pytest.raises(LLMRequestError) as caught:
        await real_sdk_runtime.setup.extract([doc.id], task_id=None)
    assert "The compiled grammar is too large" in caught.value.user_message
    assert "RoleHawk bug" in caught.value.user_message


async def test_an_over_limit_schema_is_caught_before_sending(
    real_sdk_runtime: Runtime, api: FakeAnthropic
) -> None:
    from rolehawk.llm.types import Message, SystemBlock, Task

    with pytest.raises(LLMSchemaError) as caught:
        await real_sdk_runtime.llm.structured(
            command="setup",
            task=Task.EXTRACT,
            system=[SystemBlock("x")],
            messages=[Message(role="user", text="x")],
            schema=ExtractedSetup,
        )
    assert api.bodies == []  # nothing was sent or billed
    assert "RoleHawk bug" in caught.value.user_message


def test_wire_round_trip_keeps_every_fact() -> None:
    setup = ExtractionOut.model_validate(_wire_reply()).to_setup()
    again = ExtractionOut.from_setup(setup).to_setup()
    assert again == setup
