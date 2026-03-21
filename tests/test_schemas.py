"""Integration tests for Pydantic model validation (models/schemas.py).

No Windows / PowerShell required.
Run with:  pytest tests/test_schemas.py
"""

import pytest
from ipaddress import IPv4Address
from pydantic import ValidationError

from models.schemas import (
    DHCPScopeInfo,
    DHCPScopeRequest,
    ExclusionRange,
    FailoverConfig,
    ScopeListResponse,
    ScopeStateRequest,
)
from services.executor import scope_info_from_ps


MINIMAL = dict(
    scope_name="VLAN-120-Engineering",
    network="10.20.120.0",
    subnet_mask="255.255.255.0",
    start_range="10.20.120.50",
    end_range="10.20.120.240",
    gateway="10.20.120.1",
)


class TestDHCPScopeRequest:
    def test_minimal_request_accepted(self):
        req = DHCPScopeRequest(**MINIMAL)
        assert req.scope_name == "VLAN-120-Engineering"

    def test_default_exclusions_applied_when_omitted(self):
        req = DHCPScopeRequest(**MINIMAL)
        # Two default exclusion ranges should be generated
        assert len(req.exclusions) == 2
        assert req.exclusions[0].start_address == IPv4Address("10.20.120.1")
        assert req.exclusions[0].end_address == IPv4Address("10.20.120.10")

    def test_explicit_exclusions_override_defaults(self):
        req = DHCPScopeRequest(
            **MINIMAL,
            exclusions=[{"start_address": "10.20.120.200", "end_address": "10.20.120.210"}],
        )
        assert len(req.exclusions) == 1
        assert req.exclusions[0].start_address == IPv4Address("10.20.120.200")

    def test_invalid_subnet_mask_raises(self):
        with pytest.raises(ValidationError, match="not a valid contiguous subnet mask"):
            DHCPScopeRequest(**{**MINIMAL, "subnet_mask": "255.0.255.0"})

    def test_reversed_range_raises(self):
        with pytest.raises(ValidationError, match="less than end_range"):
            DHCPScopeRequest(**{**MINIMAL, "start_range": "10.20.120.240", "end_range": "10.20.120.50"})

    def test_range_outside_network_raises(self):
        # end_range is outside the /24 but still > start_range, so the network
        # check fires (not the range-order check which would give a different message)
        with pytest.raises(ValidationError, match="outside"):
            DHCPScopeRequest(**{**MINIMAL, "end_range": "10.20.121.1"})

    def test_default_dns_applied(self):
        req = DHCPScopeRequest(**MINIMAL)
        assert len(req.dns_servers) >= 1

    def test_custom_dns_accepted(self):
        req = DHCPScopeRequest(**MINIMAL, dns_servers=["8.8.8.8", "8.8.4.4"])
        assert IPv4Address("8.8.8.8") in req.dns_servers


class TestFailoverConfig:
    def test_hotstandby_defaults(self):
        fo = FailoverConfig()
        assert fo.mode == "HotStandby"

    def test_loadbalance_standby_role_raises(self):
        with pytest.raises(ValidationError, match="only meaningful for HotStandby"):
            FailoverConfig(mode="LoadBalance", server_role="Standby")

    def test_scope_request_with_failover_defaults(self):
        req = DHCPScopeRequest(**MINIMAL, failover={})
        assert req.failover is not None
        assert req.failover.mode == "HotStandby"


class TestDHCPScopeInfo:
    """DHCPScopeInfo uses PowerShell aliases for population."""

    PS_SCOPE = {
        "ScopeId": "10.20.120.0",
        "Name": "VLAN-120",
        "SubnetMask": "255.255.255.0",
        "StartRange": "10.20.120.50",
        "EndRange": "10.20.120.240",
        "State": "Active",
    }

    def test_populated_from_powershell_dict(self):
        info = DHCPScopeInfo(**scope_info_from_ps(self.PS_SCOPE))
        assert info.scope_id == "10.20.120.0"
        assert info.name == "VLAN-120"
        assert info.state == "Active"

    def test_response_uses_snake_case_keys(self):
        info = DHCPScopeInfo(**scope_info_from_ps(self.PS_SCOPE))
        dumped = info.model_dump()
        assert "scope_id" in dumped
        assert "ScopeId" not in dumped


class TestScopeListResponse:
    def test_count_matches_list_length(self):
        ps_scopes = [
            {"ScopeId": "10.0.1.0", "Name": "A", "SubnetMask": "255.255.255.0",
             "StartRange": "10.0.1.10", "EndRange": "10.0.1.240", "State": "Active"},
            {"ScopeId": "10.0.2.0", "Name": "B", "SubnetMask": "255.255.255.0",
             "StartRange": "10.0.2.10", "EndRange": "10.0.2.240", "State": "Active"},
        ]
        resp = ScopeListResponse(
            scopes=[DHCPScopeInfo(**scope_info_from_ps(s)) for s in ps_scopes],
            count=len(ps_scopes),
        )
        assert resp.count == 2
        assert len(resp.scopes) == 2


class TestScopeStateRequest:
    def test_active_accepted(self):
        req = ScopeStateRequest(state="Active")
        assert req.state == "Active"

    def test_inactive_accepted(self):
        req = ScopeStateRequest(state="Inactive")
        assert req.state == "Inactive"

    def test_invalid_state_rejected(self):
        with pytest.raises(ValidationError):
            ScopeStateRequest(state="Disabled")
