"""Pure transport-security path policy."""


def deployment_api_key_required(path: str) -> bool:
    """Keep the server-only shared key on operator probes, never browser APIs."""

    return path == "/ready"
