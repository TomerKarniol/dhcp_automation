"""Static fake DHCP scopes used by the /scopes/test endpoint.

All entries conform to DHCPScopeInfo. They are intentionally varied:
different subnets, subnet sizes, states, and naming patterns so that
callers can exercise any client-side rendering logic.
"""

from models.schemas import DHCPScopeInfo

FAKE_SCOPES: list[DHCPScopeInfo] = [
    DHCPScopeInfo(
        scope_id="10.10.10.0",
        name="HQ-Workstations",
        subnet_mask="255.255.255.0",
        start_range="10.10.10.11",
        end_range="10.10.10.240",
        state="Active",
    ),
    DHCPScopeInfo(
        scope_id="10.10.20.0",
        name="HQ-Printers",
        subnet_mask="255.255.255.0",
        start_range="10.10.20.11",
        end_range="10.10.20.50",
        state="Active",
    ),
    DHCPScopeInfo(
        scope_id="10.10.30.0",
        name="HQ-VoIP",
        subnet_mask="255.255.255.0",
        start_range="10.10.30.11",
        end_range="10.10.30.200",
        state="Active",
    ),
    DHCPScopeInfo(
        scope_id="10.20.0.0",
        name="Branch-A-Workstations",
        subnet_mask="255.255.254.0",
        start_range="10.20.0.11",
        end_range="10.20.1.240",
        state="Active",
    ),
    DHCPScopeInfo(
        scope_id="10.20.10.0",
        name="Branch-A-WiFi-Guest",
        subnet_mask="255.255.255.0",
        start_range="10.20.10.11",
        end_range="10.20.10.240",
        state="Active",
    ),
    DHCPScopeInfo(
        scope_id="10.30.0.0",
        name="Branch-B-Workstations",
        subnet_mask="255.255.255.0",
        start_range="10.30.0.11",
        end_range="10.30.0.240",
        state="Inactive",
    ),
    DHCPScopeInfo(
        scope_id="172.16.1.0",
        name="Lab-Servers",
        subnet_mask="255.255.255.0",
        start_range="172.16.1.11",
        end_range="172.16.1.200",
        state="Active",
    ),
    DHCPScopeInfo(
        scope_id="172.16.2.0",
        name="Lab-TestBench",
        subnet_mask="255.255.255.128",
        start_range="172.16.2.11",
        end_range="172.16.2.120",
        state="Inactive",
    ),
    DHCPScopeInfo(
        scope_id="192.168.100.0",
        name="Remote-VPN-Pool",
        subnet_mask="255.255.255.0",
        start_range="192.168.100.50",
        end_range="192.168.100.200",
        state="Active",
    ),
    DHCPScopeInfo(
        scope_id="192.168.200.0",
        name="IoT-Devices",
        subnet_mask="255.255.255.0",
        start_range="192.168.200.11",
        end_range="192.168.200.240",
        state="Active",
    ),
]
