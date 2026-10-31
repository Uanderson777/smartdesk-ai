from datetime import datetime
from enum import Enum
import re
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from app.models import UserRole


def validate_email_address(value: str) -> str:
    normalized = value.strip()
    local_part, separator, domain = normalized.rpartition("@")
    if separator and domain.lower() == "smartdeskai.local":
        valid_local_part = re.fullmatch(
            r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*",
            local_part,
        )
        if valid_local_part is None:
            raise ValueError("Invalid email address.")
        return normalized

    try:
        return str(TypeAdapter(EmailStr).validate_python(normalized))
    except ValidationError:
        raise ValueError("Invalid email address.") from None


class TicketCategory(str, Enum):
    hardware = "hardware"
    software = "software"
    rede = "rede"
    acesso = "acesso"
    outro = "outro"


class TicketPriority(str, Enum):
    baixa = "baixa"
    media = "media"
    alta = "alta"
    critica = "critica"


class TicketStatus(str, Enum):
    aberto = "aberto"
    em_atendimento = "em_atendimento"
    aguardando_usuario = "aguardando_usuario"
    resolvido = "resolvido"
    fechado = "fechado"


class TicketCreate(BaseModel):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=5000)
    category: TicketCategory
    priority: TicketPriority = TicketPriority.media


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketAssigneeUpdate(BaseModel):
    technician_id: int | None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    requester_id: int | None
    assigned_technician_id: int | None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    full_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
    ]
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    company_id: int | None = Field(default=None, gt=0)

    @field_validator("email")
    @classmethod
    def validate_login_email(cls, value: str) -> str:
        return validate_email_address(value)


class TenantOption(BaseModel):
    id: int
    name: str


class UserRead(BaseModel):
    id: int
    full_name: str | None
    email: str

    @field_validator("email")
    @classmethod
    def validate_user_email(cls, value: str) -> str:
        return validate_email_address(value)


class AdminUserRead(UserRead):
    role: UserRole
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserActiveUpdate(BaseModel):
    is_active: bool


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
