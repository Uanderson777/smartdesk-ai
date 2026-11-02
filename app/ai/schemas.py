from pydantic import BaseModel, ConfigDict, Field

from app.schemas import TicketCategory, TicketPriority


class TicketTriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=5000)
    current_category: TicketCategory
    current_priority: TicketPriority


class TriageRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: TicketCategory
    priority: TicketPriority
    response_draft: str = Field(min_length=10, max_length=3000)
    rationale: str = Field(min_length=5, max_length=1000)


class TicketTriageResponse(TriageRecommendation):
    ticket_id: int
