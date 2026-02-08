"""
Defensive tool decorators for Phase 4: Tool Hardening.

Provides reusable validation decorators to harden high-risk tools with:
- Format validation (email, phone, DNI)
- Dynamic parameter validation
- State completeness checks

Usage:
    from agent.utils.tool_decorators import validate_email_format, validate_phone_format
    
    @tool
    @validate_email_format(param="email")
    @validate_phone_format(param="telefono")
    async def actualizar_datos_personales(email: str, telefono: str, ...):
        ...
"""

import re
import structlog
from functools import wraps
from typing import Callable, Any

logger = structlog.get_logger(__name__)


# =============================================================================
# FORMAT VALIDATORS
# =============================================================================

def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email address to validate
    
    Returns:
        True if valid email format
    """
    if not email or not isinstance(email, str):
        return False
    
    # Basic email regex (RFC 5322 simplified)
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def validate_phone(phone: str) -> bool:
    """
    Validate Spanish phone format.
    
    Accepts:
    - +34600000000 (international)
    - 600000000 (national)
    - +34 600 000 000 (with spaces)
    
    Args:
        phone: Phone number to validate
    
    Returns:
        True if valid Spanish phone format
    """
    if not phone or not isinstance(phone, str):
        return False
    
    # Remove spaces, dashes, parentheses
    cleaned = re.sub(r'[\s\-\(\)]', '', phone.strip())
    
    # Pattern: Optional +34, then 9 digits (6/7/8/9 prefix for mobiles)
    patterns = [
        r'^\+34[6789]\d{8}$',  # +34600000000
        r'^[6789]\d{8}$',      # 600000000
    ]
    
    return any(re.match(pattern, cleaned) for pattern in patterns)


def validate_dni(dni: str) -> bool:
    """
    Validate Spanish DNI/NIE format.
    
    Accepts:
    - 12345678A (DNI)
    - X1234567A (NIE with X/Y/Z prefix)
    
    Args:
        dni: DNI/NIE to validate
    
    Returns:
        True if valid DNI/NIE format
    """
    if not dni or not isinstance(dni, str):
        return False
    
    dni_clean = dni.strip().upper()
    
    # Pattern: 8 digits + letter OR X/Y/Z + 7 digits + letter
    patterns = [
        r'^\d{8}[A-Z]$',      # DNI
        r'^[XYZ]\d{7}[A-Z]$', # NIE
    ]
    
    if not any(re.match(pattern, dni_clean) for pattern in patterns):
        return False
    
    # Validate check letter (optional but recommended)
    # DNI algorithm: number % 23 → letter
    letters = 'TRWAGMYFPDXBNJZSQVHLCKE'
    
    if dni_clean[0] in 'XYZ':
        # NIE: Replace X/Y/Z with 0/1/2
        nie_map = {'X': '0', 'Y': '1', 'Z': '2'}
        number = int(nie_map[dni_clean[0]] + dni_clean[1:8])
    else:
        # DNI
        number = int(dni_clean[:8])
    
    expected_letter = letters[number % 23]
    return dni_clean[-1] == expected_letter


# =============================================================================
# DECORATORS
# =============================================================================

def validate_email_format(param: str = "email"):
    """
    Decorator to validate email format.
    
    Args:
        param: Parameter name to validate (default: "email")
    
    Returns:
        Decorated function that validates email before execution
    
    Example:
        @tool
        @validate_email_format(param="email")
        async def my_tool(email: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            email_value = kwargs.get(param)
            
            if email_value and not validate_email(email_value):
                logger.warning(
                    "email_format_validation_failed",
                    tool=func.__name__,
                    email=email_value,
                )
                return {
                    "success": False,
                    "error": f"Email inválido: {email_value}",
                    "error_type": "validation_error",
                    "validation_errors": [
                        f"El email '{email_value}' no tiene un formato válido (ejemplo: usuario@dominio.com)"
                    ],
                }
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def validate_phone_format(param: str = "telefono"):
    """
    Decorator to validate phone format.
    
    Args:
        param: Parameter name to validate (default: "telefono")
    
    Returns:
        Decorated function that validates phone before execution
    
    Example:
        @tool
        @validate_phone_format(param="telefono")
        async def my_tool(telefono: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            phone_value = kwargs.get(param)
            
            if phone_value and not validate_phone(phone_value):
                logger.warning(
                    "phone_format_validation_failed",
                    tool=func.__name__,
                    phone=phone_value,
                )
                return {
                    "success": False,
                    "error": f"Teléfono inválido: {phone_value}",
                    "error_type": "validation_error",
                    "validation_errors": [
                        f"El teléfono '{phone_value}' no tiene un formato válido (ejemplo: +34600000000 o 600000000)"
                    ],
                }
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def validate_dni_format(param: str = "dni"):
    """
    Decorator to validate DNI/NIE format.
    
    Args:
        param: Parameter name to validate (default: "dni")
    
    Returns:
        Decorated function that validates DNI before execution
    
    Example:
        @tool
        @validate_dni_format(param="dni")
        async def my_tool(dni: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            dni_value = kwargs.get(param)
            
            if dni_value and not validate_dni(dni_value):
                logger.warning(
                    "dni_format_validation_failed",
                    tool=func.__name__,
                    dni=dni_value,
                )
                return {
                    "success": False,
                    "error": f"DNI/NIE inválido: {dni_value}",
                    "error_type": "validation_error",
                    "validation_errors": [
                        f"El DNI/NIE '{dni_value}' no tiene un formato válido (ejemplo: 12345678A o X1234567A)"
                    ],
                }
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def validate_required_fields(get_required_fields: Callable[[dict], list[str]]):
    """
    Decorator to validate dynamic required fields.
    
    This is useful for tools that have conditional requirements based on
    other parameters or state.
    
    Args:
        get_required_fields: Function that takes kwargs and returns list of required field names
    
    Returns:
        Decorated function that validates required fields before execution
    
    Example:
        def get_elemento_fields(kwargs):
            # Dynamic: If elemento needs photos, return ["fotos"]
            return ["fotos"] if kwargs.get("needs_photos") else []
        
        @tool
        @validate_required_fields(get_required_fields=get_elemento_fields)
        async def my_tool(**kwargs):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            required_fields = get_required_fields(kwargs)
            missing_fields = [
                field for field in required_fields
                if field not in kwargs or kwargs[field] is None or kwargs[field] == ""
            ]
            
            if missing_fields:
                logger.warning(
                    "required_fields_validation_failed",
                    tool=func.__name__,
                    missing_fields=missing_fields,
                    required_fields=required_fields,
                )
                return {
                    "success": False,
                    "error": f"Faltan campos requeridos: {', '.join(missing_fields)}",
                    "error_type": "validation_error",
                    "missing_fields": missing_fields,
                    "required_fields": required_fields,
                }
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def validate_state_completeness(check_completeness: Callable[[dict], tuple[bool, list[str]]]):
    """
    Decorator to validate state completeness before tool execution.
    
    This is useful for tools like confirmar_expediente that need to verify
    all required data has been collected.
    
    Args:
        check_completeness: Function that takes state dict and returns (is_complete, missing_items)
    
    Returns:
        Decorated function that validates state completeness before execution
    
    Example:
        def check_expediente_complete(state):
            missing = []
            if not state.get("datos_personales"):
                missing.append("Datos personales")
            if not state.get("datos_vehiculo"):
                missing.append("Datos del vehículo")
            return (len(missing) == 0, missing)
        
        @tool
        @validate_state_completeness(check_completeness=check_expediente_complete)
        async def confirmar_expediente(**kwargs):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Assume state is passed as kwarg (common pattern in mode nodes)
            state = kwargs.get("state", {})
            
            is_complete, missing_items = check_completeness(state)
            
            if not is_complete:
                logger.warning(
                    "state_completeness_validation_failed",
                    tool=func.__name__,
                    missing_items=missing_items,
                )
                return {
                    "success": False,
                    "error": f"Faltan datos requeridos: {', '.join(missing_items)}",
                    "error_type": "validation_error",
                    "missing_items": missing_items,
                }
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
