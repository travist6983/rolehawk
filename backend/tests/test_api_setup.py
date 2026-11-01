import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rolehawk import cli
from rolehawk.llm.fake import FakeProvider
from rolehawk.paths import DataPaths
from tests.test_setup import extracted

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"


def wait_for_task(client: TestClient, task_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        task: dict[str, object] = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] in {"succeeded", "failed", "cancelled"}:
            return task
        time.sleep(0.02)
    raise AssertionError("task did not finish")


def test_upload_extract_review_apply(client: TestClient, fake: FakeProvider) -> None:
    pdf = (FIXTURES / "ada_example.pdf").read_bytes()
    uploaded = client.post(
        "/api/setup/documents", files={"file": ("Ada CV.pdf", pdf, "application/pdf")}
    )
    assert uploaded.status_code == 201
    doc = uploaded.json()
    assert doc["kind"] == "pdf"
    assert client.get("/api/setup/documents").json()[0]["id"] == doc["id"]

    assert client.get("/api/setup/draft").status_code == 404
    fake.queue_structured(extracted())
    started = client.post("/api/setup/extract", json={"document_ids": [doc["id"]]})
    assert started.status_code == 202
    task = wait_for_task(client, started.json()["task_id"])
    assert task["status"] == "succeeded"

    draft = client.get("/api/setup/draft").json()
    assert draft["profile"]["experience"][0]["company"] == "Northwind Payments"
    assert client.get("/api/profile").json()["profile"]["experience"] == []  # not yet

    edited = {"profile": draft["profile"], "preferences": {"target_titles": ["Staff Engineer"]}}
    applied = client.post("/api/setup/draft/apply", json=edited).json()
    assert applied["added"]["experience"] == 1
    overview = client.get("/api/profile").json()
    assert overview["profile"]["contact"]["name"] == "Ada Example"
    assert [t["title"] for t in overview["search_targets"]] == ["Staff Engineer"]
    assert 0 < overview["completeness"]["score"] < 100
    assert client.get("/api/setup/draft").status_code == 404


def test_paste_text_and_bad_uploads(client: TestClient) -> None:
    pasted = client.post("/api/setup/documents/text", json={"text": "Ada Example\nEngineer"})
    assert pasted.status_code == 201
    assert pasted.json()["filename"] == "pasted-cv.txt"
    bad = client.post("/api/setup/documents", files={"file": ("x.bin", b"\x00\x01" * 100)})
    assert bad.status_code == 400
    assert "isn't supported" in bad.json()["detail"]


def test_extract_without_claude_explains(paths: DataPaths) -> None:
    from rolehawk.api.app import create_app
    from tests.conftest import BASE_URL, TEST_TOKEN

    app = create_app(paths=paths, token=TEST_TOKEN, extra_origins=())
    with TestClient(app, base_url=BASE_URL, headers={"X-RoleHawk-Token": TEST_TOKEN}) as c:
        doc = c.post("/api/setup/documents/text", json={"text": "Ada, Engineer at Acme"}).json()
        task = wait_for_task(
            c, c.post("/api/setup/extract", json={"document_ids": [doc["id"]]}).json()["task_id"]
        )
        assert task["status"] == "failed"
        assert "Connect Claude in Settings" in str(task["error"])


def test_interview_endpoints(client: TestClient) -> None:
    state = client.get("/api/setup/interview").json()
    assert state["question"]["id"] == "basics.contact"
    assert state["question"]["kind"] == "form"

    rejected = client.post(
        "/api/setup/interview/answer",
        json={"question_id": "basics.contact", "value": {"name": ""}},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "Name is required."
    assert (
        client.post("/api/setup/interview/skip", json={"question_id": "basics.contact"}).status_code
        == 422
    )

    after = client.post(
        "/api/setup/interview/answer",
        json={"question_id": "basics.contact", "value": {"name": "Sam Rivera"}},
    ).json()
    assert after["question"]["id"] == "role.add"
    skipped = client.post("/api/setup/interview/skip", json={"question_id": "role.add"}).json()
    assert skipped["question"]["id"] == "profile.skills"
    restarted = client.post("/api/setup/interview/restart").json()
    assert restarted["question"]["id"] == "role.add"


def test_put_memory_saves_hand_edits_verbatim(client: TestClient, paths: DataPaths) -> None:
    markdown = "# Profile\n\n## Skills\n\n- Go\n- Rust\n\n## My notes\n\nAnything I like.\n"
    snapshot = client.put("/api/memory/profile", json={"markdown": markdown}).json()
    assert snapshot["profile"] == markdown
    assert (paths.memory / "profile.md").read_text(encoding="utf-8") == markdown
    assert client.get("/api/profile").json()["profile"]["skills"] == ["Go", "Rust"]
    assert client.put("/api/memory/secrets", json={"markdown": "x"}).status_code == 422


def test_setup_commands_for_skills(capsys: pytest.CaptureFixture[str]) -> None:
    path = FIXTURES / "linkedin_export.zip"
    assert cli.main(["run", "setup-import", "--param", f"path={path}", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["kind"] == "linkedin"
    assert (
        cli.main(
            [
                "run",
                "setup-extract",
                "--params-json",
                json.dumps({"document_ids": [doc["id"]]}),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert cli.main(["run", "setup-apply", "--json"]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["added"]["experience"] == 2
    assert cli.main(["run", "setup", "--json"]) == 0
    overview = json.loads(capsys.readouterr().out)
    assert overview["interview"]["question"]["id"] == "role.more"


def test_chat_cannot_run_file_reading_commands(client: TestClient, fake: FakeProvider) -> None:
    from rolehawk.llm.fake import FakeReply
    from rolehawk.llm.types import ToolCall

    session = client.post("/api/chat/sessions", json={}).json()
    fake.queue(
        FakeReply(
            tool_calls=[
                ToolCall(
                    "t1",
                    "run_command",
                    {"command": "setup-import", "params_json": '{"path": "/etc/passwd"}'},
                )
            ]
        ),
        FakeReply(text="I can't do that from chat."),
    )
    client.post(f"/api/chat/sessions/{session['id']}/messages", json={"text": "import my file"})
    result = fake.requests[1].messages[-1].tool_results[0]
    assert result.is_error
    assert "Unknown command" in result.content
    assert "setup-import" not in fake.requests[0].system[0].text
