import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.ai.providers import AIConfigurationError


@dataclass(frozen=True)
class AISettings:
    gemini_api_key: str | None = field(repr=False)
    gemini_model: str = "gemini-2.5-flash"
    timeout_seconds: float = 20.0

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "AISettings":
        values = os.environ if environment is None else environment
        api_key = values.get("GEMINI_API_KEY", "").strip() or None
        model = values.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
            raise AIConfigurationError("GEMINI_MODEL has an invalid format.")
        return cls(gemini_api_key=api_key, gemini_model=model)
