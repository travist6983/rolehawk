import json

from fastapi.testclient import TestClient

from offerbound import keychain
from offerbound.keychain import SecretName
from offerbound.llm.fake import FakeProvider, FakeReply
from offerbound.paths import DataPaths


def _sse(body: str) -> list[tuple[str, object]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if line and not line.startswith(":")
        )
        if "event" in fields:
            events.append((fields["event"], json.loads(fields.get("data", "null"))))
    return events


def test_llm_status_routes_and_settings_patch(client: TestClient, paths: DataPaths) -> None:
    status = client.get("/api/llm/status").json()
    assert status["configured"] is True
    assert status["key_source"] == "fake"
    routes = {r["task"]: r["model"] for r in status["routes"]}
    assert routes["rank"] == "claude-haiku-5-5"
    assert routes["write"] == "claude-opus-5-5"

    patched = client.patch(
        "/api/llm/settings", json={"smart_routing": False, "monthly_cap_usd": 25}
    ).json()
    assert {r["model"] for r in patched["routes"]} == {"claude-opus-5-5"}
    assert patched["monthly_cap_usd"] == 25
    config = paths.config_file.read_text(encoding="utf-8")
    assert "smart_routing = false" in config
    assert "monthly_cap_usd = 25" in config

    cleared = client.patch("/api/llm/settings", json={"monthly_cap_usd": None}).json()
    assert cleared["monthly_cap_usd"] is None
    assert client.patch("/api/llm/settings", json={"bogus": 1}).status_code == 422


def test_api_key_goes_to_keychain_never_config(
    client: TestClient, paths: DataPaths, fake: FakeProvider
) -> None:
    key = "sk-ant-api03-supersecretvalue"
    assert client.put("/api/llm/key", json={"api_key": key}).status_code == 200
    assert keychain.get_secret(SecretName.ANTHROPIC_API_KEY) == key
    assert key not in paths.config_file.read_text(encoding="utf-8")

    fake.auth_ok = False
    response = client.put("/api/llm/key", json={"api_key": "sk-ant-api03-badbadbadbad"})
    assert response.status_code == 400
    assert response.json()["kind"] == "LLMAuthError"
    assert keychain.get_secret(SecretName.ANTHROPIC_API_KEY) == key  # unchanged

    assert client.delete("/api/llm/key").status_code == 200
    assert keychain.get_secret(SecretName.ANTHROPIC_API_KEY) is None


def test_estimate_and_models(client: TestClient) -> None:
    body = {"task": "rank", "input_tokens": 10_000, "output_tokens": 1_000, "calls": 10}
    estimate = client.post("/api/llm/estimate", json=body).json()
    assert estimate["model"] == "claude-haiku-5-5"
    assert estimate["cost_usd"] > 0
    assert estimate["exceeds_cap"] is False
    models = client.get("/api/llm/models").json()
    assert any(m["id"] == "claude-opus-5-5" for m in models)


def test_chat_streams_sse_events(client: TestClient, fake: FakeProvider) -> None:
    session = client.post("/api/chat/sessions", json={}).json()
    fake.queue(FakeReply(text="Hello from Claude"))
    response = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"text": "hi", "view": {"label": "Pipeline", "route": "/"}},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse(response.text)
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "text"
    assert "done" in kinds
    text = "".join(data["text"] for kind, data in events if kind == "text")  # type: ignore[index]
    assert text == "Hello from Claude"

    history = client.get(f"/api/chat/sessions/{session['id']}/messages").json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["context"]["view"]["label"] == "Pipeline"
    assert client.post("/api/chat/sessions/missing/messages", json={"text": "x"}).status_code == 404


def test_memory_endpoints(client: TestClient) -> None:
    memory = client.get("/api/memory").json()
    assert memory["profile"].startswith("# Profile")
    assert client.get("/api/memory/proposals").json() == []
    assert client.post("/api/memory/proposals/999/accept").status_code == 404


def test_commands_endpoint(client: TestClient) -> None:
    names = {c["name"] for c in client.get("/api/commands").json()}
    assert {"selftest", "context", "memory", "spend"} <= names
    spend = client.post("/api/commands/spend", json={}).json()
    assert spend["result"]["month_to_date_usd"] == 0
    bad = client.post("/api/commands/selftest", json={"params": {"steps": 999}})
    assert bad.status_code == 422
    assert client.post("/api/commands/nope", json={}).status_code == 404


def test_not_configured_maps_to_409(paths: DataPaths) -> None:
    from offerbound.api.app import create_app
    from tests.conftest import BASE_URL, TEST_TOKEN

    app = create_app(paths=paths, token=TEST_TOKEN, extra_origins=())
    with TestClient(app, base_url=BASE_URL, headers={"X-Offerbound-Token": TEST_TOKEN}) as c:
        assert c.get("/api/llm/status").json()["configured"] is False
        session = c.post("/api/chat/sessions", json={}).json()
        events = _sse(
            c.post(f"/api/chat/sessions/{session['id']}/messages", json={"text": "hi"}).text
        )
        assert events[-1][0] == "error"
        data = events[-1][1]
        assert isinstance(data, dict)
        assert data["kind"] == "LLMNotConfiguredError"
