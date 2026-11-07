# Read and write registration records and install tokens.
# One lock guards the connection, because the health poller and the
# HTTP routes share it.

import threading

import psycopg
from psycopg.types.json import Json


class TokenAlreadyUsed(Exception):
    pass


class PipeIdTaken(Exception):
    pass


class RegistrationStore:
    def __init__(self, connection):
        self.connection = connection
        self.lock = threading.Lock()

    def insert_install_token(self, token_hash):
        # Step 1. Store the hash. used_at stays empty so the token can still be used.
        with self.lock:
            self.connection.execute(
                """
                INSERT INTO integratr.install_tokens (token_hash, created_at)
                VALUES (%s, NOW())
                """,
                (token_hash,),
            )

    def token_is_unused(self, token_hash):
        # Step 1. The token must exist.
        # Step 2. used_at must still be empty.
        with self.lock:
            row = self.connection.execute(
                """
                SELECT used_at
                FROM integratr.install_tokens
                WHERE token_hash = %s
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return False
        return row["used_at"] is None

    def pipe_exists(self, pipe_id):
        with self.lock:
            row = self.connection.execute(
                """
                SELECT id
                FROM integratr.pipes
                WHERE id = %s
                """,
                (pipe_id,),
            ).fetchone()
        return row is not None

    def claim_token_and_insert_pipe(self, token_hash, pipe_row):
        # Step 1. Mark the token used only if it is still unused.
        # Step 2. Insert the registration record in the same transaction.
        # If either step fails, both roll back. A failed register does not burn a token.
        with self.lock:
            try:
                with self.connection.transaction():
                    used = self.connection.execute(
                        """
                        UPDATE integratr.install_tokens
                        SET used_at = NOW()
                        WHERE token_hash = %s
                          AND used_at IS NULL
                        RETURNING token_hash
                        """,
                        (token_hash,),
                    ).fetchone()
                    if used is None:
                        raise TokenAlreadyUsed()

                    self.connection.execute(
                        """
                        INSERT INTO integratr.pipes (
                            id,
                            display_name,
                            version,
                            engine_api,
                            models,
                            max_budget,
                            budget_duration,
                            rpm_limit,
                            tpm_limit,
                            virtual_key,
                            config_schema,
                            data_schema,
                            desired_state,
                            health_state,
                            health_reason,
                            health_url,
                            pipe_base_url,
                            team_id,
                            created_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, NOW()
                        )
                        """,
                        (
                            pipe_row["id"],
                            pipe_row["display_name"],
                            pipe_row["version"],
                            pipe_row["engine_api"],
                            Json(pipe_row["models"]),
                            pipe_row["max_budget"],
                            pipe_row["budget_duration"],
                            pipe_row["rpm_limit"],
                            pipe_row["tpm_limit"],
                            pipe_row["virtual_key"],
                            Json(pipe_row["config_schema"]),
                            Json(pipe_row["data_schema"]),
                            pipe_row["desired_state"],
                            pipe_row["health_state"],
                            pipe_row["health_reason"],
                            pipe_row["health_url"],
                            pipe_row["pipe_base_url"],
                            pipe_row["team_id"],
                        ),
                    )
            except psycopg.errors.UniqueViolation:
                raise PipeIdTaken()

    def get_pipe(self, pipe_id):
        with self.lock:
            row = self.connection.execute(
                """
                SELECT
                    id,
                    display_name,
                    version,
                    engine_api,
                    models,
                    max_budget,
                    budget_duration,
                    rpm_limit,
                    tpm_limit,
                    virtual_key,
                    config_schema,
                    data_schema,
                    desired_state,
                    health_state,
                    health_reason,
                    health_url,
                    pipe_base_url,
                    team_id
                FROM integratr.pipes
                WHERE id = %s
                """,
                (pipe_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def mark_ready(self, pipe_id, health_url, pipe_base_url):
        # Step 1. desired_state becomes active.
        # Step 2. Save the address the poller and the disable call will use.
        # health_state stays whatever the poller last wrote. Ready does not pretend the process is ok.
        with self.lock:
            self.connection.execute(
                """
                UPDATE integratr.pipes
                SET desired_state = 'active',
                    health_url = %s,
                    pipe_base_url = %s,
                    ready_at = NOW()
                WHERE id = %s
                """,
                (health_url, pipe_base_url, pipe_id),
            )

    def mark_disabled(self, pipe_id):
        with self.lock:
            self.connection.execute(
                """
                UPDATE integratr.pipes
                SET desired_state = 'disabled',
                    disabled_at = NOW()
                WHERE id = %s
                """,
                (pipe_id,),
            )

    def set_health_state(self, pipe_id, health_state, health_reason):
        with self.lock:
            self.connection.execute(
                """
                UPDATE integratr.pipes
                SET health_state = %s,
                    health_reason = %s
                WHERE id = %s
                """,
                (health_state, health_reason, pipe_id),
            )

    def delete_pipe(self, pipe_id):
        with self.lock:
            self.connection.execute(
                """
                DELETE FROM integratr.pipes
                WHERE id = %s
                """,
                (pipe_id,),
            )

    def list_pipes(self):
        with self.lock:
            rows = self.connection.execute(
                """
                SELECT
                    id,
                    display_name,
                    version,
                    models,
                    max_budget,
                    budget_duration,
                    rpm_limit,
                    tpm_limit,
                    virtual_key,
                    desired_state,
                    health_state,
                    health_reason,
                    health_url,
                    pipe_base_url
                FROM integratr.pipes
                ORDER BY id
                """
            ).fetchall()
        return [dict(row) for row in rows]
