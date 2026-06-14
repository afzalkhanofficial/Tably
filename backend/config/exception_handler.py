"""
Custom DRF exception handler.

Ensures every API error response has a consistent JSON shape:
{
    "error": "Human readable message",
    "code": "MACHINE_READABLE_CODE",
    "details": { ...field-level errors if validation... }
}

Never returns HTML error pages in API responses.
"""
from http import HTTPStatus

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Replace DRF's default exception handler to guarantee JSON output.
    """
    # Convert Django exceptions to DRF exceptions so they get JSON responses
    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = drf_exceptions.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        # Django model-level validation → DRF validation error
        if hasattr(exc, 'message_dict'):
            exc = drf_exceptions.ValidationError(exc.message_dict)
        else:
            exc = drf_exceptions.ValidationError(exc.messages)

    # Let DRF handle known exception types first
    response = exception_handler(exc, context)

    if response is not None:
        return _format_response(response, exc)

    # Unhandled exceptions — return 500 with a generic message
    # (never leak stack traces in production)
    return Response(
        {
            'error': 'An unexpected error occurred.',
            'code': 'INTERNAL_SERVER_ERROR',
            'details': {},
        },
        status=500,
    )


def _format_response(response, exc):
    """
    Reshape any DRF error response into our standard envelope.
    """
    status_code = response.status_code
    code = _get_error_code(exc, status_code)

    # Validation errors have field-level detail
    if isinstance(exc, drf_exceptions.ValidationError):
        details = response.data if isinstance(response.data, dict) else {'non_field_errors': response.data}
        error_message = 'Validation failed.'
    else:
        details = {}
        # DRF puts detail as a string or list
        raw_detail = response.data.get('detail', str(exc))
        error_message = raw_detail if isinstance(raw_detail, str) else str(raw_detail)

    response.data = {
        'error': error_message,
        'code': code,
        'details': details,
    }
    return response


def _get_error_code(exc, status_code):
    """
    Derive a MACHINE_READABLE_CODE from the exception or HTTP status.
    """
    # Map common DRF exceptions to codes
    code_map = {
        drf_exceptions.AuthenticationFailed: 'AUTHENTICATION_FAILED',
        drf_exceptions.NotAuthenticated: 'NOT_AUTHENTICATED',
        drf_exceptions.PermissionDenied: 'PERMISSION_DENIED',
        drf_exceptions.NotFound: 'NOT_FOUND',
        drf_exceptions.MethodNotAllowed: 'METHOD_NOT_ALLOWED',
        drf_exceptions.Throttled: 'THROTTLED',
        drf_exceptions.ValidationError: 'VALIDATION_ERROR',
        drf_exceptions.ParseError: 'PARSE_ERROR',
        drf_exceptions.UnsupportedMediaType: 'UNSUPPORTED_MEDIA_TYPE',
    }

    for exc_class, code in code_map.items():
        if isinstance(exc, exc_class):
            return code

    # Fallback to HTTP status phrase
    try:
        return HTTPStatus(status_code).phrase.upper().replace(' ', '_')
    except ValueError:
        return 'ERROR'
