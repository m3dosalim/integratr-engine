# Register one Pipe.
# Order matches the pipe spec: check the body, check the token, mint one key,
# store the record, return the Engine base URL and the key once.

from app.action_result import ActionResult, ok, reject
from app.check_register_body import check_register_body
from app.install_tokens import hash_install_token
from app.litellm_client import LiteLLMError
from app.registration_store import PipeIdTaken, TokenAlreadyUsed


def register_pipe(body, store, litellm, engine_base_url, team_id):
    # Step 1. Check the body. Do this before minting a key or touching a token.
    cleaned, errors = check_register_body(body)
    if len(errors) > 0:
        return ActionResult(400, {"errors": errors})

    # Step 2. The install token must exist and must not have been used yet.
    token_hash = hash_install_token(cleaned["token"])
    if store.token_is_unused(token_hash) is False:
        return reject(401, "install token is missing or already used.")

    # Step 3. Reject an id that is already registered.
    if store.pipe_exists(cleaned["id"]):
        return reject(409, "id is already registered.")

    # Step 4. Mint one virtual key. The allow-list and the budget come from the request.
    budget = cleaned["budget"]
    try:
        virtual_key = litellm.generate_key(
            pipe_id=cleaned["id"],
            models=cleaned["models"],
            max_budget=budget["max_budget"],
            budget_duration=budget["budget_duration"],
            rpm_limit=budget["rpm_limit"],
            tpm_limit=budget["tpm_limit"],
            team_id=team_id,
        )
    except LiteLLMError as error:
        return reject(502, "LiteLLM did not mint a key: " + error.message)

    # Step 5. Store the registration record and consume the token together.
    # The Pipe starts inactive. Ready is a later call, after its config is filled.
    pipe_row = {
        "id": cleaned["id"],
        "display_name": cleaned["display_name"],
        "version": cleaned["version"],
        "engine_api": cleaned["engine_api"],
        "models": cleaned["models"],
        "max_budget": budget["max_budget"],
        "budget_duration": budget["budget_duration"],
        "rpm_limit": budget["rpm_limit"],
        "tpm_limit": budget["tpm_limit"],
        "virtual_key": virtual_key,
        "config_schema": cleaned["config_schema"],
        "data_schema": cleaned["data_schema"],
        "desired_state": "inactive",
        "health_state": "unknown",
        "health_reason": None,
        "health_url": None,
        "pipe_base_url": None,
        "team_id": team_id,
    }
    try:
        store.claim_token_and_insert_pipe(token_hash, pipe_row)
    except TokenAlreadyUsed:
        # The token was used between the check and the write. Drop the key we just minted.
        _revoke_quietly(litellm, virtual_key)
        return reject(401, "install token is missing or already used.")
    except PipeIdTaken:
        _revoke_quietly(litellm, virtual_key)
        return reject(409, "id is already registered.")

    # Step 6. Return the Engine base URL and the key. This response is the only time the key is sent.
    return ok(
        {
            "id": cleaned["id"],
            "engineBaseUrl": engine_base_url,
            "key": virtual_key,
        }
    )


def _revoke_quietly(litellm, virtual_key):
    # Best-effort cleanup. The caller still receives the original register error.
    try:
        litellm.delete_key(virtual_key)
    except LiteLLMError:
        return
