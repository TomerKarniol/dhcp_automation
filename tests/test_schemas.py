"""Integration tests for Pydantic model validation (models/schemas.py).

No Windows / PowerShell required.
Run with:  pytest tests/test_schemas.py
"""

import pytest
from ipaddress import IPv4Address
from pydantic import ValidationError

from models.schemas import (
    DHCPScopeRequest,
    ExclusionRange,
    FailoverConfig,
    FullScopeDetailResponse,
    FullScopeExclusion,
    FullScopeFailover,
    FullScopeInfo,
    FullScopeListResponse,
    ScopeStateRequest,
)
from services.executor import full_scope_from_ps


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


class TestFullScopeInfo:
    """FullScopeInfo is the rich response model for all GET scope endpoints."""

    PS_SCOPE = {
        "ScopeId": "10.20.120.0",
        "Name": "VLAN-120",
        "SubnetMask": "255.255.255.0",
        "StartRange": "10.20.120.50",
        "EndRange": "10.20.120.240",
        "State": "Active",
        "LeaseDuration": "8.00:00:00",
        "Description": "Engineering floor",
    }

    def test_populated_from_powershell_dict(self):
        info = FullScopeInfo(**full_scope_from_ps(self.PS_SCOPE))
        assert info.scope_id == "10.20.120.0"
        assert info.name == "VLAN-120"
        assert info.state == "Active"
        assert info.lease_duration == "8.00:00:00"
        assert info.description == "Engineering floor"

    def test_optional_fields_default_to_none_or_empty(self):
        info = FullScopeInfo(**full_scope_from_ps(self.PS_SCOPE))
        assert info.gateway is None
        assert info.dns_servers == []
        assert info.dns_domain is None
        assert info.exclusions == []
        assert info.failover is None

    def test_response_uses_snake_case_keys(self):
        info = FullScopeInfo(**full_scope_from_ps(self.PS_SCOPE))
        dumped = info.model_dump()
        assert "scope_id" in dumped
        assert "ScopeId" not in dumped

    def test_fully_populated(self):
        info = FullScopeInfo(
            scope_id="10.20.120.0",
            name="VLAN-120",
            subnet_mask="255.255.255.0",
            start_range="10.20.120.50",
            end_range="10.20.120.240",
            state="Active",
            lease_duration="8.00:00:00",
            description="test",
            gateway="10.20.120.1",
            dns_servers=["10.10.1.5", "10.10.1.6"],
            dns_domain="lab.local",
            exclusions=[
                FullScopeExclusion(start_range="10.20.120.1", end_range="10.20.120.10"),
            ],
            failover=FullScopeFailover(
                relationship_name="FO-VLAN-120",
                partner_server="dhcp02.lab.local",
                mode="HotStandby",
                state="Normal",
                server_role="Active",
                reserve_percent=5,
                max_client_lead_time="1:00:00",
                scope_ids=["10.20.120.0"],
            ),
        )
        assert info.gateway == "10.20.120.1"
        assert info.dns_servers == ["10.10.1.5", "10.10.1.6"]
        assert len(info.exclusions) == 1
        assert info.failover is not None
        assert info.failover.mode == "HotStandby"

    def test_missing_lease_duration_defaults_to_none(self):
        ps_scope = {k: v for k, v in self.PS_SCOPE.items() if k != "LeaseDuration"}
        info = FullScopeInfo(**full_scope_from_ps(ps_scope))
        assert info.lease_duration is None


class TestFullScopeExclusion:
    def test_construction(self):
        exc = FullScopeExclusion(start_range="10.0.0.1", end_range="10.0.0.10")
        assert exc.start_range == "10.0.0.1"
        assert exc.end_range == "10.0.0.10"


class TestFullScopeFailover:
    def test_hotstandby_shape(self):
        fo = FullScopeFailover(
            relationship_name="FO-TEST",
            partner_server="dhcp02.lab.local",
            mode="HotStandby",
            state="Normal",
            server_role="Active",
            reserve_percent=5,
            scope_ids=["10.0.0.0"],
        )
        assert fo.mode == "HotStandby"
        assert fo.server_role == "Active"
        assert fo.load_balance_percent is None

    def test_loadbalance_shape(self):
        fo = FullScopeFailover(
            relationship_name="FO-TEST",
            partner_server="dhcp02.lab.local",
            mode="LoadBalance",
            state="Normal",
            load_balance_percent=50,
            scope_ids=["10.0.0.0"],
        )
        assert fo.mode == "LoadBalance"
        assert fo.load_balance_percent == 50
        assert fo.server_role is None


class TestFullScopeListResponse:
    def test_count_matches_list_length(self):
        scopes = [
            FullScopeInfo(
                scope_id="10.0.1.0", name="A", subnet_mask="255.255.255.0",
                start_range="10.0.1.10", end_range="10.0.1.240", state="Active",
            ),
            FullScopeInfo(
                scope_id="10.0.2.0", name="B", subnet_mask="255.255.255.0",
                start_range="10.0.2.10", end_range="10.0.2.240", state="Active",
            ),
        ]
        resp = FullScopeListResponse(scopes=scopes, count=len(scopes))
        assert resp.count == 2
        assert len(resp.scopes) == 2

    def test_count_mismatch_raises(self):
        scopes = [
            FullScopeInfo(
                scope_id="10.0.1.0", name="A", subnet_mask="255.255.255.0",
                start_range="10.0.1.10", end_range="10.0.1.240", state="Active",
            ),
        ]
        with pytest.raises(ValidationError, match="count"):
            FullScopeListResponse(scopes=scopes, count=99)


class TestFullScopeDetailResponse:
    def test_wraps_single_scope(self):
        scope = FullScopeInfo(
            scope_id="10.0.1.0", name="A", subnet_mask="255.255.255.0",
            start_range="10.0.1.10", end_range="10.0.1.240", state="Active",
        )
        resp = FullScopeDetailResponse(scope=scope)
        assert resp.scope.scope_id == "10.0.1.0"


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
