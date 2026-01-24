"""Add response_constraints table for anti-hallucination validation

Revision ID: 027_response_constraints
Revises: 026_inherit_parent_data
Create Date: 2026-01-24 00:00:00.000000

Changes:
- Create response_constraints table for DB-driven LLM response validation.
  Stores regex patterns that detect potential hallucinations (e.g., prices
  mentioned without calling the tariff tool) and correction messages to
  inject when violations are detected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "027_response_constraints"
down_revision: Union[str, None] = "026_inherit_parent_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "response_constraints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("category_id", UUID(as_uuid=True), sa.ForeignKey("vehicle_categories.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("constraint_type", sa.String(50), nullable=False),
        sa.Column("detection_pattern", sa.String(500), nullable=False),
        sa.Column("required_tool", sa.String(200), nullable=False),
        sa.Column("error_injection", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Insert default constraints (global - category_id NULL = applies to all)
    # NOTE: Using sa.text() with literal_column to avoid SQLAlchemy interpreting
    # regex (?:...) as bind parameters (it treats :word as a named param)
    from sqlalchemy import text as sa_text
    conn = op.get_bind()
    conn.execute(sa_text(r"""
        INSERT INTO response_constraints (id, category_id, constraint_type, detection_pattern, required_tool, error_injection, is_active, priority)
        VALUES
        (
            gen_random_uuid(),
            NULL,
            'price_requires_tool',
            '\d+\s*€|\d+\s*EUR|presupuesto.*\d+|\d+.*\+\s*IVA',
            'calcular_tarifa_con_elementos',
            'CORRECCION OBLIGATORIA: Has mencionado un precio sin haber llamado a calcular_tarifa_con_elementos. NUNCA inventes precios. Llama PRIMERO a calcular_tarifa_con_elementos con los codigos de elementos resueltos, y usa el precio que devuelve la herramienta. Si no tienes codigos resueltos, llama primero a identificar_y_resolver_elementos.',
            true,
            100
        ),
        (
            gen_random_uuid(),
            NULL,
            'variant_requires_tool',
            '¿.*tipo.*\:|¿.*estandar.*full|¿.*variante|¿.*cual.*prefer|¿.*instalad[oa].*en',
            'identificar_y_resolver_elementos|seleccionar_variante_por_respuesta',
            'CORRECCION OBLIGATORIA: Estas haciendo una pregunta de variante que NO viene de la base de datos. NUNCA inventes preguntas de clasificacion. Llama a identificar_y_resolver_elementos y usa EXACTAMENTE la question_hint que devuelve la herramienta para preguntar al usuario.',
            true,
            90
        ),
        (
            gen_random_uuid(),
            NULL,
            'docs_from_tool_only',
            'certificado.*(resistencia|anclaje|instalacion)|normativa.*UNE|homologacion.*requiere.*(proyecto|boletin)|documentacion.*(necesaria|requerida|obligatoria).*\:',
            'calcular_tarifa_con_elementos|obtener_documentacion_elemento',
            'CORRECCION OBLIGATORIA: Estas describiendo requisitos de documentacion que NO vienen de las herramientas. NUNCA inventes requisitos documentales. La documentacion requerida viene SOLO del campo "documentacion" en la respuesta de calcular_tarifa_con_elementos o de obtener_documentacion_elemento. Usa esos datos exactos.',
            true,
            80
        ),
        (
            gen_random_uuid(),
            NULL,
            'images_narration_blocked',
            '\[.*[Ll]lamando.*herramienta|imagenes.*se.*enviaran.*a.*continuacion|fotos.*adjunt|ejemplo.*imagenes.*adjunt',
            'enviar_imagenes_ejemplo',
            'CORRECCION OBLIGATORIA: Estas NARRANDO el envio de imagenes en texto en lugar de llamar a la herramienta. NUNCA describas que vas a enviar imagenes. Llama a enviar_imagenes_ejemplo() directamente. Si ya la llamaste y fallo, informa al usuario que las imagenes no estan disponibles en este momento.',
            true,
            95
        );
    """))


def downgrade() -> None:
    op.drop_table("response_constraints")
