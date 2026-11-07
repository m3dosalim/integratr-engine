# Checks for the Engine shell, in the same order as the build:
# register, ready, health poll, disable, remove, spend.

from fastapi.testclient import TestClient

from app.health_poller import poll_one_pipe
from app.install_tokens import create_install_token
from app.litellm_client import LiteLLMError
from app.main import create_app
from app.read_spend import read_pipe_spend
from app.register_pipe import register_pipe
from app.registration_store import PipeIdTaken, TokenAlreadyUsed
from app.settings import Settings


class MemoryStore:
    def __init__(self):
        # token hash -> True once the token has been used
        self.tokens = {}
        self.pipes = {}

    def insert_install_token(self, token_hash):
        self.tokens[token_hash] = False

    def token_is_unused(self, token_hash):
        return self.tokens.get(token_hash) is False

    def pipe_exists(self, pipe_id):
        return pipe_id in self.pipes

    def claim_token_and_insert_pipe(self, token_hash, pipe_row):
        if self.tokens.get(token_hash) is not False:
            raise TokenAlreadyUsed()
        if pipe_row["id"] in self.pipes:
            raise PipeIdTaken()
        self.tokens[token_hash] = True
        self.pipes[pipe_row["id"]] = dict(pipe_row)

    def get_pipe(self, pipe_id):
        pipe = self.pipes.get(pipe_id)
        if pipe is None:
            return None
        return dict(pipe)

    def mark_ready(self, pipe_id, health_url, pipe_base_url):
        self.pipes[pipe_id]["desired_state"] = "active"
        self.pipes[pipe_id]["health_url"] = health_url
        self.pipes[pipe_id]["pipe_base_url"] = pipe_base_url

    def mark_disabled(self, pipe_id):
        self.pipes[pipe_id]["desired_state"] = "disabled"

    def set_health_state(self, pipe_id, health_state, health_reason):
        self.pipes[pipe_id]["health_state"] = health_state
        self.pipes[pipe_id]["health_reason"] = health_reason

    def delete_pipe(self, pipe_id):
        del self.pipes[pipe_id]

    def list_pipes(self):
        names = sorted(self.pipes.keys())
        rows = []
        for name in names:
            rows.append(dict(self.pipes[name]))
        return rows


class FakeLiteLLM:
    def __init__(self):
        self.minted = []
        self.deleted = []
        self.fail_delete = False
        self.logs = []

    def generate_key(
        self,
        pipe_id,
        models,
        max_budget,
        budget_duration,
        rpm_limit,
        tpm_limit,
        team_id,
    ):
        key = "sk-test-" + pipe_id
        self.minted.append(
            {
                "pipe_id": pipe_id,
                "models": models,
                "max_budget": max_budget,
                "budget_duration": budget_duration,
                "rpm_limit": rpm_limit,
                "tpm_limit": tpm_limit,
                "team_id": team_id,
                "key": key,
            }
        )
        return key

    def delete_key(self, virtual_key):
        if self.fail_delete:
            raise LiteLLMError("delete failed")
        self.deleted.append(virtual_key)

    def get_spend_logs(self, virtual_key, request_id):
        return list(self.logs)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self):
        self.posts = []
        self.get_result = FakeResponse(200, {"status": "ok"})
        self.post_status = 200
        self.fail_get = False

    def get(self, url, timeout):
        if self.fail_get:
            import httpx

            raise httpx.ConnectError("connection refused")
        return self.get_result

    def post(self, url, timeout):
        self.posts.append(url)
        return FakeResponse(self.post_status, {})


def settings():
    return Settings(
        database_url="postgresql://example",
        litellm_internal_url="http://litellm:4000",
        engine_base_url="http://localhost:4000",
        litellm_master_key="sk-master",
        engine_admin_token="admin-token",
        poll_seconds=15,
        host="127.0.0.1",
        port=4100,
    )


def valid_body(token):
    return {
        "token": token,
        "engineApi": "1",
        "id": "image",
        "displayName": "Image",
        "version": "1.0.0",
        "models": ["image-default"],
        "budget": {
            "maxBudget": 20,
            "budgetDuration": "30d",
            "rpmLimit": 30,
        },
        "configSchema": [
            {
                "name": "defaultSize",
                "label": "Default image size",
                "kind": "string",
                "required": True,
                "default": "1024x1024",
            }
        ],
        "dataSchema": [
            {
                "name": "generatedImages",
                "description": "Images this Pipe generated.",
                "retention": "Kept until an admin deletes them in the Image Pipe.",
            }
        ],
    }


def test_register_rejects_a_wrong_contract_version():
    store = MemoryStore()
    litellm = FakeLiteLLM()
    body = valid_body("token")
    body["engineApi"] = "2"

    result = register_pipe(body, store, litellm, "http://localhost:4000", "integratr")

    assert result.status_code == 400
    assert litellm.minted == []
    assert store.pipes == {}


def test_register_rejects_a_secret_default_and_a_foreign_model():
    store = MemoryStore()
    litellm = FakeLiteLLM()
    token = create_install_token(store).body["token"]
    body = valid_body(token)
    body["models"] = ["gpt-4o"]
    body["configSchema"] = [
        {
            "name": "storageKey",
            "label": "Storage key",
            "kind": "secret",
            "required": True,
            "default": "nope",
        }
    ]

    result = register_pipe(body, store, litellm, "http://localhost:4000", "integratr")

    assert result.status_code == 400
    assert len(result.body["errors"]) >= 2
    assert litellm.minted == []


def test_register_mints_one_key_and_returns_it_once():
    store = MemoryStore()
    litellm = FakeLiteLLM()
    token = create_install_token(store).body["token"]

    result = register_pipe(
        valid_body(token),
        store,
        litellm,
        "http://localhost:4000",
        "integratr",
    )

    assert result.status_code == 200
    assert result.body["engineBaseUrl"] == "http://localhost:4000"
    assert result.body["key"] == "sk-test-image"
    assert litellm.minted[0]["models"] == ["image-default"]
    assert litellm.minted[0]["max_budget"] == 20
    assert litellm.minted[0]["rpm_limit"] == 30
    assert litellm.minted[0]["tpm_limit"] is None
    assert litellm.minted[0]["team_id"] == "integratr"

    saved = store.get_pipe("image")
    assert saved["desired_state"] == "inactive"
    assert saved["virtual_key"] == "sk-test-image"
    assert saved["config_schema"][0]["name"] == "defaultSize"


def test_register_rejects_a_used_token_and_a_duplicate_id():
    store = MemoryStore()
    litellm = FakeLiteLLM()
    token = create_install_token(store).body["token"]
    first = register_pipe(
        valid_body(token),
        store,
        litellm,
        "http://localhost:4000",
        "integratr",
    )
    assert first.status_code == 200

    second = register_pipe(
        valid_body(token),
        store,
        litellm,
        "http://localhost:4000",
        "integratr",
    )
    assert second.status_code == 401
    assert len(litellm.minted) == 1

    other = create_install_token(store).body["token"]
    duplicate = valid_body(other)
    duplicate_result = register_pipe(
        duplicate,
        store,
        litellm,
        "http://localhost:4000",
        "integratr",
    )
    assert duplicate_result.status_code == 409
    assert len(litellm.minted) == 1


def test_ready_disable_remove_and_spend_follow_the_spec_order():
    store = MemoryStore()
    litellm = FakeLiteLLM()
    http = FakeHttp()
    app = create_app(settings(), store, litellm, http)
    client = TestClient(app)

    # Step 1. An admin creates an install token.
    token_response = client.post(
        "/admin/install-tokens",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert token_response.status_code == 200
    token = token_response.json()["token"]

    # Step 2. Register with that token.
    register_response = client.post("/pipes/register", json=valid_body(token))
    assert register_response.status_code == 200
    key = register_response.json()["key"]

    # Step 3. Ready requires the virtual key and a /health address.
    ready_response = client.post(
        "/pipes/ready",
        headers={"Authorization": "Bearer " + key},
        json={"id": "image", "healthUrl": "http://image:8080/health"},
    )
    assert ready_response.status_code == 200
    assert store.get_pipe("image")["desired_state"] == "active"
    assert store.get_pipe("image")["pipe_base_url"] == "http://image:8080"

    # Step 4. A health answer of ok is stored. A dead process is unreachable.
    state, reason = poll_one_pipe("http://image:8080/health", http)
    assert state == "ok"
    assert reason is None
    http.fail_get = True
    state, reason = poll_one_pipe("http://image:8080/health", http)
    assert state == "unreachable"
    http.fail_get = False
    http.get_result = FakeResponse(200, {"status": "degraded", "reason": "disk full"})
    state, reason = poll_one_pipe("http://image:8080/health", http)
    assert state == "degraded"
    assert reason == "disk full"

    # Step 5. Disable calls the Pipe, then records disabled.
    disable_response = client.post(
        "/pipes/image/disable",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert disable_response.status_code == 200
    assert http.posts == ["http://image:8080/disable"]
    assert store.get_pipe("image")["desired_state"] == "disabled"

    # Step 6. Spend rows join on pipeId and requestId. The raw key is not returned.
    litellm.logs = [
        {
            "request_id": "litellm-1",
            "api_key": key,
            "spend": 0.2,
            "metadata": {
                "spend_logs_metadata": {
                    "pipeId": "image",
                    "requestId": "req-1",
                }
            },
        },
        {
            "request_id": "litellm-2",
            "spend": 0.1,
            "metadata": {
                "spend_logs_metadata": {
                    "pipeId": "image",
                    "requestId": "req-2",
                }
            },
        },
    ]
    spend = read_pipe_spend("image", "req-1", store, litellm)
    assert spend.status_code == 200
    assert len(spend.body["logs"]) == 1
    assert spend.body["logs"][0]["request_id"] == "litellm-1"
    assert "api_key" not in spend.body["logs"][0]

    # Step 7. Remove revokes the key before the record disappears.
    remove_response = client.post(
        "/pipes/image/remove",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert remove_response.status_code == 200
    assert litellm.deleted == [key]
    assert store.get_pipe("image") is None


def test_remove_keeps_the_record_when_revoke_fails():
    store = MemoryStore()
    litellm = FakeLiteLLM()
    token = create_install_token(store).body["token"]
    register_pipe(valid_body(token), store, litellm, "http://localhost:4000", "integratr")
    litellm.fail_delete = True

    app = create_app(settings(), store, litellm, FakeHttp())
    client = TestClient(app)
    response = client.post(
        "/pipes/image/remove",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 502
    assert store.get_pipe("image") is not None
    assert store.get_pipe("image")["virtual_key"] == "sk-test-image"


def test_disable_does_not_mark_disabled_when_the_pipe_refuses():
    store = MemoryStore()
    litellm = FakeLiteLLM()
    http = FakeHttp()
    http.post_status = 500
    token = create_install_token(store).body["token"]
    registered = register_pipe(
        valid_body(token),
        store,
        litellm,
        "http://localhost:4000",
        "integratr",
    )
    app = create_app(settings(), store, litellm, http)
    client = TestClient(app)
    client.post(
        "/pipes/ready",
        headers={"Authorization": "Bearer " + registered.body["key"]},
        json={"id": "image", "healthUrl": "http://image:8080/health"},
    )

    response = client.post(
        "/pipes/image/disable",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 502
    assert store.get_pipe("image")["desired_state"] == "active"
