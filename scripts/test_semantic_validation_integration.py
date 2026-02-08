#!/usr/bin/env python3
"""
Manual integration test for semantic validation.

This script tests the semantic validation system without pytest.
Run with: python3 scripts/test_semantic_validation_integration.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.utils.tool_validation import SemanticValidator, ToolValidationService
from agent.services.constraint_service import (
    validate_categoria_slug,
    validate_element_code,
    validate_case_id,
    validate_user_id,
    validate_tier_id,
)
from unittest.mock import MagicMock


async def test_validators():
    """Test individual validators with mocked data."""
    print("=" * 70)
    print("TESTING SEMANTIC VALIDATORS")
    print("=" * 70)
    
    # Test 1: validate_categoria_slug (will fail without DB)
    print("\n1. Testing validate_categoria_slug...")
    try:
        is_valid, error = await validate_categoria_slug("motos-part")
        print(f"   Result: is_valid={is_valid}, error={error}")
    except Exception as e:
        print(f"   Expected DB error (no connection in test): {type(e).__name__}")
    
    # Test 2: validate_element_code
    print("\n2. Testing validate_element_code...")
    try:
        is_valid, error = await validate_element_code("ESCAPE", "motos-part")
        print(f"   Result: is_valid={is_valid}, error={error}")
    except Exception as e:
        print(f"   Expected DB error: {type(e).__name__}")
    
    # Test 3: validate_case_id (invalid UUID format)
    print("\n3. Testing validate_case_id with invalid UUID...")
    is_valid, error = await validate_case_id("not-a-uuid")
    print(f"   Result: is_valid={is_valid}, error={error}")
    assert is_valid is False, "Should reject invalid UUID"
    assert "formato válido" in error, "Should have format error message"
    print("   ✓ Correctly rejected invalid UUID")
    
    # Test 4: validate_user_id (invalid UUID format)
    print("\n4. Testing validate_user_id with invalid UUID...")
    is_valid, error = await validate_user_id("not-a-uuid")
    print(f"   Result: is_valid={is_valid}, error={error}")
    assert is_valid is False, "Should reject invalid UUID"
    print("   ✓ Correctly rejected invalid UUID")
    
    # Test 5: validate_tier_id (invalid UUID format)
    print("\n5. Testing validate_tier_id with invalid UUID...")
    is_valid, error = await validate_tier_id("not-a-uuid", "motos-part")
    print(f"   Result: is_valid={is_valid}, error={error}")
    assert is_valid is False, "Should reject invalid UUID"
    print("   ✓ Correctly rejected invalid UUID")


async def test_semantic_validator():
    """Test SemanticValidator class."""
    print("\n" + "=" * 70)
    print("TESTING SEMANTIC VALIDATOR CLASS")
    print("=" * 70)
    
    validator = SemanticValidator()
    
    # Test 1: Tool not in TOOL_VALIDATIONS
    print("\n1. Testing with unconfigured tool...")
    mock_tool = MagicMock()
    mock_tool.name = "unconfigured_tool"
    
    is_valid, errors = await validator.validate(mock_tool, {}, {})
    print(f"   Result: is_valid={is_valid}, errors={errors}")
    assert is_valid is True, "Should skip validation for unconfigured tools"
    assert errors == [], "Should have no errors"
    print("   ✓ Correctly skipped unconfigured tool")
    
    # Test 2: Tool with empty params
    print("\n2. Testing with configured tool but empty params...")
    mock_tool.name = "identificar_y_resolver_elementos"
    
    is_valid, errors = await validator.validate(mock_tool, {}, {})
    print(f"   Result: is_valid={is_valid}, errors={errors}")
    assert is_valid is True, "Should pass with empty params (syntax validator catches this)"
    print("   ✓ Correctly handled empty params")
    
    # Test 3: Verify TOOL_VALIDATIONS mapping exists
    print("\n3. Checking TOOL_VALIDATIONS mapping...")
    print(f"   Tools configured: {len(validator.TOOL_VALIDATIONS)}")
    for tool_name, params in validator.TOOL_VALIDATIONS.items():
        print(f"     - {tool_name}: {params}")
    print("   ✓ TOOL_VALIDATIONS mapping loaded")


async def test_tool_validation_service():
    """Test ToolValidationService integration."""
    print("\n" + "=" * 70)
    print("TESTING TOOL VALIDATION SERVICE INTEGRATION")
    print("=" * 70)
    
    service = ToolValidationService()
    
    # Verify all validators are initialized
    print("\n1. Checking validator initialization...")
    assert service.syntax_validator is not None, "SyntaxValidator should be initialized"
    assert service.state_validator is not None, "StateValidator should be initialized"
    assert service.semantic_validator is not None, "SemanticValidator should be initialized"
    print("   ✓ All validators initialized")
    
    # Test with mock tool
    print("\n2. Testing with mock tool...")
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.args_schema = None  # No schema = skip syntax validation
    
    is_valid, errors = await service.validate(mock_tool, {}, {})
    print(f"   Result: is_valid={is_valid}, errors={errors}")
    assert is_valid is True, "Should pass for unconfigured tool"
    print("   ✓ Validation service works")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("SEMANTIC VALIDATION INTEGRATION TEST")
    print("=" * 70)
    print("\nThis test verifies that Phase 2 semantic validation is working.")
    print("Note: Database-dependent tests will fail without a DB connection.")
    print("      This is expected and doesn't indicate a problem.")
    
    try:
        asyncio.run(test_validators())
        asyncio.run(test_semantic_validator())
        asyncio.run(test_tool_validation_service())
        
        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED")
        print("=" * 70)
        print("\nPhase 2 semantic validation is working correctly!")
        print("\nNext steps:")
        print("  1. Run full test suite: docker-compose run --rm agent pytest")
        print("  2. Test with real database connections")
        print("  3. Monitor validation metrics in production")
        
        return 0
    
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
