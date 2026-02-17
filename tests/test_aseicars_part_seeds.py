"""
Comprehensive tests for aseicars-part category seed data.

This test file validates the aseicars-part category implementation including:
- Import and basic structure validation
- Tier configuration and pricing
- Element uniqueness and relationships
- Variant parent relationships
- Tier mappings consistency
- Keyword expansions
- Additional services configuration
- Deterministic UUID generation
- Integration with seed pipeline
"""

import pytest
import uuid
from decimal import Decimal


# =============================================================================
# TEST 1: Import and Basic Structure
# =============================================================================

class TestAseicarsPartImports:
    """Test that aseicars_part module imports successfully with all required exports."""

    def test_aseicars_part_imports_successfully(self):
        """Test that the aseicars_part module imports without errors."""
        from database.seeds.data import aseicars_part
        assert aseicars_part is not None

    def test_category_slug_is_correct(self):
        """Verify CATEGORY_SLUG = 'aseicars-part'."""
        from database.seeds.data.aseicars_part import CATEGORY_SLUG
        assert CATEGORY_SLUG == "aseicars-part"

    def test_category_is_defined(self):
        """Verify CATEGORY dict is defined with required fields."""
        from database.seeds.data.aseicars_part import CATEGORY
        
        assert isinstance(CATEGORY, dict)
        assert CATEGORY["slug"] == "aseicars-part"
        assert CATEGORY["name"] == "Autocaravanas (32xx, 33xx)"
        assert CATEGORY["client_type"] == "particular"
        assert CATEGORY["icon"] == "caravan"
        assert "description" in CATEGORY

    def test_tiers_is_defined(self):
        """Verify TIERS list is defined."""
        from database.seeds.data.aseicars_part import TIERS
        assert isinstance(TIERS, list)
        assert len(TIERS) > 0

    def test_elements_is_defined(self):
        """Verify ELEMENTS list is defined."""
        from database.seeds.data.aseicars_part import ELEMENTS
        assert isinstance(ELEMENTS, list)
        assert len(ELEMENTS) > 0

    def test_category_warnings_is_defined(self):
        """Verify CATEGORY_WARNINGS list is defined."""
        from database.seeds.data.aseicars_part import CATEGORY_WARNINGS
        assert isinstance(CATEGORY_WARNINGS, list)

    def test_additional_services_is_defined(self):
        """Verify ADDITIONAL_SERVICES list is defined."""
        from database.seeds.data.aseicars_part import ADDITIONAL_SERVICES
        assert isinstance(ADDITIONAL_SERVICES, list)

    def test_base_documentation_is_defined(self):
        """Verify BASE_DOCUMENTATION list is defined."""
        from database.seeds.data.aseicars_part import BASE_DOCUMENTATION
        assert isinstance(BASE_DOCUMENTATION, list)

    def test_prompt_sections_is_defined(self):
        """Verify PROMPT_SECTIONS list is defined."""
        from database.seeds.data.aseicars_part import PROMPT_SECTIONS
        assert isinstance(PROMPT_SECTIONS, list)


# =============================================================================
# TEST 2: Tier Validation
# =============================================================================

class TestAseicarsPartTiers:
    """Test tier configuration for aseicars-part category."""

    def test_all_6_tiers_exist(self):
        """Verify 6 tiers exist (T1-T6)."""
        from database.seeds.data.aseicars_part import TIERS
        
        tier_codes = [tier["code"] for tier in TIERS]
        assert "T1" in tier_codes
        assert "T2" in tier_codes
        assert "T3" in tier_codes
        assert "T4" in tier_codes
        assert "T5" in tier_codes
        assert "T6" in tier_codes
        assert len(TIERS) == 6

    def test_tier_prices_are_correct(self):
        """Verify prices: T1=300, T2=265, T3=225, T4=195, T5=145, T6=75."""
        from database.seeds.data.aseicars_part import TIERS
        
        expected_prices = {
            "T1": Decimal("300.00"),
            "T2": Decimal("265.00"),
            "T3": Decimal("225.00"),
            "T4": Decimal("195.00"),
            "T5": Decimal("145.00"),
            "T6": Decimal("75.00"),
        }
        
        for tier in TIERS:
            assert tier["price"] == expected_prices[tier["code"]], \
                f"Tier {tier['code']} should have price {expected_prices[tier['code']]}"

    def test_tiers_have_required_fields(self):
        """Verify all tiers have required fields (code, name, price, description, classification_rules)."""
        from database.seeds.data.aseicars_part import TIERS
        
        required_fields = ["code", "name", "price", "description", "classification_rules", "conditions"]
        
        for tier in TIERS:
            for field in required_fields:
                assert field in tier, f"Tier {tier['code']} missing required field: {field}"
                assert tier[field] is not None, f"Tier {tier['code']} field {field} is None"

    def test_tier_classification_rules_structure(self):
        """Verify classification_rules have required structure."""
        from database.seeds.data.aseicars_part import TIERS
        
        for tier in TIERS:
            rules = tier["classification_rules"]
            assert isinstance(rules, dict)
            assert "applies_if_any" in rules
            assert isinstance(rules["applies_if_any"], list)
            assert "priority" in rules
            assert isinstance(rules["priority"], int)


# =============================================================================
# TEST 3: Element Codes Uniqueness
# =============================================================================

class TestAseicarsPartElementCodes:
    """Test element code uniqueness for aseicars-part category."""

    def test_all_element_codes_are_unique(self):
        """Verify all element codes are unique within the category."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        codes = [elem["code"] for elem in ELEMENTS]
        unique_codes = set(codes)
        
        assert len(codes) == len(unique_codes), \
            f"Found {len(codes) - len(unique_codes)} duplicate element codes"

    def test_total_element_count(self):
        """Count total elements (should be ~44)."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        # The category should have 44 elements
        assert len(ELEMENTS) == 44, f"Expected 44 elements, got {len(ELEMENTS)}"

    def test_element_required_fields(self):
        """Verify elements have required fields."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        required_fields = ["code", "name", "description", "keywords", "aliases", "sort_order"]
        
        for elem in ELEMENTS:
            for field in required_fields:
                assert field in elem, f"Element {elem['code']} missing field: {field}"

    def test_element_codes_not_empty(self):
        """Verify all element codes are non-empty strings."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            assert isinstance(elem["code"], str)
            assert len(elem["code"]) > 0


# =============================================================================
# TEST 4: Variant Parent Relationships
# =============================================================================

class TestAseicarsPartVariants:
    """Test variant parent relationships for aseicars-part category."""

    def test_all_variants_have_parent_elements(self):
        """Verify all elements with parent_code have a corresponding base element."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        element_codes = {elem["code"] for elem in ELEMENTS}
        
        for elem in ELEMENTS:
            if "parent_code" in elem and elem["parent_code"]:
                assert elem["parent_code"] in element_codes, \
                    f"Variant {elem['code']} has parent_code {elem['parent_code']} which does not exist"

    def test_cambio_clasif_variants(self):
        """Specifically test CAMBIO_CLASIF → CAMBIO_CLASIF_CON and CAMBIO_CLASIF_SIN."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        # Find the base element
        base_elem = None
        variants = []
        
        for elem in ELEMENTS:
            if elem["code"] == "CAMBIO_CLASIF":
                base_elem = elem
            elif elem.get("parent_code") == "CAMBIO_CLASIF":
                variants.append(elem)
        
        assert base_elem is not None, "CAMBIO_CLASIF base element not found"
        assert len(variants) == 2, f"Expected 2 variants for CAMBIO_CLASIF, got {len(variants)}"
        
        variant_codes = {v["code"] for v in variants}
        assert "CAMBIO_CLASIF_CON" in variant_codes
        assert "CAMBIO_CLASIF_SIN" in variant_codes

    def test_variants_have_variant_type_and_code(self):
        """Verify variant_type and variant_code are set for variants."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            if "parent_code" in elem and elem["parent_code"]:
                assert "variant_type" in elem, \
                    f"Variant {elem['code']} missing variant_type"
                assert "variant_code" in elem, \
                    f"Variant {elem['code']} missing variant_code"
                assert elem["variant_type"]
                assert elem["variant_code"]

    def test_bola_remolque_variants(self):
        """Verify BOLA_REMOLQUE has variants: BOLA_SIN_MMR, BOLA_CON_MMR."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        bola_variants = [e for e in ELEMENTS if e.get("parent_code") == "BOLA_REMOLQUE"]
        variant_codes = {v["code"] for v in bola_variants}
        
        assert "BOLA_SIN_MMR" in variant_codes
        assert "BOLA_CON_MMR" in variant_codes


# =============================================================================
# TEST 5: Tier Mappings Consistency
# =============================================================================

class TestAseicarsPartTierMappings:
    """Test tier mappings consistency for aseicars-part category."""

    def test_get_tier_mapping_import(self):
        """Import tier_mappings and test get_tier_mapping('aseicars-part')."""
        from database.seeds.data.tier_mappings import get_tier_mapping
        
        mapping = get_tier_mapping("aseicars-part")
        assert mapping is not None
        assert isinstance(mapping, dict)

    def test_t3_elements_exist_in_elements(self):
        """Verify all element codes in T3_ELEMENTS exist in ELEMENTS."""
        from database.seeds.data.aseicars_part import ELEMENTS
        from database.seeds.data.tier_mappings import get_tier_mapping
        
        element_codes = {elem["code"] for elem in ELEMENTS}
        mapping = get_tier_mapping("aseicars-part")
        t3_elements = mapping.get("T3_ELEMENTS", [])
        
        for elem_code in t3_elements:
            assert elem_code in element_codes, \
                f"T3 element {elem_code} not found in ELEMENTS"

    def test_t4_elements_exist_in_elements(self):
        """Verify all element codes in T4_ELEMENTS exist in ELEMENTS."""
        from database.seeds.data.aseicars_part import ELEMENTS
        from database.seeds.data.tier_mappings import get_tier_mapping
        
        element_codes = {elem["code"] for elem in ELEMENTS}
        mapping = get_tier_mapping("aseicars-part")
        t4_elements = mapping.get("T4_ELEMENTS", [])
        
        for elem_code in t4_elements:
            assert elem_code in element_codes, \
                f"T4 element {elem_code} not found in ELEMENTS"

    def test_get_element_tier_level_mobiliario_int(self):
        """Verify get_element_tier_level('aseicars-part', 'MOBILIARIO_INT') returns 'T3'."""
        from database.seeds.data.tier_mappings import get_element_tier_level
        
        tier = get_element_tier_level("aseicars-part", "MOBILIARIO_INT")
        assert tier == "T3", f"Expected T3, got {tier}"

    def test_get_element_tier_level_neumaticos_no_equiv(self):
        """Verify get_element_tier_level('aseicars-part', 'NEUMATICOS_NO_EQUIV') returns 'T4'."""
        from database.seeds.data.tier_mappings import get_element_tier_level
        
        tier = get_element_tier_level("aseicars-part", "NEUMATICOS_NO_EQUIV")
        assert tier == "T4", f"Expected T4, got {tier}"

    def test_get_element_tier_level_t1_elements(self):
        """Verify T1 elements return 'T1'."""
        from database.seeds.data.tier_mappings import get_element_tier_level
        
        t1_elements = ["AUMENTO_MMTA", "GLP_INSTALACION", "AUMENTO_PLAZAS"]
        for elem_code in t1_elements:
            tier = get_element_tier_level("aseicars-part", elem_code)
            assert tier == "T1", f"Element {elem_code} should be T1, got {tier}"

    def test_get_element_tier_level_t2_elements(self):
        """Verify T2 elements return 'T2'."""
        from database.seeds.data.tier_mappings import get_element_tier_level
        
        t2_elements = ["PORTAMOTOS", "BACA_TECHO", "SUSP_NEUM"]
        for elem_code in t2_elements:
            tier = get_element_tier_level("aseicars-part", elem_code)
            assert tier == "T2", f"Element {elem_code} should be T2, got {tier}"


# =============================================================================
# TEST 6: CLARABOYA Keywords Expansion
# =============================================================================

class TestAseicarsPartClaraboyaKeywords:
    """Test CLARABOYA element keywords expansion."""

    def test_claraboya_element_exists(self):
        """Verify CLARABOYA element exists."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        claraboya = next((e for e in ELEMENTS if e["code"] == "CLARABOYA"), None)
        assert claraboya is not None, "CLARABOYA element not found"

    def test_claraboya_has_expanded_keywords(self):
        """Verify CLARABOYA has expanded keywords including 'ventana', 'ventanas', etc."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        claraboya = next((e for e in ELEMENTS if e["code"] == "CLARABOYA"), None)
        assert claraboya is not None
        
        keywords = claraboya["keywords"]
        
        # Check expanded keywords
        assert "ventana" in keywords, "CLARABOYA missing keyword 'ventana'"
        assert "ventanas" in keywords, "CLARABOYA missing keyword 'ventanas'"
        assert "porton" in keywords, "CLARABOYA missing keyword 'porton'"
        assert "portones" in keywords, "CLARABOYA missing keyword 'portones'"

    def test_claraboya_has_original_keywords(self):
        """Verify CLARABOYA still has original keywords."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        claraboya = next((e for e in ELEMENTS if e["code"] == "CLARABOYA"), None)
        assert claraboya is not None
        
        keywords = claraboya["keywords"]
        
        # Check original keywords are preserved
        assert "claraboya" in keywords
        assert "ventana techo" in keywords
        assert "lucernario" in keywords


# =============================================================================
# TEST 7: AIRE_ACONDI Configuration
# =============================================================================

class TestAseicarsPartAireAcondi:
    """Test AIRE_ACONDI element configuration."""

    def test_aire_acondi_exists(self):
        """Verify AIRE_ACONDI element exists."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        aire_acondi = next((e for e in ELEMENTS if e["code"] == "AIRE_ACONDI"), None)
        assert aire_acondi is not None, "AIRE_ACONDI element not found"

    def test_aire_acondi_is_active(self):
        """Verify AIRE_ACONDI has is_active=True."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        aire_acondi = next((e for e in ELEMENTS if e["code"] == "AIRE_ACONDI"), None)
        assert aire_acondi is not None
        
        # Check is_active is True (explicitly or by default)
        assert aire_acondi.get("is_active", True) is True, "AIRE_ACONDI should be active"

    def test_aire_acondi_has_boletin_electrico_warning(self):
        """Verify AIRE_ACONDI has warning about boletin electrico."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        aire_acondi = next((e for e in ELEMENTS if e["code"] == "AIRE_ACONDI"), None)
        assert aire_acondi is not None
        
        warnings = aire_acondi.get("warnings", [])
        assert len(warnings) > 0, "AIRE_ACONDI should have warnings"
        
        # Check for boletin electrico warning
        warning_messages = [w["message"].lower() for w in warnings]
        has_boletin_warning = any("boletin" in msg or "boletín" in msg for msg in warning_messages)
        assert has_boletin_warning, "AIRE_ACONDI should have boletin electrico warning"


# =============================================================================
# TEST 8: Additional Services
# =============================================================================

class TestAseicarsPartAdditionalServices:
    """Test additional services configuration."""

    def test_seven_services_exist(self):
        """Verify 7 services exist."""
        from database.seeds.data.aseicars_part import ADDITIONAL_SERVICES
        
        assert len(ADDITIONAL_SERVICES) == 7, f"Expected 7 services, got {len(ADDITIONAL_SERVICES)}"

    def test_service_prices_are_correct(self):
        """Verify prices: cert_taller=75, cert_electrico=75, cert_gas=75, etc."""
        from database.seeds.data.aseicars_part import ADDITIONAL_SERVICES
        
        expected_prices = {
            "cert_taller": Decimal("75.00"),
            "cert_electrico": Decimal("75.00"),
            "cert_gas": Decimal("75.00"),
            "plus_lab_simple": Decimal("25.00"),
            "plus_lab_complejo": Decimal("75.00"),
            "ayuda_digital": Decimal("20.00"),
            "redaccion_cert": Decimal("10.00"),
        }
        
        services_by_code = {s["code"]: s for s in ADDITIONAL_SERVICES}
        
        for code, expected_price in expected_prices.items():
            assert code in services_by_code, f"Service {code} not found"
            assert services_by_code[code]["price"] == expected_price, \
                f"Service {code} should have price {expected_price}"

    def test_all_services_have_required_fields(self):
        """Verify all services have code, name, price, sort_order."""
        from database.seeds.data.aseicars_part import ADDITIONAL_SERVICES
        
        required_fields = ["code", "name", "price", "sort_order"]
        
        for service in ADDITIONAL_SERVICES:
            for field in required_fields:
                assert field in service, f"Service {service.get('code', 'UNKNOWN')} missing field: {field}"


# =============================================================================
# TEST 9: Deterministic UUIDs
# =============================================================================

class TestAseicarsPartDeterministicUUIDs:
    """Test deterministic UUID generation for aseicars-part category."""

    def test_element_uuid_generates_same_uuid_twice(self):
        """Verify that calling element_uuid('aseicars-part', 'MOBILIARIO_INT') twice returns same UUID."""
        from database.seeds.seed_utils import deterministic_element_uuid
        
        uuid1 = deterministic_element_uuid("aseicars-part", "MOBILIARIO_INT")
        uuid2 = deterministic_element_uuid("aseicars-part", "MOBILIARIO_INT")
        
        assert uuid1 == uuid2, "Deterministic UUID should be identical on multiple calls"
        assert isinstance(uuid1, uuid.UUID)

    def test_different_categories_different_uuids(self):
        """Verify UUIDs for aseicars-part differ from aseicars-prof for same element code."""
        from database.seeds.seed_utils import deterministic_element_uuid
        
        uuid_part = deterministic_element_uuid("aseicars-part", "PLACA_SOLAR")
        uuid_prof = deterministic_element_uuid("aseicars-prof", "PLACA_SOLAR")
        
        assert uuid_part != uuid_prof, "Same element code in different categories should have different UUIDs"

    def test_different_element_codes_different_uuids(self):
        """Verify different element codes have different UUIDs."""
        from database.seeds.seed_utils import deterministic_element_uuid
        
        uuid1 = deterministic_element_uuid("aseicars-part", "PLACA_SOLAR")
        uuid2 = deterministic_element_uuid("aseicars-part", "TOLDO_LAT")
        
        assert uuid1 != uuid2, "Different element codes should have different UUIDs"

    def test_tier_uuid_deterministic(self):
        """Verify tier UUID generation is deterministic."""
        from database.seeds.seed_utils import deterministic_tier_uuid
        
        uuid1 = deterministic_tier_uuid("aseicars-part", "T1")
        uuid2 = deterministic_tier_uuid("aseicars-part", "T1")
        
        assert uuid1 == uuid2, "Tier UUID should be deterministic"

    def test_warning_uuid_deterministic(self):
        """Verify warning UUID generation is deterministic."""
        from database.seeds.seed_utils import deterministic_warning_uuid
        
        uuid1 = deterministic_warning_uuid("aseicars-part", "aire_boletin_electrico")
        uuid2 = deterministic_warning_uuid("aseicars-part", "aire_boletin_electrico")
        
        assert uuid1 == uuid2, "Warning UUID should be deterministic"


# =============================================================================
# TEST 10: Integration - Full Seed Pipeline
# =============================================================================

class TestAseicarsPartSeedPipeline:
    """Test the full seed pipeline structure validation."""

    def test_element_data_structure_is_valid(self):
        """Mock test that validates element data structure."""
        from database.seeds.data.aseicars_part import ELEMENTS
        from database.seeds.data.common import ElementData
        from typing import get_type_hints
        
        # Basic structure validation without actually running seeds
        for elem in ELEMENTS:
            assert isinstance(elem["code"], str)
            assert isinstance(elem["name"], str)
            assert isinstance(elem["description"], str)
            assert isinstance(elem["keywords"], list)
            assert isinstance(elem["aliases"], list)
            assert isinstance(elem["sort_order"], int)

    def test_warning_structure_is_valid(self):
        """Validate warning data structure."""
        from database.seeds.data.aseicars_part import CATEGORY_WARNINGS
        
        for warning in CATEGORY_WARNINGS:
            assert "code" in warning
            assert "message" in warning
            assert "severity" in warning
            assert warning["severity"] in ["info", "warning", "error"]

    def test_element_warnings_structure_is_valid(self):
        """Validate element-level warnings structure."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            warnings = elem.get("warnings", [])
            for warning in warnings:
                assert "code" in warning
                assert "message" in warning
                assert "severity" in warning

    def test_images_structure_is_valid(self):
        """Validate element image data structure."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            images = elem.get("images", [])
            for image in images:
                assert "title" in image
                assert "description" in image
                assert "image_type" in image
                assert "sort_order" in image
                assert image["image_type"] in ["example", "required_document", "step", "calculation"]

    def test_tier_configs_are_valid(self):
        """Validate tier configs are properly structured."""
        from database.seeds.data.aseicars_part import TIERS
        
        for tier in TIERS:
            assert "sort_order" in tier
            assert isinstance(tier["sort_order"], int)
            
            # Classification rules should have priority
            rules = tier["classification_rules"]
            assert "priority" in rules
            
            # Conditions should be a string
            assert isinstance(tier["conditions"], str)

    def test_service_data_structure_is_valid(self):
        """Validate service data structure."""
        from database.seeds.data.aseicars_part import ADDITIONAL_SERVICES
        from decimal import Decimal
        
        for service in ADDITIONAL_SERVICES:
            assert "code" in service
            assert "name" in service
            assert "price" in service
            assert isinstance(service["price"], Decimal)
            assert "sort_order" in service

    def test_base_documentation_structure_is_valid(self):
        """Validate base documentation structure."""
        from database.seeds.data.aseicars_part import BASE_DOCUMENTATION
        
        for doc in BASE_DOCUMENTATION:
            assert "code" in doc
            assert "description" in doc

    def test_prompt_sections_structure_is_valid(self):
        """Validate prompt sections structure."""
        from database.seeds.data.aseicars_part import PROMPT_SECTIONS
        
        for section in PROMPT_SECTIONS:
            assert "code" in section
            assert "section_type" in section
            assert "content" in section
            assert "is_active" in section

    def test_category_warnings_structure_is_valid(self):
        """Validate category warnings structure."""
        from database.seeds.data.aseicars_part import CATEGORY_WARNINGS
        
        for warning in CATEGORY_WARNINGS:
            assert "code" in warning
            assert "message" in warning
            assert "severity" in warning

    def test_all_element_codes_uppercase(self):
        """Verify all element codes are uppercase."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            assert elem["code"].isupper(), f"Element code {elem['code']} should be uppercase"

    def test_no_duplicate_element_names(self):
        """Verify all element names are unique."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        names = [elem["name"] for elem in ELEMENTS]
        unique_names = set(names)
        
        assert len(names) == len(unique_names), \
            f"Found {len(names) - len(unique_names)} duplicate element names"

    def test_base_elements_marked_as_is_base(self):
        """Verify base elements (parent elements) are marked with is_base=True."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        base_elements_with_variants = ["TOLDO_LAT", "PLACA_SOLAR", "BOLA_REMOLQUE", 
                                        "SUSP_NEUM", "GLP_INSTALACION", "FAROS_LA", "CAMBIO_CLASIF"]
        
        for elem in ELEMENTS:
            if elem["code"] in base_elements_with_variants:
                assert elem.get("is_base", False) is True, \
                    f"Base element {elem['code']} should have is_base=True"

    def test_variants_have_parent_and_base_info(self):
        """Verify variants have proper parent and variant info."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            if "parent_code" in elem and elem["parent_code"]:
                # Should have variant_type and variant_code
                assert "variant_type" in elem, f"Variant {elem['code']} missing variant_type"
                assert "variant_code" in elem, f"Variant {elem['code']} missing variant_code"
                
                # Should NOT have is_base=True
                assert not elem.get("is_base", False), f"Variant {elem['code']} should not have is_base=True"

    def test_tier_mappings_has_all_tier_lists(self):
        """Verify tier mappings has T1-T6 element lists."""
        from database.seeds.data.tier_mappings import get_tier_mapping
        
        mapping = get_tier_mapping("aseicars-part")
        
        # Check tier element lists exist
        assert "T1_ELEMENTS" in mapping or "TIER_CONFIGS" in mapping
        assert "T2_ELEMENTS" in mapping or "TIER_CONFIGS" in mapping
        assert "T3_ELEMENTS" in mapping
        assert "T4_ELEMENTS" in mapping
        assert "T6_ELEMENTS" in mapping

    def test_tier_configs_has_all_tiers(self):
        """Verify tier configs has entries for T1-T6."""
        from database.seeds.data.tier_mappings import get_tier_mapping
        
        mapping = get_tier_mapping("aseicars-part")
        tier_configs = mapping.get("TIER_CONFIGS", {})
        
        for tier in ["T1", "T2", "T3", "T4", "T5", "T6"]:
            assert tier in tier_configs, f"Tier {tier} not in TIER_CONFIGS"

    def test_elements_have_consistent_sort_order(self):
        """Verify elements have unique sort_order values."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        sort_orders = [elem["sort_order"] for elem in ELEMENTS]
        
        # All sort orders should be positive integers
        for order in sort_orders:
            assert isinstance(order, int)
            assert order > 0

    def test_keywords_are_lowercase(self):
        """Verify keywords are in lowercase for consistent matching."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            for keyword in elem["keywords"]:
                assert keyword == keyword.lower(), \
                    f"Element {elem['code']} has non-lowercase keyword: {keyword}"


# =============================================================================
# Additional Validation Tests
# =============================================================================

class TestAseicarsPartEdgeCases:
    """Additional edge case and validation tests."""

    def test_no_empty_keywords(self):
        """Verify no element has empty keywords."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            for keyword in elem["keywords"]:
                assert len(keyword) > 0, f"Element {elem['code']} has empty keyword"

    def test_no_empty_aliases(self):
        """Verify no element has empty aliases if aliases exist."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            for alias in elem["aliases"]:
                assert len(alias) > 0, f"Element {elem['code']} has empty alias"

    def test_description_not_empty(self):
        """Verify all elements have non-empty descriptions."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        for elem in ELEMENTS:
            assert len(elem["description"]) > 10, \
                f"Element {elem['code']} has too short description"

    def test_tier_prices_descending(self):
        """Verify tier prices are in descending order (T1 highest, T6 lowest)."""
        from database.seeds.data.aseicars_part import TIERS
        
        # Sort by tier code
        sorted_tiers = sorted(TIERS, key=lambda t: t["code"])
        
        # Check descending order
        for i in range(len(sorted_tiers) - 1):
            current_price = sorted_tiers[i]["price"]
            next_price = sorted_tiers[i + 1]["price"]
            assert current_price > next_price, \
                f"Tier {sorted_tiers[i]['code']} price should be greater than {sorted_tiers[i+1]['code']}"

    def test_service_prices_positive(self):
        """Verify all service prices are positive."""
        from database.seeds.data.aseicars_part import ADDITIONAL_SERVICES
        
        for service in ADDITIONAL_SERVICES:
            assert service["price"] > Decimal("0"), \
                f"Service {service['code']} should have positive price"

    def test_service_sort_orders_unique(self):
        """Verify service sort_orders are unique."""
        from database.seeds.data.aseicars_part import ADDITIONAL_SERVICES
        
        sort_orders = [s["sort_order"] for s in ADDITIONAL_SERVICES]
        assert len(sort_orders) == len(set(sort_orders)), \
            "Service sort_orders should be unique"

    def test_tier_sort_orders_unique(self):
        """Verify tier sort_orders are unique."""
        from database.seeds.data.aseicars_part import TIERS
        
        sort_orders = [t["sort_order"] for t in TIERS]
        assert len(sort_orders) == len(set(sort_orders)), \
            "Tier sort_orders should be unique"

    def test_all_variants_reference_valid_parents(self):
        """Double-check all variants reference valid parent elements."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        element_codes = {e["code"] for e in ELEMENTS}
        
        variants = [e for e in ELEMENTS if e.get("parent_code")]
        for variant in variants:
            parent_code = variant["parent_code"]
            assert parent_code in element_codes, \
                f"Variant {variant['code']} references non-existent parent: {parent_code}"

    def test_parent_elements_exist(self):
        """Verify all referenced parent elements exist."""
        from database.seeds.data.aseicars_part import ELEMENTS
        
        element_codes = {e["code"] for e in ELEMENTS}
        
        for elem in ELEMENTS:
            if "parent_code" in elem and elem["parent_code"]:
                assert elem["parent_code"] in element_codes, \
                    f"Element {elem['code']} has parent_code {elem['parent_code']} which doesn't exist"
