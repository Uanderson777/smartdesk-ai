"""Add user roles, account status, and ticket ownership.

Revision ID: 20261030_0001
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261030_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column(
                "role",
                sa.String(length=20),
                nullable=False,
                server_default="requester",
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_id", "users", ["id"])
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    else:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        with op.batch_alter_table("users") as batch:
            if "role" not in user_columns:
                batch.add_column(
                    sa.Column(
                        "role",
                        sa.String(length=20),
                        nullable=False,
                        server_default="requester",
                    )
                )
            if "is_active" not in user_columns:
                batch.add_column(
                    sa.Column(
                        "is_active",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.true(),
                    )
                )

    if "tickets" not in tables:
        op.create_table(
            "tickets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("category", sa.String(length=40), nullable=False),
            sa.Column(
                "priority", sa.String(length=20), nullable=False, server_default="media"
            ),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="aberto"
            ),
            sa.Column("requester_id", sa.Integer(), nullable=True),
            sa.Column("assigned_technician_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["assigned_technician_id"], ["users.id"]),
        )
        op.create_index("ix_tickets_id", "tickets", ["id"])
        op.create_index("ix_tickets_requester_id", "tickets", ["requester_id"])
        op.create_index(
            "ix_tickets_assigned_technician_id",
            "tickets",
            ["assigned_technician_id"],
        )
    else:
        ticket_columns = {
            column["name"] for column in inspector.get_columns("tickets")
        }
        with op.batch_alter_table("tickets") as batch:
            if "requester_id" not in ticket_columns:
                batch.add_column(
                    sa.Column("requester_id", sa.Integer(), nullable=True)
                )
                batch.create_foreign_key(
                    "fk_tickets_requester_id_users",
                    "users",
                    ["requester_id"],
                    ["id"],
                )
            if "assigned_technician_id" not in ticket_columns:
                batch.add_column(
                    sa.Column("assigned_technician_id", sa.Integer(), nullable=True)
                )
                batch.create_foreign_key(
                    "fk_tickets_assigned_technician_id_users",
                    "users",
                    ["assigned_technician_id"],
                    ["id"],
                )
    index_specs = (
        ("users", "ix_users_id", ["id"], False),
        ("users", "ix_users_email", ["email"], True),
        ("tickets", "ix_tickets_id", ["id"], False),
        ("tickets", "ix_tickets_requester_id", ["requester_id"], False),
        (
            "tickets",
            "ix_tickets_assigned_technician_id",
            ["assigned_technician_id"],
            False,
        ),
    )
    inspector = inspect(bind)
    for table_name, index_name, columns, unique in index_specs:
        existing_indexes = {
            index["name"] for index in inspector.get_indexes(table_name)
        }
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, columns, unique=unique)


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "tickets" in tables:
        columns = {column["name"] for column in inspector.get_columns("tickets")}
        indexes = {
            index["name"] for index in inspector.get_indexes("tickets")
        }
        for index_name in (
            "ix_tickets_assigned_technician_id",
            "ix_tickets_requester_id",
        ):
            if index_name in indexes:
                op.drop_index(index_name, table_name="tickets")
        with op.batch_alter_table("tickets") as batch:
            for name in ("assigned_technician_id", "requester_id"):
                if name in columns:
                    batch.drop_column(name)

    if "users" in tables:
        columns = {column["name"] for column in inspector.get_columns("users")}
        with op.batch_alter_table("users") as batch:
            for name in ("is_active", "role"):
                if name in columns:
                    batch.drop_column(name)
