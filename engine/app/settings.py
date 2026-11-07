# Required settings for the Engine shell.
# The process stops when any of these is missing. The database is not optional:
# LiteLLM does not enforce budgets without one.

import os


class Settings:
    def __init__(
        self,
        database_url,
        litellm_internal_url,
        engine_base_url,
        litellm_master_key,
        engine_admin_token,
        poll_seconds,
        host,
        port,
    ):
        self.database_url = database_url
        self.litellm_internal_url = litellm_internal_url
        self.engine_base_url = engine_base_url
        self.litellm_master_key = litellm_master_key
        self.engine_admin_token = engine_admin_token
        self.poll_seconds = poll_seconds
        self.host = host
        self.port = port

        # One deployment has one team. Pipes get their own keys inside this team.
        self.team_id = "integratr"
        self.team_alias = "integratr"


def load_settings():
    # Step 1. Read each required value. Blank counts as missing.
    database_url = os.environ.get("DATABASE_URL", "").strip()
    litellm_internal_url = os.environ.get("LITELLM_INTERNAL_URL", "").strip().rstrip("/")
    engine_base_url = os.environ.get("ENGINE_BASE_URL", "").strip().rstrip("/")
    litellm_master_key = os.environ.get("LITELLM_MASTER_KEY", "").strip()
    engine_admin_token = os.environ.get("ENGINE_ADMIN_TOKEN", "").strip()

    missing = []
    if database_url == "":
        missing.append("DATABASE_URL")
    if litellm_internal_url == "":
        missing.append("LITELLM_INTERNAL_URL")
    if engine_base_url == "":
        missing.append("ENGINE_BASE_URL")
    if litellm_master_key == "":
        missing.append("LITELLM_MASTER_KEY")
    if engine_admin_token == "":
        missing.append("ENGINE_ADMIN_TOKEN")

    # Step 2. Stop before opening a port when the shell cannot do its job.
    if len(missing) > 0:
        names = ", ".join(missing)
        raise SystemExit(
            "The Engine shell is missing required settings: "
            + names
            + ". DATABASE_URL is required because budgets do not run without a database."
        )

    # Step 3. Optional knobs have defaults. They do not replace the required list.
    poll_raw = os.environ.get("HEALTH_POLL_SECONDS", "15").strip()
    host = os.environ.get("ENGINE_HOST", "0.0.0.0").strip()
    port_raw = os.environ.get("ENGINE_PORT", "4100").strip()

    return Settings(
        database_url=database_url,
        litellm_internal_url=litellm_internal_url,
        engine_base_url=engine_base_url,
        litellm_master_key=litellm_master_key,
        engine_admin_token=engine_admin_token,
        poll_seconds=int(poll_raw),
        host=host,
        port=int(port_raw),
    )
