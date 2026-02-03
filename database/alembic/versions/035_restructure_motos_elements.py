"""Restructure motorcycle elements: add parent nodes, fields, warnings

Revision ID: 035_restructure_motos_elements
Revises: 7dc32f4a106a
Create Date: 2026-02-03 00:00:00.000000

Changes:
1. Insert 2 new base elements (FRENADO, CARROCERIA_EXT) as parent nodes
2. Update parent_element_id for 9 child elements (5 brake + 4 bodywork)
3. Insert 19 new ElementRequiredField records for 10 elements
4. Insert 3 new Warning records (2 new + 1 for FRENADO_LATIGUILLOS)
5. Insert 3 new ElementWarningAssociation records (dual warning system)
6. Insert 1 new element (ACCESORIO_GENERICO) with 5 fields + 1 warning

This migration applies the motorcycle seeds restructuring documented in:
- database/seeds/PLAN_CAMBIOS_MOTOS.md
- database/seeds/RESTRUCTURE_COMPLETED.md
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "035_restructure_motos_elements"
down_revision: Union[str, None] = "7dc32f4a106a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# =============================================================================
# Deterministic UUID Generation (matches database/seeds/seed_utils.py)
# =============================================================================

SEED_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
CATEGORY_SLUG = "motos-part"


def element_uuid(code: str) -> str:
    """Generate deterministic UUID for an element."""
    seed_string = f"{CATEGORY_SLUG}:element:{code}"
    return str(uuid.uuid5(SEED_NAMESPACE, seed_string))


def warning_uuid(code: str) -> str:
    """Generate deterministic UUID for a warning."""
    seed_string = f"{CATEGORY_SLUG}:warning:{code}"
    return str(uuid.uuid5(SEED_NAMESPACE, seed_string))


def field_uuid(element_code: str, field_key: str) -> str:
    """Generate deterministic UUID for a required field."""
    seed_string = f"{CATEGORY_SLUG}:field:{element_code}:{field_key}"
    return str(uuid.uuid5(SEED_NAMESPACE, seed_string))


def assoc_uuid(element_id: str, warning_id: str) -> str:
    """Generate deterministic UUID for element-warning association."""
    seed_string = f"element_warning_assoc:{element_id}:{warning_id}"
    return str(uuid.uuid5(SEED_NAMESPACE, seed_string))


# =============================================================================
# Pre-calculated UUIDs
# =============================================================================

# Get category ID (motos-part)
def get_category_id():
    """Get UUID of motos-part category."""
    seed_string = f"{CATEGORY_SLUG}:category:{CATEGORY_SLUG}"
    return str(uuid.uuid5(SEED_NAMESPACE, seed_string))


CATEGORY_ID = get_category_id()

# New base elements
FRENADO_ID = element_uuid("FRENADO")
CARROCERIA_EXT_ID = element_uuid("CARROCERIA_EXT")
ACCESORIO_GENERICO_ID = element_uuid("ACCESORIO_GENERICO")

# Existing elements (children that need parent_element_id update)
FRENADO_DISCOS_ID = element_uuid("FRENADO_DISCOS")
FRENADO_PINZAS_ID = element_uuid("FRENADO_PINZAS")
FRENADO_BOMBAS_ID = element_uuid("FRENADO_BOMBAS")
FRENADO_LATIGUILLOS_ID = element_uuid("FRENADO_LATIGUILLOS")
FRENADO_DEPOSITO_ID = element_uuid("FRENADO_DEPOSITO")

CARENADO_ID = element_uuid("CARENADO")
GUARDABARROS_DEL_ID = element_uuid("GUARDABARROS_DEL")
GUARDABARROS_TRAS_ID = element_uuid("GUARDABARROS_TRAS")
CARROCERIA_ID = element_uuid("CARROCERIA")

# Existing elements that get new fields
INTERMITENTES_DEL_ID = element_uuid("INTERMITENTES_DEL")
INTERMITENTES_TRAS_ID = element_uuid("INTERMITENTES_TRAS")
PILOTO_FRENO_ID = element_uuid("PILOTO_FRENO")
LUZ_MATRICULA_ID = element_uuid("LUZ_MATRICULA")
CATADIOPTRICO_ID = element_uuid("CATADIOPTRICO")
ANTINIEBLAS_ID = element_uuid("ANTINIEBLAS")
MANDOS_AVANZADOS_ID = element_uuid("MANDOS_AVANZADOS")
MATRICULA_ID = element_uuid("MATRICULA")
VELOCIMETRO_ID = element_uuid("VELOCIMETRO")
LLANTAS_ID = element_uuid("LLANTAS")

# New warnings
WARNING_FRENADO_LAT_ID = warning_uuid("frenado_latiguillos_especificacion")
WARNING_ANTINIEBLAS_ID = warning_uuid("antinieblas_pictograma_obligatorio")
WARNING_LLANTAS_ID = warning_uuid("llantas_ensayo_neumatico")
WARNING_ACCESORIO_ID = warning_uuid("accesorio_generico_evaluacion")


def upgrade() -> None:
    conn = op.get_bind()

    # ==========================================================================
    # 1. Insert 2 new base elements (FRENADO, CARROCERIA_EXT)
    # ==========================================================================
    
    # FRENADO (parent of brake components)
    op.execute(
        sa.text("""
            INSERT INTO elements (
                id, category_id, code, name, description, keywords, aliases,
                is_base, parent_element_id, is_active, sort_order,
                created_at, updated_at
            ) VALUES (
                :id, :category_id, :code, :name, :description, :keywords::jsonb, :aliases::jsonb,
                :is_base, :parent_element_id, :is_active, :sort_order,
                now(), now()
            )
        """).bindparams(
            id=FRENADO_ID,
            category_id=CATEGORY_ID,
            code="FRENADO",
            name="Sistema de frenado",
            description="Sistema de frenado modificado. Incluye discos, pinzas, latiguillos, bombas y depósitos.",
            keywords='["frenado", "frenos", "freno", "brake", "brembo", "nissin", "galfer", "ng brakes", "beringer", "j.juan", "braking", "ebc", "performance friction"]',
            aliases='["brake system", "braking system"]',
            is_base=True,
            parent_element_id=None,
            is_active=True,
            sort_order=39
        )
    )

    # CARROCERIA_EXT (parent of bodywork components)
    op.execute(
        sa.text("""
            INSERT INTO elements (
                id, category_id, code, name, description, keywords, aliases,
                is_base, parent_element_id, is_active, sort_order,
                created_at, updated_at
            ) VALUES (
                :id, :category_id, :code, :name, :description, :keywords::jsonb, :aliases::jsonb,
                :is_base, :parent_element_id, :is_active, :sort_order,
                now(), now()
            )
        """).bindparams(
            id=CARROCERIA_EXT_ID,
            category_id=CATEGORY_ID,
            code="CARROCERIA_EXT",
            name="Carrocería exterior",
            description="Elementos de carrocería exterior: carenados, guardabarros, paneles de carrocería.",
            keywords='["carroceria", "chapa", "panel", "plastico", "exterior", "bodywork"]',
            aliases='["bodywork", "exterior panels"]',
            is_base=True,
            parent_element_id=None,
            is_active=True,
            sort_order=49
        )
    )

    # ==========================================================================
    # 2. Update parent_element_id for 9 child elements
    # ==========================================================================
    
    # Brake system children → FRENADO
    op.execute(
        sa.text("""
            UPDATE elements 
            SET parent_element_id = :parent_id, updated_at = now()
            WHERE id IN (:id1, :id2, :id3, :id4, :id5)
        """).bindparams(
            parent_id=FRENADO_ID,
            id1=FRENADO_DISCOS_ID,
            id2=FRENADO_PINZAS_ID,
            id3=FRENADO_BOMBAS_ID,
            id4=FRENADO_LATIGUILLOS_ID,
            id5=FRENADO_DEPOSITO_ID
        )
    )

    # Bodywork children → CARROCERIA_EXT
    op.execute(
        sa.text("""
            UPDATE elements 
            SET parent_element_id = :parent_id, updated_at = now()
            WHERE id IN (:id1, :id2, :id3, :id4)
        """).bindparams(
            parent_id=CARROCERIA_EXT_ID,
            id1=CARENADO_ID,
            id2=GUARDABARROS_DEL_ID,
            id3=GUARDABARROS_TRAS_ID,
            id4=CARROCERIA_ID
        )
    )

    # ==========================================================================
    # 3. Insert new warnings (3 warnings)
    # ==========================================================================
    
    # Warning for FRENADO_LATIGUILLOS
    op.execute(
        sa.text("""
            INSERT INTO warnings (
                id, code, message, severity, element_id,
                created_at, updated_at
            ) VALUES (
                :id, :code, :message, :severity, :element_id,
                now(), now()
            )
        """).bindparams(
            id=WARNING_FRENADO_LAT_ID,
            code="frenado_latiguillos_especificacion",
            message="Especificar material (tela, acero, aero) y si son delanteros, traseros o ambos.",
            severity="info",
            element_id=FRENADO_LATIGUILLOS_ID
        )
    )

    # Warning for ANTINIEBLAS
    op.execute(
        sa.text("""
            INSERT INTO warnings (
                id, code, message, severity, element_id,
                created_at, updated_at
            ) VALUES (
                :id, :code, :message, :severity, :element_id,
                now(), now()
            )
        """).bindparams(
            id=WARNING_ANTINIEBLAS_ID,
            code="antinieblas_pictograma_obligatorio",
            message="Los faros antiniebla deben incluir pictograma homologado visible (marcado E).",
            severity="warning",
            element_id=ANTINIEBLAS_ID
        )
    )

    # Warning for LLANTAS
    op.execute(
        sa.text("""
            INSERT INTO warnings (
                id, code, message, severity, element_id,
                created_at, updated_at
            ) VALUES (
                :id, :code, :message, :severity, :element_id,
                now(), now()
            )
        """).bindparams(
            id=WARNING_LLANTAS_ID,
            code="llantas_ensayo_neumatico",
            message="Si se cambian llantas puede ser necesario ensayo de neumático (375 EUR adicionales). Consultar antes de confirmar.",
            severity="warning",
            element_id=LLANTAS_ID
        )
    )

    # Warning for ACCESORIO_GENERICO (will be inserted with element below)

    # ==========================================================================
    # 4. Insert element_warning_associations (dual warning system)
    # ==========================================================================
    
    # Association: FRENADO_LATIGUILLOS
    op.execute(
        sa.text("""
            INSERT INTO element_warning_associations (
                id, element_id, warning_id, show_condition,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :warning_id, :show_condition,
                now(), now()
            )
        """).bindparams(
            id=assoc_uuid(FRENADO_LATIGUILLOS_ID, WARNING_FRENADO_LAT_ID),
            element_id=FRENADO_LATIGUILLOS_ID,
            warning_id=WARNING_FRENADO_LAT_ID,
            show_condition="always"
        )
    )

    # Association: ANTINIEBLAS
    op.execute(
        sa.text("""
            INSERT INTO element_warning_associations (
                id, element_id, warning_id, show_condition,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :warning_id, :show_condition,
                now(), now()
            )
        """).bindparams(
            id=assoc_uuid(ANTINIEBLAS_ID, WARNING_ANTINIEBLAS_ID),
            element_id=ANTINIEBLAS_ID,
            warning_id=WARNING_ANTINIEBLAS_ID,
            show_condition="always"
        )
    )

    # Association: LLANTAS
    op.execute(
        sa.text("""
            INSERT INTO element_warning_associations (
                id, element_id, warning_id, show_condition,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :warning_id, :show_condition,
                now(), now()
            )
        """).bindparams(
            id=assoc_uuid(LLANTAS_ID, WARNING_LLANTAS_ID),
            element_id=LLANTAS_ID,
            warning_id=WARNING_LLANTAS_ID,
            show_condition="always"
        )
    )

    # ==========================================================================
    # 5. Insert new element: ACCESORIO_GENERICO
    # ==========================================================================
    
    op.execute(
        sa.text("""
            INSERT INTO elements (
                id, category_id, code, name, description, keywords, aliases,
                is_base, parent_element_id, is_active, sort_order,
                created_at, updated_at
            ) VALUES (
                :id, :category_id, :code, :name, :description, :keywords::jsonb, :aliases::jsonb,
                :is_base, :parent_element_id, :is_active, :sort_order,
                now(), now()
            )
        """).bindparams(
            id=ACCESORIO_GENERICO_ID,
            category_id=CATEGORY_ID,
            code="ACCESORIO_GENERICO",
            name="Accesorio genérico",
            description="Elemento o accesorio no contemplado en el catálogo. Describe el elemento modificado o instalado para evaluación manual.",
            keywords='["otro", "otros", "accesorio", "modificacion", "custom", "personalizado", "elemento no listado", "no identificado", "generico", "otro elemento"]',
            aliases='["other accessory", "custom part", "unlisted element"]',
            is_base=False,
            parent_element_id=None,
            is_active=True,
            sort_order=200
        )
    )

    # Warning for ACCESORIO_GENERICO
    op.execute(
        sa.text("""
            INSERT INTO warnings (
                id, code, message, severity, element_id,
                created_at, updated_at
            ) VALUES (
                :id, :code, :message, :severity, :element_id,
                now(), now()
            )
        """).bindparams(
            id=WARNING_ACCESORIO_ID,
            code="accesorio_generico_evaluacion",
            message="Este elemento requiere evaluación manual por el equipo técnico. Proporciona máxima información posible (marca, modelo, función, ubicación) para facilitar el análisis.",
            severity="info",
            element_id=ACCESORIO_GENERICO_ID
        )
    )

    # Association for ACCESORIO_GENERICO warning
    op.execute(
        sa.text("""
            INSERT INTO element_warning_associations (
                id, element_id, warning_id, show_condition,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :warning_id, :show_condition,
                now(), now()
            )
        """).bindparams(
            id=assoc_uuid(ACCESORIO_GENERICO_ID, WARNING_ACCESORIO_ID),
            element_id=ACCESORIO_GENERICO_ID,
            warning_id=WARNING_ACCESORIO_ID,
            show_condition="always"
        )
    )

    # ==========================================================================
    # 6. Insert 19 new required_fields for 11 elements
    # ==========================================================================
    
    # --- INTERMITENTES_DEL: altura_mm ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("INTERMITENTES_DEL", "altura_mm"),
            element_id=INTERMITENTES_DEL_ID,
            field_key="altura_mm",
            field_label="Altura desde el suelo (mm)",
            field_type="number",
            sort_order=10,
            example_value="400",
            llm_instruction="Solicita la altura de los intermitentes desde el suelo en milímetros (mínimo 350mm)",
            is_required=True
        )
    )

    # --- INTERMITENTES_TRAS: altura_mm ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("INTERMITENTES_TRAS", "altura_mm"),
            element_id=INTERMITENTES_TRAS_ID,
            field_key="altura_mm",
            field_label="Altura desde el suelo (mm)",
            field_type="number",
            sort_order=10,
            example_value="400",
            llm_instruction="Solicita la altura de los intermitentes traseros desde el suelo en milímetros (mínimo 350mm)",
            is_required=True
        )
    )

    # --- PILOTO_FRENO: marca ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("PILOTO_FRENO", "marca"),
            element_id=PILOTO_FRENO_ID,
            field_key="marca",
            field_label="Marca",
            field_type="text",
            sort_order=1,
            example_value="Puig",
            llm_instruction="Solicita la marca del piloto de freno",
            is_required=True
        )
    )

    # --- LUZ_MATRICULA: marca ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("LUZ_MATRICULA", "marca"),
            element_id=LUZ_MATRICULA_ID,
            field_key="marca",
            field_label="Marca",
            field_type="text",
            sort_order=1,
            example_value="Puig",
            llm_instruction="Solicita la marca de la luz de matrícula",
            is_required=True
        )
    )

    # --- CATADIOPTRICO: marca ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("CATADIOPTRICO", "marca"),
            element_id=CATADIOPTRICO_ID,
            field_key="marca",
            field_label="Marca",
            field_type="text",
            sort_order=1,
            example_value="Puig",
            llm_instruction="Solicita la marca del catadióptrico",
            is_required=True
        )
    )

    # --- ANTINIEBLAS: marca ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("ANTINIEBLAS", "marca"),
            element_id=ANTINIEBLAS_ID,
            field_key="marca",
            field_label="Marca",
            field_type="text",
            sort_order=1,
            example_value="Hella",
            llm_instruction="Solicita la marca de los faros antiniebla",
            is_required=True
        )
    )

    # --- MANDOS_AVANZADOS: pedal_freno_material ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type, options,
                sort_order, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type, :options::jsonb,
                :sort_order, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("MANDOS_AVANZADOS", "pedal_freno_material"),
            element_id=MANDOS_AVANZADOS_ID,
            field_key="pedal_freno_material",
            field_label="Material del pedal de freno",
            field_type="select",
            options='["Aluminio", "Acero", "Fibra de carbono"]',
            sort_order=1,
            llm_instruction="Pregunta el material del pedal de freno",
            is_required=True
        )
    )

    # --- MANDOS_AVANZADOS: pedal_cambio_material ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type, options,
                sort_order, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type, :options::jsonb,
                :sort_order, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("MANDOS_AVANZADOS", "pedal_cambio_material"),
            element_id=MANDOS_AVANZADOS_ID,
            field_key="pedal_cambio_material",
            field_label="Material del pedal de cambio",
            field_type="select",
            options='["Aluminio", "Acero", "Fibra de carbono"]',
            sort_order=2,
            llm_instruction="Pregunta el material del pedal de cambio",
            is_required=True
        )
    )

    # --- MATRICULA: 4 conditional fields ---
    # ubicacion_sin_brazo
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                condition_field_key, condition_operator, condition_value,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                :condition_field_key, :condition_operator, :condition_value,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("MATRICULA", "ubicacion_sin_brazo"),
            element_id=MATRICULA_ID,
            field_key="ubicacion_sin_brazo",
            field_label="Ubicación (sin brazo)",
            field_type="text",
            sort_order=2,
            example_value="Bajo el colín",
            llm_instruction="Si es sin brazo, describe la ubicación específica del portamatrículas",
            is_required=False,
            condition_field_key="tipo_montaje",
            condition_operator="equals",
            condition_value="Sin brazo (portamatrículas corto)"
        )
    )

    # brazo_material
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type, options,
                sort_order, llm_instruction, is_required,
                condition_field_key, condition_operator, condition_value,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type, :options::jsonb,
                :sort_order, :llm_instruction, :is_required,
                :condition_field_key, :condition_operator, :condition_value,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("MATRICULA", "brazo_material"),
            element_id=MATRICULA_ID,
            field_key="brazo_material",
            field_label="Material del brazo",
            field_type="select",
            options='["Aluminio", "Acero", "Fibra de carbono", "Plástico ABS"]',
            sort_order=3,
            llm_instruction="Si es con brazo lateral, pregunta el material del brazo",
            is_required=False,
            condition_field_key="tipo_montaje",
            condition_operator="equals",
            condition_value="Con brazo lateral"
        )
    )

    # brazo_tipo
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type, options,
                sort_order, llm_instruction, is_required,
                condition_field_key, condition_operator, condition_value,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type, :options::jsonb,
                :sort_order, :llm_instruction, :is_required,
                :condition_field_key, :condition_operator, :condition_value,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("MATRICULA", "brazo_tipo"),
            element_id=MATRICULA_ID,
            field_key="brazo_tipo",
            field_label="Tipo de brazo",
            field_type="select",
            options='["Artesanal", "Marca comercial"]',
            sort_order=4,
            llm_instruction="Si es con brazo lateral, pregunta si es artesanal o de marca comercial",
            is_required=False,
            condition_field_key="tipo_montaje",
            condition_operator="equals",
            condition_value="Con brazo lateral"
        )
    )

    # brazo_marca
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                condition_field_key, condition_operator, condition_value,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                :condition_field_key, :condition_operator, :condition_value,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("MATRICULA", "brazo_marca"),
            element_id=MATRICULA_ID,
            field_key="brazo_marca",
            field_label="Marca del brazo",
            field_type="text",
            sort_order=5,
            example_value="Puig / Artesanal",
            llm_instruction="Si es de marca comercial, solicita la marca. Si es artesanal, indica 'Artesanal'",
            is_required=False,
            condition_field_key="brazo_tipo",
            condition_operator="equals",
            condition_value="Marca comercial"
        )
    )

    # --- VELOCIMETRO: ubicacion_captador_nuevo ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                condition_field_key, condition_operator, condition_value,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                :condition_field_key, :condition_operator, :condition_value,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("VELOCIMETRO", "ubicacion_captador_nuevo"),
            element_id=VELOCIMETRO_ID,
            field_key="ubicacion_captador_nuevo",
            field_label="Ubicación del captador nuevo",
            field_type="text",
            sort_order=7,
            example_value="Rueda delantera / Caja de cambios",
            llm_instruction="Si instala captador nuevo, pregunta dónde se ubicará (rueda delantera, caja de cambios, etc.)",
            is_required=False,
            condition_field_key="captador",
            condition_operator="equals",
            condition_value="Nuevo captador"
        )
    )

    # --- LLANTAS: posicion ---
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type, options,
                sort_order, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type, :options::jsonb,
                :sort_order, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("LLANTAS", "posicion"),
            element_id=LLANTAS_ID,
            field_key="posicion",
            field_label="Posición",
            field_type="select",
            options='["Delantera", "Trasera", "Ambas"]',
            sort_order=1,
            llm_instruction="Pregunta si se cambian llantas delanteras, traseras o ambas",
            is_required=True
        )
    )

    # --- ACCESORIO_GENERICO: 5 fields ---
    # descripcion_elemento
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("ACCESORIO_GENERICO", "descripcion_elemento"),
            element_id=ACCESORIO_GENERICO_ID,
            field_key="descripcion_elemento",
            field_label="Descripción del elemento",
            field_type="text",
            sort_order=1,
            example_value="Protector de motor tipo crash bars",
            llm_instruction="Solicita una descripción detallada del elemento: tipo, función, ubicación en el vehículo",
            is_required=True
        )
    )

    # marca
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("ACCESORIO_GENERICO", "marca"),
            element_id=ACCESORIO_GENERICO_ID,
            field_key="marca",
            field_label="Marca",
            field_type="text",
            sort_order=2,
            example_value="Givi / Artesanal",
            llm_instruction="Pregunta la marca del elemento si es comercial, o indica 'Artesanal' si es fabricación propia",
            is_required=False
        )
    )

    # modelo
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, example_value, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :example_value, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("ACCESORIO_GENERICO", "modelo"),
            element_id=ACCESORIO_GENERICO_ID,
            field_key="modelo",
            field_label="Modelo o referencia",
            field_type="text",
            sort_order=3,
            example_value="TN1234",
            llm_instruction="Si es de marca comercial, solicita modelo o código de referencia",
            is_required=False
        )
    )

    # tipo_modificacion
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type, options,
                sort_order, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type, :options::jsonb,
                :sort_order, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("ACCESORIO_GENERICO", "tipo_modificacion"),
            element_id=ACCESORIO_GENERICO_ID,
            field_key="tipo_modificacion",
            field_label="Tipo de modificación",
            field_type="select",
            options='["Instalación nueva", "Sustitución", "Eliminación", "Modificación"]',
            sort_order=4,
            llm_instruction="Pregunta si es instalación de elemento nuevo, sustitución de original, eliminación o modificación",
            is_required=True
        )
    )

    # afecta_estructura
    op.execute(
        sa.text("""
            INSERT INTO element_required_fields (
                id, element_id, field_key, field_label, field_type,
                sort_order, llm_instruction, is_required,
                created_at, updated_at
            ) VALUES (
                :id, :element_id, :field_key, :field_label, :field_type,
                :sort_order, :llm_instruction, :is_required,
                now(), now()
            )
        """).bindparams(
            id=field_uuid("ACCESORIO_GENERICO", "afecta_estructura"),
            element_id=ACCESORIO_GENERICO_ID,
            field_key="afecta_estructura",
            field_label="¿Afecta a estructura o bastidor?",
            field_type="boolean",
            sort_order=5,
            llm_instruction="Confirma si la modificación requiere perforación, soldadura o alteración del bastidor/chasis",
            is_required=True
        )
    )


def downgrade() -> None:
    """
    Revert all changes from upgrade().
    
    Order: reverse of upgrade (delete fields, associations, warnings, elements, parent updates)
    """
    
    # ==========================================================================
    # 1. Delete all new required_fields (19 fields)
    # ==========================================================================
    
    field_ids = [
        field_uuid("INTERMITENTES_DEL", "altura_mm"),
        field_uuid("INTERMITENTES_TRAS", "altura_mm"),
        field_uuid("PILOTO_FRENO", "marca"),
        field_uuid("LUZ_MATRICULA", "marca"),
        field_uuid("CATADIOPTRICO", "marca"),
        field_uuid("ANTINIEBLAS", "marca"),
        field_uuid("MANDOS_AVANZADOS", "pedal_freno_material"),
        field_uuid("MANDOS_AVANZADOS", "pedal_cambio_material"),
        field_uuid("MATRICULA", "ubicacion_sin_brazo"),
        field_uuid("MATRICULA", "brazo_material"),
        field_uuid("MATRICULA", "brazo_tipo"),
        field_uuid("MATRICULA", "brazo_marca"),
        field_uuid("VELOCIMETRO", "ubicacion_captador_nuevo"),
        field_uuid("LLANTAS", "posicion"),
        field_uuid("ACCESORIO_GENERICO", "descripcion_elemento"),
        field_uuid("ACCESORIO_GENERICO", "marca"),
        field_uuid("ACCESORIO_GENERICO", "modelo"),
        field_uuid("ACCESORIO_GENERICO", "tipo_modificacion"),
        field_uuid("ACCESORIO_GENERICO", "afecta_estructura"),
    ]
    
    for field_id in field_ids:
        op.execute(
            sa.text("DELETE FROM element_required_fields WHERE id = :id").bindparams(id=field_id)
        )

    # ==========================================================================
    # 2. Delete element_warning_associations (4 associations)
    # ==========================================================================
    
    assoc_ids = [
        assoc_uuid(FRENADO_LATIGUILLOS_ID, WARNING_FRENADO_LAT_ID),
        assoc_uuid(ANTINIEBLAS_ID, WARNING_ANTINIEBLAS_ID),
        assoc_uuid(LLANTAS_ID, WARNING_LLANTAS_ID),
        assoc_uuid(ACCESORIO_GENERICO_ID, WARNING_ACCESORIO_ID),
    ]
    
    for assoc_id in assoc_ids:
        op.execute(
            sa.text("DELETE FROM element_warning_associations WHERE id = :id").bindparams(id=assoc_id)
        )

    # ==========================================================================
    # 3. Delete warnings (4 warnings)
    # ==========================================================================
    
    warning_ids = [
        WARNING_FRENADO_LAT_ID,
        WARNING_ANTINIEBLAS_ID,
        WARNING_LLANTAS_ID,
        WARNING_ACCESORIO_ID,
    ]
    
    for warning_id in warning_ids:
        op.execute(
            sa.text("DELETE FROM warnings WHERE id = :id").bindparams(id=warning_id)
        )

    # ==========================================================================
    # 4. Delete ACCESORIO_GENERICO element
    # ==========================================================================
    
    op.execute(
        sa.text("DELETE FROM elements WHERE id = :id").bindparams(id=ACCESORIO_GENERICO_ID)
    )

    # ==========================================================================
    # 5. Remove parent_element_id from 9 children
    # ==========================================================================
    
    child_ids = [
        FRENADO_DISCOS_ID,
        FRENADO_PINZAS_ID,
        FRENADO_BOMBAS_ID,
        FRENADO_LATIGUILLOS_ID,
        FRENADO_DEPOSITO_ID,
        CARENADO_ID,
        GUARDABARROS_DEL_ID,
        GUARDABARROS_TRAS_ID,
        CARROCERIA_ID,
    ]
    
    for child_id in child_ids:
        op.execute(
            sa.text("""
                UPDATE elements 
                SET parent_element_id = NULL, updated_at = now()
                WHERE id = :id
            """).bindparams(id=child_id)
        )

    # ==========================================================================
    # 6. Delete 2 base elements (FRENADO, CARROCERIA_EXT)
    # ==========================================================================
    
    op.execute(
        sa.text("DELETE FROM elements WHERE id = :id").bindparams(id=FRENADO_ID)
    )
    
    op.execute(
        sa.text("DELETE FROM elements WHERE id = :id").bindparams(id=CARROCERIA_EXT_ID)
    )
