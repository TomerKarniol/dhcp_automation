"""Health-check endpoint."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from core.decorators import http_response, log_route
from services import executor

router = APIRouter(tags=["health"])


@router.get("/health")
@log_route
@http_response
async def health():
    """Return 200 if the DHCP service is reachable, 503 otherwise."""
    result = await executor.run_powershell("Get-DhcpServerSetting | Select-Object -Property IsDomainJoined")
    if not result.success:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "error": result.stderr},
        )
    return {"status": "healthy", "dhcp_server": result.stdout}
