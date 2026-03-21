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
)
@log_route
@http_response
async def list_failover():
    result = await executor.list_failover()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)
    relationships = parse_ps_json(result.stdout)
    return FailoverListResponse(relationships=relationships, count=len(relationships))
