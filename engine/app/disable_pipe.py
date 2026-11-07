# Engine-side disable.
# This tells the Pipe to stop new work and background work.
# The virtual key is not revoked here. Remove is the flow that revokes the key.

import httpx

from app.action_result import ok, reject


def disable_pipe(pipe_id, store, http):
    # Step 1. Load the registration record.
    pipe = store.get_pipe(pipe_id)
    if pipe is None:
        return reject(404, "Pipe is not registered.")

    # Step 2. Ready must have run, so we know where the Pipe is listening.
    pipe_base_url = pipe["pipe_base_url"]
    if pipe_base_url is None or pipe_base_url == "":
        return reject(409, "Pipe has no address yet. It has not called ready.")

    # Step 3. Tell the Pipe to stop. The Pipe's own route is POST /disable.
    disable_url = pipe_base_url + "/disable"
    try:
        response = http.post(disable_url, timeout=5.0)
    except httpx.HTTPError as error:
        return reject(502, "Pipe did not accept disable: " + str(error))

    # Step 4. A non-success answer means the Pipe is still allowed to work.
    # Do not mark it disabled in that case.
    if response.status_code < 200 or response.status_code >= 300:
        return reject(
            502,
            "Pipe did not accept disable. Status " + str(response.status_code) + ".",
        )

    # Step 5. Record the admin choice only after the Pipe accepted it.
    store.mark_disabled(pipe_id)
    return ok(
        {
            "id": pipe_id,
            "desiredState": "disabled",
        }
    )
