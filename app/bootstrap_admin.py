import argparse
from getpass import getpass

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select

from app.database import SessionLocal, engine, run_migrations
from app.models import Company, Membership, User, UserRole
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or promote the initial SmartDesk administrator."
    )
    parser.add_argument("email", help="Email address for the administrator")
    args = parser.parse_args()
    email = str(TypeAdapter(EmailStr).validate_python(args.email)).lower()

    run_migrations(engine)
    with SessionLocal() as db:
        companies = db.scalars(select(Company).order_by(Company.id).limit(2)).all()
        if len(companies) != 1:
            parser.error(
                "Bootstrap requires exactly one company; select the company explicitly "
                "before bootstrapping in a multi-company database."
            )
        company = companies[0]
        if db.scalar(
            select(Membership.id).where(
                Membership.company_id == company.id,
                Membership.role == UserRole.ADMIN,
                Membership.is_active.is_(True),
                Membership.user.has(User.is_active.is_(True)),
            )
        ):
            parser.error("An active company administrator already exists.")

        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            password = getpass("Administrator password (minimum 8 characters): ")
            confirmation = getpass("Confirm password: ")
            if len(password) < 8 or password != confirmation:
                parser.error("Passwords must match and contain at least 8 characters.")
            user = User(email=email, password_hash=hash_password(password))
            db.add(user)

        user.role = UserRole.ADMIN
        user.is_active = True
        membership = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.company_id == company.id,
            )
        )
        if membership is None:
            membership = Membership(
                user_id=user.id,
                company_id=company.id,
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(membership)
        else:
            membership.role = UserRole.ADMIN
            membership.is_active = True
        db.commit()
    print(f"Administrator ready: {email}")


if __name__ == "__main__":
    main()
