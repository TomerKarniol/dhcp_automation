"""Centralized default configuration for DHCP provisioning.

Edit these values to match your environment. They are applied automatically
when the caller omits optional fields from the API request.
"""

# --------------------------------------------------------------------------- #
#  Lease defaults
# --------------------------------------------------------------------------- #
DEFAULT_LEASE_DURATION_DAYS: int = 8

# --------------------------------------------------------------------------- #
#  DNS defaults
# --------------------------------------------------------------------------- #
DEFAULT_DNS_SERVERS: list[str] = ["10.10.1.5", "10.10.1.6"]
DEFAULT_DNS_DOMAIN: str = "lab.local"

# --------------------------------------------------------------------------- #
#  Failover defaults
# --------------------------------------------------------------------------- #
DEFAULT_FAILOVER_PARTNER: str = "dhcp02.lab.local"
DEFAULT_FAILOVER_MODE: str = "HotStandby"           # "HotStandby" | "LoadBalance"
DEFAULT_FAILOVER_SERVER_ROLE: str = "Active"         # "Active" | "Standby"  (HotStandby only)
DEFAULT_FAILOVER_RESERVE_PERCENT: int = 5            # HotStandby: % reserved for standby
DEFAULT_FAILOVER_LB_PERCENT: int = 50                # LoadBalance: % handled by this server
DEFAULT_FAILOVER_MCLT_MINUTES: int = 60
DEFAULT_FAILOVER_SHARED_SECRET: str | None = None

# --------------------------------------------------------------------------- #
#  Default exclusion offsets (relative to network address)
#  These are applied when the caller sends no explicit exclusions.
#  Example: for 10.20.120.0/24 with the defaults below, excludes:
#     10.20.120.1  – 10.20.120.10   (infrastructure: gateway, switches, APs)
#     10.20.120.241 – 10.20.120.254  (top-of-range: reserved / static)
#
#  WARNING: these offsets are designed for /24 scopes.
#  For larger subnets (e.g. /16) they will exclude a small block near the
#  bottom of the range instead of the intended top-of-range addresses.
#  For smaller subnets (e.g. /30) the offsets will exceed the subnet size
#  and the request will be rejected at validation time.
#  Always supply explicit exclusions in the API request for non-/24 scopes.
# --------------------------------------------------------------------------- #
DEFAULT_EXCLUSION_OFFSETS: list[dict[str, int]] = [
    {"start_offset": 1, "end_offset": 10},
    {"start_offset": 241, "end_offset": 254},
]
