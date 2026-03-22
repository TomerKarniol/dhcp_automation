"""Failover relationship endpoints."""

from fastapi import APIRouter, HTTPException, status

from core.decorators import http_response, log_route
from models.schemas import FailoverListResponse
from services import executor
from services.executor import parse_ps_json

router = APIRouter(prefix="/failover", tags=["failover"])


@router.get(
    "",
    response_model=FailoverListResponse,
    summary="List all failover relationships",
    responses={
        200: {"description": "List of all failover relationships"},
        401: {"description": "Missing or invalid API key"},
        500: {"description": "PowerShell command failed"},
        503: {"description": "PowerShell unavailable or access denied"},
    },
)
@log_route
@http_response
async def list_failover():
    """
    Returns 200 with the list of all failover relationships on this server.
    Returns 401 if the API key is missing or invalid.
    Returns 500 if the PowerShell command failed.
    Returns 503 if PowerShell is unavailable or access is denied.
    """
    result = await executor.list_failover()
    if result.return_code < 0:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result.stderr)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)
    relationships = parse_ps_json(result.stdout)
    return FailoverListResponse(relationships=relationships, count=len(relationships))
