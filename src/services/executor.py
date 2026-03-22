"""Service layer – builds and executes PowerShell commands for DHCP management."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from ipaddress import IPv4Address

from pydantic import ValidationError

from models.schemas import (
    DHCPScopeRequest,
    FullScopeExclusion,
    FullScopeFailover,
    FullScopeInfo,
    StepResult,
)

logger = logging.getLogger("dhcp_api.executor")

POWERSHELL_EXE = "powershell.exe"


# --------------------------------------------------------------------------- #
#  Custom exceptions
#  Raised by build_full_scope_list / build_full_scope_detail so that route
#  handlers can map them to the correct HTTP status codes.
# --------------------------------------------------------------------------- #

class ScopeNotFoundError(Exception):
    pass


class PowerShellUnavailableError(Exception):
    pass


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
    safe_cmd = re.sub(r'(-SharedSecret\s+")[^"]*(")', r'\1***\2', command)
    logger.info("Executing: %s", safe_cmd)
    try:
        proc = await asyncio.create_subprocess_exec(
            POWERSHELL_EXE, "-NoProfile", "-NonInteractive", "-Command", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        result = CommandResult(
            return_code=proc.returncode if proc.returncode is not None else -3,
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
        except OSError as exc:
            logger.warning("Failed to kill timed-out PowerShell process: %s", exc)
        return CommandResult(return_code=-1, stdout="", stderr=f"Timed out after {timeout}s")
    except FileNotFoundError:
        logger.error("powershell.exe not found – is this running on Windows?")
        return CommandResult(return_code=-2, stdout="", stderr="powershell.exe not found")


def parse_ps_json(stdout: str) -> list:
    """Parse PowerShell ConvertTo-Json output into a list.

    PowerShell's ConvertTo-Json degrades to a plain object (not array) when
    the pipeline has exactly one item.  This helper normalises both cases so
    callers always receive a list.

    Returns [] for empty output or when the pipeline produced $null.
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
    # PowerShell ConvertTo-Json outputs "null" when the pipeline is empty ($null).
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


def _ip(addr: IPv4Address) -> str:
    return str(addr)


def _ps_escape(s: str) -> str:
    """Escape a string for safe embedding inside a PowerShell double-quoted string.

    In PowerShell, a literal double-quote inside "..." is written as "".
    Applying this before interpolation prevents command injection via
    user-supplied fields like scope_name, description, dns_domain, etc.
    """
    return s.replace('"', '""')


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
#  PS output → Python dict mappers
# --------------------------------------------------------------------------- #

def full_scope_from_ps(d: dict) -> dict:
    """Map a PowerShell PascalCase scope dict to FullScopeInfo base field names.

    Only maps fields that come from Get-DhcpServerv4Scope.  Options,
    exclusions, and failover are merged in by the build_* functions.
    """
    required = ("ScopeId", "Name", "SubnetMask", "StartRange", "EndRange", "State")
    missing = [k for k in required if k not in d]
    if missing:
        raise RuntimeError(f"Unexpected PowerShell response schema: missing keys {missing}")
    lease = d.get("LeaseDuration")
    desc = d.get("Description")
    return {
        "scope_id": str(d["ScopeId"]),
        "name": str(d["Name"]),
        "subnet_mask": str(d["SubnetMask"]),
        "start_range": str(d["StartRange"]),
        "end_range": str(d["EndRange"]),
        "state": str(d["State"]),
        "lease_duration": str(lease) if lease else None,
        "description": str(desc) if desc else None,
    }


# --------------------------------------------------------------------------- #
#  Bulk PS JSON parsers
#  Pure functions – no I/O.  Take the parsed list from parse_ps_json and
#  return dicts keyed by scope_id for O(1) lookup during the join step.
# --------------------------------------------------------------------------- #

def parse_options_by_scope(options_json: list[dict]) -> dict[str, dict]:
    """Extract gateway (003), DNS servers (006), and DNS domain (015) keyed by ScopeId.

    Options with no ScopeId (server-level options) are silently skipped.
    Options with an empty Value list are silently skipped.
    Unknown OptionIds are ignored.
    """
    result: dict[str, dict] = {}
    for obj in options_json:
        scope_id = str(obj.get("ScopeId") or "")
        if not scope_id:
            continue
        if scope_id not in result:
            result[scope_id] = {"gateway": None, "dns_servers": [], "dns_domain": None}
        option_id = obj.get("OptionId")
        values = obj.get("Value") or []
        if option_id == 3 and values:
            result[scope_id]["gateway"] = str(values[0])
        elif option_id == 6 and values:
            result[scope_id]["dns_servers"] = [str(v) for v in values]
        elif option_id == 15 and values:
            result[scope_id]["dns_domain"] = str(values[0])
    return result


def parse_exclusions_by_scope(exclusions_json: list[dict]) -> dict[str, list[dict]]:
    """Group exclusion ranges by ScopeId."""
    result: dict[str, list[dict]] = {}
    for obj in exclusions_json:
        scope_id = str(obj.get("ScopeId") or "")
        if not scope_id:
            continue
        start = str(obj.get("StartRange") or "")
        end = str(obj.get("EndRange") or "")
        if not start or not end:
            logger.warning("Skipping exclusion with missing StartRange/EndRange: %s", obj)
            continue
        if scope_id not in result:
            result[scope_id] = []
        result[scope_id].append({"start_range": start, "end_range": end})
    return result


def parse_failovers_by_scope(failovers_json: list[dict]) -> dict[str, dict]:
    """Index failover relationships by ScopeId.

    A single relationship can cover multiple scopes.  Each covered scope_id
    gets its own entry pointing to the same failover data so lookups are O(1).
    The PS ScopeId field may be a single string or a list — both are handled.
    """
    result: dict[str, dict] = {}
    for obj in failovers_json:
        raw_ids = obj.get("ScopeId", [])
        scope_ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        scope_ids = [str(s) for s in scope_ids if s is not None]
        fo_data = {
            "relationship_name": str(obj.get("Name", "")),
            "partner_server": str(obj.get("PartnerServer", "")),
            "mode": str(obj.get("Mode", "")),
            "state": str(obj.get("State", "")),
            "server_role": obj.get("ServerRole"),
            "reserve_percent": obj.get("ReservePercent"),
            "load_balance_percent": obj.get("LoadBalancePercent"),
            "max_client_lead_time": obj.get("MaxClientLeadTime"),
            "scope_ids": [str(s) for s in scope_ids],
        }
        for sid in scope_ids:
            result[str(sid)] = fo_data
    return result


# --------------------------------------------------------------------------- #
#  Standalone service functions
#  Each wraps one or more PowerShell cmdlets.  Routes call these instead of
#  calling run_powershell directly so that all command-building stays in
#  the service layer.
# --------------------------------------------------------------------------- #

_SCOPE_NOT_FOUND_MARKERS = ("not found", "does not exist", "no scope")


async def scope_exists(scope_id: str) -> bool:
    """Return True if the scope exists, False if not found.

    Raises RuntimeError when:
    - PowerShell itself is unavailable (return_code < 0)
    - The DHCP server denies access
    - rc=1 but stderr does not look like a "not found" error (e.g. service down,
      WMI error) — distinguishes a real service failure from a missing scope so
      callers do not silently proceed on unreliable data.
    """
    result = await run_powershell(f"Get-DhcpServerv4Scope -ScopeId {scope_id}")
    if result.return_code < 0:
        raise RuntimeError(result.stderr)
    if not result.success:
        lower_err = result.stderr.lower()
        if "access is denied" in lower_err:
            raise RuntimeError(f"Access denied to DHCP server: {result.stderr}")
        # If stderr is non-empty and does not match a known "scope not found"
        # pattern, treat it as a service error rather than a missing scope.
        if result.stderr and not any(m in lower_err for m in _SCOPE_NOT_FOUND_MARKERS):
            raise RuntimeError(f"DHCP server error querying scope {scope_id}: {result.stderr}")
    return result.success


async def list_scopes() -> CommandResult:
    return await run_powershell(
        "Get-DhcpServerv4Scope"
        " | Select-Object ScopeId, Name, SubnetMask, StartRange, EndRange, State, LeaseDuration, Description"
        " | ConvertTo-Json -Compress"
    )


async def list_all_scope_options() -> CommandResult:
    """Fetch options for all scopes in one call (no -ScopeId filter)."""
    return await run_powershell(
        "Get-DhcpServerv4OptionValue | ConvertTo-Json -Compress"
    )


async def list_all_exclusions() -> CommandResult:
    """Fetch exclusion ranges for all scopes in one call (no -ScopeId filter)."""
    return await run_powershell(
        "Get-DhcpServerv4ExclusionRange | ConvertTo-Json -Compress"
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
        cmd += f' -DnsDomain "{_ps_escape(dns_domain)}"'
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
#  Rich scope builders
#  Execute 4 parallel PS calls and join the results in Python.
# --------------------------------------------------------------------------- #

def _assemble_full_scope(
    base: dict,
    options_by_scope: dict[str, dict],
    exclusions_by_scope: dict[str, list[dict]],
    failovers_by_scope: dict[str, dict],
) -> FullScopeInfo:
    scope_id = base["scope_id"]
    opts = options_by_scope.get(scope_id, {})
    excls = exclusions_by_scope.get(scope_id, [])
    fo = failovers_by_scope.get(scope_id)

    failover = None
    if fo is not None:
        try:
            failover = FullScopeFailover(**fo)
        except ValidationError:
            logger.warning(
                "Failed to construct FullScopeFailover for scope %s — unexpected PS output: %s",
                scope_id, fo,
            )

    return FullScopeInfo(
        **base,
        gateway=opts.get("gateway"),
        dns_servers=opts.get("dns_servers", []),
        dns_domain=opts.get("dns_domain"),
        exclusions=[FullScopeExclusion(**e) for e in excls],
        failover=failover,
    )


def _safe_parse(result: CommandResult, label: str) -> list:
    """Parse a non-critical PS result, returning [] and logging a warning on failure."""
    if not result.success:
        logger.warning("Non-critical PS call failed (%s): %s", label, result.stderr)
        return []
    try:
        return parse_ps_json(result.stdout)
    except RuntimeError:
        logger.warning("Failed to parse PS output for %s", label)
        return []


async def build_full_scope_list() -> list[FullScopeInfo]:
    """Return all scopes with full option/exclusion/failover detail.

    Executes exactly 4 PowerShell calls in parallel regardless of scope count.
    Raises:
        PowerShellUnavailableError: if PowerShell itself cannot be reached (rc < 0)
        RuntimeError: if the scope list call fails (rc > 0)
    Non-critical call failures (options, exclusions, failover) are logged as
    warnings and those fields default to None / empty lists.
    """
    scope_r, opts_r, excl_r, fo_r = await asyncio.gather(
        list_scopes(),
        list_all_scope_options(),
        list_all_exclusions(),
        list_failover(),
    )

    if scope_r.return_code < 0:
        raise PowerShellUnavailableError(scope_r.stderr)
    if not scope_r.success:
        raise RuntimeError(scope_r.stderr)

    scopes_raw = parse_ps_json(scope_r.stdout)

    opts_raw = _safe_parse(opts_r, "options")
    excl_raw = _safe_parse(excl_r, "exclusions")
    fo_raw = _safe_parse(fo_r, "failover")

    options_by_scope = parse_options_by_scope(opts_raw)
    exclusions_by_scope = parse_exclusions_by_scope(excl_raw)
    failovers_by_scope = parse_failovers_by_scope(fo_raw)

    return [
        _assemble_full_scope(
            full_scope_from_ps(scope_dict),
            options_by_scope,
            exclusions_by_scope,
            failovers_by_scope,
        )
        for scope_dict in scopes_raw
    ]


async def build_full_scope_detail(scope_id: str) -> FullScopeInfo:
    """Return full detail for a single scope.

    Executes exactly 4 PowerShell calls in parallel.
    Raises:
        PowerShellUnavailableError: if PowerShell itself cannot be reached (rc < 0)
        ScopeNotFoundError: if the scope does not exist
        RuntimeError: on any other unexpected failure
    Non-critical call failures (options, exclusions, failover) are logged as
    warnings and those fields default to None / empty lists.
    """
    scope_r, opts_r, excl_r, fo_r = await asyncio.gather(
        run_powershell(f"Get-DhcpServerv4Scope -ScopeId {scope_id} | ConvertTo-Json -Compress"),
        run_powershell(f"Get-DhcpServerv4OptionValue -ScopeId {scope_id} | ConvertTo-Json -Compress"),
        run_powershell(f"Get-DhcpServerv4ExclusionRange -ScopeId {scope_id} | ConvertTo-Json -Compress"),
        run_powershell(
            f"Get-DhcpServerv4Failover -ScopeId {scope_id} -ErrorAction SilentlyContinue"
            f" | ConvertTo-Json -Compress"
        ),
    )

    if scope_r.return_code < 0:
        raise PowerShellUnavailableError(scope_r.stderr)
    if not scope_r.success:
        raise ScopeNotFoundError(f"Scope {scope_id} not found")

    scope_list = parse_ps_json(scope_r.stdout)
    if not scope_list:
        raise RuntimeError(f"Unexpected empty response from DHCP server for scope {scope_id}")

    base = full_scope_from_ps(scope_list[0])

    opts_raw = _safe_parse(opts_r, f"options for scope {scope_id}")
    excl_raw = _safe_parse(excl_r, f"exclusions for scope {scope_id}")
    fo_raw = _safe_parse(fo_r, f"failover for scope {scope_id}")

    return _assemble_full_scope(
        base,
        parse_options_by_scope(opts_raw),
        parse_exclusions_by_scope(excl_raw),
        parse_failovers_by_scope(fo_raw),
    )


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
            f'Add-DhcpServerv4Scope -Name "{_ps_escape(r.scope_name)}" '
            f"-StartRange {_ip(r.start_range)} -EndRange {_ip(r.end_range)} "
            f"-SubnetMask {_ip(r.subnet_mask)} "
            f"-State Active -LeaseDuration {lease} -Type Dhcp"
        )
        if r.description:
            cmd += f' -Description "{_ps_escape(r.description)}"'
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
            cmd += f' -DnsDomain "{_ps_escape(r.dns_domain)}"'
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
            f'Add-DhcpServerv4Failover -Name "{_ps_escape(rel_name)}" '
            f"-ScopeId {_ip(self.req.network)} "
            f'-PartnerServer "{_ps_escape(fo.partner_server)}" '
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
            cmd += f' -SharedSecret "{_ps_escape(fo.shared_secret)}"'

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
