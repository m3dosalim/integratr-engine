# Create a one-time install token.
# The raw token is returned once. The database stores only a hash.

import hashlib
import secrets

from app.action_result import ok


def hash_install_token(token):
    # Step 1. Hash the raw token. The same raw token always produces the same hash.
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest


def create_install_token(store):
    # Step 1. Make a new random token.
    token = secrets.token_urlsafe(32)

    # Step 2. Store the hash. The raw token is not written to the database.
    token_hash = hash_install_token(token)
    store.insert_install_token(token_hash)

    # Step 3. Return the raw token once. The caller has to keep it.
    return ok({"token": token})
