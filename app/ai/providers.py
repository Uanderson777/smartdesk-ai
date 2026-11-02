from typing import Protocol

from app.ai.schemas import TicketTriageInput, TriageRecommendation


class AIConfigurationError(Exception):
    """Raised when an AI provider is not configured for use."""


class AIProviderError(Exception):
    """Raised when an AI provider cannot return a valid recommendation."""


class AIProvider(Protocol):
    def analyze(self, ticket: TicketTriageInput) -> TriageRecommendation:
        """Return a validated recommendation for a ticket."""
