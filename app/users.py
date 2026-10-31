from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import TenantContext, require_roles
from app.models import Membership, User, UserRole
from app.schemas import AdminUserRead, UserActiveUpdate, UserRoleUpdate

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


def lock_active_admins(db: Session, tenant_id: int) -> None:
    if db.get_bind().dialect.name == "sqlite":
        db.rollback()
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        return

    statement = (
        select(Membership.id)
        .where(
            Membership.company_id == tenant_id,
            Membership.role == UserRole.ADMIN,
            Membership.is_active.is_(True),
        )
        .order_by(Membership.id)
        .with_for_update()
    )
    db.scalars(statement).all()


def active_admin_count(db: Session, tenant_id: int) -> int:
    return db.scalar(
        select(func.count(Membership.id)).where(
            Membership.company_id == tenant_id,
            Membership.role == UserRole.ADMIN,
            Membership.is_active.is_(True),
        )
    ) or 0


def find_membership(
    db: Session,
    user_id: int,
    tenant_id: int,
) -> tuple[User, Membership]:
    result = db.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(
            User.id == user_id,
            Membership.company_id == tenant_id,
        )
    ).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return result


def user_membership_read(user: User, membership: Membership) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=UserRole(membership.role),
        is_active=membership.is_active and user.is_active,
    )


@router.get("", response_model=list[AdminUserRead])
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_roles(UserRole.ADMIN)),
):
    statement = (
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.company_id == context.tenant_id)
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
    )
    return [
        user_membership_read(user, membership)
        for user, membership in db.execute(statement).all()
    ]


@router.patch("/{user_id}/role", response_model=AdminUserRead)
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_roles(UserRole.ADMIN)),
):
    lock_active_admins(db, context.tenant_id)
    user, membership = find_membership(db, user_id, context.tenant_id)

    if (
        membership.is_active
        and user.is_active
        and membership.role == UserRole.ADMIN
        and payload.role != UserRole.ADMIN
        and active_admin_count(db, context.tenant_id) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não é possível remover o último administrador ativo da empresa.",
        )

    membership.role = payload.role
    db.commit()
    db.refresh(user)
    db.refresh(membership)
    return user_membership_read(user, membership)


@router.patch("/{user_id}/active", response_model=AdminUserRead)
def update_user_active_status(
    user_id: int,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
    context: TenantContext = Depends(require_roles(UserRole.ADMIN)),
):
    lock_active_admins(db, context.tenant_id)
    user, membership = find_membership(db, user_id, context.tenant_id)

    if (
        membership.is_active
        and user.is_active
        and not payload.is_active
        and membership.role == UserRole.ADMIN
        and active_admin_count(db, context.tenant_id) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não é possível desativar o último administrador ativo da empresa.",
        )

    membership.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    db.refresh(membership)
    return user_membership_read(user, membership)
