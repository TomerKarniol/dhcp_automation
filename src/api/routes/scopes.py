"""DHCP scope CRUD endpoints."""

import logging
from ipaddress import IPv4Address

from fastapi import APIRouter, HTTPException, Path, status
from fastapi.responses import JSONResponse

from core.decorators import http_response, log_route

logger = logging.getLogger("dhcp_api.routes")
from models.schemas import (
    DHCPScopeInfo,
    DHCPScopeRequest,
    DHCPScopeResponse,
    DeleteScopeResponse,
    ScopeDetailResponse,
    ScopeExistsResponse,
    ScopeListResponse,
    ScopeStateRequest,
    ScopeStateResponse,
)
from services import executor
from services.executor import DHCPProvisioner, parse_ps_json, scope_info_from_ps

router = APIRouter(prefix="/scopes", tags=["scopes"])


@router.post(
    "",
    response_model=DHCPScopeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DHCP scope with DNS, exclusions, and optional failover",
)
@log_route
@http_response
async def create_scope(req: DHCPScopeRequest):
    """
    Full scope provisioning pipeline:

    1. **Create scope** – `Add-DhcpServerv4Scope`
    2. **Set DNS options** – `Set-DhcpServerv4OptionValue` (option 006 + 015)
    3. **Set gateway** – router option 003 (if provided)
    4. **Add exclusions** – `Add-DhcpServerv4ExclusionRange`
    5. **Configure failover** – `Add-DhcpServerv4Failover` (if provided)

    Returns 409 if a scope for this network already exists.
    Returns 207 if a non-critical step fails (exclusions, failover).
    """
    try:
        exists = await executor.scope_exists(str(req.network))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scope {req.network} already exists. Delete it first or choose a different network.",
        )

    provisioner = DHCPProvisioner(req=req)
    steps = await provisioner.provision()
    overall = all(s.success for s in steps)

    response = DHCPScopeResponse(
        scope_name=req.scope_name,
        network=str(req.network),
        overall_success=overall,
        steps=steps,
    )

    # If the critical create_scope step itself failed, nothing was created
    create_step = next((s for s in steps if s.step == "create_scope"), None)
    if create_step and not create_step.success:
        error = create_step.error or ""
        # Another process may have created the scope between our exists-check and
        # Add-DhcpServerv4Scope (TOCTOU) — map that to 409 instead of 500.
        if "already exists" in error.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Scope {req.network} already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create scope: {error}",
        )

    # Scope was created but one or more non-critical steps failed → 207
    if not overall:
        return JSONResponse(
            status_code=status.HTTP_207_MULTI_STATUS,
            content=response.model_dump(),
        )
    return response


@router.get(
    "",
    response_model=ScopeListResponse,
    summary="List all DHCP scopes",
)
@log_route
@http_response
async def list_scopes():
    result = await executor.list_scopes()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)
    scopes = [DHCPScopeInfo(**scope_info_from_ps(s)) for s in parse_ps_json(result.stdout)]
    return ScopeListResponse(scopes=scopes, count=len(scopes))


@router.get(
    "/{scope_id}/exists",
    response_model=ScopeExistsResponse,
    summary="Check whether a scope exists for a given network segment",
)
@log_route
@http_response
async def check_scope_exists(scope_id: IPv4Address = Path(...)):
    try:
        exists = await executor.scope_exists(str(scope_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return ScopeExistsResponse(scope_id=str(scope_id), exists=exists)


@router.get(
    "/{scope_id}",
    response_model=ScopeDetailResponse,
    summary="Get details for a single scope",
)
@log_route
@http_response
async def get_scope(scope_id: IPv4Address = Path(...)):
    scope_r, opts_r, excl_r = await executor.get_scope_detail(str(scope_id))

    if scope_r.return_code < 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=scope_r.stderr,
        )
    if not scope_r.success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope {scope_id} not found",
        )

    scope_list = parse_ps_json(scope_r.stdout)
    scope_info = DHCPScopeInfo(**scope_info_from_ps(scope_list[0])) if scope_list else None
    if scope_info is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected empty response from DHCP server",
        )

    if not opts_r.success:
        logger.warning("Failed to fetch options for scope %s: %s", scope_id, opts_r.stderr)
    if not excl_r.success:
        logger.warning("Failed to fetch exclusions for scope %s: %s", scope_id, excl_r.stderr)

    return ScopeDetailResponse(
        scope=scope_info,
        options=parse_ps_json(opts_r.stdout) if opts_r.success else [],
        exclusions=parse_ps_json(excl_r.stdout) if excl_r.success else [],
    )


@router.delete(
    "/{scope_id}",
    response_model=DeleteScopeResponse,
    summary="Remove a DHCP scope (also removes its failover relationship)",
)
@log_route
@http_response
async def delete_scope(scope_id: IPv4Address = Path(...)):
    try:
        exists = await executor.scope_exists(str(scope_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope {scope_id} not found",
        )

    steps = await executor.delete_scope(str(scope_id))
    overall = all(s.success for s in steps)

    scope_step = next((s for s in steps if s.step == "remove_scope"), None)
    if scope_step is None or not scope_step.success:
        detail = scope_step.error if scope_step else "remove_scope step missing from response"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)

    return DeleteScopeResponse(
        deleted=str(scope_id),
        steps=steps,
        overall_success=overall,
    )


@router.patch(
    "/{scope_id}/state",
    response_model=ScopeStateResponse,
    summary="Activate or deactivate a DHCP scope",
)
@log_route
@http_response
async def set_scope_state(req: ScopeStateRequest, scope_id: IPv4Address = Path(...)):
    try:
        exists = await executor.scope_exists(str(scope_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope {scope_id} not found",
        )

    result = await executor.set_scope_state(str(scope_id), req.state)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)

    return ScopeStateResponse(scope_id=str(scope_id), state=req.state)
