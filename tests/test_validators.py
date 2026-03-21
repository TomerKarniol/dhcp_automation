"""Unit tests for models/validators.py.

These tests run on any OS – no Windows, no PowerShell, no mocking required.
Run with:  pytest tests/test_validators.py
"""

import pytest
from ipaddress import IPv4Address

from models.validators import (
    ExclusionPair,
    build_default_exclusions,
    check_address_in_network,
    check_exclusion_order,
    check_failover_mode_params,
    check_range_order,
    check_subnet_mask,
)


# --------------------------------------------------------------------------- #
#  check_subnet_mask
# --------------------------------------------------------------------------- #

class TestCheckSubnetMask:
    def test_valid_class_c(self):
        mask = IPv4Address("255.255.255.0")
        assert check_subnet_mask(mask) == mask

    def test_valid_class_b(self):
        assert check_subnet_mask(IPv4Address("255.255.0.0")) == IPv4Address("255.255.0.0")

    def test_valid_slash_28(self):
        assert check_subnet_mask(IPv4Address("255.255.255.240")) is not None

    def test_rejects_all_zeros(self):
        with pytest.raises(ValueError, match="cannot be 0.0.0.0"):
            check_subnet_mask(IPv4Address("0.0.0.0"))

    def test_rejects_non_contiguous(self):
        # 255.0.255.0 is not a valid subnet mask
        with pytest.raises(ValueError, match="not a valid contiguous subnet mask"):
            check_subnet_mask(IPv4Address("255.0.255.0"))


# --------------------------------------------------------------------------- #
#  check_range_order
# --------------------------------------------------------------------------- #

class TestCheckRangeOrder:
    def test_valid_order(self):
        check_range_order(IPv4Address("10.0.0.10"), IPv4Address("10.0.0.200"))  # no error

    def test_equal_addresses_raises(self):
        with pytest.raises(ValueError, match="less than end_range"):
            check_range_order(IPv4Address("10.0.0.50"), IPv4Address("10.0.0.50"))

    def test_reversed_order_raises(self):
        with pytest.raises(ValueError, match="less than end_range"):
            check_range_order(IPv4Address("10.0.0.200"), IPv4Address("10.0.0.10"))


# --------------------------------------------------------------------------- #
#  check_address_in_network
# --------------------------------------------------------------------------- #

class TestCheckAddressInNetwork:
    NET = IPv4Address("10.20.30.0")
    MASK = IPv4Address("255.255.255.0")

    def test_valid_host(self):
        check_address_in_network("start_range", IPv4Address("10.20.30.50"), self.NET, self.MASK)

    def test_network_address_rejected(self):
        with pytest.raises(ValueError, match="outside"):
            check_address_in_network("start_range", IPv4Address("10.20.30.0"), self.NET, self.MASK)

    def test_broadcast_address_rejected(self):
        with pytest.raises(ValueError, match="outside"):
            check_address_in_network("end_range", IPv4Address("10.20.30.255"), self.NET, self.MASK)

    def test_different_network_rejected(self):
        with pytest.raises(ValueError, match="outside"):
            check_address_in_network("start_range", IPv4Address("10.20.31.1"), self.NET, self.MASK)


# --------------------------------------------------------------------------- #
#  check_exclusion_order
# --------------------------------------------------------------------------- #

class TestCheckExclusionOrder:
    def test_valid_order(self):
        check_exclusion_order(IPv4Address("10.0.0.1"), IPv4Address("10.0.0.10"))

    def test_equal_is_valid(self):
        check_exclusion_order(IPv4Address("10.0.0.5"), IPv4Address("10.0.0.5"))

    def test_reversed_raises(self):
        with pytest.raises(ValueError, match="must not be greater than end"):
            check_exclusion_order(IPv4Address("10.0.0.10"), IPv4Address("10.0.0.1"))


# --------------------------------------------------------------------------- #
#  build_default_exclusions
# --------------------------------------------------------------------------- #

class TestBuildDefaultExclusions:
    OFFSETS = [
        {"start_offset": 1, "end_offset": 10},
        {"start_offset": 241, "end_offset": 254},
    ]

    def test_returns_correct_count(self):
        result = build_default_exclusions(IPv4Address("10.20.120.0"), self.OFFSETS)
        assert len(result) == 2

    def test_first_range(self):
        result = build_default_exclusions(IPv4Address("10.20.120.0"), self.OFFSETS)
        assert result[0] == ExclusionPair(
            start_address=IPv4Address("10.20.120.1"),
            end_address=IPv4Address("10.20.120.10"),
        )

    def test_second_range(self):
        result = build_default_exclusions(IPv4Address("10.20.120.0"), self.OFFSETS)
        assert result[1] == ExclusionPair(
            start_address=IPv4Address("10.20.120.241"),
            end_address=IPv4Address("10.20.120.254"),
        )

    def test_empty_offsets(self):
        assert build_default_exclusions(IPv4Address("192.168.1.0"), []) == []

    def test_mask_provided_valid_offsets_accepted(self):
        """Offsets within /24 are accepted when mask is provided."""
        mask = IPv4Address("255.255.255.0")
        result = build_default_exclusions(IPv4Address("10.20.120.0"), self.OFFSETS, mask)
        assert len(result) == 2

    def test_mask_provided_offset_outside_subnet_raises(self):
        """Offset 10 falls outside a /30 (only .1–.2 are usable), so it should raise."""
        mask = IPv4Address("255.255.255.252")   # /30: .0 network, .1-.2 hosts, .3 broadcast
        with pytest.raises(ValueError, match="outside"):
            build_default_exclusions(
                IPv4Address("10.0.0.0"),
                [{"start_offset": 1, "end_offset": 10}],
                mask,
            )

    def test_no_mask_skips_subnet_validation(self):
        """Without mask, out-of-range offsets are not caught (backward-compatible)."""
        result = build_default_exclusions(
            IPv4Address("10.0.0.0"),
            [{"start_offset": 1, "end_offset": 10}],
        )
        assert len(result) == 1


# --------------------------------------------------------------------------- #
#  check_failover_mode_params
# --------------------------------------------------------------------------- #

class TestCheckFailoverModeParams:
    def test_hotstandby_active_ok(self):
        check_failover_mode_params("HotStandby", "Active")

    def test_hotstandby_standby_ok(self):
        check_failover_mode_params("HotStandby", "Standby")

    def test_loadbalance_active_ok(self):
        check_failover_mode_params("LoadBalance", "Active")

    def test_loadbalance_standby_raises(self):
        with pytest.raises(ValueError, match="only meaningful for HotStandby"):
            check_failover_mode_params("LoadBalance", "Standby")
