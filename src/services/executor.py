"""Service layer – builds and executes PowerShell commands for DHCP management."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from ipaddress import IPv4Address

from models.schemas import DHCPScopeRequest, StepResult

logger = logging.getLogger("dhcp_api.executor")

POWERSHELL_EXE = "powershell.exe"


@dataclass
class CommandResult:
    return_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.return_code == 0


async def run_powershell(command: str, timeout: int = 30) -> CommandResult:
    """Execute a single PowerShell command asynchronously."""
    logger.info("Executing: %s", command)
    try:
        proc = await asyncio.create_subprocess_exec(
            POWERSHELL_EXE, "-NoProfile", "-NonInteractive", "-Command", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        result = CommandResult(
            return_code=proc.returncode if proc.returncode is not None else 0,
            stdout=stdout.decode("utf-8", errors="replace").strip(),
            stderr=stderr.decode("utf-8", errors="replace").strip(),
        )
        if not result.success:
            logger.error("Command failed (rc=%d): %s\nSTDERR: %s", result.return_code, command, result.stderr)
        return result
    except asyncio.TimeoutError:
        logger.error("Command timed out after %ds: %s", timeout, command)
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return CommandResult(return_code=-1, stdout="", stderr=f"Timed out after {timeout}s")
    except FileNotFoundError:
        logger.error("powershell.exe not found – is this running on Windows?")
        return CommandResult(return_code=-2, stdout="", stderr="powershell.exe not found")


def scope_info_from_ps(d: dict) -> dict:
    """Map a PowerShell PascalCase scope dict to DHCPScopeInfo field names."""
    required = ("ScopeId", "Name", "SubnetMask", "StartRange", "EndRange", "State")
    missing = [k for k in required if k not in d]
    if missing:
        raise RuntimeError(f"Unexpected PowerShell response schema: missing keys {missing}")
    return {
        "scope_id": str(d["ScopeId"]),
        "name": str(d["Name"]),
        "subnet_mask": str(d["SubnetMask"]),
        "start_range": str(d["StartRange"]),
        "end_range": str(d["EndRange"]),
        "state": str(d["State"]),
    }


def parse_ps_json(stdout: str) -> list:
    """Parse PowerShell ConvertTo-Json output into a list.

    PowerShell's ConvertTo-Json degrades to a plain object (not array) when
    the pipeline has exactly one item.  This helper normalises both cases so
    callers always receive a list.

    Raises RuntimeError on malformed JSON so callers get a clean 500 rather
    than a raw JSONDecodeError traceback.
    """
    if not stdout:
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse PowerShell output as JSON: {exc}\nOutput: {stdout!r}"
        ) from exc
    return data if isinstance(data, list) else [data]


def _ip(addr: IPv4Address) -> str:
    return str(addr)


def _minutes_to_timespan(minutes: int) -> str:
    """Convert minutes to a PowerShell TimeSpan string (H:MM:SS).

    Examples:
        15  → 0:15:00
        60  → 1:00:00
        90  → 1:30:00
    """
    if minutes <= 0:
        raise ValueError(f"minutes must be a positive integer, got {minutes}")
    hours, mins = divmod(minutes, 60)
    return f"{hours}:{mins:02d}:00"


# --------------------------------------------------------------------------- #
#  Standalone service functions
#  Each wraps one or more PowerShell cmdlets.  Routes call these instead of
#  calling run_powershell directly so that all command-building stays in
#  the service layer.
# --------------------------------------------------------------------------- #

async def scope_exists(scope_id: str) -> bool:
    """Return True if the scope exists, False if not found.

    Raises RuntimeError when PowerShell itself is unavailable (return_code < 0)
    or when the DHCP server denies access (Access is denied in stderr).
    """
    result = await run_powershell(f"Get-DhcpServerv4Scope -ScopeId {scope_id}")
    if result.return_code < 0:
        raise RuntimeError(result.stderr)
    if not result.success and "access is denied" in result.stderr.lower():
        raise RuntimeError(f"Access denied to DHCP server: {result.stderr}")
    return result.success


async def list_scopes() -> CommandResult:
    return await run_powershell(
        "Get-DhcpServerv4Scope"
        " | Select-Object ScopeId, Name, SubnetMask, StartRange, EndRange, State"
        " | ConvertTo-Json -Compress"
    )


async def get_scope_detail(scope_id: str) -> tuple[CommandResult, CommandResult, CommandResult]:
    """Fetch scope info, options, and exclusions in parallel."""
    return await asyncio.gather(
        run_powershell(f"Get-DhcpServerv4Scope -ScopeId {scope_id} | ConvertTo-Json -Compress"),
        run_powershell(f"Get-DhcpServerv4OptionValue -ScopeId {scope_id} | ConvertTo-Json -Compress"),
        run_powershell(f"Get-DhcpServerv4ExclusionRange -ScopeId {scope_id} | ConvertTo-Json -Compress"),
    )


async def delete_scope(scope_id: str) -> list[StepResult]:
    """Remove failover relationship (if any), then remove the scope.

    Failover removal is non-critical – failure is recorded but does not
    prevent the scope from being deleted.
    """
    steps: list[StepResult] = []

    # Step 1 – Remove failover (non-critical)
    fo_cmd = (
        f"Get-DhcpServerv4Failover -ScopeId {scope_id} -ErrorAction SilentlyContinue"
        f" | Remove-DhcpServerv4Failover -Force -ErrorAction SilentlyContinue"
    )
    fo_result = await run_powershell(fo_cmd)
    steps.append(StepResult(
        step="remove_failover",
        success=fo_result.success,
        command=fo_cmd,
        detail=fo_result.stdout or None,
        error=fo_result.stderr if not fo_result.success else None,
    ))

    # Step 2 – Remove scope (critical)
    scope_cmd = f"Remove-DhcpServerv4Scope -ScopeId {scope_id} -Force"
    scope_result = await run_powershell(scope_cmd)
    steps.append(StepResult(
        step="remove_scope",
        success=scope_result.success,
        command=scope_cmd,
        detail=scope_result.stdout or None,
        error=scope_result.stderr if not scope_result.success else None,
    ))

    return steps


async def update_dns(
    scope_id: str,
    dns_servers: list[str],
    dns_domain: str | None,
) -> CommandResult:
    dns_csv = ",".join(dns_servers)
    cmd = f"Set-DhcpServerv4OptionValue -ScopeId {scope_id} -DnsServer {dns_csv}"
    if dns_domain:
        cmd += f' -DnsDomain "{dns_domain}"'
    return await run_powershell(cmd)


async def add_exclusion(scope_id: str, start: str, end: str) -> CommandResult:
    return await run_powershell(
        f"Add-DhcpServerv4ExclusionRange -ScopeId {scope_id} -StartRange {start} -EndRange {end}"
    )


async def remove_exclusion(scope_id: str, start: str, end: str) -> CommandResult:
    return await run_powershell(
        f"Remove-DhcpServerv4ExclusionRange -ScopeId {scope_id} -StartRange {start} -EndRange {end}"
    )


async def set_scope_state(scope_id: str, state: str) -> CommandResult:
    """Set scope state to 'Active' or 'Inactive'."""
    return await run_powershell(
        f"Set-DhcpServerv4Scope -ScopeId {scope_id} -State {state}"
    )


async def list_failover() -> CommandResult:
    return await run_powershell("Get-DhcpServerv4Failover | ConvertTo-Json -Compress")


# --------------------------------------------------------------------------- #
#  DHCPProvisioner – multi-step scope creation pipeline
# --------------------------------------------------------------------------- #

@dataclass
class DHCPProvisioner:
    """Orchestrates the multi-step DHCP scope provisioning."""

    req: DHCPScopeRequest
    steps: list[StepResult] = field(default_factory=list)
    _failed: bool = False

    async def _run_step(self, step_name: str, command: str, abort_on_fail: bool = True) -> bool:
        result = await run_powershell(command)
        step = StepResult(
            step=step_name,
            success=result.success,
            command=command,
            detail=result.stdout or None,
            error=result.stderr if not result.success else None,
        )
        self.steps.append(step)
        if not result.success and abort_on_fail:
            self._failed = True
        return result.success

    # ------------------------------------------------------------------
    # Step 1 – Create scope
    # ------------------------------------------------------------------
    async def create_scope(self) -> bool:
        r = self.req
        lease = f"{r.lease_duration_days}.00:00:00"
        cmd = (
            f'Add-DhcpServerv4Scope -Name "{r.scope_name}" '
            f"-StartRange {_ip(r.start_range)} -EndRange {_ip(r.end_range)} "
            f"-SubnetMask {_ip(r.subnet_mask)} "
            f"-State Active -LeaseDuration {lease} -Type Dhcp"
        )
        if r.description:
            cmd += f' -Description "{r.description}"'
        return await self._run_step("create_scope", cmd)

    # ------------------------------------------------------------------
    # Step 2 – DNS options
    # ------------------------------------------------------------------
    async def set_dns_options(self) -> bool:
        r = self.req
        dns_csv = ",".join(_ip(d) for d in r.dns_servers)
        cmd = (
            f"Set-DhcpServerv4OptionValue -ScopeId {_ip(r.network)} "
            f"-DnsServer {dns_csv}"
        )
        if r.dns_domain:
            cmd += f' -DnsDomain "{r.dns_domain}"'
        return await self._run_step("set_dns_options", cmd)

    # ------------------------------------------------------------------
    # Step 3 – Default gateway (non-critical)
    # ------------------------------------------------------------------
    async def set_gateway(self) -> bool:
        if not self.req.gateway:
            return True
        cmd = (
            f"Set-DhcpServerv4OptionValue -ScopeId {_ip(self.req.network)} "
            f"-Router {_ip(self.req.gateway)}"
        )
        return await self._run_step("set_gateway", cmd, abort_on_fail=False)

    # ------------------------------------------------------------------
    # Step 4 – Exclusion ranges
    # ------------------------------------------------------------------
    async def add_exclusions(self) -> bool:
        all_ok = True
        for i, exc in enumerate(self.req.exclusions or []):
            cmd = (
                f"Add-DhcpServerv4ExclusionRange -ScopeId {_ip(self.req.network)} "
                f"-StartRange {_ip(exc.start_address)} -EndRange {_ip(exc.end_address)}"
            )
            ok = await self._run_step(f"add_exclusion_{i}", cmd, abort_on_fail=False)
            all_ok = all_ok and ok
        return all_ok

    # ------------------------------------------------------------------
    # Step 5 – Failover
    # ------------------------------------------------------------------
    async def configure_failover(self) -> bool:
        """Build Add-DhcpServerv4Failover using the correct parameter set.

        The real cmdlet has NO -Mode parameter.  Mode is implied by which
        parameters you supply:

        HotStandby set:
            Add-DhcpServerv4Failover ... -ServerRole Active|Standby
                                         -ReservePercent <int>

        LoadBalance set:
            Add-DhcpServerv4Failover ... -LoadBalancePercent <int>

        MaxClientLeadTime expects a TimeSpan (H:MM:SS), NOT raw minutes.
        """
        fo = self.req.failover
        if fo is None:
            return True

        rel_name = fo.relationship_name or f"FO-{self.req.scope_name}"
        mclt = _minutes_to_timespan(fo.max_client_lead_time_minutes)

        cmd = (
            f'Add-DhcpServerv4Failover -Name "{rel_name}" '
            f"-ScopeId {_ip(self.req.network)} "
            f"-PartnerServer {fo.partner_server} "
            f"-MaxClientLeadTime {mclt} "
            f"-Force"
        )

        if fo.mode == "HotStandby":
            cmd += (
                f" -ServerRole {fo.server_role}"
                f" -ReservePercent {fo.reserve_percent}"
            )
        else:  # LoadBalance
            cmd += f" -LoadBalancePercent {fo.load_balance_percent}"

        if fo.shared_secret:
            cmd += f' -SharedSecret "{fo.shared_secret}"'

        return await self._run_step("configure_failover", cmd)

    # ------------------------------------------------------------------
    # Pipeline orchestrator
    # ------------------------------------------------------------------
    async def provision(self) -> list[StepResult]:
        pipeline = [
            self.create_scope,
            self.set_dns_options,
            self.set_gateway,
            self.add_exclusions,
            self.configure_failover,
        ]
        for step_fn in pipeline:
            if self._failed:
                self.steps.append(StepResult(
                    step=step_fn.__name__,
                    success=False,
                    command="(skipped)",
                    error="Skipped due to earlier critical failure",
                ))
                continue
            await step_fn()
        return self.steps
