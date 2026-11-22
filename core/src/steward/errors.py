# SPDX-License-Identifier: AGPL-3.0-or-later
"""API errors.

The UI translates ``code`` (with ``params``) into a message in the user's language.
"""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, **params: Any) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.params = params


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "params": exc.params},
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A request the API cannot take, with a code the UI can explain: too many photos at once
    (``max``: how many one request takes), otherwise an invalid request."""
    assert isinstance(exc, RequestValidationError)
    for error in exc.errors():
        if error.get("type") == "too_long" and error.get("loc", ())[-1:] == ("ids",):
            limit = (error.get("ctx") or {}).get("max_length")
            return JSONResponse(
                status_code=422, content={"code": "too_many_photos", "params": {"max": limit}}
            )
    return JSONResponse(status_code=422, content={"code": "invalid_request", "params": {}})
