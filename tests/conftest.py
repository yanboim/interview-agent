"""Hermetic defaults for the repository test process.

Production ``.env`` files may exist in an operator checkout.  Tests must never
inherit their credentials, rollout stage, database, queues, or telemetry
destinations before application modules are imported during collection.
Individual integration tests can still opt in by overriding these variables.
"""

import os
import tempfile
from pathlib import Path


_TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="interview-agent-pytest-")
_TEST_DATABASE = Path(_TEST_RUNTIME.name) / "conversation.db"

_HERMETIC_ENV = {
    "APP_API_KEY": "",
    "AUTH_REQUIRED": "false",
    "AUTO_CREATE_SCHEMA": "true",
    "DATABASE_URL": "",
    "CONVERSATION_DB_PATH": str(_TEST_DATABASE),
    "ZHIPU_API_KEY": "",
    "ZHIPU_EMBEDDING_API_KEY": "",
    "WEB_SEARCH_API_KEY": "",
    "TRANSCRIPTION_API_KEY": "",
    "OTEL_ENABLED": "false",
}

for _name, _value in _HERMETIC_ENV.items():
    os.environ[_name] = _value
