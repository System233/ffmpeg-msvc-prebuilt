"""Shared Responses endpoint configuration. Never downgrade the protocol."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class APIConfig:
    base_url: str
    key: str
    model: str


def api_config(*, audit: bool = False) -> APIConfig:
    url = (os.environ.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = (os.environ.get("OPENAI_AUDIT_MODEL", "").strip() if audit else "") or os.environ.get("OPENAI_MODEL", "").strip()
    if not key or not model:
        raise ValueError("Set OPENAI_API_KEY and OPENAI_MODEL")
    parsed = urlsplit(url)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path.endswith(("/responses", "/chat/completions"))
            or (parsed.scheme != "https" and not (parsed.scheme == "http"
                and parsed.hostname in ("localhost", "127.0.0.1", "::1")))):
        raise ValueError("OPENAI_BASE_URL must be an HTTPS API root (HTTP loopback is permitted for tests)")
    return APIConfig(url, key, model)
