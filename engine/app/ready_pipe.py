# Mark a Pipe active after it reports that its required config is filled.
# The Engine does not store those config values. It stores the address
# it will poll, because the register body does not include a running address.

from urllib.parse import urlparse

from app.action_result import ok, reject
from app.bearer import read_bearer_token


def mark_pipe_ready(body, authorization_header, store):
    # Step 1. The body names the Pipe and the health address.
    if not isinstance(body, dict):
        return reject(400, "Ready body must be a JSON object.")

    pipe_id = body.get("id")
    health_url = body.get("healthUrl")
    if not isinstance(pipe_id, str) or pipe_id == "":
        return reject(400, "id must be a non-empty string.")
    if not isinstance(health_url, str) or health_url == "":
        return reject(400, "healthUrl must be the Pipe /health address.")

    # Step 2. Load the registration record.
    pipe = store.get_pipe(pipe_id)
    if pipe is None:
        return reject(404, "Pipe is not registered.")

    # Step 3. A disabled Pipe stays disabled. Ready does not turn it back on.
    if pipe["desired_state"] == "disabled":
        return reject(409, "Pipe is disabled.")

    # Step 4. The caller must present the virtual key returned at register.
    presented_key = read_bearer_token(authorization_header)
    if presented_key == "" or presented_key != pipe["virtual_key"]:
        return reject(401, "Ready requires the Pipe virtual key.")

    # Step 5. healthUrl must be an http(s) URL that ends with /health.
    pipe_base_url = _base_url_from_health_url(health_url)
    if pipe_base_url is None:
        return reject(
            400,
            "healthUrl must look like http://host:port/health.",
        )

    # Step 6. Mark the Pipe active and save the address. Config values stay in the Pipe.
    store.mark_ready(pipe_id, health_url, pipe_base_url)
    return ok(
        {
            "id": pipe_id,
            "desiredState": "active",
            "healthUrl": health_url,
        }
    )


def _base_url_from_health_url(health_url):
    # Step 1. Drop a trailing slash so /health/ and /health are the same.
    trimmed = health_url.strip()
    while trimmed.endswith("/"):
        trimmed = trimmed[:-1]

    # Step 2. Require http or https, and a host.
    parsed = urlparse(trimmed)
    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.netloc == "":
        return None

    # Step 3. The path must be exactly /health. The base is everything before that.
    if parsed.path != "/health":
        return None

    return parsed.scheme + "://" + parsed.netloc
