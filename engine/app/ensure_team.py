# Make sure the one deployment team exists in LiteLLM.
# Pipes do not create teams. Every virtual key is minted inside this team.

import time

from app.litellm_client import LiteLLMError
from app.model_aliases import ENGINE_MODEL_ALIASES


def ensure_single_team(litellm, team_id, team_alias):
    # Step 1. The proxy may still be starting. Try the lookup a few times.
    attempt = 1
    last_error = None
    while attempt <= 30:
        try:
            existing = litellm.find_team(team_id)
            # Step 2. The team is already there. Nothing else to create.
            if existing is not None:
                return existing

            # Step 3. Create it with every Engine alias. Pipe keys narrow this list.
            return litellm.create_team(team_id, team_alias, ENGINE_MODEL_ALIASES)
        except LiteLLMError as error:
            last_error = error
            print(
                "Waiting for LiteLLM before creating the team. Attempt "
                + str(attempt)
                + ": "
                + error.message
            )
            time.sleep(2)
            attempt = attempt + 1

    raise SystemExit(
        "The single team could not be created. Last error: " + last_error.message
    )
