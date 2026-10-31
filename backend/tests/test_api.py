import time

import pytest
from fastapi.testclient import TestClient

from offerbound.api.app import create_app
from offerbound.api.security import TOKEN_COOKIE
from offerbound.llm.fake import FakeProvider
from offerbound.paths import DataPaths
from tests.conftest import BASE_URL, TEST_TOKEN


def test_health_is_public(anon_client: TestClient) -> None:
    response = anon_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_requires_token(anon_client: TestClient) -> None:
    assert anon_client.get("/api/tasks").status_code == 401
    assert anon_client.get("/api/tasks", headers={"X-Offerbound-Token": "wrong"}).status_code == 401


def test_header_token_allows_all_methods(client: TestClient) -> None:
    assert client.get("/api/tasks").status_code == 200
    assert (
        client.post(
            "/api/commands/selftest", json={"params": {"steps": 1, "delay_s": 0}}
        ).status_code
        == 200
    )


def test_launch_url_sets_cookie_for_safe_methods_only(anon_client: TestClient) -> None:
    launch = anon_client.get(f"/?token={TEST_TOKEN}")
    set_cookie = launch.headers.get("set-cookie", "")
    assert f"{TOKEN_COOKIE}={TEST_TOKEN}" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Strict" in set_cookie

    assert anon_client.get("/api/tasks").status_code == 200  # cookie now stored
    session = anon_client.get("/api/session")
    assert session.status_code == 200
    assert session.json()["token"] == TEST_TOKEN
    # Cookies alone never authorize writes.
    assert anon_client.post("/api/commands/selftest", json={}).status_code == 401


def test_wrong_launch_token_sets_no_cookie(anon_client: TestClient) -> None:
    assert "set-cookie" not in anon_client.get("/?token=nope").headers


@pytest.mark.parametrize("host", ["evil.example:8765", "127.0.0.1:9999", "attacker.localhost"])
def test_dns_rebinding_blocked(client: TestClient, host: str) -> None:
    assert client.get("/api/health", headers={"Host": host}).status_code == 421


def test_foreign_origin_blocked(client: TestClient) -> None:
    response = client.post(
        "/api/tasks/selftest", json={}, headers={"Origin": "http://evil.example"}
    )
    assert response.status_code == 403
    same = client.get("/api/tasks", headers={"Origin": BASE_URL})
    assert same.status_code == 200


def test_dev_origin_allowed_when_configured(paths: DataPaths, fake: FakeProvider) -> None:
    app = create_app(
        paths=paths, token=TEST_TOKEN, extra_origins=["http://127.0.0.1:5173"], provider=fake
    )
    with TestClient(app, base_url=BASE_URL, headers={"X-Offerbound-Token": TEST_TOKEN}) as c:
        assert c.get("/api/tasks", headers={"Origin": "http://127.0.0.1:5173"}).status_code == 200


def test_selftest_runs_to_completion(client: TestClient) -> None:
    body = {"params": {"steps": 2, "delay_s": 0}}
    task_id = client.post("/api/commands/selftest", json=body).json()["task_id"]
    deadline = time.monotonic() + 5
    status = None
    while time.monotonic() < deadline:
        status = client.get(f"/api/tasks/{task_id}").json()["status"]
        if status in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert status == "succeeded"
    assert client.get("/api/tasks").json()[0]["id"] == task_id


def test_unknown_task_404(client: TestClient) -> None:
    assert client.get("/api/tasks/nope").status_code == 404
    assert client.post("/api/tasks/nope/cancel").status_code == 404


def test_startup_creates_data_folder_and_config(paths: DataPaths, client: TestClient) -> None:
    assert paths.db.exists()
    assert paths.config_file.exists()
    assert "api_key" not in paths.config_file.read_text(encoding="utf-8")


def test_openapi_lists_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert {"/api/health", "/api/tasks", "/api/events"} <= set(schema.json()["paths"])
