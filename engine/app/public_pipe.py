# Shape a registration record for an admin read.
# The virtual key is left out. It was returned once, at register.


def public_pipe_record(pipe):
    max_budget = pipe["max_budget"]
    if not isinstance(max_budget, (int, float)):
        max_budget = float(max_budget)

    return {
        "id": pipe["id"],
        "displayName": pipe["display_name"],
        "version": pipe["version"],
        "models": pipe["models"],
        "budget": {
            "maxBudget": max_budget,
            "budgetDuration": pipe["budget_duration"],
            "rpmLimit": pipe["rpm_limit"],
            "tpmLimit": pipe["tpm_limit"],
        },
        "configSchema": pipe["config_schema"],
        "dataSchema": pipe["data_schema"],
        "desiredState": pipe["desired_state"],
        "healthState": pipe["health_state"],
        "healthReason": pipe["health_reason"],
        "healthUrl": pipe["health_url"],
    }
