"""HTTP-level tests for the FastAPI routes.

Uses FastAPI's TestClient + mock – no Windows / PowerShell required.
Run with:  pytest tests/test_routes.py
"""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from helpers import _fail, _ok
from main import app
from models.schemas import FullScopeInfo
from services.executor import PowerShellUnavailableError, ScopeNotFoundError

client = TestClient(app, headers={"X-API-Key": "BALBALA"})
unauthenticated_client = TestClient(app, raise_server_exceptions=False)


SCOPE_PAYLOAD = {
    "scope_name": "VLAN-99-Test",
    "network": "10.99.0.0",
    "subnet_mask": "255.255.255.0",
    "start_range": "10.99.0.50",
    "end_range": "10.99.0.240",
    "gateway": "10.99.0.1",
    "failover": None,
}

# Minimal FullScopeInfo used across multiple test classes
FAKE_SCOPE = FullScopeInfo(
    scope_id="10.99.0.0",
    name="VLAN-99-Test",
    subnet_mask="255.255.255.0",
    start_range="10.99.0.50",
    end_range="10.99.0.240",
    state="Active",
    lease_duration="8.00:00:00",
    gateway="10.99.0.1",
    dns_servers=["10.10.1.5", "10.10.1.6"],
    dns_domain="lab.local",
)


# --------------------------------------------------------------------------- #
#  Authentication
# --------------------------------------------------------------------------- #

class TestAuthentication:
    def test_missing_api_key_returns_401(self):
        resp = unauthenticated_client.get("/health")
        assert resp.status_code == 401

    def test_wrong_api_key_returns_401(self):
        resp = unauthenticated_client.get("/health", headers={"X-API-Key": "wrongkey"})
        assert resp.status_code == 401


# --------------------------------------------------------------------------- #
#  GET /health
# --------------------------------------------------------------------------- #

class TestHealth:
    def test_healthy_returns_200(self):
        with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
            mock_ps.return_value = _ok("IsDomainJoined: True")
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_unhealthy_returns_503(self):
        with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
            mock_ps.return_value = _fail("DHCP service not running")
            resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "unhealthy"


# --------------------------------------------------------------------------- #
#  POST /scopes
# --------------------------------------------------------------------------- #

class TestCreateScope:
    def test_full_success_returns_201(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _ok()
                resp = client.post("/scopes", json=SCOPE_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["overall_success"] is True
        assert body["scope_name"] == "VLAN-99-Test"

    def test_create_scope_critical_failure_returns_500(self):
        """create_scope step failure → nothing was created → 500."""
        call_count = 0

        async def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fail("Scope creation failed")
            return _ok()

        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            with patch("services.executor.run_powershell", side_effect=side_effect):
                resp = client.post("/scopes", json=SCOPE_PAYLOAD)
        assert resp.status_code == 500

    def test_partial_failure_returns_207(self):
        """Scope created but a non-critical step (exclusion) fails → 207."""
        async def side_effect(cmd, **kwargs):
            if "ExclusionRange" in cmd:
                return _fail("Exclusion conflict")
            return _ok()

        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            with patch("services.executor.run_powershell", side_effect=side_effect):
                resp = client.post("/scopes", json=SCOPE_PAYLOAD)
        assert resp.status_code == 207
        assert resp.json()["overall_success"] is False

    def test_existing_scope_returns_409(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            resp = client.post("/scopes", json=SCOPE_PAYLOAD)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_race_condition_returns_409(self):
        """If a scope is created between the exists-check and Add-DhcpServerv4Scope
        (TOCTOU), the 'already exists' PS error should map to 409, not 500."""
        async def side_effect(cmd, **kwargs):
            if "Add-DhcpServerv4Scope" in cmd:
                return _fail("The specified scope already exists.")
            return _ok()

        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            with patch("services.executor.run_powershell", side_effect=side_effect):
                resp = client.post("/scopes", json=SCOPE_PAYLOAD)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_invalid_payload_returns_422(self):
        resp = client.post("/scopes", json={"scope_name": "bad"})
        assert resp.status_code == 422

    def test_invalid_subnet_mask_returns_422(self):
        payload = {**SCOPE_PAYLOAD, "subnet_mask": "255.0.255.0"}
        resp = client.post("/scopes", json=payload)
        assert resp.status_code == 422

    def test_powershell_unavailable_returns_503(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, side_effect=RuntimeError("powershell.exe not found")):
            resp = client.post("/scopes", json=SCOPE_PAYLOAD)
        assert resp.status_code == 503


# --------------------------------------------------------------------------- #
#  GET /scopes
# --------------------------------------------------------------------------- #

class TestListScopes:
    def test_success_returns_structured_response(self):
        with patch("services.executor.build_full_scope_list", new_callable=AsyncMock, return_value=[FAKE_SCOPE]):
            resp = client.get("/scopes")
        assert resp.status_code == 200
        body = resp.json()
        assert "scopes" in body
        assert body["count"] == 1
        scope = body["scopes"][0]
        assert scope["scope_id"] == "10.99.0.0"
        assert scope["gateway"] == "10.99.0.1"
        assert scope["dns_servers"] == ["10.10.1.5", "10.10.1.6"]
        assert scope["dns_domain"] == "lab.local"

    def test_empty_server_returns_empty_list(self):
        with patch("services.executor.build_full_scope_list", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/scopes")
        assert resp.status_code == 200
        assert resp.json() == {"scopes": [], "count": 0}

    def test_powershell_failure_returns_500(self):
        with patch("services.executor.build_full_scope_list", new_callable=AsyncMock, side_effect=RuntimeError("PS failed")):
            resp = client.get("/scopes")
        assert resp.status_code == 500

    def test_powershell_unavailable_returns_503(self):
        with patch("services.executor.build_full_scope_list", new_callable=AsyncMock, side_effect=PowerShellUnavailableError("powershell.exe not found")):
            resp = client.get("/scopes")
        assert resp.status_code == 503


# --------------------------------------------------------------------------- #
#  GET /scopes/{scope_id}
# --------------------------------------------------------------------------- #

class TestGetScope:
    def test_scope_found_returns_full_detail(self):
        with patch("services.executor.build_full_scope_detail", new_callable=AsyncMock, return_value=FAKE_SCOPE):
            resp = client.get("/scopes/10.99.0.0")
        assert resp.status_code == 200
        body = resp.json()
        assert "scope" in body
        scope = body["scope"]
        assert scope["scope_id"] == "10.99.0.0"
        assert scope["gateway"] == "10.99.0.1"
        assert scope["dns_servers"] == ["10.10.1.5", "10.10.1.6"]
        assert "exclusions" in scope
        assert "failover" in scope
        # Old response structure is gone
        assert "options" not in body

    def test_scope_not_found_returns_404(self):
        with patch("services.executor.build_full_scope_detail", new_callable=AsyncMock, side_effect=ScopeNotFoundError("not found")):
            resp = client.get("/scopes/10.99.0.0")
        assert resp.status_code == 404

    def test_powershell_unavailable_returns_503(self):
        with patch("services.executor.build_full_scope_detail", new_callable=AsyncMock, side_effect=PowerShellUnavailableError("powershell.exe not found")):
            resp = client.get("/scopes/10.99.0.0")
        assert resp.status_code == 503

    def test_invalid_scope_id_returns_422(self):
        resp = client.get("/scopes/not-an-ip")
        assert resp.status_code == 422


# --------------------------------------------------------------------------- #
#  GET /scopes/test
# --------------------------------------------------------------------------- #

class TestGetTestScopes:
    def test_returns_10_scopes(self):
        resp = client.get("/scopes/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 10
        assert len(body["scopes"]) == 10

    def test_each_scope_has_full_shape(self):
        resp = client.get("/scopes/test")
        for scope in resp.json()["scopes"]:
            assert "scope_id" in scope
            assert "gateway" in scope
            assert "dns_servers" in scope
            assert "dns_domain" in scope
            assert "exclusions" in scope
            assert "failover" in scope
            assert "lease_duration" in scope


# --------------------------------------------------------------------------- #
#  GET /scopes/{scope_id}/exists
# --------------------------------------------------------------------------- #

class TestScopeExists:
    def test_scope_found_returns_true(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            resp = client.get("/scopes/10.99.0.0/exists")
        assert resp.status_code == 200
        assert resp.json() == {"scope_id": "10.99.0.0", "exists": True}

    def test_scope_not_found_returns_false(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            resp = client.get("/scopes/10.99.0.0/exists")
        assert resp.status_code == 200
        assert resp.json() == {"scope_id": "10.99.0.0", "exists": False}

    def test_powershell_unavailable_returns_503(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, side_effect=RuntimeError("powershell.exe not found")):
            resp = client.get("/scopes/10.99.0.0/exists")
        assert resp.status_code == 503

    def test_invalid_scope_id_returns_422(self):
        resp = client.get("/scopes/not-an-ip/exists")
        assert resp.status_code == 422


# --------------------------------------------------------------------------- #
#  DELETE /scopes/{scope_id}
# --------------------------------------------------------------------------- #

class TestDeleteScope:
    def test_success_returns_200(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _ok()
                resp = client.delete("/scopes/10.99.0.0")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] == "10.99.0.0"
        assert body["overall_success"] is True

    def test_scope_not_found_returns_404(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            resp = client.delete("/scopes/10.99.0.0")
        assert resp.status_code == 404

    def test_invalid_scope_id_returns_422(self):
        resp = client.delete("/scopes/not-an-ip")
        assert resp.status_code == 422

    def test_failover_cleanup_precedes_scope_removal(self):
        captured = []

        async def capture(cmd, **kwargs):
            captured.append(cmd)
            return _ok()

        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", side_effect=capture):
                client.delete("/scopes/10.99.0.0")

        assert any("Failover" in cmd or "failover" in cmd.lower() for cmd in captured), \
            "Expected a failover removal command"
        failover_idx = next(i for i, c in enumerate(captured) if "Failover" in c or "failover" in c.lower())
        scope_idx = next(i for i, c in enumerate(captured) if "Remove-DhcpServerv4Scope" in c)
        assert failover_idx < scope_idx


# --------------------------------------------------------------------------- #
#  PATCH /scopes/{scope_id}/dns
# --------------------------------------------------------------------------- #

class TestUpdateDNS:
    def test_dns_update_success(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _ok()
                resp = client.patch(
                    "/scopes/10.99.0.0/dns",
                    json={"dns_servers": ["10.10.1.5", "10.10.1.6"], "dns_domain": "lab.local"},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["scope_id"] == "10.99.0.0"
        assert "10.10.1.5" in body["dns_servers"]
        assert body["dns_domain"] == "lab.local"

    def test_dns_update_without_domain(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _ok()
                resp = client.patch(
                    "/scopes/10.99.0.0/dns",
                    json={"dns_servers": ["8.8.8.8"]},
                )
        assert resp.status_code == 200
        assert resp.json()["dns_domain"] is None

    def test_dns_update_failure_returns_500(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _fail("DNS update failed")
                resp = client.patch(
                    "/scopes/10.99.0.0/dns",
                    json={"dns_servers": ["10.10.1.5"]},
                )
        assert resp.status_code == 500

    def test_scope_not_found_returns_404(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            resp = client.patch(
                "/scopes/10.99.0.0/dns",
                json={"dns_servers": ["10.10.1.5"]},
            )
        assert resp.status_code == 404

    def test_invalid_scope_id_returns_422(self):
        resp = client.patch("/scopes/not-an-ip/dns", json={"dns_servers": ["10.10.1.5"]})
        assert resp.status_code == 422

    def test_empty_dns_list_rejected(self):
        resp = client.patch("/scopes/10.99.0.0/dns", json={"dns_servers": []})
        assert resp.status_code == 422

    def test_command_contains_scope_id_and_dns(self):
        captured = []

        async def capture(cmd, **kwargs):
            captured.append(cmd)
            return _ok()

        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", side_effect=capture):
                client.patch(
                    "/scopes/10.99.0.0/dns",
                    json={"dns_servers": ["10.10.1.5", "10.10.1.6"], "dns_domain": "corp.local"},
                )

        assert len(captured) == 1
        assert "10.99.0.0" in captured[0]
        assert "10.10.1.5,10.10.1.6" in captured[0]
        assert "corp.local" in captured[0]


# --------------------------------------------------------------------------- #
#  POST/DELETE /scopes/{scope_id}/exclusions
# --------------------------------------------------------------------------- #

class TestExclusions:
    def test_add_exclusion_success(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _ok()
                resp = client.post(
                    "/scopes/10.99.0.0/exclusions",
                    params={"start": "10.99.0.200", "end": "10.99.0.210"},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "added"
        assert body["scope_id"] == "10.99.0.0"

    def test_add_exclusion_scope_not_found_returns_404(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            resp = client.post(
                "/scopes/10.99.0.0/exclusions",
                params={"start": "10.99.0.200", "end": "10.99.0.210"},
            )
        assert resp.status_code == 404

    def test_add_exclusion_active_lease_returns_409(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _fail("The specified IP address range is currently in use.")
                resp = client.post(
                    "/scopes/10.99.0.0/exclusions",
                    params={"start": "10.99.0.200", "end": "10.99.0.210"},
                )
        assert resp.status_code == 409
        assert "active leases" in resp.json()["detail"]

    def test_add_exclusion_invalid_scope_id_returns_422(self):
        resp = client.post(
            "/scopes/not-an-ip/exclusions",
            params={"start": "10.99.0.200", "end": "10.99.0.210"},
        )
        assert resp.status_code == 422

    def test_add_exclusion_invalid_start_ip_returns_422(self):
        resp = client.post(
            "/scopes/10.99.0.0/exclusions",
            params={"start": "not-an-ip", "end": "10.99.0.210"},
        )
        assert resp.status_code == 422

    def test_add_exclusion_reversed_range_returns_422(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            resp = client.post(
                "/scopes/10.99.0.0/exclusions",
                params={"start": "10.99.0.210", "end": "10.99.0.200"},
            )
        assert resp.status_code == 422

    def test_remove_exclusion_success(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _ok()
                resp = client.delete(
                    "/scopes/10.99.0.0/exclusions",
                    params={"start": "10.99.0.200", "end": "10.99.0.210"},
                )
        assert resp.status_code == 200
        assert resp.json()["action"] == "removed"

    def test_remove_exclusion_not_found_returns_404(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _fail("The specified range is not present in the DHCP server")
                resp = client.delete(
                    "/scopes/10.99.0.0/exclusions",
                    params={"start": "10.99.0.200", "end": "10.99.0.210"},
                )
        assert resp.status_code == 404

    def test_remove_exclusion_scope_not_found_returns_404(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            resp = client.delete(
                "/scopes/10.99.0.0/exclusions",
                params={"start": "10.99.0.200", "end": "10.99.0.210"},
            )
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
#  PATCH /scopes/{scope_id}/state
# --------------------------------------------------------------------------- #

class TestScopeState:
    def test_set_active_returns_200(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _ok()
                resp = client.patch("/scopes/10.99.0.0/state", json={"state": "Active"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["scope_id"] == "10.99.0.0"
        assert body["state"] == "Active"

    def test_set_inactive_returns_200(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
                mock_ps.return_value = _ok()
                resp = client.patch("/scopes/10.99.0.0/state", json={"state": "Inactive"})
        assert resp.status_code == 200
        assert resp.json()["state"] == "Inactive"

    def test_scope_not_found_returns_404(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=False):
            resp = client.patch("/scopes/10.99.0.0/state", json={"state": "Active"})
        assert resp.status_code == 404

    def test_invalid_state_value_returns_422(self):
        with patch("services.executor.scope_exists", new_callable=AsyncMock, return_value=True):
            resp = client.patch("/scopes/10.99.0.0/state", json={"state": "Disabled"})
        assert resp.status_code == 422

    def test_invalid_scope_id_returns_422(self):
        resp = client.patch("/scopes/not-an-ip/state", json={"state": "Active"})
        assert resp.status_code == 422


# --------------------------------------------------------------------------- #
#  GET /failover
# --------------------------------------------------------------------------- #

class TestFailover:
    def test_success_returns_structured_response(self):
        fo_json = '[{"Name":"FO-VLAN-99","PartnerServer":"dhcp02","Mode":"HotStandby","ScopeId":"10.99.0.0","State":"Normal"}]'
        with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
            mock_ps.return_value = _ok(fo_json)
            resp = client.get("/failover")
        assert resp.status_code == 200
        body = resp.json()
        assert "relationships" in body
        assert body["count"] == 1

    def test_powershell_failure_returns_500(self):
        with patch("services.executor.run_powershell", new_callable=AsyncMock) as mock_ps:
            mock_ps.return_value = _fail()
            resp = client.get("/failover")
        assert resp.status_code == 500
