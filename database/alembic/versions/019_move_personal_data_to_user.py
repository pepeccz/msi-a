"""Move personal data from Case to User

Revision ID: 019_move_personal_data_to_user
Revises: 018_fix_field_lengths
Create Date: 2026-01-13 00:00:00.000000

Changes:
- Add address fields to users table (domicilio_*)
- Migrate existing data from cases to users where user_id exists
- Remove personal data fields from cases table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "019_move_personal_data_to_user"
down_revision: Union[str, None] = "018_fix_field_lengths"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add address columns to users table
    op.add_column(
        "users",
        sa.Column(
            "domicilio_calle",
            sa.String(255),
            nullable=True,
            comment="Street address",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "domicilio_localidad",
            sa.String(100),
            nullable=True,
            comment="City/town",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "domicilio_provincia",
            sa.String(100),
            nullable=True,
            comment="Province",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "domicilio_cp",
            sa.String(10),
            nullable=True,
            comment="Postal code",
        ),
    )

    # Step 2: Migrate existing data from cases to users
    # Only update users where they have a related case with data
    # Uses the most recent case data for each user
    op.execute("""
        UPDATE users u
        SET
            first_name = COALESCE(u.first_name, c.nombre),
            last_name = COALESCE(u.last_name, c.apellidos),
            email = COALESCE(u.email, c.email),
            nif_cif = COALESCE(u.nif_cif, c.dni_cif),
            domicilio_calle = c.domicilio_calle,
            domicilio_localidad = c.domicilio_localidad,
            domicilio_provincia = c.domicilio_provincia,
            domicilio_cp = c.domicilio_cp
        FROM (
            SELECT DISTINCT ON (user_id)
                user_id, nombre, apellidos, email, dni_cif,
                domicilio_calle, domicilio_localidad, domicilio_provincia, domicilio_cp
            FROM cases
            WHERE user_id IS NOT NULL
            ORDER BY user_id, created_at DESC
        ) c
        WHERE u.id = c.user_id
    """)

    # Step 3: Remove personal data columns from cases table
    op.drop_column("cases", "nombre")
    op.drop_column("cases", "apellidos")
    op.drop_column("cases", "email")
    op.drop_column("cases", "telefono")
    op.drop_column("cases", "dni_cif")
    op.drop_column("cases", "domicilio_calle")
    op.drop_column("cases", "domicilio_localidad")
    op.drop_column("cases", "domicilio_provincia")
    op.drop_column("cases", "domicilio_cp")


def downgrade() -> None:
    # Step 1: Re-add personal data columns to cases
    op.add_column(
        "cases",
        sa.Column("nombre", sa.String(100), nullable=True),
    )
    op.add_column(
        "cases",
        sa.Column("apellidos", sa.String(200), nullable=True),
    )
    op.add_column(
        "cases",
        sa.Column("email", sa.String(255), nullable=True),
    )
    op.add_column(
        "cases",
        sa.Column(
            "telefono",
            sa.String(30),
            nullable=True,
            comment="Additional phone (WhatsApp already in user record)",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "dni_cif",
            sa.String(20),
            nullable=True,
            comment="DNI or CIF of petitioner",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "domicilio_calle",
            sa.String(255),
            nullable=True,
            comment="Street address",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "domicilio_localidad",
            sa.String(100),
            nullable=True,
            comment="City/Town",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "domicilio_provincia",
            sa.String(100),
            nullable=True,
            comment="Province",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "domicilio_cp",
            sa.String(10),
            nullable=True,
            comment="Postal code",
        ),
    )

    # Step 2: Copy data back from users to cases
    op.execute("""
        UPDATE cases c
        SET
            nombre = u.first_name,
            apellidos = u.last_name,
            email = u.email,
            dni_cif = u.nif_cif,
            domicilio_calle = u.domicilio_calle,
            domicilio_localidad = u.domicilio_localidad,
            domicilio_provincia = u.domicilio_provincia,
            domicilio_cp = u.domicilio_cp
        FROM users u
        WHERE c.user_id = u.id
    """)

    # Step 3: Remove address columns from users
    op.drop_column("users", "domicilio_calle")
    op.drop_column("users", "domicilio_localidad")
    op.drop_column("users", "domicilio_provincia")
    op.drop_column("users", "domicilio_cp")
