from collections.abc import Sequence
import logging

from pydantic import ValidationError

from app.ai.providers import (
    AIConfigurationError,
    AIProvider,
    AIProviderError,
)
from app.ai.schemas import TicketTriageInput, TriageRecommendation

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    """Raised when no configured AI provider can complete a pipeline."""


class TicketTriageService:
    def __init__(self, providers: Sequence[AIProvider]) -> None:
        self._providers = tuple(providers)

    def analyze(self, ticket: TicketTriageInput) -> TriageRecommendation:
        if not self._providers:
            raise AIConfigurationError("No AI provider is configured.")

        for provider in self._providers:
            try:
                result = provider.analyze(ticket)
                return TriageRecommendation.model_validate(result)
            except AIProviderError as error:
                logger.warning(
                    "AI provider failed during triage (%s).",
                    type(error).__name__,
                )
            except ValidationError:
                logger.warning("AI provider returned invalid triage output.")

        logger.error("All configured AI providers failed during triage.")
        raise AIServiceError("All configured AI providers failed.")
