"""
Error handling utilities for safe, standardized error responses.

Standard Error Response Format:
{
    "detail": {
        "code": "ERROR_CODE",
        "message": "Human readable message"
    }
}

For simple cases, FastAPI's default format is also acceptable:
{
    "detail": "Error message string"
}
"""
from enum import Enum
from typing import Optional, Dict, Any
from loguru import logger
from fastapi import HTTPException
from fastapi.responses import JSONResponse


class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""

    # Authentication errors (401)
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"

    # Authorization errors (403)
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"

    # Not found errors (404)
    NOT_FOUND = "NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"

    # Validation errors (400/422)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"

    # Conflict errors (409)
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"

    # Server errors (500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"

    # Configuration errors
    CONFIG_ERROR = "CONFIG_ERROR"
    SETUP_REQUIRED = "SETUP_REQUIRED"


def create_error_response(
    code: ErrorCode,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a standardized error response dict.

    Args:
        code: Error code enum value
        message: Human-readable error message
        status_code: HTTP status code (for reference, not included in response)
        details: Optional additional details

    Returns:
        Error response dict suitable for HTTPException detail
    """
    response = {
        "code": code.value,
        "message": message
    }
    if details:
        response["details"] = details
    return response


def raise_error(
    code: ErrorCode,
    message: str,
    status_code: int = 500,
    details: Optional[Dict[str, Any]] = None,
    log: bool = True
) -> None:
    """
    Raise a standardized HTTP exception.

    Args:
        code: Error code enum value
        message: Human-readable error message
        status_code: HTTP status code
        details: Optional additional details
        log: Whether to log the error (default True)
    """
    if log:
        logger.error(f"API Error [{code.value}]: {message}")

    raise HTTPException(
        status_code=status_code,
        detail=create_error_response(code, message, status_code, details)
    )


def safe_error_response(
    error: Exception,
    status_code: int = 500,
    user_message: str = "An internal error occurred",
    log_message: str = None,
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
) -> HTTPException:
    """
    Create a safe HTTP exception that doesn't expose internal details.

    Args:
        error: The caught exception
        status_code: HTTP status code (default 500)
        user_message: Message shown to user (generic, safe)
        log_message: Optional context for the log entry
        code: Error code (default INTERNAL_ERROR)

    Returns:
        HTTPException with sanitized message
    """
    # Log the full error for debugging
    context = f" ({log_message})" if log_message else ""
    logger.error(f"Error{context}: {type(error).__name__}: {error}")

    # Return generic message to user with standardized format
    return HTTPException(
        status_code=status_code,
        detail=create_error_response(code, user_message, status_code)
    )


def log_and_raise_500(error: Exception, context: str) -> None:
    """
    Log error and raise a generic 500 response.

    Args:
        error: The caught exception
        context: Context description for logging (e.g., "getting stream history")
    """
    logger.error(f"Error {context}: {type(error).__name__}: {error}")
    raise HTTPException(
        status_code=500,
        detail=create_error_response(
            ErrorCode.INTERNAL_ERROR,
            f"Failed to {context}. Please check logs for details.",
            500
        )
    )
