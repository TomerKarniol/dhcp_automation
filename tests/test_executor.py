"""Tests for DHCPProvisioner pipeline and standalone service functions.

run_powershell is mocked – no Windows / PowerShell required.
Run with:  pytest tests/test_executor.py
"""

import pytest
from ipaddress import IPv4Address
from unittest.mock import AsyncMock, patch

from helpers import _fail, _ok, _unavailable
from models.schemas import DHCPScopeRequest
from services.executor import (
    DHCPProvisioner,
    _minutes_to_timespan,
    delete_scope,
    parse_ps_json,
    scope_exists,
    scope_info_from_ps,
    set_scope_state,
)


MINIMAL_REQ = DHCPScopeRequest(
    scope_name="TEST-VLAN",
    network="10.0.1.0",
    subnet_mask="255.255.255.0",
    start_range="10.0.1.50",
    end_range="10.0.1.240",
    gateway="10.0.1.1",
)


# --------------------------------------------------------------------------- #
#  DHCPProvisioner – happy path
# --------------------------------------------------------------------------- #

async def test_full_provision_all_steps_succeed():
    with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
        mock_ps.return_value = _ok()
        provisioner = DHCPProvisioner(req=MINIMAL_REQ)
        steps = await provisioner.provision()

    assert all(s.success for s in steps)
    # create_scope + set_dns + set_gateway + 2 default exclusions = 5 calls minimum
    assert mock_ps.call_count >= 5


async def test_steps_contain_expected_names():
    with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
        mock_ps.return_value = _ok()
        provisioner = DHCPProvisioner(req=MINIMAL_REQ)
        steps = await provisioner.provision()

    step_names = [s.step for s in steps]
    assert "create_scope" in step_names
    assert "set_dns_options" in step_names
    assert "set_gateway" in step_names


# --------------------------------------------------------------------------- #
#  DHCPProvisioner – failure propagation
# --------------------------------------------------------------------------- #

async def test_create_scope_failure_skips_remaining_steps():
    """A critical failure on step 1 must skip all subsequent steps."""
    with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
        mock_ps.return_value = _fail("Scope already exists")
        provisioner = DHCPProvisioner(req=MINIMAL_REQ)
        steps = await provisioner.provision()

    failed = [s for s in steps if not s.success]
    skipped = [s for s in steps if s.command == "(skipped)"]

    assert failed[0].step == "create_scope"
    assert len(skipped) > 0, "Subsequent steps should be skipped"


async def test_exclusion_failure_does_not_abort_pipeline():
    """Exclusion failures are non-critical – failover should still run."""
    call_count = 0

    async def side_effect(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        # Fail only on exclusion commands
        if "ExclusionRange" in cmd:
            return _fail("Exclusion conflict")
        return _ok()

    with patch("services.executor.run_powershell", side_effect=side_effect):
        provisioner = DHCPProvisioner(req=MINIMAL_REQ)
        steps = await provisioner.provision()

    exclusion_steps = [s for s in steps if s.step.startswith("add_exclusion")]
    other_steps = [s for s in steps if not s.step.startswith("add_exclusion")]

    assert all(not s.success for s in exclusion_steps)
    # Non-exclusion steps should not be skipped
    assert all(s.command != "(skipped)" for s in other_steps)


async def test_gateway_failure_does_not_abort_pipeline():
    """Gateway is non-critical – exclusions and failover must still run after gateway failure."""
    async def side_effect(cmd, **kwargs):
        if "Router" in cmd:
            return _fail("Router option failed")
        return _ok()

    with patch("services.executor.run_powershell", side_effect=side_effect):
        provisioner = DHCPProvisioner(req=MINIMAL_REQ)
        steps = await provisioner.provision()

    gateway_step = next(s for s in steps if s.step == "set_gateway")
    assert not gateway_step.success

    # Exclusion steps must still have executed (not skipped)
    exclusion_steps = [s for s in steps if s.step.startswith("add_exclusion")]
    assert len(exclusion_steps) > 0
    assert all(s.command != "(skipped)" for s in exclusion_steps)


# --------------------------------------------------------------------------- #
#  DHCPProvisioner – command content
# --------------------------------------------------------------------------- #

async def test_create_scope_command_contains_scope_name():
    captured = []

    async def capture(cmd, **kwargs):
        captured.append(cmd)
        return _ok()

    with patch("services.executor.run_powershell", side_effect=capture):
        provisioner = DHCPProvisioner(req=MINIMAL_REQ)
        await provisioner.provision()

    create_cmd = next(c for c in captured if "Add-DhcpServerv4Scope" in c)
    assert "TEST-VLAN" in create_cmd
    assert "10.0.1.50" in create_cmd
    assert "10.0.1.240" in create_cmd


# --------------------------------------------------------------------------- #
#  scope_exists standalone function
# --------------------------------------------------------------------------- #

async def test_scope_exists_returns_true_when_found():
    with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
        mock_ps.return_value = _ok("ScopeId: 10.0.1.0")
        result = await scope_exists("10.0.1.0")
    assert result is True


async def test_scope_exists_returns_false_when_not_found():
    with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
        mock_ps.return_value = _fail("Scope not found")
        result = await scope_exists("10.0.1.0")
    assert result is False


async def test_scope_exists_raises_when_powershell_unavailable():
    with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
        mock_ps.return_value = _unavailable()
        with pytest.raises(RuntimeError):
            await scope_exists("10.0.1.0")


async def test_scope_exists_raises_when_access_denied():
    with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
        mock_ps.return_value = _fail("Access is denied.")
        with pytest.raises(RuntimeError, match="Access denied"):
            await scope_exists("10.0.1.0")


# --------------------------------------------------------------------------- #
#  delete_scope standalone function
# --------------------------------------------------------------------------- #

async def test_delete_scope_failover_removal_precedes_scope_removal():
    captured = []

    async def capture(cmd, **kwargs):
        captured.append(cmd)
        return _ok()

    with patch("services.executor.run_powershell", side_effect=capture):
        steps = await delete_scope("10.0.1.0")

    assert len(steps) == 2
    failover_idx = next(i for i, c in enumerate(captured) if "Failover" in c)
    scope_idx = next(i for i, c in enumerate(captured) if "Remove-DhcpServerv4Scope" in c)
    assert failover_idx < scope_idx


async def test_delete_scope_proceeds_even_if_failover_removal_fails():
    """Failover removal failure is non-critical – scope removal must still run."""
    call_count = 0

    async def side_effect(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _fail("No failover relationship found")
        return _ok()

    with patch("services.executor.run_powershell", side_effect=side_effect):
        steps = await delete_scope("10.0.1.0")

    assert steps[0].step == "remove_failover"
    assert steps[1].step == "remove_scope"
    assert steps[1].success is True


# --------------------------------------------------------------------------- #
#  set_scope_state standalone function
# --------------------------------------------------------------------------- #

async def test_set_scope_state_active_command():
    captured = []

    async def capture(cmd, **kwargs):
        captured.append(cmd)
        return _ok()

    with patch("services.executor.run_powershell", side_effect=capture):
        await set_scope_state("10.0.1.0", "Active")

    assert len(captured) == 1
    assert "Set-DhcpServerv4Scope" in captured[0]
    assert "10.0.1.0" in captured[0]
    assert "Active" in captured[0]


async def test_set_scope_state_inactive_command():
    captured = []

    async def capture(cmd, **kwargs):
        captured.append(cmd)
        return _ok()

    with patch("services.executor.run_powershell", side_effect=capture):
        await set_scope_state("10.0.1.0", "Inactive")

    assert "Inactive" in captured[0]


# --------------------------------------------------------------------------- #
#  parse_ps_json
# --------------------------------------------------------------------------- #

class TestParsePsJson:
    def test_empty_string_returns_empty_list(self):
        assert parse_ps_json("") == []

    def test_json_array_returned_as_list(self):
        result = parse_ps_json('[{"ScopeId": "10.0.0.0"}, {"ScopeId": "10.0.1.0"}]')
        assert len(result) == 2
        assert result[0]["ScopeId"] == "10.0.0.0"

    def test_single_json_object_normalized_to_list(self):
        """PowerShell emits a bare object (not array) when pipeline has one item."""
        result = parse_ps_json('{"ScopeId": "10.0.0.0"}')
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["ScopeId"] == "10.0.0.0"

    def test_invalid_json_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="Failed to parse PowerShell output"):
            parse_ps_json("not valid json {{{")

    def test_invalid_json_error_includes_raw_output(self):
        bad = "WARNING: something went wrong\n{broken"
        with pytest.raises(RuntimeError, match="broken"):
            parse_ps_json(bad)


# --------------------------------------------------------------------------- #
#  scope_info_from_ps
# --------------------------------------------------------------------------- #

class TestScopeInfoFromPs:
    VALID = {
        "ScopeId": "10.0.1.0",
        "Name": "TEST-VLAN",
        "SubnetMask": "255.255.255.0",
        "StartRange": "10.0.1.50",
        "EndRange": "10.0.1.240",
        "State": "Active",
    }

    def test_valid_dict_maps_all_fields(self):
        result = scope_info_from_ps(self.VALID)
        assert result["scope_id"] == "10.0.1.0"
        assert result["name"] == "TEST-VLAN"
        assert result["subnet_mask"] == "255.255.255.0"
        assert result["start_range"] == "10.0.1.50"
        assert result["end_range"] == "10.0.1.240"
        assert result["state"] == "Active"

    def test_missing_scope_id_raises(self):
        d = {k: v for k, v in self.VALID.items() if k != "ScopeId"}
        with pytest.raises(RuntimeError, match="missing keys"):
            scope_info_from_ps(d)

    def test_missing_multiple_keys_lists_all_in_error(self):
        with pytest.raises(RuntimeError, match="missing keys"):
            scope_info_from_ps({})

    def test_extra_keys_are_ignored(self):
        d = {**self.VALID, "LeaseDuration": "8.00:00:00", "Type": "Dhcp"}
        result = scope_info_from_ps(d)
        assert "LeaseDuration" not in result


# --------------------------------------------------------------------------- #
#  _minutes_to_timespan
# --------------------------------------------------------------------------- #

class TestMinutesToTimespan:
    def test_less_than_one_hour(self):
        assert _minutes_to_timespan(15) == "0:15:00"

    def test_exactly_one_hour(self):
        assert _minutes_to_timespan(60) == "1:00:00"

    def test_over_one_hour(self):
        assert _minutes_to_timespan(90) == "1:30:00"

    def test_single_minute(self):
        assert _minutes_to_timespan(1) == "0:01:00"

    def test_large_value(self):
        assert _minutes_to_timespan(1440) == "24:00:00"

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="positive"):
            _minutes_to_timespan(0)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="positive"):
            _minutes_to_timespan(-5)

    def test_minutes_padded_to_two_digits(self):
        result = _minutes_to_timespan(5)
        assert result == "0:05:00"
