# Read a bearer token from an Authorization header.


def read_bearer_token(authorization_header):
    # Step 1. A missing header is an empty token. The caller decides the error.
    if authorization_header is None:
        return ""

    # Step 2. Only the "Bearer <token>" form is accepted.
    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        return ""

    # Step 3. Return the token text with surrounding spaces removed.
    return authorization_header[len(prefix) :].strip()
