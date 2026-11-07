# Check the POST /pipes/register body before any key is minted.
# Field order matches the pipe spec.

from app.model_aliases import ENGINE_MODEL_ALIASES

CONFIG_KINDS = ["string", "number", "boolean", "secret"]


def check_register_body(body):
    errors = []

    # Step 1. The body must be a JSON object.
    if not isinstance(body, dict):
        return None, ["Register body must be a JSON object."]

    # Step 2. Contract version. Only "1" is accepted.
    engine_api = body.get("engineApi")
    if engine_api != "1":
        errors.append('engineApi must be "1".')

    # Step 3. Identity.
    pipe_id = body.get("id")
    if not isinstance(pipe_id, str) or _is_pipe_id(pipe_id) is False:
        errors.append(
            "id must be a short stable name: a lowercase letter, then lowercase letters, digits, or hyphens."
        )

    display_name = body.get("displayName")
    if not isinstance(display_name, str) or display_name.strip() == "":
        errors.append("displayName must be a non-empty string.")

    version = body.get("version")
    if not isinstance(version, str) or version.strip() == "":
        errors.append("version must be a non-empty string.")

    # Step 4. Model allow-list. Only Engine aliases are legal.
    models = body.get("models")
    if not isinstance(models, list) or len(models) == 0:
        errors.append("models must be a non-empty list of Engine aliases.")
    else:
        seen = []
        for model_name in models:
            if model_name not in ENGINE_MODEL_ALIASES:
                errors.append(
                    "models may only contain Engine aliases: "
                    + ", ".join(ENGINE_MODEL_ALIASES)
                    + "."
                )
                break
            if model_name in seen:
                errors.append("models contains a duplicate alias: " + model_name + ".")
                break
            seen.append(model_name)

    # Step 5. Budget and rate limits that will be copied onto the virtual key.
    budget = body.get("budget")
    cleaned_budget = None
    if not isinstance(budget, dict):
        errors.append("budget must be an object.")
    else:
        cleaned_budget = _check_budget(budget, errors)

    # Step 6. Config shape. Values stay in the Pipe. This is only the shape.
    config_schema = body.get("configSchema")
    if not isinstance(config_schema, list):
        errors.append("configSchema must be a list.")
    else:
        _check_config_schema(config_schema, errors)

    # Step 7. Data declaration. Rows stay in the Pipe. This is only the declaration.
    data_schema = body.get("dataSchema")
    if not isinstance(data_schema, list):
        errors.append("dataSchema must be a list.")
    else:
        _check_data_schema(data_schema, errors)

    # Step 8. The install token is present. One-time use is checked against the database later.
    token = body.get("token")
    if not isinstance(token, str) or token.strip() == "":
        errors.append("token must be a non-empty string.")

    if len(errors) > 0:
        return None, errors

    cleaned = {
        "token": token,
        "engine_api": engine_api,
        "id": pipe_id,
        "display_name": display_name,
        "version": version,
        "models": models,
        "budget": cleaned_budget,
        "config_schema": config_schema,
        "data_schema": data_schema,
    }
    return cleaned, []


def _is_pipe_id(pipe_id):
    # Step 1. Empty is rejected by the caller. Guard here as well.
    if pipe_id == "":
        return False

    # Step 2. First character is a lowercase letter.
    first = pipe_id[0]
    if first < "a" or first > "z":
        return False

    # Step 3. The rest may be lowercase letters, digits, or hyphens.
    index = 1
    while index < len(pipe_id):
        character = pipe_id[index]
        is_letter = "a" <= character <= "z"
        is_digit = "0" <= character <= "9"
        is_hyphen = character == "-"
        if not is_letter and not is_digit and not is_hyphen:
            return False
        index = index + 1

    # Step 4. Keep ids short enough to use as a key alias.
    if len(pipe_id) > 63:
        return False
    return True


def _check_budget(budget, errors):
    max_budget = budget.get("maxBudget")
    if isinstance(max_budget, bool) or not isinstance(max_budget, (int, float)):
        errors.append("budget.maxBudget must be a number.")
    elif max_budget < 0:
        errors.append("budget.maxBudget must be zero or greater.")

    budget_duration = budget.get("budgetDuration")
    if not isinstance(budget_duration, str) or budget_duration.strip() == "":
        errors.append("budget.budgetDuration must be a non-empty string, such as 30d or 1d.")

    rpm_limit = budget.get("rpmLimit")
    if isinstance(rpm_limit, bool) or not isinstance(rpm_limit, int):
        errors.append("budget.rpmLimit must be a whole number.")
    elif rpm_limit < 0:
        errors.append("budget.rpmLimit must be zero or greater.")

    # tpmLimit is optional. Image-only pipes omit it.
    tpm_limit = budget.get("tpmLimit")
    if "tpmLimit" in budget and tpm_limit is not None:
        if isinstance(tpm_limit, bool) or not isinstance(tpm_limit, int):
            errors.append("budget.tpmLimit must be a whole number when it is sent.")
        elif tpm_limit < 0:
            errors.append("budget.tpmLimit must be zero or greater.")
    else:
        tpm_limit = None

    return {
        "max_budget": max_budget,
        "budget_duration": budget_duration,
        "rpm_limit": rpm_limit,
        "tpm_limit": tpm_limit,
    }


def _check_config_schema(config_schema, errors):
    index = 0
    while index < len(config_schema):
        field = config_schema[index]
        label = "configSchema[" + str(index) + "]"
        if not isinstance(field, dict):
            errors.append(label + " must be an object.")
            index = index + 1
            continue

        name = field.get("name")
        if not isinstance(name, str) or name.strip() == "":
            errors.append(label + ".name must be a non-empty string.")

        field_label = field.get("label")
        if not isinstance(field_label, str) or field_label.strip() == "":
            errors.append(label + ".label must be a non-empty string.")

        kind = field.get("kind")
        if kind not in CONFIG_KINDS:
            errors.append(label + ".kind must be string, number, boolean, or secret.")

        required = field.get("required")
        if not isinstance(required, bool):
            errors.append(label + ".required must be true or false.")

        # A secret default would put a secret into the spec. Reject that.
        if kind == "secret" and "default" in field:
            errors.append(label + " is a secret and must not include a default.")

        index = index + 1


def _check_data_schema(data_schema, errors):
    index = 0
    while index < len(data_schema):
        record = data_schema[index]
        label = "dataSchema[" + str(index) + "]"
        if not isinstance(record, dict):
            errors.append(label + " must be an object.")
            index = index + 1
            continue

        name = record.get("name")
        if not isinstance(name, str) or name.strip() == "":
            errors.append(label + ".name must be a non-empty string.")

        description = record.get("description")
        if not isinstance(description, str) or description.strip() == "":
            errors.append(label + ".description must be a non-empty string.")

        retention = record.get("retention")
        if not isinstance(retention, str) or retention.strip() == "":
            errors.append(label + ".retention must be a non-empty string.")

        index = index + 1
