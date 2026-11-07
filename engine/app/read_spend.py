# Read spend logs from LiteLLM and join them to a Pipe failure.
# The join key is pipeId plus requestId. The Engine does not keep a second spend database.

from app.action_result import ok, reject
from app.litellm_client import LiteLLMError


def read_pipe_spend(pipe_id, request_id, store, litellm):
    # Step 1. The Pipe id selects which virtual key's logs we read.
    if not isinstance(pipe_id, str) or pipe_id == "":
        return reject(400, "pipeId is required.")

    pipe = store.get_pipe(pipe_id)
    if pipe is None:
        return reject(404, "Pipe is not registered.")

    # Step 2. Ask LiteLLM for this key's spend logs.
    try:
        logs = litellm.get_spend_logs(pipe["virtual_key"], request_id)
    except LiteLLMError as error:
        return reject(502, "LiteLLM spend logs could not be read: " + error.message)

    # Step 3. Keep the rows that join to this pipeId and, when given, this requestId.
    matched = []
    index = 0
    while index < len(logs):
        row = logs[index]
        if _row_matches(row, pipe_id, request_id):
            matched.append(_public_log_row(row, pipe["virtual_key"]))
        index = index + 1

    # Step 4. Return the join result. The virtual key itself is not included.
    return ok(
        {
            "pipeId": pipe_id,
            "requestId": request_id,
            "logs": matched,
        }
    )


def _row_matches(row, pipe_id, request_id):
    # Step 1. Read the metadata the Pipe was told to send, in either place LiteLLM stores it.
    if not isinstance(row, dict):
        return False

    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    custom = metadata.get("spend_logs_metadata")
    if not isinstance(custom, dict):
        custom = {}

    row_pipe_id = custom.get("pipeId")
    if row_pipe_id is None:
        row_pipe_id = metadata.get("pipeId")

    row_request_id = custom.get("requestId")
    if row_request_id is None:
        row_request_id = metadata.get("requestId")

    litellm_request_id = row.get("request_id")

    # Step 2. A row that names a different Pipe does not join.
    # A row with no pipeId still belongs to this Pipe, because it was fetched with this Pipe's key.
    if row_pipe_id not in (None, "") and row_pipe_id != pipe_id:
        return False

    # Step 3. When the caller passed a requestId, it must match the Pipe's id or LiteLLM's id.
    if request_id is None or request_id == "":
        return True

    if row_request_id == request_id:
        return True
    if litellm_request_id == request_id:
        return True
    return False


def _public_log_row(row, virtual_key):
    # Copy the log and drop any field that is the raw virtual key.
    public_row = {}
    for field_name in row:
        value = row[field_name]
        if value == virtual_key:
            continue
        public_row[field_name] = value
    return public_row
