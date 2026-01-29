"""
MSI Automotive - Element Required Fields Service.

Provides functionality for managing element-specific required fields
during case data collection. Handles field retrieval, validation,
and conditional field evaluation.
"""

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import get_async_session
from database.models import Element, ElementRequiredField, CaseElementData

logger = logging.getLogger(__name__)


class ElementRequiredFieldsService:
    """
    Service for managing element required fields.

    Provides:
    - Field retrieval for elements
    - Field value validation
    - Conditional field evaluation
    - Progress tracking for data collection
    """

    async def get_fields_for_element(
        self,
        element_id: str,
        is_active: bool = True,
    ) -> list[ElementRequiredField]:
        """
        Get all required fields for an element, ordered by sort_order.

        Args:
            element_id: UUID of the element
            is_active: Filter by active status (default True)

        Returns:
            List of ElementRequiredField objects
        """
        async with get_async_session() as session:
            query = (
                select(ElementRequiredField)
                .where(ElementRequiredField.element_id == uuid.UUID(element_id))
            )

            if is_active:
                query = query.where(ElementRequiredField.is_active == True)  # noqa: E712

            query = query.order_by(ElementRequiredField.sort_order)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_fields_for_element_code(
        self,
        element_code: str,
        category_id: str,
    ) -> list[ElementRequiredField]:
        """
        Get all required fields for an element by code and category.

        Args:
            element_code: Element code (e.g., 'SUSP_TRAS')
            category_id: UUID of the vehicle category

        Returns:
            List of ElementRequiredField objects
        """
        async with get_async_session() as session:
            # First get the element
            element_result = await session.execute(
                select(Element)
                .where(Element.code == element_code)
                .where(Element.category_id == uuid.UUID(category_id))
                .where(Element.is_active == True)  # noqa: E712
            )
            element = element_result.scalar_one_or_none()

            if not element:
                return []

            # Then get the fields
            fields_result = await session.execute(
                select(ElementRequiredField)
                .where(ElementRequiredField.element_id == element.id)
                .where(ElementRequiredField.is_active == True)  # noqa: E712
                .order_by(ElementRequiredField.sort_order)
            )
            return list(fields_result.scalars().all())

    def evaluate_field_condition(
        self,
        field: ElementRequiredField,
        collected_values: dict[str, Any],
        all_fields: list[ElementRequiredField],
    ) -> bool:
        """
        Evaluate if a conditional field should be shown based on collected values.

        Args:
            field: The field to evaluate
            collected_values: Already collected field values
            all_fields: All fields for the element (for condition lookup)

        Returns:
            True if field should be shown, False otherwise
        """
        if not field.condition_field_id:
            return True  # No condition, always show

        # Find the condition field
        condition_field = next(
            (f for f in all_fields if str(f.id) == str(field.condition_field_id)),
            None,
        )
        if not condition_field:
            return True  # Condition field not found, show by default

        condition_value = collected_values.get(condition_field.field_key)
        operator = field.condition_operator or "equals"
        expected = field.condition_value

        if operator == "equals":
            if condition_value is None:
                return False
            return str(condition_value).lower() == str(expected).lower()
        elif operator == "not_equals":
            if condition_value is None:
                return True
            return str(condition_value).lower() != str(expected).lower()
        elif operator == "exists":
            return condition_value is not None and condition_value != ""
        elif operator == "not_exists":
            return condition_value is None or condition_value == ""

        return True

    def validate_field_value(
        self,
        value: Any,
        field: ElementRequiredField,
    ) -> tuple[bool, str | None]:
        """
        Validate a field value against its type and validation rules.

        Args:
            value: The value to validate
            field: The field definition

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Required check
        if field.is_required and (value is None or value == ""):
            return False, f"El campo '{field.field_label}' es obligatorio"

        # Skip validation if empty and not required
        if value is None or value == "":
            return True, None

        # Type validation
        if field.field_type == "number":
            try:
                num_val = float(value)
                rules = field.validation_rules or {}
                # Support both "min"/"max" and "min_value"/"max_value" keys (DB uses latter)
                min_val = rules.get("min") if "min" in rules else rules.get("min_value")
                max_val = rules.get("max") if "max" in rules else rules.get("max_value")
                if min_val is not None and num_val < min_val:
                    return False, f"El valor debe ser mayor o igual a {min_val}"
                if max_val is not None and num_val > max_val:
                    return False, f"El valor debe ser menor o igual a {max_val}"
            except (ValueError, TypeError):
                return False, f"'{value}' no es un número válido"

        elif field.field_type == "boolean":
            valid_values = ("true", "false", "sí", "si", "no", "1", "0")
            if str(value).lower() not in valid_values:
                return False, "El valor debe ser Sí o No"

        elif field.field_type == "select":
            if field.options:
                # Case-insensitive matching for select options
                options_lower = {o.lower(): o for o in field.options}
                value_lower = str(value).lower()
                if value_lower not in options_lower:
                    return False, f"Valor no válido. Opciones: {', '.join(field.options)}"

        elif field.field_type == "text":
            rules = field.validation_rules or {}
            str_val = str(value)
            if "min_length" in rules and len(str_val) < rules["min_length"]:
                return False, f"El texto debe tener al menos {rules['min_length']} caracteres"
            if "max_length" in rules and len(str_val) > rules["max_length"]:
                return False, f"El texto debe tener como máximo {rules['max_length']} caracteres"
            if "pattern" in rules:
                if not re.match(rules["pattern"], str_val):
                    # Include pattern description or example if available
                    pattern_hint = rules.get("pattern_description") or rules.get("example")
                    if pattern_hint:
                        return False, f"El formato no es válido. Ejemplo esperado: {pattern_hint}"
                    return False, f"El formato no es válido (patrón requerido: {rules['pattern']})"

        return True, None

    async def get_missing_required_fields(
        self,
        element_id: str,
        collected_values: dict[str, Any],
    ) -> list[ElementRequiredField]:
        """
        Get list of required fields that haven't been collected yet.

        Args:
            element_id: UUID of the element
            collected_values: Already collected field values

        Returns:
            List of missing required fields
        """
        fields = await self.get_fields_for_element(element_id)
        missing = []

        for field in fields:
            # Check if field should be shown (conditional)
            if not self.evaluate_field_condition(field, collected_values, fields):
                continue

            # Check if required and not collected
            if field.is_required and field.field_key not in collected_values:
                missing.append(field)

        return missing

    async def are_all_required_fields_complete(
        self,
        element_id: str,
        collected_values: dict[str, Any],
    ) -> bool:
        """
        Check if all required fields for an element have been collected.

        Args:
            element_id: UUID of the element
            collected_values: Collected field values

        Returns:
            True if all required fields are complete
        """
        missing = await self.get_missing_required_fields(element_id, collected_values)
        return len(missing) == 0

    async def get_applicable_fields(
        self,
        element_id: str,
        collected_values: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Get all fields that currently apply (based on conditions), with their status.

        Args:
            element_id: UUID of the element
            collected_values: Already collected field values

        Returns:
            List of field info dicts with collection status
        """
        fields = await self.get_fields_for_element(element_id)
        result = []

        for field in fields:
            # Check if field applies based on conditions
            if not self.evaluate_field_condition(field, collected_values, fields):
                continue

            field_info = {
                "field_key": field.field_key,
                "field_label": field.field_label,
                "field_type": field.field_type,
                "is_required": field.is_required,
                "options": field.options,
                "example_value": field.example_value,
                "llm_instruction": field.llm_instruction,
                "validation_rules": field.validation_rules,
                "current_value": collected_values.get(field.field_key),
                "is_collected": field.field_key in collected_values,
            }

            # Add condition info for UI display
            if field.condition_field_id:
                condition_field = next(
                    (f for f in fields if str(f.id) == str(field.condition_field_id)),
                    None,
                )
                if condition_field:
                    field_info["condition"] = {
                        "depends_on": condition_field.field_key,
                        "depends_on_label": condition_field.field_label,
                        "operator": field.condition_operator,
                        "value": field.condition_value,
                    }

            result.append(field_info)

        return result

    async def get_element_data_for_case(
        self,
        case_id: str,
        element_code: str,
    ) -> CaseElementData | None:
        """
        Get the CaseElementData record for a specific case and element.

        Args:
            case_id: UUID of the case
            element_code: Element code

        Returns:
            CaseElementData or None
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(CaseElementData)
                .where(CaseElementData.case_id == uuid.UUID(case_id))
                .where(CaseElementData.element_code == element_code)
            )
            return result.scalar_one_or_none()

    async def get_all_element_data_for_case(
        self,
        case_id: str,
    ) -> list[CaseElementData]:
        """
        Get all CaseElementData records for a case.

        Args:
            case_id: UUID of the case

        Returns:
            List of CaseElementData records
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(CaseElementData)
                .where(CaseElementData.case_id == uuid.UUID(case_id))
                .order_by(CaseElementData.created_at)
            )
            return list(result.scalars().all())


# Singleton instance
_service_instance: ElementRequiredFieldsService | None = None


def get_element_required_fields_service() -> ElementRequiredFieldsService:
    """Get or create the singleton service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ElementRequiredFieldsService()
    return _service_instance
