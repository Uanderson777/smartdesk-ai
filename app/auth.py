from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import TenantContext, get_current_user, get_tenant_context
from app.models import Company, Membership, User, UserRole
from app.schemas import AccessToken, TenantOption, UserCreate, UserLogin, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado.",
        )

    companies = db.scalars(select(Company).order_by(Company.id).limit(2)).all()
    if not companies:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nenhuma empresa está configurada para cadastro.",
        )
    if len(companies) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O cadastro em empresas exige um convite válido.",
        )

    user = User(
        full_name=payload.full_name,
        email=email,
        password_hash=hash_password(payload.password),
        role=UserRole.REQUESTER,
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                company_id=companies[0].id,
                role=UserRole.REQUESTER,
                is_active=True,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado.",
        ) from None
    db.refresh(user)
    return user


@router.get("/me", response_model=UserRead)
def read_current_user(
    user: User = Depends(get_current_user),
    _: TenantContext = Depends(get_tenant_context),
):
    return user


@router.post("/login", response_model=AccessToken)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    memberships = db.execute(
        select(Membership, Company)
        .join(Company, Company.id == Membership.company_id)
        .where(
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
        )
        .order_by(Company.id)
    ).all()
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.company_id is None:
        if len(memberships) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Selecione uma empresa para continuar.",
                    "companies": [
                        TenantOption(id=company.id, name=company.name).model_dump()
                        for _, company in memberships
                    ],
                },
            )
        membership, company = memberships[0]
    else:
        selection = next(
            (
                (membership, company)
                for membership, company in memberships
                if company.id == payload.company_id
            ),
            None,
        )
        if selection is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="O usuário não possui participação ativa nessa empresa.",
            )
        membership, company = selection

    return AccessToken(
        access_token=create_access_token(str(user.id), tenant_id=company.id)
    )
