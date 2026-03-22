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
    PowerShellUnavailableError,
    ScopeNotFoundError,
    _minutes_to_timespan,
    delete_scope,
    full_scope_from_ps,
    parse_exclusions_by_scope,
    parse_failovers_by_scope,
    parse_options_by_scope,
    parse_ps_json,
    scope_exists,
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
        if "ExclusionRange" in cmd:
            return _fail("Exclusion conflict")
        return _ok()

    with patch("services.executor.run_powershell", side_effect=side_effect):
        provisioner = DHCPProvisioner(req=MINIMAL_REQ)
        steps = await provisioner.provision()

    exclusion_steps = [s for s in steps if s.step.startswith("add_exclusion")]
    other_steps = [s for s in steps if not s.step.startswith("add_exclusion")]

    assert all(not s.success for s in exclusion_steps)
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
#  full_scope_from_ps
# --------------------------------------------------------------------------- #

class TestFullScopeFromPs:
    VALID = {
        "ScopeId": "10.0.1.0",
        "Name": "TEST-VLAN",
        "SubnetMask": "255.255.255.0",
        "StartRange": "10.0.1.50",
        "EndRange": "10.0.1.240",
        "State": "Active",
        "LeaseDuration": "8.00:00:00",
        "Description": "Test scope",
    }

    def test_valid_dict_maps_all_base_fields(self):
        result = full_scope_from_ps(self.VALID)
        assert result["scope_id"] == "10.0.1.0"
        assert result["name"] == "TEST-VLAN"
        assert result["subnet_mask"] == "255.255.255.0"
        assert result["start_range"] == "10.0.1.50"
        assert result["end_range"] == "10.0.1.240"
        assert result["state"] == "Active"
        assert result["lease_duration"] == "8.00:00:00"
        assert result["description"] == "Test scope"

    def test_missing_lease_duration_maps_to_none(self):
        d = {k: v for k, v in self.VALID.items() if k != "LeaseDuration"}
        result = full_scope_from_ps(d)
        assert result["lease_duration"] is None

    def test_missing_description_maps_to_none(self):
        d = {k: v for k, v in self.VALID.items() if k != "Description"}
        result = full_scope_from_ps(d)
        assert result["description"] is None

    def test_missing_required_field_raises(self):
        d = {k: v for k, v in self.VALID.items() if k != "ScopeId"}
        with pytest.raises(RuntimeError, match="missing keys"):
            full_scope_from_ps(d)

    def test_missing_multiple_required_fields_raises(self):
        with pytest.raises(RuntimeError, match="missing keys"):
            full_scope_from_ps({})

    def test_does_not_include_option_fields(self):
        """Options/exclusions/failover are not set by this function."""
        result = full_scope_from_ps(self.VALID)
        assert "gateway" not in result
        assert "dns_servers" not in result
        assert "exclusions" not in result


# --------------------------------------------------------------------------- #
#  parse_options_by_scope
# --------------------------------------------------------------------------- #

class TestParseOptionsByScope:
    def test_extracts_gateway_dns_domain(self):
        options = [
            {"ScopeId": "10.0.1.0", "OptionId": 3, "Value": ["10.0.1.1"]},
            {"ScopeId": "10.0.1.0", "OptionId": 6, "Value": ["10.10.1.5", "10.10.1.6"]},
            {"ScopeId": "10.0.1.0", "OptionId": 15, "Value": ["lab.local"]},
        ]
        result = parse_options_by_scope(options)
        assert result["10.0.1.0"]["gateway"] == "10.0.1.1"
        assert result["10.0.1.0"]["dns_servers"] == ["10.10.1.5", "10.10.1.6"]
        assert result["10.0.1.0"]["dns_domain"] == "lab.local"

    def test_multiple_scopes_keyed_separately(self):
        options = [
            {"ScopeId": "10.0.1.0", "OptionId": 3, "Value": ["10.0.1.1"]},
            {"ScopeId": "10.0.2.0", "OptionId": 3, "Value": ["10.0.2.1"]},
        ]
        result = parse_options_by_scope(options)
        assert result["10.0.1.0"]["gateway"] == "10.0.1.1"
        assert result["10.0.2.0"]["gateway"] == "10.0.2.1"

    def test_missing_scope_id_skipped(self):
        options = [{"OptionId": 3, "Value": ["10.0.0.1"]}]  # no ScopeId = server-level option
        result = parse_options_by_scope(options)
        assert result == {}

    def test_empty_value_list_skipped(self):
        options = [{"ScopeId": "10.0.1.0", "OptionId": 3, "Value": []}]
        result = parse_options_by_scope(options)
        assert result["10.0.1.0"]["gateway"] is None

    def test_none_value_skipped(self):
        options = [{"ScopeId": "10.0.1.0", "OptionId": 6, "Value": None}]
        result = parse_options_by_scope(options)
        assert result["10.0.1.0"]["dns_servers"] == []

    def test_unknown_option_id_ignored(self):
        options = [{"ScopeId": "10.0.1.0", "OptionId": 44, "Value": ["something"]}]
        result = parse_options_by_scope(options)
        assert result["10.0.1.0"]["gateway"] is None
        assert result["10.0.1.0"]["dns_servers"] == []
        assert result["10.0.1.0"]["dns_domain"] is None

    def test_empty_input_returns_empty_dict(self):
        assert parse_options_by_scope([]) == {}


# --------------------------------------------------------------------------- #
#  parse_exclusions_by_scope
# --------------------------------------------------------------------------- #

class TestParseExclusionsByScope:
    def test_groups_by_scope_id(self):
        exclusions = [
            {"ScopeId": "10.0.1.0", "StartRange": "10.0.1.1", "EndRange": "10.0.1.10"},
            {"ScopeId": "10.0.1.0", "StartRange": "10.0.1.241", "EndRange": "10.0.1.254"},
        ]
        result = parse_exclusions_by_scope(exclusions)
        assert len(result["10.0.1.0"]) == 2
        assert result["10.0.1.0"][0]["start_range"] == "10.0.1.1"
        assert result["10.0.1.0"][1]["end_range"] == "10.0.1.254"

    def test_multiple_scopes_keyed_separately(self):
        exclusions = [
            {"ScopeId": "10.0.1.0", "StartRange": "10.0.1.1", "EndRange": "10.0.1.10"},
            {"ScopeId": "10.0.2.0", "StartRange": "10.0.2.1", "EndRange": "10.0.2.10"},
        ]
        result = parse_exclusions_by_scope(exclusions)
        assert "10.0.1.0" in result
        assert "10.0.2.0" in result
        assert len(result["10.0.1.0"]) == 1
        assert len(result["10.0.2.0"]) == 1

    def test_missing_scope_id_skipped(self):
        exclusions = [{"StartRange": "10.0.0.1", "EndRange": "10.0.0.10"}]
        result = parse_exclusions_by_scope(exclusions)
        assert result == {}

    def test_empty_input_returns_empty_dict(self):
        assert parse_exclusions_by_scope([]) == {}


# --------------------------------------------------------------------------- #
#  parse_failovers_by_scope
# --------------------------------------------------------------------------- #

class TestParseFailoversByScope:
    def test_single_scope_relationship(self):
        failovers = [{
            "Name": "FO-TEST",
            "PartnerServer": "dhcp02.lab.local",
            "Mode": "HotStandby",
            "State": "Normal",
            "ServerRole": "Active",
            "ReservePercent": 5,
            "MaxClientLeadTime": "1:00:00",
            "ScopeId": "10.0.1.0",
        }]
        result = parse_failovers_by_scope(failovers)
        assert "10.0.1.0" in result
        fo = result["10.0.1.0"]
        assert fo["relationship_name"] == "FO-TEST"
        assert fo["partner_server"] == "dhcp02.lab.local"
        assert fo["mode"] == "HotStandby"
        assert fo["server_role"] == "Active"
        assert fo["reserve_percent"] == 5

    def test_multi_scope_relationship_indexes_each_scope(self):
        """One relationship covering two scopes should appear under both keys."""
        failovers = [{
            "Name": "FO-BRANCH",
            "PartnerServer": "dhcp02.lab.local",
            "Mode": "LoadBalance",
            "State": "Normal",
            "LoadBalancePercent": 50,
            "ScopeId": ["10.0.1.0", "10.0.2.0"],
        }]
        result = parse_failovers_by_scope(failovers)
        assert "10.0.1.0" in result
        assert "10.0.2.0" in result
        assert result["10.0.1.0"]["relationship_name"] == "FO-BRANCH"
        assert result["10.0.2.0"]["relationship_name"] == "FO-BRANCH"
        assert result["10.0.1.0"]["scope_ids"] == ["10.0.1.0", "10.0.2.0"]

    def test_loadbalance_mode_fields(self):
        failovers = [{
            "Name": "FO-LB",
            "PartnerServer": "dhcp02",
            "Mode": "LoadBalance",
            "State": "Normal",
            "LoadBalancePercent": 60,
            "ScopeId": "10.0.1.0",
        }]
        result = parse_failovers_by_scope(failovers)
        fo = result["10.0.1.0"]
        assert fo["load_balance_percent"] == 60
        assert fo["server_role"] is None
        assert fo["reserve_percent"] is None

    def test_empty_input_returns_empty_dict(self):
        assert parse_failovers_by_scope([]) == {}


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
