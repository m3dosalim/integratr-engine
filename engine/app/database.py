# Open the required database and create the Integratr tables.
# LiteLLM keeps its own tables in this same database. Integratr uses
# the integratr schema so the two do not overwrite each other.

import psycopg
from psycopg.rows import dict_row


def connect(database_url):
    # Step 1. Open one connection. Rows come back as dictionaries.
    connection = psycopg.connect(database_url, row_factory=dict_row)

    # Step 2. Each single statement is saved on its own.
    # The register path is the exception: it uses one transaction so the
    # token and the pipe row succeed or fail together.
    connection.autocommit = True
    return connection


def create_tables(connection):
    # Step 1. Own schema for the shell.
    connection.execute("CREATE SCHEMA IF NOT EXISTS integratr")

    # Step 2. Install tokens. The raw token is never stored, only its hash.
    # used_at stays empty until a register call consumes the token.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS integratr.install_tokens (
            token_hash text PRIMARY KEY,
            created_at timestamptz NOT NULL,
            used_at timestamptz NULL
        )
        """
    )

    # Step 3. One registration record per Pipe.
    # The virtual key stays in this row until the remove flow revokes it.
    # desired_state is the admin choice: inactive, active, or disabled.
    # health_state is what the poller last saw: unknown, ok, inactive,
    # degraded, or unreachable.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS integratr.pipes (
            id text PRIMARY KEY,
            display_name text NOT NULL,
            version text NOT NULL,
            engine_api text NOT NULL,
            models jsonb NOT NULL,
            max_budget numeric NOT NULL,
            budget_duration text NOT NULL,
            rpm_limit integer NOT NULL,
            tpm_limit integer NULL,
            virtual_key text NOT NULL,
            config_schema jsonb NOT NULL,
            data_schema jsonb NOT NULL,
            desired_state text NOT NULL,
            health_state text NOT NULL,
            health_reason text NULL,
            health_url text NULL,
            pipe_base_url text NULL,
            team_id text NOT NULL,
            created_at timestamptz NOT NULL,
            ready_at timestamptz NULL,
            disabled_at timestamptz NULL
        )
        """
    )

    # Step 4. autocommit already saved the statements above.
