"""DHCP scope CRUD endpoints."""

from ipaddress import IPv4Address

from fastapi import APIRouter, HTTPException, Path, status
from fastapi.responses import JSONResponse

from api.test_data import FAKE_SCOPES
from core.decorators import http_response, log_route
from models.schemas import (
    DHCPScopeRequest,
    DHCPScopeResponse,
    DeleteScopeResponse,
    FullScopeDetailResponse,
    FullScopeListResponse,
    ScopeExistsResponse,
    ScopeStateRequest,
    ScopeStateResponse,
)
from services import executor
from services.executor import (
    DHCPProvisioner,
    PowerShellUnavailableError,
    ScopeNotFoundError,
)


router = APIRouter(prefix="/scopes", tags=["scopes"])


@router.get(
    "/test",
    response_model=FullScopeListResponse,
    summary="Return 10 fake DHCP scopes for client testing",
    responses={
        200: {"description": "Ten fake scopes in the standard FullScopeListResponse shape"},
        401: {"description": "Missing or invalid API key"},
    },
)
@log_route
@http_response
async def get_test_scopes():
    """
    Returns a static list of 10 fake DHCP scopes that match the real response
    structure, including options, exclusions, and failover. No PowerShell is
    executed. Use this endpoint to develop and test clients without a live
    DHCP server.

    Returns 200 with the fake scope list.
    Returns 401 if the API key is missing or invalid.
    """
    return FullScopeListResponse(scopes=FAKE_SCOPES, count=len(FAKE_SCOPES))


@router.get(
    "",
    response_model=FullScopeListResponse,
    summary="List all DHCP scopes with full configuration details",
    responses={
        200: {"description": "All scopes with DNS, gateway, exclusions, and failover details"},
        401: {"description": "Missing or invalid API key"},
        500: {"description": "PowerShell command failed"},
        503: {"description": "PowerShell unavailable or access denied"},
    },
)
@log_route
@http_response
async def list_scopes():
    """
    Returns all DHCP scopes with full configuration detail in a single call.
    Executes 4 PowerShell commands in parallel: scope list, all options,
    all exclusions, and failover. Results are joined in Python by ScopeId.

    Returns 200 with the full scope list.
    Returns 401 if the API key is missing or invalid.
    Returns 500 if the PowerShell command failed.
    Returns 503 if PowerShell is unavailable or access is denied.
    """
    try:
        scopes = await executor.build_full_scope_list()
    except PowerShellUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return FullScopeListResponse(scopes=scopes, count=len(scopes))


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
    response_model=FullScopeDetailResponse,
    summary="Get full details for a single scope",
    responses={
        200: {"description": "Full scope details including options, exclusions, and failover"},
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
    Returns full scope detail including gateway, DNS servers, DNS domain,
    exclusion ranges, and failover configuration. Executes 4 PowerShell
    commands in parallel.

    Returns 200 with complete scope details.
    Returns 401 if the API key is missing or invalid.
    Returns 404 if the scope does not exist.
    Returns 500 if the PowerShell command failed.
    Returns 503 if PowerShell is unavailable or access is denied.
    """
    try:
        scope = await executor.build_full_scope_detail(str(scope_id))
    except PowerShellUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ScopeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope {scope_id} not found",
        )
    return FullScopeDetailResponse(scope=scope)


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

    scope_step = next((s for s in steps if s.step == "remove_scope"), None)
    if scope_step is None or not scope_step.success:
        detail = scope_step.error if scope_step else "remove_scope step missing from response"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)

    # overall_success reflects whether the scope was deleted (the critical step).
    # Non-critical steps like remove_failover may fail without affecting this flag;
    # inspect steps[] for the full picture.
    return DeleteScopeResponse(
        deleted=str(scope_id),
        steps=steps,
        overall_success=scope_step.success,
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
