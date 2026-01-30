"""
FastAPI Error Handlers for Unified Error Handling System.

This module provides exception handlers for FastAPI applications to convert
exceptions into standardized APIErrorResponse format with proper HTTP status
codes and Spanish user messages.

Usage:
    from fastapi import FastAPI
    from shared.fastapi_errors import register_error_handlers
    
    app = FastAPI()
    register_error_handlers(app)
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from shared.errors import (
    APIErrorResponse,
    ErrorCategory,
    ErrorLogger,
    get_error_logger,
    map_status_to_category,
    translate_to_spanish,
)


logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert HTTPException to standardized APIErrorResponse.
    
    Handles FastAPI HTTPException and converts to consistent format with:
    - Proper error category based on status code
    - Spanish translation of error message
    - Structured logging with request context
    - Unique log reference for correlation
    
    Args:
        request: FastAPI request object
        exc: HTTPException that was raised
        
    Returns:
        JSONResponse with APIErrorResponse body
    """
    error_logger = get_error_logger()
    category = map_status_to_category(exc.status_code)
    
    # Extract request context
    context: dict[str, Any] = {
        "path": str(request.url.path),
        "method": request.method,
        "status_code": exc.status_code,
    }
    
    # Add query params if present (sanitize sensitive data)
    if request.url.query:
        context["query_params"] = str(request.url.query)
    
    # Log the error
    log_ref = error_logger.log_error(
        error=exc,
        category=category,
        endpoint=str(request.url.path),
        method=request.method,
        context=context,
        exc_info=False,  # HTTPException is expected, no stack trace needed
    )
    
    # Translate error message to Spanish
    detail_str = str(exc.detail)
    spanish_message = translate_to_spanish(detail_str)
    
    # Build standardized response
    response = APIErrorResponse(
        success=False,
        error_category=category,
        error_code=f"HTTP_{exc.status_code}",
        message=spanish_message,
        guidance=error_logger._build_guidance(category),
        log_ref=log_ref,
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump()
    )


async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Convert Pydantic ValidationError to standardized APIErrorResponse.
    
    Handles Pydantic validation errors and converts to consistent format with:
    - Validation error category
    - Spanish error message with field details
    - List of specific validation errors in context
    
    Args:
        request: FastAPI request object
        exc: ValidationError that was raised
        
    Returns:
        JSONResponse with APIErrorResponse body and 400 status
    """
    error_logger = get_error_logger()
    
    # Extract validation errors
    errors = exc.errors()
    
    # Build context with validation details
    context: dict[str, Any] = {
        "path": str(request.url.path),
        "method": request.method,
        "validation_errors": errors,
    }
    
    # Log the error
    log_ref = error_logger.log_error(
        error=exc,
        category=ErrorCategory.VALIDATION_ERROR,
        endpoint=str(request.url.path),
        method=request.method,
        context=context,
        exc_info=False,  # Validation errors are expected
    )
    
    # Build user-friendly message
    if len(errors) == 1:
        error_detail = errors[0]
        field = ".".join(str(loc) for loc in error_detail["loc"])
        message = f"Error de validación en '{field}': {error_detail['msg']}"
    else:
        message = f"Errores de validación en {len(errors)} campos. Verifique los datos proporcionados."
    
    # Build standardized response
    response = APIErrorResponse(
        success=False,
        error_category=ErrorCategory.VALIDATION_ERROR,
        error_code="VALIDATION_ERROR",
        message=message,
        guidance="Verifique los datos proporcionados y corrija los errores de validación.",
        log_ref=log_ref,
        context={"validation_errors": errors},
    )
    
    return JSONResponse(
        status_code=400,
        content=response.model_dump()
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert general exceptions to standardized APIErrorResponse.
    
    Handles all unhandled exceptions and converts to consistent format with:
    - Unexpected error category
    - Generic Spanish error message (no internal details)
    - Full stack trace logging
    - CORS headers preservation
    
    Args:
        request: FastAPI request object
        exc: Exception that was raised
        
    Returns:
        JSONResponse with APIErrorResponse body and 500 status
    """
    error_logger = get_error_logger()
    
    # Extract request context
    context: dict[str, Any] = {
        "path": str(request.url.path),
        "method": request.method,
        "exception_type": type(exc).__name__,
    }
    
    # Log the error with full stack trace
    log_ref = error_logger.log_error(
        error=exc,
        category=ErrorCategory.UNEXPECTED_ERROR,
        endpoint=str(request.url.path),
        method=request.method,
        context=context,
        exc_info=True,  # Include full stack trace for unexpected errors
    )
    
    # Build standardized response (generic message, no internal details)
    response = APIErrorResponse(
        success=False,
        error_category=ErrorCategory.UNEXPECTED_ERROR,
        error_code="INTERNAL_SERVER_ERROR",
        message="Error interno del servidor. Por favor, intente nuevamente.",
        guidance="Si el problema persiste, contacte al soporte técnico.",
        log_ref=log_ref,
    )
    
    return JSONResponse(
        status_code=500,
        content=response.model_dump()
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register custom error handlers with FastAPI app.
    
    Registers handlers for:
    - HTTPException (400, 401, 403, 404, etc.)
    - ValidationError (Pydantic validation)
    - Exception (all unhandled exceptions)
    
    Args:
        app: FastAPI application instance
    """
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("Registered unified error handlers for FastAPI")
