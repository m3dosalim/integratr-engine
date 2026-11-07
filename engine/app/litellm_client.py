# Calls the LiteLLM proxy admin API.
# The master key is used here and is never returned to a Pipe.


class LiteLLMError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class LiteLLMClient:
    def __init__(self, base_url, master_key, http):
        self.base_url = base_url.rstrip("/")
        self.master_key = master_key
        self.http = http

    def _admin_headers(self):
        return {
            "Authorization": "Bearer " + self.master_key,
            "Content-Type": "application/json",
        }

    def find_team(self, team_id):
        # Step 1. Ask the proxy if this deployment's team is already there.
        response = self.http.get(
            self.base_url + "/team/info",
            params={"team_id": team_id},
            headers=self._admin_headers(),
            timeout=10.0,
        )

        # Step 2. 404 means the team has not been created yet.
        if response.status_code == 404:
            return None

        # Step 3. Any other failure is a proxy problem, not a missing team.
        if response.status_code != 200:
            raise LiteLLMError(
                "LiteLLM team lookup failed with status "
                + str(response.status_code)
                + ": "
                + response.text
            )

        return response.json()

    def create_team(self, team_id, team_alias, models):
        # Step 1. Create the one team for this deployment.
        # Its model list is every Engine alias. A Pipe key then narrows that list.
        response = self.http.post(
            self.base_url + "/team/new",
            headers=self._admin_headers(),
            timeout=10.0,
            json={
                "team_id": team_id,
                "team_alias": team_alias,
                "models": models,
            },
        )

        if response.status_code != 200:
            raise LiteLLMError(
                "LiteLLM team create failed with status "
                + str(response.status_code)
                + ": "
                + response.text
            )

        return response.json()

    def generate_key(
        self,
        pipe_id,
        models,
        max_budget,
        budget_duration,
        rpm_limit,
        tpm_limit,
        team_id,
    ):
        # Step 1. Build the key request from the register body.
        # The key may call only the aliases this Pipe declared.
        key_body = {
            "key_alias": "pipe-" + pipe_id,
            "team_id": team_id,
            "models": models,
            "max_budget": max_budget,
            "budget_duration": budget_duration,
            "rpm_limit": rpm_limit,
            "metadata": {
                "pipe_id": pipe_id,
            },
        }

        # Step 2. Token limits apply only when the Pipe sent tpmLimit.
        # An image-only Pipe does not have to send one.
        if tpm_limit is not None:
            key_body["tpm_limit"] = tpm_limit

        # Step 3. Ask LiteLLM to mint the key.
        response = self.http.post(
            self.base_url + "/key/generate",
            headers=self._admin_headers(),
            timeout=10.0,
            json=key_body,
        )
        if response.status_code != 200:
            raise LiteLLMError(
                "LiteLLM key generate failed with status "
                + str(response.status_code)
                + ": "
                + response.text
            )

        # Step 4. The raw key is the field named "key". Keep it for the register response.
        payload = response.json()
        key = payload.get("key")
        if not isinstance(key, str) or key == "":
            raise LiteLLMError("LiteLLM key generate did not return a key.")
        return key

    def delete_key(self, virtual_key):
        # Step 1. Revoke the key. This is what stops spend.
        response = self.http.post(
            self.base_url + "/key/delete",
            headers=self._admin_headers(),
            timeout=10.0,
            json={"keys": [virtual_key]},
        )

        # Step 2. A missing key is already revoked. Later steps may continue.
        if response.status_code == 404:
            return

        if response.status_code != 200:
            raise LiteLLMError(
                "LiteLLM key delete failed with status "
                + str(response.status_code)
                + ": "
                + response.text
            )

    def get_spend_logs(self, virtual_key, request_id):
        # Step 1. Read this Pipe's key from the proxy spend log.
        # summarize=false asks for individual calls, not a rolled-up total.
        params = {
            "api_key": virtual_key,
            "summarize": "false",
        }
        if request_id is not None and request_id != "":
            params["request_id"] = request_id

        response = self.http.get(
            self.base_url + "/spend/logs",
            params=params,
            headers=self._admin_headers(),
            timeout=10.0,
        )
        if response.status_code != 200:
            raise LiteLLMError(
                "LiteLLM spend logs failed with status "
                + str(response.status_code)
                + ": "
                + response.text
            )

        # Step 2. The proxy returns either a list, or an object that holds a list.
        payload = response.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for field_name in ("spend_logs", "logs", "data"):
                maybe_logs = payload.get(field_name)
                if isinstance(maybe_logs, list):
                    return maybe_logs
        raise LiteLLMError("LiteLLM spend logs returned an unexpected shape.")
