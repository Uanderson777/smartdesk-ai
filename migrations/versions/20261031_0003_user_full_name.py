"""Add an optional full name to user accounts.

Revision ID: 20261031_0003
Revises: 20261030_0002
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0003"
down_revision = "20261030_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("full_name", sa.String(length=160), nullable=True),
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("email", sa.String(length=320)),
        sa.column("full_name", sa.String(length=160)),
    )
    op.execute(
        sa.update(users)
        .where(
            users.c.id == 1,
            sa.func.lower(users.c.email) == "andubryanrj@hotmail.com",
        )
        .values(full_name="Uanderson Martins")
    )


def downgrade():
    op.drop_column("users", "full_name")
