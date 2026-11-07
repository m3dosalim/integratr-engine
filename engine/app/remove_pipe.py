# Remove a Pipe.
# The virtual key is revoked first. The registration record is deleted
# only after that revoke succeeds.

from app.action_result import ok, reject
from app.litellm_client import LiteLLMError


def remove_pipe(pipe_id, store, litellm):
    # Step 1. Load the record. There is nothing to remove if it is already gone.
    pipe = store.get_pipe(pipe_id)
    if pipe is None:
        return reject(404, "Pipe is not registered.")

    # Step 2. Revoke the virtual key first. Spend stops here.
    # If this call fails, the record stays so the key can be revoked later.
    try:
        litellm.delete_key(pipe["virtual_key"])
    except LiteLLMError as error:
        return reject(502, "Virtual key was not revoked: " + error.message)

    # Step 3. Delete the registration record only after the key is revoked.
    store.delete_pipe(pipe_id)
    return ok(
        {
            "id": pipe_id,
            "keyRevoked": True,
            "registrationRemoved": True,
        }
    )
