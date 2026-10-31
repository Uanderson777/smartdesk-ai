"""Add companies, memberships, and ticket tenant ownership.

Revision ID: 20261030_0002
Revises: 20261030_0001
"""

from alembic import op
import sqlalchemy as sa

revision = "20261030_0002"
down_revision = "20261030_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
    )
    op.create_index("ix_companies_id", "companies", ["id"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint(
            "user_id",
            "company_id",
            name="uq_memberships_user_company",
        ),
    )
    op.create_index("ix_memberships_id", "memberships", ["id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_company_id", "memberships", ["company_id"])

    op.add_column(
        "tickets",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("tickets") as batch:
        batch.create_foreign_key(
            "fk_tickets_tenant_id_companies",
            "companies",
            ["tenant_id"],
            ["id"],
        )

    bind = op.get_bind()
    company_table = sa.table(
        "companies",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String(length=160)),
    )
    bind.execute(sa.insert(company_table).values(name="Empresa legada"))
    company_id = bind.scalar(sa.select(sa.func.max(company_table.c.id)))
    if company_id is None:
        raise RuntimeError("Não foi possível criar a empresa legada para a migration.")

    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("role", sa.String(length=20)),
        sa.column("is_active", sa.Boolean()),
    )
    memberships = sa.table(
        "memberships",
        sa.column("user_id", sa.Integer()),
        sa.column("company_id", sa.Integer()),
        sa.column("role", sa.String(length=20)),
        sa.column("is_active", sa.Boolean()),
    )
    existing_users = bind.execute(
        sa.select(users.c.id, users.c.role, users.c.is_active)
    ).mappings()
    membership_rows = [
        {
            "user_id": user["id"],
            "company_id": company_id,
            "role": user["role"],
            "is_active": user["is_active"],
        }
        for user in existing_users
    ]
    if membership_rows:
        bind.execute(sa.insert(memberships), membership_rows)

    tickets = sa.table(
        "tickets",
        sa.column("tenant_id", sa.Integer()),
    )
    bind.execute(
        sa.update(tickets)
        .where(tickets.c.tenant_id.is_(None))
        .values(tenant_id=company_id)
    )
    op.create_index("ix_tickets_tenant_id", "tickets", ["tenant_id"])


def downgrade():
    op.drop_index("ix_tickets_tenant_id", table_name="tickets")
    with op.batch_alter_table("tickets") as batch:
        batch.drop_constraint("fk_tickets_tenant_id_companies", type_="foreignkey")
        batch.drop_column("tenant_id")

    op.drop_index("ix_memberships_company_id", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_id", table_name="memberships")
    op.drop_table("memberships")

    op.drop_index("ix_companies_id", table_name="companies")
    op.drop_table("companies")
