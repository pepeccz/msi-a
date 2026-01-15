"""
Utilidades para seeds idempotentes con UUIDs determinísticos.

Este módulo proporciona funciones para generar UUIDs consistentes basados
en los datos del elemento, permitiendo que las seeds sean idempotentes
(ejecutables múltiples veces sin efectos adversos).
"""

import uuid

# Namespace fijo del proyecto para UUIDs determinísticos (UUID v5)
# Este namespace garantiza que los mismos inputs siempre generen el mismo UUID
SEED_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def deterministic_uuid(category_slug: str, entity_type: str, code: str) -> uuid.UUID:
    """
    Genera un UUID determinístico basado en categoría, tipo de entidad y código.

    Siempre retorna el mismo UUID para la misma combinación de parámetros,
    lo que permite que las seeds actualicen registros existentes en lugar
    de crear duplicados o borrar datos del usuario.

    Args:
        category_slug: Slug de la categoría (ej: "motos-part", "aseicars-prof")
        entity_type: Tipo de entidad (ej: "element", "warning", "base_doc", "element_image")
        code: Código único del elemento dentro de su categoría

    Returns:
        UUID v5 determinístico

    Examples:
        >>> deterministic_uuid("motos-part", "element", "ESCAPE")
        UUID('...')  # Siempre el mismo valor
        >>> deterministic_uuid("motos-part", "warning", "ensayo_frenada")
        UUID('...')  # Siempre el mismo valor
        >>> deterministic_uuid("motos-part", "element_image", "ESCAPE_reference")
        UUID('...')  # Siempre el mismo valor
    """
    seed_string = f"{category_slug}:{entity_type}:{code}"
    return uuid.uuid5(SEED_NAMESPACE, seed_string)


def deterministic_element_uuid(category_slug: str, element_code: str) -> uuid.UUID:
    """Atajo para generar UUID de Element."""
    return deterministic_uuid(category_slug, "element", element_code)


def deterministic_warning_uuid(category_slug: str, warning_code: str) -> uuid.UUID:
    """Atajo para generar UUID de Warning."""
    return deterministic_uuid(category_slug, "warning", warning_code)


def deterministic_base_doc_uuid(category_slug: str, doc_code: str) -> uuid.UUID:
    """Atajo para generar UUID de BaseDocumentation."""
    return deterministic_uuid(category_slug, "base_doc", doc_code)


def deterministic_element_image_uuid(
    category_slug: str, element_code: str, image_identifier: str
) -> uuid.UUID:
    """
    Atajo para generar UUID de ElementImage.

    Args:
        category_slug: Slug de la categoría
        element_code: Código del elemento padre
        image_identifier: Identificador único de la imagen (ej: "reference", "example_1")
    """
    code = f"{element_code}_{image_identifier}"
    return deterministic_uuid(category_slug, "element_image", code)


def deterministic_tier_inclusion_uuid(
    category_slug: str, tier_code: str, element_code: str
) -> uuid.UUID:
    """
    Genera UUID determinístico para TierElementInclusion (tier-element).

    Args:
        category_slug: Slug de la categoría (ej: "motos-part")
        tier_code: Código del tier (ej: "T1", "T6")
        element_code: Código del elemento

    Returns:
        UUID v5 determinístico
    """
    seed_string = f"tier_inclusion:{category_slug}:{tier_code}:{element_code}"
    return uuid.uuid5(SEED_NAMESPACE, seed_string)


def deterministic_tier_to_tier_uuid(
    category_slug: str, parent_tier_code: str, included_tier_code: str
) -> uuid.UUID:
    """
    Genera UUID determinístico para TierElementInclusion (tier-to-tier reference).

    Args:
        category_slug: Slug de la categoría
        parent_tier_code: Código del tier padre (ej: "T1")
        included_tier_code: Código del tier incluido (ej: "T2")

    Returns:
        UUID v5 determinístico
    """
    seed_string = f"tier_to_tier:{category_slug}:{parent_tier_code}:{included_tier_code}"
    return uuid.uuid5(SEED_NAMESPACE, seed_string)


def deterministic_category_uuid(category_slug: str) -> uuid.UUID:
    """Genera UUID determinístico para VehicleCategory."""
    return deterministic_uuid(category_slug, "category", category_slug)


def deterministic_tier_uuid(category_slug: str, tier_code: str) -> uuid.UUID:
    """Genera UUID determinístico para TariffTier."""
    return deterministic_uuid(category_slug, "tier", tier_code)


def deterministic_additional_service_uuid(
    category_slug: str, service_code: str
) -> uuid.UUID:
    """Genera UUID determinístico para AdditionalService."""
    return deterministic_uuid(category_slug, "additional_service", service_code)


def deterministic_prompt_section_uuid(
    category_slug: str, section_key: str
) -> uuid.UUID:
    """Genera UUID determinístico para TariffPromptSection."""
    return deterministic_uuid(category_slug, "prompt_section", section_key)
