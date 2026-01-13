"""Expand case fields for complete expediente data collection

Revision ID: 017_expand_case_fields
Revises: 016_cases
Create Date: 2026-01-13 00:00:00.000000

Changes:
- Add dni_cif field for petitioner identification
- Add domicilio fields (calle, localidad, provincia, cp)
- Add itv_nombre field
- Add taller fields (propio, nombre, responsable, domicilio, etc.)
- Add dimensional changes fields (plazas, altura, ancho, longitud)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "017_expand_case_fields"
down_revision: Union[str, None] = "016_cases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Add DNI/CIF field
    # =========================================================================
    op.add_column(
        "cases",
        sa.Column(
            "dni_cif",
            sa.String(20),
            nullable=True,
            comment="DNI or CIF of petitioner",
        ),
    )

    # =========================================================================
    # 2. Add domicilio fields
    # =========================================================================
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

    # =========================================================================
    # 3. Add ITV field
    # =========================================================================
    op.add_column(
        "cases",
        sa.Column(
            "itv_nombre",
            sa.String(200),
            nullable=True,
            comment="Name of the ITV station",
        ),
    )

    # =========================================================================
    # 4. Add taller (workshop) fields
    # =========================================================================
    op.add_column(
        "cases",
        sa.Column(
            "taller_propio",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if client uses their own workshop, False if MSI provides certificate",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "taller_nombre",
            sa.String(200),
            nullable=True,
            comment="Workshop name (only if taller_propio=True)",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "taller_responsable",
            sa.String(200),
            nullable=True,
            comment="Workshop responsible person",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "taller_domicilio",
            sa.String(255),
            nullable=True,
            comment="Workshop street address",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "taller_provincia",
            sa.String(100),
            nullable=True,
            comment="Workshop province",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "taller_ciudad",
            sa.String(100),
            nullable=True,
            comment="Workshop city",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "taller_telefono",
            sa.String(20),
            nullable=True,
            comment="Workshop phone",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "taller_registro_industrial",
            sa.String(50),
            nullable=True,
            comment="Workshop industrial registration number",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "taller_actividad",
            sa.String(200),
            nullable=True,
            comment="Workshop activity description",
        ),
    )

    # =========================================================================
    # 5. Add dimensional changes fields
    # =========================================================================
    op.add_column(
        "cases",
        sa.Column(
            "cambio_plazas",
            sa.Boolean(),
            nullable=True,
            comment="True if there is a change in number of seats",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "plazas_iniciales",
            sa.Integer(),
            nullable=True,
            comment="Initial number of seats",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "plazas_finales",
            sa.Integer(),
            nullable=True,
            comment="Final number of seats",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "cambio_altura",
            sa.Boolean(),
            nullable=True,
            comment="True if there is a height change",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "altura_final",
            sa.Float(),
            nullable=True,
            comment="Final height in mm",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "cambio_ancho",
            sa.Boolean(),
            nullable=True,
            comment="True if there is a width change",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "ancho_final",
            sa.Float(),
            nullable=True,
            comment="Final width in mm",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "cambio_longitud",
            sa.Boolean(),
            nullable=True,
            comment="True if there is a length change",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "longitud_final",
            sa.Float(),
            nullable=True,
            comment="Final length in mm",
        ),
    )


def downgrade() -> None:
    # Remove dimensional changes fields
    op.drop_column("cases", "longitud_final")
    op.drop_column("cases", "cambio_longitud")
    op.drop_column("cases", "ancho_final")
    op.drop_column("cases", "cambio_ancho")
    op.drop_column("cases", "altura_final")
    op.drop_column("cases", "cambio_altura")
    op.drop_column("cases", "plazas_finales")
    op.drop_column("cases", "plazas_iniciales")
    op.drop_column("cases", "cambio_plazas")

    # Remove taller fields
    op.drop_column("cases", "taller_actividad")
    op.drop_column("cases", "taller_registro_industrial")
    op.drop_column("cases", "taller_telefono")
    op.drop_column("cases", "taller_ciudad")
    op.drop_column("cases", "taller_provincia")
    op.drop_column("cases", "taller_domicilio")
    op.drop_column("cases", "taller_responsable")
    op.drop_column("cases", "taller_nombre")
    op.drop_column("cases", "taller_propio")

    # Remove ITV field
    op.drop_column("cases", "itv_nombre")

    # Remove domicilio fields
    op.drop_column("cases", "domicilio_cp")
    op.drop_column("cases", "domicilio_provincia")
    op.drop_column("cases", "domicilio_localidad")
    op.drop_column("cases", "domicilio_calle")

    # Remove DNI/CIF field
    op.drop_column("cases", "dni_cif")
