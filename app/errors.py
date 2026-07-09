"""Uniform error envelope used across all non-2xx responses."""
from fastapi.responses import JSONResponse


def error_response(code: int, message: str, details: dict | None = None) -> JSONResponse:
    body = {"error": True, "code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=code, content=body)


def bad_request(message: str, details: dict | None = None):
    return error_response(400, message, details)


def forbidden(message: str = "Invalid access token."):
    return error_response(403, message)


def not_found(message: str):
    return error_response(404, message)


def server_error(message: str = "Internal server error."):
    return error_response(500, message)


def unavailable(message: str = "Service temporarily unavailable. Retry later."):
    return error_response(503, message, {"retry_after": 5})
