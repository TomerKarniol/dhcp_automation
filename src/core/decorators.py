"""Reusable decorators for FastAPI route handlers.

Usage
-----
Stack both decorators on every route handler, with @log_route outermost:

    @router.get("/example")
    @log_route
    @http_response
    async def my_handler(...):
        ...

Decorator responsibilities
--------------------------
@log_route
    Logs route entry (function name), exit (OK / FAILED), and elapsed time in ms.
    Re-raises any exception so @http_response or FastAPI can handle it.

@http_response
    Converts unhandled Python exceptions into structured JSONResponse objects
    with appropriate HTTP status codes:
        TimeoutError / PermissionError  → 503 Service Unavailable
        Exception (catch-all)           → 500 Internal Server Error
    HTTPException is intentionally NOT caught here – FastAPI handles it natively.
"""

import functools
import logging
import time

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

_root_logger = logging.getLogger("dhcp_api")


def log_route(func):
    """Log route entry, exit, and elapsed wall-clock time."""
    logger = logging.getLogger(f"dhcp_api.routes.{func.__name__}")

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info("→ %s", func.__name__)
        t0 = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            ms = (time.perf_counter() - t0) * 1000
            logger.info("← %s OK (%.0f ms)", func.__name__, ms)
            return result
        except Exception:
            ms = (time.perf_counter() - t0) * 1000
            logger.exception("← %s FAILED (%.0f ms)", func.__name__, ms)
            raise

    return wrapper


def http_response(func):
    """Convert unhandled exceptions into structured HTTP error responses."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            # Let FastAPI handle these natively (404, 422, etc.)
            raise
        except TimeoutError as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"error": "DHCP service unavailable", "detail": str(exc)},
            )
        except PermissionError as exc:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"error": "Access denied to DHCP server", "detail": str(exc)},
            )
        except Exception as exc:
            _root_logger.exception("Unhandled error in %s", func.__name__)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Internal server error", "detail": str(exc)},
            )

    return wrapper
