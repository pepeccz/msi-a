#!/usr/bin/env python3
"""
Verification script for REFACTOR-001 Phase 1.
Checks that removed flags don't exist in code.
"""

import re
import sys
from pathlib import Path

def search_flag_usage(flag_name: str, search_path: Path) -> list[tuple[str, int, str]]:
    """Search for flag usage in Python files."""
    matches = []
    
    for py_file in search_path.rglob("*.py"):
        # Skip __pycache__
        if "__pycache__" in str(py_file):
            continue
            
        try:
            content = py_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                # Skip comment-only lines
                if line.strip().startswith('#'):
                    continue
                    
                # Check if flag is used (not in comments)
                code_part = line.split('#')[0]  # Remove comments
                if flag_name in code_part:
                    matches.append((str(py_file), line_num, line.strip()))
        except Exception as e:
            print(f"Warning: Could not read {py_file}: {e}", file=sys.stderr)
    
    return matches

def main():
    project_root = Path(__file__).parent
    agent_path = project_root / "agent"
    
    # Flags that should be REMOVED
    removed_flags = [
        "opcion_seleccionada",
        "precio_calculado", 
        "variante_resuelta"
    ]
    
    # Flags that should REMAIN
    kept_flags = [
        "gateway_attempts"
    ]
    
    print("=" * 80)
    print("REFACTOR-001 Phase 1 Verification")
    print("=" * 80)
    print()
    
    all_passed = True
    
    # Check removed flags
    print("1. Checking REMOVED flags (should have 0 references)...")
    print()
    for flag in removed_flags:
        matches = search_flag_usage(flag, agent_path)
        if matches:
            print(f"❌ FAIL: Found {len(matches)} reference(s) to '{flag}':")
            for file_path, line_num, line in matches[:5]:  # Show first 5
                print(f"   {file_path}:{line_num}")
                print(f"      {line}")
            all_passed = False
        else:
            print(f"✅ PASS: '{flag}' - 0 references found")
    
    print()
    print("2. Checking KEPT flags (should still exist)...")
    print()
    for flag in kept_flags:
        matches = search_flag_usage(flag, agent_path)
        if not matches:
            print(f"❌ FAIL: '{flag}' was accidentally removed! Expected references.")
            all_passed = False
        else:
            print(f"✅ PASS: '{flag}' - {len(matches)} reference(s) found (as expected)")
    
    print()
    print("=" * 80)
    
    if all_passed:
        print("✅ ALL CHECKS PASSED - Phase 1 Complete!")
        print()
        print("Summary:")
        print("- opcion_seleccionada: REMOVED (was write-only dead code)")
        print("- precio_calculado: REMOVED (redundant with tarifa_calculada)")
        print("- variante_resuelta: REMOVED (derived from pending_variants)")
        print("- gateway_attempts: KEPT (actively used in evaluacion_gateway)")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Review output above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
