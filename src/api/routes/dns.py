"""DNS configuration endpoints for existing DHCP scopes."""

from ipaddress import IPv4Address

from fastapi import APIRouter, HTTPException, Path, status

from core.decorators import http_response, log_route
from models.schemas import DNSUpdateRequest, DNSUpdateResponse
from services import executor

router = APIRouter(prefix="/scopes", tags=["dns"])


@router.patch(
    "/{scope_id}/dns",
    response_model=DNSUpdateResponse,
    summary="Update DNS servers (and optional domain suffix) for an existing scope",
    responses={
        200: {"description": "DNS settings updated successfully"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Scope not found"},
        500: {"description": "PowerShell command failed"},
        503: {"description": "PowerShell unavailable or access denied"},
    },
)
@log_route
@http_response
async def update_dns(req: DNSUpdateRequest, scope_id: IPv4Address = Path(...)):
    """
    Overwrites the DNS server list and (optionally) the DNS domain suffix
    for the given scope using `Set-DhcpServerv4OptionValue`.

    - **dns_servers** – replaces the current list (option 006)
    - **dns_domain** – sets the DNS suffix (option 015); omit to leave unchanged

    Returns 200 with the updated DNS settings.
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

    result = await executor.update_dns(
        str(scope_id),
        [str(ip) for ip in req.dns_servers],
        req.dns_domain,
    )
    if not result.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.stderr)

    return DNSUpdateResponse(
        scope_id=str(scope_id),
        dns_servers=[str(ip) for ip in req.dns_servers],
        dns_domain=req.dns_domain,
    )
