"""Exclusion range management endpoints."""

from ipaddress import IPv4Address

from fastapi import APIRouter, HTTPException, Path, Query, status

from core.decorators import http_response, log_route
from models.schemas import ExclusionResponse
from models.validators import check_exclusion_order
from services import executor

router = APIRouter(prefix="/scopes", tags=["exclusions"])

# Substring matched case-insensitively against PowerShell stderr to detect
# the "address already leased" error from Add-DhcpServerv4ExclusionRange.
_LEASE_CONFLICT_MARKERS = ("currently in use", "active lease", "already in use")


def _is_lease_conflict(stderr: str) -> bool:
    lower = stderr.lower()
    return any(m in lower for m in _LEASE_CONFLICT_MARKERS)


def _is_range_not_found(stderr: str) -> bool:
    lower = stderr.lower()
    return "not present" in lower or "does not exist" in lower


@router.post(
    "/{scope_id}/exclusions",
    response_model=ExclusionResponse,
    summary="Add an exclusion range to an existing scope",
)
@log_route
@http_response
async def add_exclusion(
    scope_id: IPv4Address = Path(...),
    start: IPv4Address = Query(..., description="First IP in the exclusion range"),
    end: IPv4Address = Query(..., description="Last IP in the exclusion range"),
):
    """
    Adds an IP exclusion range to the scope so those addresses are never leased.

    Returns 409 if one or more IPs in the range are currently leased.
    Returns 404 if the scope does not exist.
    """
    try:
        check_exclusion_order(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        exists = await executor.scope_exists(str(scope_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope {scope_id} not found",
        )

    result = await executor.add_exclusion(str(scope_id), str(start), str(end))
    if not result.success:
        if _is_lease_conflict(result.stderr):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot add exclusion: one or more IPs in the range have active leases",
            )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)

    return ExclusionResponse(scope_id=str(scope_id), start=str(start), end=str(end), action="added")


@router.delete(
    "/{scope_id}/exclusions",
    response_model=ExclusionResponse,
    summary="Remove an exclusion range from an existing scope",
)
@log_route
@http_response
async def remove_exclusion(
    scope_id: IPv4Address = Path(...),
    start: IPv4Address = Query(..., description="First IP in the exclusion range"),
    end: IPv4Address = Query(..., description="Last IP in the exclusion range"),
):
    """
    Removes an IP exclusion range from the scope.

    Returns 404 if the scope or the exclusion range does not exist.
    """
    try:
        check_exclusion_order(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        exists = await executor.scope_exists(str(scope_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope {scope_id} not found",
        )

    result = await executor.remove_exclusion(str(scope_id), str(start), str(end))
    if not result.success:
        if _is_range_not_found(result.stderr):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Exclusion range {start}–{end} not found in scope {scope_id}",
            )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)

    return ExclusionResponse(scope_id=str(scope_id), start=str(start), end=str(end), action="removed")
