"""Health-check endpoint."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from core.decorators import http_response, log_route
from services import executor

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    responses={
        200: {"description": "DHCP service is reachable"},
        401: {"description": "Missing or invalid API key"},
        503: {"description": "DHCP service unreachable or PowerShell unavailable"},
    },
)
@log_route
@http_response
async def health():
    """
    Returns 200 if the DHCP service is reachable and PowerShell is available.
    Returns 401 if the API key is missing or invalid.
    Returns 503 if PowerShell is unavailable or the DHCP service is unreachable.
    """
    result = await executor.run_powershell("Get-DhcpServerSetting | Select-Object -Property IsDomainJoined")
    if not result.success:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "error": result.stderr},
        )
    return {"status": "healthy", "dhcp_server": result.stdout}
