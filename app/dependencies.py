from collections.abc import Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Membership, User, UserRole
from app.security import decode_access_token_claims

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TenantContext:
    user_id: int
    tenant_id: int
    role: UserRole


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais de autenticação inválidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        user_id, _ = decode_access_token_claims(credentials.credentials)
    except jwt.InvalidTokenError:
        raise unauthorized from None

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise unauthorized
    return user


def get_tenant_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    forbidden = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Selecione uma empresa com participação ativa.",
    )
    if credentials is None:
        raise forbidden
    try:
        token_user_id, tenant_id = decode_access_token_claims(
            credentials.credentials
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de autenticação inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    if tenant_id is None or int(token_user_id) != user.id:
        raise forbidden

    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.company_id == tenant_id,
            Membership.is_active.is_(True),
        )
    )
    if membership is None:
        raise forbidden
    return TenantContext(
        user_id=user.id,
        tenant_id=membership.company_id,
        role=UserRole(membership.role),
    )


def require_roles(*allowed_roles: UserRole) -> Callable[..., TenantContext]:
    def role_dependency(
        context: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        if context.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para esta operação.",
            )
        return context

    return role_dependency
