from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import User, UserRole
from app.schemas import AdminUserRead, UserActiveUpdate, UserRoleUpdate

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


def lock_active_admins(db: Session) -> None:
    if db.get_bind().dialect.name == "sqlite":
        db.rollback()
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        return

    statement = (
        select(User.id)
        .where(
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
        )
        .order_by(User.id)
        .with_for_update()
    )
    db.scalars(statement).all()


def active_admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
        )
    ) or 0


@router.get("", response_model=list[AdminUserRead])
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = select(User).order_by(User.id).offset(skip).limit(limit)
    return list(db.scalars(statement).all())


@router.patch("/{user_id}/role", response_model=AdminUserRead)
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
):
    lock_active_admins(db)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if (
        user.is_active
        and user.role == UserRole.ADMIN
        and payload.role != UserRole.ADMIN
        and active_admin_count(db) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não é possível remover o último administrador ativo.",
        )

    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/active", response_model=AdminUserRead)
def update_user_active_status(
    user_id: int,
    payload: UserActiveUpdate,
    db: Session = Depends(get_db),
):
    lock_active_admins(db)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if (
        user.is_active
        and not payload.is_active
        and user.role == UserRole.ADMIN
        and active_admin_count(db) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não é possível desativar o último administrador ativo.",
        )

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user
