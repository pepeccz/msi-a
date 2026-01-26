#!/usr/bin/env python3
"""
Generate SQL INSERT statements for element_required_fields table.

This script reads the required_fields definitions from motos_part.py seed data
and generates SQL to insert them directly into the database.

Usage:
    python scripts/generate_required_fields_sql.py > scripts/insert_required_fields.sql
"""

import json
import sys
from decimal import Decimal
from typing import Any

# Manually parse the seed file to extract required_fields
# We need to do this without importing because dependencies may not be available

def parse_elements_from_file():
    """Parse ELEMENTS list from motos_part.py."""
    with open('database/seeds/data/motos_part.py', 'r') as f:
        content = f.read()
    
    # Find the ELEMENTS list
    start = content.find('ELEMENTS: list[ElementData] = [')
    if start == -1:
        raise ValueError("Could not find ELEMENTS list")
    
    # Find the closing bracket
    bracket_count = 0
    end = start
    in_string = False
    string_char = None
    
    for i, char in enumerate(content[start:], start):
        if char in ('"', "'") and (i == start or content[i-1] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
        
        if not in_string:
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    end = i + 1
                    break
    
    elements_str = content[start:end]
    
    # Extract just the list part
    list_start = elements_str.find('[')
    elements_list_str = elements_str[list_start:]
    
    # Parse as Python literal (safely via ast)
    import ast
    
    # We need to handle Decimal values - replace them with strings temporarily
    elements_list_str = elements_list_str.replace('Decimal(', 'str(')
    
    try:
        elements = ast.literal_eval(elements_list_str)
        return elements
    except Exception as e:
        print(f"Error parsing elements: {e}", file=sys.stderr)
        return []


def generate_sql():
    """Generate SQL INSERT statements."""
    
    # Element code to ID mapping - these are the actual IDs from production DB
    # You need to get these from: 
    # docker-compose exec -T postgres psql -U msia msia_db -c "SELECT id, code FROM elements WHERE category_id = '6a57c85d-b915-5070-957b-1505e20c7474';"
    
    print("""-- ============================================================================
-- SQL Script to insert element_required_fields for Motocicletas category
-- Generated from motos_part.py seed data
-- ============================================================================
-- 
-- INSTRUCTIONS:
-- 1. First, get the element IDs from the database:
--    docker-compose exec -T postgres psql -U msia msia_db -c "SELECT id, code FROM elements WHERE category_id = '6a57c85d-b915-5070-957b-1505e20c7474' ORDER BY code;"
-- 
-- 2. Update the element_ids CTE below with the actual UUIDs
-- 
-- 3. Run this script:
--    docker-compose exec -T postgres psql -U msia msia_db < scripts/insert_required_fields.sql
-- ============================================================================

-- Clean up existing data (optional - uncomment if needed)
-- DELETE FROM element_required_fields WHERE element_id IN (
--     SELECT id FROM elements WHERE category_id = '6a57c85d-b915-5070-957b-1505e20c7474'
-- );

-- Use a CTE to map element codes to IDs
WITH element_ids AS (
    SELECT id, code FROM elements 
    WHERE category_id = '6a57c85d-b915-5070-957b-1505e20c7474'
)
INSERT INTO element_required_fields (
    id,
    element_id,
    field_key,
    field_label,
    field_type,
    options,
    is_required,
    validation_rules,
    example_value,
    llm_instruction,
    sort_order,
    condition_field_id,
    condition_operator,
    condition_value,
    created_at,
    updated_at
)
SELECT 
    gen_random_uuid(),
    e.id,
    v.field_key,
    v.field_label,
    v.field_type,
    v.options,
    COALESCE(v.is_required, true),
    v.validation_rules,
    v.example_value,
    v.llm_instruction,
    v.sort_order,
    NULL, -- condition_field_id will be updated in a second pass
    v.condition_operator,
    v.condition_value,
    NOW(),
    NOW()
FROM element_ids e
CROSS JOIN LATERAL (
    VALUES
""")
    
    # Parse elements
    elements = parse_elements_from_file()
    
    values = []
    conditional_fields = []  # Track fields that need condition_field_id updates
    
    for element in elements:
        if 'required_fields' not in element:
            continue
            
        code = element['code']
        
        for field in element['required_fields']:
            field_key = field['field_key']
            field_label = field['field_label']
            field_type = field['field_type']
            options = json.dumps(field.get('options')) if field.get('options') else 'NULL'
            is_required = field.get('is_required', True)
            validation_rules = json.dumps(field.get('validation_rules')) if field.get('validation_rules') else 'NULL'
            example_value = field.get('example_value', '')
            llm_instruction = field.get('llm_instruction', '')
            sort_order = field['sort_order']
            condition_field_key = field.get('condition_field_key')
            condition_operator = field.get('condition_operator')
            condition_value = field.get('condition_value')
            
            # Escape single quotes
            field_label = field_label.replace("'", "''")
            example_value = example_value.replace("'", "''") if example_value else ''
            llm_instruction = llm_instruction.replace("'", "''") if llm_instruction else ''
            
            if options != 'NULL':
                options = f"'{options}'"
            if validation_rules != 'NULL':
                validation_rules = f"'{validation_rules}'"
            
            value = f"""        ('{code}', '{field_key}', '{field_label}', '{field_type}', {options}, {str(is_required).lower()}, {validation_rules}, '{example_value}', '{llm_instruction}', {sort_order}, {f"'{condition_operator}'" if condition_operator else 'NULL'}, {f"'{condition_value}'" if condition_value else 'NULL'})"""
            values.append(value)
            
            if condition_field_key:
                conditional_fields.append({
                    'element_code': code,
                    'field_key': field_key,
                    'condition_field_key': condition_field_key
                })
    
    print(',\n'.join(values))
    
    print("""
) AS v(element_code, field_key, field_label, field_type, options, is_required, validation_rules, example_value, llm_instruction, sort_order, condition_operator, condition_value)
WHERE e.code = v.element_code
ON CONFLICT DO NOTHING;

-- ============================================================================
-- Update condition_field_id for conditional fields
-- ============================================================================
""")
    
    # Generate UPDATE statements for conditional fields
    for cf in conditional_fields:
        print(f"""
UPDATE element_required_fields erf
SET condition_field_id = parent.id
FROM element_required_fields parent
JOIN elements e ON parent.element_id = e.id
WHERE erf.element_id = e.id
  AND e.code = '{cf['element_code']}'
  AND erf.field_key = '{cf['field_key']}'
  AND parent.field_key = '{cf['condition_field_key']}';
""")
    
    print("""
-- ============================================================================
-- Verify insertion
-- ============================================================================
SELECT 
    e.code as element_code,
    COUNT(erf.id) as field_count
FROM elements e
LEFT JOIN element_required_fields erf ON e.id = erf.element_id
WHERE e.category_id = '6a57c85d-b915-5070-957b-1505e20c7474'
  AND erf.id IS NOT NULL
GROUP BY e.code
ORDER BY e.code;
""")


if __name__ == '__main__':
    generate_sql()
