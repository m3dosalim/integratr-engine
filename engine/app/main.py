# HTTP entry for the Engine shell.
#
# Startup order is the sequence in main() at the bottom of this file:
#   1. Load required settings.
#   2. Open the database and create Integratr tables.
#   3. Make sure the single LiteLLM team exists.
#   4. Start health polling.
#   5. Serve the routes below.
#
# Routes:
#   POST /admin/install-tokens     admin creates a one-time install token
#   POST /pipes/register           the register body from the pipe spec
#   POST /pipes/ready              Pipe reports that required config is filled
#   POST /pipes/{pipe_id}/disable  Engine tells that Pipe to stop work
#   POST /pipes/{pipe_id}/remove   revoke the key, then delete the record
#   GET  /admin/pipes/{pipe_id}    read the record, including health state
#   GET  /admin/spend              read LiteLLM spend logs for a pipeId

import hmac
import threading

import httpx
import uvicorn
from fastapi import Body, FastAPI, Header
from fastapi.responses import JSONResponse

from app.bearer import read_bearer_token
from app.database import connect, create_tables
from app.disable_pipe import disable_pipe
from app.ensure_team import ensure_single_team
from app.health_poller import poll_loop
from app.install_tokens import create_install_token
from app.litellm_client import LiteLLMClient
from app.public_pipe import public_pipe_record
from app.read_spend import read_pipe_spend
from app.ready_pipe import mark_pipe_ready
from app.register_pipe import register_pipe
from app.registration_store import RegistrationStore
from app.remove_pipe import remove_pipe
from app.settings import load_settings


def create_app(settings, store, litellm, http):
    app = FastAPI()

    def require_admin(authorization_header):
        # Step 1. Read the bearer token.
        presented = read_bearer_token(authorization_header)

        # Step 2. Compare it to the admin token in constant time.
        presented_bytes = presented.encode("utf-8")
        expected_bytes = settings.engine_admin_token.encode("utf-8")
        if presented == "" or not hmac.compare_digest(presented_bytes, expected_bytes):
            return JSONResponse(
                status_code=401,
                content={"errors": ["Admin token is missing or wrong."]},
            )
        return None

    @app.post("/admin/install-tokens")
    def http_create_install_token(authorization: str | None = Header(default=None)):
        # Step 1. Only an admin can mint an install token.
        denied = require_admin(authorization)
        if denied is not None:
            return denied

        # Step 2. Create the token and return it once.
        result = create_install_token(store)
        return JSONResponse(status_code=result.status_code, content=result.body)

    @app.post("/pipes/register")
    def http_register(body: dict = Body(...)):
        # The install token in the body is the credential for this route.
        result = register_pipe(
            body=body,
            store=store,
            litellm=litellm,
            engine_base_url=settings.engine_base_url,
            team_id=settings.team_id,
        )
        return JSONResponse(status_code=result.status_code, content=result.body)

    @app.post("/pipes/ready")
    def http_ready(
        body: dict = Body(...),
        authorization: str | None = Header(default=None),
    ):
        result = mark_pipe_ready(body, authorization, store)
        return JSONResponse(status_code=result.status_code, content=result.body)

    @app.post("/pipes/{pipe_id}/disable")
    def http_disable(
        pipe_id: str,
        authorization: str | None = Header(default=None),
    ):
        # Step 1. Only an admin can tell a Pipe to stop.
        denied = require_admin(authorization)
        if denied is not None:
            return denied

        # Step 2. Call the Pipe, then record disabled if it accepted.
        result = disable_pipe(pipe_id, store, http)
        return JSONResponse(status_code=result.status_code, content=result.body)

    @app.post("/pipes/{pipe_id}/remove")
    def http_remove(
        pipe_id: str,
        authorization: str | None = Header(default=None),
    ):
        # Step 1. Only an admin can remove a Pipe.
        denied = require_admin(authorization)
        if denied is not None:
            return denied

        # Step 2. Revoke the key first. The record is deleted only after that.
        result = remove_pipe(pipe_id, store, litellm)
        return JSONResponse(status_code=result.status_code, content=result.body)

    @app.get("/admin/pipes/{pipe_id}")
    def http_read_pipe(
        pipe_id: str,
        authorization: str | None = Header(default=None),
    ):
        # Step 1. Only an admin can read the registration record.
        denied = require_admin(authorization)
        if denied is not None:
            return denied

        # Step 2. Return the record without the virtual key.
        # healthState is what the poller last stored.
        pipe = store.get_pipe(pipe_id)
        if pipe is None:
            return JSONResponse(
                status_code=404,
                content={"errors": ["Pipe is not registered."]},
            )
        return JSONResponse(status_code=200, content=public_pipe_record(pipe))

    @app.get("/admin/spend")
    def http_spend(
        pipeId: str,
        requestId: str | None = None,
        authorization: str | None = Header(default=None),
    ):
        # Step 1. Only an admin can read spend.
        denied = require_admin(authorization)
        if denied is not None:
            return denied

        # Step 2. Read LiteLLM's spend log and join on pipeId and requestId.
        result = read_pipe_spend(pipeId, requestId, store, litellm)
        return JSONResponse(status_code=result.status_code, content=result.body)

    return app


def main():
    # Step 1. Stop here when the database URL or the keys are missing.
    settings = load_settings()

    # Step 2. Open the required database and create the Integratr tables.
    connection = connect(settings.database_url)
    create_tables(connection)
    store = RegistrationStore(connection)

    # Step 3. One HTTP client for the proxy, for disable, and for health polls.
    http = httpx.Client()
    litellm = LiteLLMClient(
        base_url=settings.litellm_internal_url,
        master_key=settings.litellm_master_key,
        http=http,
    )
    ensure_single_team(litellm, settings.team_id, settings.team_alias)

    # Step 4. Poll Pipe health on a background thread until the process exits.
    stop_event = threading.Event()
    poller = threading.Thread(
        target=poll_loop,
        args=(store, http, settings.poll_seconds, stop_event),
        daemon=True,
    )
    poller.start()

    # Step 5. Serve the routes. This call stays running.
    app = create_app(settings, store, litellm, http)
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
