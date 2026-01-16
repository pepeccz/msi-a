---
name: msia-tariffs
description: >
  MSI-a tariff system for vehicle homologations.
  Trigger: When working with tariffs, elements, tiers, categories, or pricing logic.
metadata:
  author: msi-automotive
  version: "1.0"
  scope: [root, api, agent]
  auto_invoke: "Working with tariffs or elements"
---

## Tariff System Overview

MSI-a uses a tiered pricing system for vehicle homologations:

```
VehicleCategory (e.g., "Autocaravanas - Particular")
    ↓
TariffTier (T1, T2, T3, T4, T5, T6)
    ↓
Elements (escalera, toldo, portabicis, etc.)
```

## Key Concepts

### Categories by Client Type

Categories are **duplicated** by client type:
- `motos-part` - Motocicletas (particular)
- `motos-prof` - Motocicletas (professional)
- `aseicars-part` - Autocaravanas (particular)
- `aseicars-prof` - Autocaravanas (professional)

Each has its own elements, tiers, and prices.

### Tier Classification

Tiers are determined by number of elements:

| Tier | Elements | Price (example) |
|------|----------|-----------------|
| T1 | 0 | Proyecto base |
| T2 | 0 | Proyecto simple |
| T3 | 1-2 | ~200€ |
| T4 | 3-4 | ~300€ |
| T5 | 5-6 | ~400€ |
| T6 | 7+ | ~500€ |

### Element Matching

Elements are matched by keywords:

```python
element = {
    "code": "ESC_MEC",
    "name": "Escalera Mecánica",
    "keywords": ["escalera", "escalera mecanica", "peldaños"],
}

# User says: "Quiero homologar una escalera"
# → Matches "ESC_MEC" via keyword "escalera"
```

## Data Model

```
VehicleCategory
├── slug: "aseicars-part"
├── name: "Autocaravanas"
├── client_type: "particular"
├── tariff_tiers: [TariffTier...]
├── elements: [Element...]
├── base_documentation: [BaseDocumentation...]
├── warnings: [Warning...]
└── additional_services: [AdditionalService...]

TariffTier
├── code: "T3"
├── name: "Proyecto Mediano"
├── price: 250.00
├── min_elements: 1
├── max_elements: 2
└── element_inclusions: [TierElementInclusion...]

Element
├── code: "ESC_MEC"
├── name: "Escalera Mecánica"
├── keywords: ["escalera", ...]
├── parent_element_id: null  # or UUID for variants
├── children: [Element...]   # variants
└── images: [ElementImage...]
```

## Tariff Calculation Flow

```python
async def calculate_tariff(
    category_slug: str,
    elements: list[str],
    client_type: str,
) -> TariffResult:
    # 1. Get category
    category = await get_category(category_slug, client_type)
    
    # 2. Match elements
    matched_elements = await match_elements(category.id, elements)
    
    # 3. Determine tier
    count = len(matched_elements)
    tier = await get_tier_by_element_count(category.id, count)
    
    # 4. Get documentation
    base_docs = category.base_documentation
    element_docs = [e.images for e in matched_elements]
    
    # 5. Get warnings
    warnings = await get_applicable_warnings(
        category.id, tier.id, [e.id for e in matched_elements]
    )
    
    return TariffResult(
        tier=tier,
        elements=matched_elements,
        base_documentation=base_docs,
        element_documentation=element_docs,
        warnings=warnings,
    )
```

## Element Variants

Some elements have variants (e.g., with/without MMR):

```
Suspensión (parent)
├── Suspensión sin MMR (variant_code: "SIN_MMR")
└── Suspensión con MMR (variant_code: "CON_MMR")
```

```python
# Parent element
element = Element(
    code="SUSPENSION",
    name="Suspensión",
    parent_element_id=None,  # Base element
)

# Variant
variant = Element(
    code="SUSPENSION_CON_MMR",
    name="Suspensión con MMR",
    parent_element_id=element.id,
    variant_type="mmr_option",
    variant_code="CON_MMR",
)
```

## Tier Element Inclusions

Define which elements belong to each tier:

```python
# T3 includes elements with 1-2 count
TierElementInclusion(
    tier_id=t3.id,
    element_id=escalera.id,
    min_quantity=1,
    max_quantity=2,
)

# T4 includes everything from T3
TierElementInclusion(
    tier_id=t4.id,
    included_tier_id=t3.id,  # Inherit from T3
)
```

## Warnings System

Warnings can be scoped to:
- **Global**: Always shown
- **Category**: Only for specific category
- **Tier**: Only when specific tier selected
- **Element**: Only when specific element matched

```python
# Element-specific warning
warning = Warning(
    code="antiniebla_sin_marcado",
    message="Los faros antiniebla sin marcado E requieren certificado adicional",
    severity="warning",
    element_id=antiniebla_element.id,
)

# Category warning
warning = Warning(
    code="peso_maximo",
    message="El peso máximo autorizado no debe superar 3500kg",
    severity="info",
    category_id=aseicars_part.id,
)
```

## Agent Tool Usage

```python
@tool
async def calculate_tariff(
    category_slug: str,
    elements: list[str],
    client_type: str
) -> str:
    """Calculate homologation tariff.
    
    Args:
        category_slug: Vehicle category (motos, aseicars)
        elements: List of elements to homologate
        client_type: particular or professional
    
    Returns:
        Formatted tariff with tier, price, and documentation
    """
    result = await TarifaService.calculate(...)
    
    return f"""
**Tarifa: {result.tier.name}**
Precio: {result.tier.price}€

**Elementos detectados:**
{format_elements(result.elements)}

**Documentación necesaria:**
{format_documentation(result.base_documentation, result.element_documentation)}

**Avisos:**
{format_warnings(result.warnings)}
"""
```

## Critical Rules

- ALWAYS match categories by (slug, client_type)
- ALWAYS use keywords for element matching (case-insensitive)
- NEVER hardcode prices - always from database
- ALWAYS include base documentation in results
- ALWAYS check for applicable warnings
- Element count determines tier automatically

## Resources

- [msia-database skill](../msia-database/SKILL.md) - Database models
- [msia-agent skill](../msia-agent/SKILL.md) - Agent tools
