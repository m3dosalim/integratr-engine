# Poll each registered Pipe's GET /health endpoint.
# The Pipe answers ok, inactive, or degraded.
# No answer, or any other answer, is stored as unreachable.

import httpx


def poll_all_pipes(store, http):
    # Step 1. Read every registration record.
    pipes = store.list_pipes()

    # Step 2. Poll one Pipe at a time. Pipes with no address yet are skipped.
    index = 0
    while index < len(pipes):
        pipe = pipes[index]
        health_url = pipe["health_url"]
        if health_url is not None and health_url != "":
            health_state, health_reason = poll_one_pipe(health_url, http)
            store.set_health_state(pipe["id"], health_state, health_reason)
        index = index + 1


def poll_one_pipe(health_url, http):
    # Step 1. Call the Pipe.
    try:
        response = http.get(health_url, timeout=3.0)
    except httpx.HTTPError as error:
        return "unreachable", str(error)

    # Step 2. A failed HTTP status means the process is not answering health.
    if response.status_code != 200:
        return "unreachable", "Health status " + str(response.status_code) + "."

    # Step 3. Read the status field. Only the three spec values are healthy answers.
    try:
        payload = response.json()
    except ValueError:
        return "unreachable", "Health body was not JSON."

    if not isinstance(payload, dict):
        return "unreachable", "Health body was not a JSON object."

    status = payload.get("status")
    if status not in ("ok", "inactive", "degraded"):
        return "unreachable", "Health status was not ok, inactive, or degraded."

    # Step 4. degraded may include a reason sentence. The other states do not need one.
    reason = payload.get("reason")
    if not isinstance(reason, str):
        reason = None
    return status, reason


def poll_loop(store, http, poll_seconds, stop_event):
    # Keep polling until the process is asked to stop.
    while stop_event.is_set() is False:
        try:
            poll_all_pipes(store, http)
        except Exception as error:
            # One bad pass must not kill the loop. The next wait tries again.
            print("Health poll failed: " + str(error))
        stop_event.wait(poll_seconds)
