"""Pydantic model definitions for DHCP API requests and responses.

This module owns only data shape (fields, types, defaults).
All validation logic lives in models.validators and is called from
the Pydantic validator hooks below.
"""

from ipaddress import IPv4Address
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from core import config
from models.validators import (
    build_default_exclusions,
    check_address_in_network,
    check_exclusion_order,
    check_failover_mode_params,
    check_range_order,
    check_subnet_mask,
)


class ExclusionRange(BaseModel):
    """An IP range to exclude from the DHCP scope."""

    start_address: IPv4Address
    end_address: IPv4Address


class FailoverConfig(BaseModel):
    """DHCP failover relationship configuration.

    Mode is chosen by parameter set – mirrors the real cmdlet:
      • HotStandby  → uses server_role + reserve_percent
      • LoadBalance → uses load_balance_percent
    There is NO -Mode parameter on Add-DhcpServerv4Failover.
    """

    partner_server: str = Field(
        default=config.DEFAULT_FAILOVER_PARTNER,
        min_length=1,
        description="FQDN or IP of the partner DHCP server",
    )
    relationship_name: Optional[str] = Field(
        default=None,
        description="Name for the failover relationship (auto-generated if omitted)",
    )
    mode: Literal["HotStandby", "LoadBalance"] = Field(
        default=config.DEFAULT_FAILOVER_MODE,
        description="Determines which parameter set is used (not passed as -Mode)",
    )

    # --- HotStandby params ---
    server_role: Literal["Active", "Standby"] = Field(
        default=config.DEFAULT_FAILOVER_SERVER_ROLE,
        description="Only used when mode=HotStandby",
    )
    reserve_percent: int = Field(
        default=config.DEFAULT_FAILOVER_RESERVE_PERCENT,
        ge=0,
        le=100,
        description="Percentage reserved for standby (HotStandby only)",
    )

    # --- LoadBalance params ---
    load_balance_percent: int = Field(
        default=config.DEFAULT_FAILOVER_LB_PERCENT,
        ge=0,
        le=100,
        description="Percentage of traffic handled by this server (LoadBalance only)",
    )

    max_client_lead_time_minutes: int = Field(
        default=config.DEFAULT_FAILOVER_MCLT_MINUTES,
        ge=1,
        description="MCLT in minutes",
    )
    shared_secret: Optional[str] = Field(
        default=config.DEFAULT_FAILOVER_SHARED_SECRET,
        min_length=8,
        description="Shared secret for the relationship",
    )

    @model_validator(mode="after")
    def _validate_mode_params(self) -> "FailoverConfig":
        check_failover_mode_params(self.mode, self.server_role)
        return self


class DHCPScopeRequest(BaseModel):
    """Request model for creating a new DHCP scope with full configuration."""

    # --- Scope definition ---
    scope_name: str = Field(..., min_length=1, max_length=128)
    network: IPv4Address = Field(..., description="Network address (e.g. 10.20.30.0)")
    subnet_mask: IPv4Address = Field(..., description="Subnet mask (e.g. 255.255.255.0)")
    start_range: IPv4Address = Field(..., description="First IP in the DHCP lease range")
    end_range: IPv4Address = Field(..., description="Last IP in the DHCP lease range")
    lease_duration_days: int = Field(
        default=config.DEFAULT_LEASE_DURATION_DAYS, ge=1, le=365,
    )
    description: Optional[str] = Field(default=None, max_length=256)

    # --- Default gateway ---
    gateway: Optional[IPv4Address] = Field(default=None, description="Default gateway (option 003)")

    # --- DNS ---
    dns_servers: list[IPv4Address] = Field(
        default_factory=lambda: [IPv4Address(s) for s in config.DEFAULT_DNS_SERVERS],
        min_length=1,
    )
    dns_domain: Optional[str] = Field(default=config.DEFAULT_DNS_DOMAIN)

    # --- Exclusion ranges ---
    exclusions: Optional[list[ExclusionRange]] = Field(
        default=None,
        description="IP ranges to exclude. If omitted, default offsets from config are applied.",
    )

    # --- Failover ---
    failover: Optional[FailoverConfig] = Field(
        default=None,
        description="DHCP failover config. Pass {} to use all defaults.",
    )

    @field_validator("subnet_mask")
    @classmethod
    def _validate_subnet_mask(cls, v: IPv4Address) -> IPv4Address:
        return check_subnet_mask(v)

    @model_validator(mode="after")
    def _apply_defaults_and_validate(self) -> "DHCPScopeRequest":
        # Network address must not have host bits set (e.g. 10.0.0.5/24 is invalid)
        if int(self.network) & int(self.subnet_mask) != int(self.network):
            raise ValueError(
                f"network {self.network} has host bits set for mask {self.subnet_mask}. "
                f"Did you mean {IPv4Address(int(self.network) & int(self.subnet_mask))}?"
            )

        # Auto-generate exclusions from config offsets when caller omits them
        if self.exclusions is None:
            pairs = build_default_exclusions(self.network, config.DEFAULT_EXCLUSION_OFFSETS, self.subnet_mask)
            self.exclusions = [
                ExclusionRange(start_address=p.start_address, end_address=p.end_address)
                for p in pairs
            ]

        check_range_order(self.start_range, self.end_range)

        for label, addr in [("start_range", self.start_range), ("end_range", self.end_range)]:
            check_address_in_network(label, addr, self.network, self.subnet_mask)

        for exc in self.exclusions:
            check_exclusion_order(exc.start_address, exc.end_address)
            check_address_in_network(
                "exclusion start", exc.start_address, self.network, self.subnet_mask
            )
            check_address_in_network(
                "exclusion end", exc.end_address, self.network, self.subnet_mask
            )

        return self


# --------------------------------------------------------------------------- #
#  Scope list / detail responses
#  Fields use PowerShell alias names so model_validate(ps_json_dict) works
#  directly without manual mapping.
# --------------------------------------------------------------------------- #

class DHCPScopeInfo(BaseModel):
    """One scope row from Get-DhcpServerv4Scope.

    Field names are snake_case Python names.  Routes are responsible for
    mapping PascalCase PowerShell property names before constructing this model.
    """

    scope_id: str
    name: str
    subnet_mask: str
    start_range: str
    end_range: str
    state: str


class ScopeListResponse(BaseModel):
    scopes: list[DHCPScopeInfo]
    count: int

    @model_validator(mode="after")
    def _validate_count(self) -> "ScopeListResponse":
        if self.count != len(self.scopes):
            raise ValueError(
                f"count ({self.count}) does not match number of scopes ({len(self.scopes)})"
            )
        return self


class ScopeDetailResponse(BaseModel):
    """Full scope detail: scope info + options + exclusion ranges."""

    scope: DHCPScopeInfo
    options: list[Any]      # raw PS JSON – structure varies by option type
    exclusions: list[Any]   # raw PS JSON


# --------------------------------------------------------------------------- #
#  DNS update
# --------------------------------------------------------------------------- #

class DNSUpdateRequest(BaseModel):
    dns_servers: list[IPv4Address] = Field(min_length=1, description="One or more DNS server IPs")
    dns_domain: Optional[str] = Field(default=None, description="DNS suffix (option 015)")


class DNSUpdateResponse(BaseModel):
    scope_id: str
    dns_servers: list[str]
    dns_domain: Optional[str]


# --------------------------------------------------------------------------- #
#  Scope existence check
# --------------------------------------------------------------------------- #

class ScopeExistsResponse(BaseModel):
    scope_id: str
    exists: bool


# --------------------------------------------------------------------------- #
#  Scope state (activate / deactivate)
# --------------------------------------------------------------------------- #

class ScopeStateRequest(BaseModel):
    state: Literal["Active", "Inactive"]


class ScopeStateResponse(BaseModel):
    scope_id: str
    state: str


# --------------------------------------------------------------------------- #
#  Exclusion operation response
# --------------------------------------------------------------------------- #

class ExclusionResponse(BaseModel):
    scope_id: str
    start: str
    end: str
    action: Literal["added", "removed"]


# --------------------------------------------------------------------------- #
#  Failover
# --------------------------------------------------------------------------- #

class FailoverListResponse(BaseModel):
    relationships: list[Any]  # raw PS JSON – field names vary
    count: int

    @model_validator(mode="after")
    def _validate_count(self) -> "FailoverListResponse":
        if self.count != len(self.relationships):
            raise ValueError(
                f"count ({self.count}) does not match number of relationships ({len(self.relationships)})"
            )
        return self


# --------------------------------------------------------------------------- #
#  Provisioning response models
# --------------------------------------------------------------------------- #

class StepResult(BaseModel):
    step: str
    success: bool
    command: str
    detail: Optional[str] = None
    error: Optional[str] = None


class DHCPScopeResponse(BaseModel):
    scope_name: str
    network: str
    overall_success: bool
    steps: list[StepResult]


class DeleteScopeResponse(BaseModel):
    deleted: str
    steps: list[StepResult]
    overall_success: bool
