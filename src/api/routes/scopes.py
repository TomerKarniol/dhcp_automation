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
from api.test_data import FAKE_SCOPES
from services import executor
from services.executor import DHCPProvisioner, parse_ps_json, scope_info_from_ps

router = APIRouter(prefix="/scopes", tags=["scopes"])


@router.get(
    "/test",
    response_model=ScopeListResponse,
    summary="Return 10 fake DHCP scopes for client testing",
    responses={
        200: {"description": "Ten fake scopes in the standard ScopeListResponse shape"},
        401: {"description": "Missing or invalid API key"},
    },
)
@log_route
@http_response
async def get_test_scopes():
    """
    Returns a static list of 10 fake DHCP scopes that match the real response
    structure. No PowerShell is executed. Use this endpoint to develop and test
    clients without a live DHCP server.

    Returns 200 with the fake scope list.
    Returns 401 if the API key is missing or invalid.
    """
    return ScopeListResponse(scopes=FAKE_SCOPES, count=len(FAKE_SCOPES))


@router.post(
    "",
    response_model=DHCPScopeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DHCP scope with DNS, exclusions, and optional failover",
    responses={
        201: {"description": "Scope created successfully, all steps succeeded"},
        207: {"description": "Scope created but a non-critical step failed — inspect steps[]"},
        401: {"description": "Missing or invalid API key"},
        409: {"description": "Scope already exists"},
        500: {"description": "PowerShell command failed — scope was not created"},
        503: {"description": "PowerShell unavailable or access denied"},
    },
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

    Returns 201 if all steps succeeded.
    Returns 207 if the scope was created but a non-critical step failed — inspect steps[].
    Returns 401 if the API key is missing or invalid.
    Returns 409 if the scope already exists.
    Returns 500 if the PowerShell command failed and the scope was not created.
    Returns 503 if PowerShell is unavailable or access is denied.
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
    responses={
        200: {"description": "List of all DHCP scopes"},
        401: {"description": "Missing or invalid API key"},
        500: {"description": "PowerShell command failed"},
    },
)
@log_route
@http_response
async def list_scopes():
    """
    Returns 200 with all DHCP scopes on this server.
    Returns 401 if the API key is missing or invalid.
    Returns 500 if the PowerShell command failed.
    """
    result = await executor.list_scopes()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)
    scopes = [DHCPScopeInfo(**scope_info_from_ps(s)) for s in parse_ps_json(result.stdout)]
    return ScopeListResponse(scopes=scopes, count=len(scopes))


@router.get(
    "/{scope_id}/exists",
    response_model=ScopeExistsResponse,
    summary="Check whether a scope exists for a given network segment",
    responses={
        200: {"description": "Scope existence check result"},
        401: {"description": "Missing or invalid API key"},
        503: {"description": "PowerShell unavailable or access denied"},
    },
)
@log_route
@http_response
async def check_scope_exists(scope_id: IPv4Address = Path(...)):
    """
    Returns 200 with exists=true or exists=false.
    Returns 401 if the API key is missing or invalid.
    Returns 503 if PowerShell is unavailable or access is denied.
    """
    try:
        exists = await executor.scope_exists(str(scope_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return ScopeExistsResponse(scope_id=str(scope_id), exists=exists)


@router.get(
    "/{scope_id}",
    response_model=ScopeDetailResponse,
    summary="Get details for a single scope",
    responses={
        200: {"description": "Scope details including options and exclusions"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Scope not found"},
        500: {"description": "PowerShell command failed"},
        503: {"description": "PowerShell unavailable or access denied"},
    },
)
@log_route
@http_response
async def get_scope(scope_id: IPv4Address = Path(...)):
    """
    Returns 200 with scope details including options and exclusions.
    Returns 401 if the API key is missing or invalid.
    Returns 404 if the scope does not exist.
    Returns 500 if the PowerShell command failed.
    Returns 503 if PowerShell is unavailable or access is denied.
    """
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
    responses={
        200: {"description": "Scope removed successfully"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Scope not found"},
        500: {"description": "PowerShell command failed"},
        503: {"description": "PowerShell unavailable or access denied"},
    },
)
@log_route
@http_response
async def delete_scope(scope_id: IPv4Address = Path(...)):
    """
    Returns 200 on success. Failover relationship is removed automatically before the scope.
    Returns 401 if the API key is missing or invalid.
    Returns 404 if the scope does not exist.
    Returns 500 if the PowerShell command failed.
    Returns 503 if PowerShell is unavailable or access is denied.
    """
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
    responses={
        200: {"description": "Scope state updated successfully"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Scope not found"},
        500: {"description": "PowerShell command failed"},
        503: {"description": "PowerShell unavailable or access denied"},
    },
)
@log_route
@http_response
async def set_scope_state(req: ScopeStateRequest, scope_id: IPv4Address = Path(...)):
    """
    Returns 200 with the updated scope state.
    Returns 401 if the API key is missing or invalid.
    Returns 404 if the scope does not exist.
    Returns 500 if the PowerShell command failed.
    Returns 503 if PowerShell is unavailable or access is denied.
    """
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
