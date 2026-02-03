#!/usr/bin/env python3
"""
MSI-a Session Parameter Audit Script

Audits all API route files to find functions that use `session` but don't
have `session: AsyncSession = Depends(get_session)` as a parameter.

Usage:
    python scripts/audit_session_params.py

Returns:
    Exit code 0 if all files pass
    Exit code 1 if any issues found
"""

import re
import sys
from pathlib import Path
from typing import NamedTuple


class SessionIssue(NamedTuple):
    """Represents a missing session parameter issue."""
    file: str
    line: int
    function: str
    first_usage_line: int
    first_usage: str


def audit_file(file_path: Path) -> list[SessionIssue]:
    """
    Audit a single file for missing session parameters.
    
    Returns list of SessionIssue objects.
    """
    issues = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    current_function = None
    function_start_line = 0
    
    for i, line in enumerate(lines, 1):
        # Detect async function definitions
        if re.match(r'^\s*async def (\w+)', line):
            match = re.match(r'^\s*async def (\w+)', line)
            current_function = match.group(1)
            function_start_line = i
            
            # Check if function has session parameter (look ahead 30 lines)
            # Collect all signature lines first
            signature_lines = []
            for j in range(i, min(i + 30, len(lines))):
                signature_lines.append(lines[j])
                if ')' in lines[j] and (':' in lines[j] or '->' in lines[j]):
                    # End of function signature
                    break
            
            # Check full signature for session parameter
            full_signature = ''.join(signature_lines)
            has_session_param = ('session' in full_signature and 
                                'AsyncSession' in full_signature and 
                                'Depends' in full_signature and
                                'get_session' in full_signature)
            
            # If no session parameter, check if function uses session
            if not has_session_param and current_function:
                # Look ahead for session usage (up to 150 lines)
                for j in range(i, min(i + 150, len(lines))):
                    # Stop at next function definition
                    if j != i and re.match(r'^\s*async def ', lines[j]):
                        break
                    
                    # Check for session usage
                    if re.search(r'\bsession\.(execute|add|commit|get|scalar|refresh|delete|query)\b', lines[j]):
                        usage = lines[j].strip()
                        issues.append(SessionIssue(
                            file=str(file_path),
                            line=function_start_line,
                            function=current_function,
                            first_usage_line=j,
                            first_usage=usage
                        ))
                        break
    
    return issues


def audit_all_routes() -> dict[str, list[SessionIssue]]:
    """
    Audit all route files in api/routes/
    
    Returns dict mapping filename to list of issues.
    """
    routes_dir = Path('api/routes')
    results = {}
    
    if not routes_dir.exists():
        print(f"❌ Directory not found: {routes_dir}")
        sys.exit(1)
    
    for route_file in sorted(routes_dir.glob('*.py')):
        if route_file.name == '__init__.py':
            continue
        
        issues = audit_file(route_file)
        if issues:
            results[route_file.name] = issues
    
    return results


def print_report(results: dict[str, list[SessionIssue]]) -> None:
    """Print audit report to stdout."""
    
    if not results:
        print("✅ **AUDIT PASSED** - All route files are clean!")
        print()
        print("No functions found that use session without having it as a parameter.")
        return
    
    # Count total issues
    total_issues = sum(len(issues) for issues in results.values())
    
    print("❌ **AUDIT FAILED** - Session parameter issues found!")
    print()
    print(f"**Summary**: {len(results)} files with issues, {total_issues} functions need fixing")
    print("=" * 80)
    print()
    
    for filename, issues in results.items():
        print(f"📁 **{filename}** ({len(issues)} issue{'s' if len(issues) > 1 else ''})")
        print()
        
        for issue in issues:
            print(f"  ❌ Line {issue.line}: `{issue.function}()`")
            print(f"     Missing: `session: AsyncSession = Depends(get_session)`")
            print(f"     First usage at line {issue.first_usage_line}:")
            print(f"       {issue.first_usage}")
            print()
    
    print("=" * 80)
    print()
    print("**Fix Required**: Add `session: AsyncSession = Depends(get_session)` parameter")
    print("to all listed functions (before closing parenthesis of function signature).")
    print()


def main():
    """Main entry point."""
    print("🔍 MSI-a Session Parameter Audit")
    print("=" * 80)
    print()
    
    results = audit_all_routes()
    print_report(results)
    
    # Exit with error code if issues found
    if results:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
