"""Pure validation functions for DHCP data.

All functions in this module operate only on stdlib types (IPv4Address, str, int).
They have no Pydantic dependency and can be unit-tested without any framework setup.

Raises ValueError on invalid input so they can be called directly from
Pydantic @field_validator / @model_validator without any adapter code.
"""

from ipaddress import IPv4Address
from typing import NamedTuple


class ExclusionPair(NamedTuple):
    """Plain-Python result of build_default_exclusions – no Pydantic involved."""
    start_address: IPv4Address
    end_address: IPv4Address


# --------------------------------------------------------------------------- #
#  Subnet mask
# --------------------------------------------------------------------------- #

def check_subnet_mask(mask: IPv4Address) -> IPv4Address:
    """Validate that *mask* is a non-zero contiguous subnet mask."""
    mask_int = int(mask)
    if mask_int == 0:
        raise ValueError("Subnet mask cannot be 0.0.0.0")
    inverted = mask_int ^ 0xFFFFFFFF
    if (inverted & (inverted + 1)) != 0:
        raise ValueError(f"{mask} is not a valid contiguous subnet mask")
    return mask


# --------------------------------------------------------------------------- #
#  IP range ordering
# --------------------------------------------------------------------------- #

def check_range_order(start: IPv4Address, end: IPv4Address) -> None:
    """Validate that *start* is strictly less than *end*."""
    if int(start) >= int(end):
        raise ValueError("start_range must be strictly less than end_range")


def check_address_in_network(
    label: str,
    addr: IPv4Address,
    network: IPv4Address,
    mask: IPv4Address,
) -> None:
    """Validate that *addr* falls inside the usable host range of *network*/*mask*
    (i.e. not the network address itself and not the broadcast address).
    """
    mask_int = int(mask)
    net_int = int(network) & mask_int
    broadcast_int = net_int | (mask_int ^ 0xFFFFFFFF)
    addr_int = int(addr)
    if addr_int <= net_int or addr_int >= broadcast_int:
        raise ValueError(f"{label} ({addr}) is outside {network}/{mask}")


# --------------------------------------------------------------------------- #
#  Exclusion ranges
# --------------------------------------------------------------------------- #

def check_exclusion_order(start: IPv4Address, end: IPv4Address) -> None:
    """Validate that exclusion *start* ≤ *end*."""
    if int(start) > int(end):
        raise ValueError(f"Exclusion start {start} must not be greater than end {end}")


def build_default_exclusions(
    network: IPv4Address,
    offsets: list[dict[str, int]],
    mask: IPv4Address | None = None,
) -> list[ExclusionPair]:
    """Compute default exclusion ranges from *network* address + offset dicts.

    If *mask* is provided, each computed address is validated against the usable
    host range of the subnet — raises ValueError if an offset falls outside.

    Example:
        network = 10.20.120.0
        offsets = [{"start_offset": 1, "end_offset": 10}, ...]
        → ExclusionPair(10.20.120.1, 10.20.120.10), ...
    """
    net_int = int(network)
    pairs: list[ExclusionPair] = []
    for off in offsets:
        start = IPv4Address(net_int + off["start_offset"])
        end = IPv4Address(net_int + off["end_offset"])
        if mask is not None:
            check_address_in_network("default exclusion start", start, network, mask)
            check_address_in_network("default exclusion end", end, network, mask)
        pairs.append(ExclusionPair(start_address=start, end_address=end))
    return pairs


# --------------------------------------------------------------------------- #
#  Failover mode
# --------------------------------------------------------------------------- #

def check_failover_mode_params(mode: str, server_role: str) -> None:
    """Validate that *server_role* is not overridden for LoadBalance mode."""
    if mode == "LoadBalance" and server_role != "Active":
        raise ValueError("server_role is only meaningful for HotStandby mode")
