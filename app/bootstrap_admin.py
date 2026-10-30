import argparse
from getpass import getpass

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select

from app.database import SessionLocal, engine, run_migrations
from app.models import User, UserRole
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
        if db.scalar(
            select(User.id).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
        ):
            parser.error("An active administrator already exists.")

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
        db.commit()
    print(f"Administrator ready: {email}")


if __name__ == "__main__":
    main()
