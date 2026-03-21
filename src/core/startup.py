"""Startup validation — called once from main.py before the app is created.

Validates all values in core/config.py and raises ValueError with a descriptive
message if anything is misconfigured, so the server refuses to start rather than
failing silently on the first API request.
"""

import logging
import os
from ipaddress import IPv4Address

from core import config

_logger = logging.getLogger("dhcp_api.startup")


def validate_config() -> None:
    """Check every config value and collect all errors before raising."""
    errors: list[str] = []

    # Lease
    if not (1 <= config.DEFAULT_LEASE_DURATION_DAYS <= 365):
        errors.append(
            f"DEFAULT_LEASE_DURATION_DAYS={config.DEFAULT_LEASE_DURATION_DAYS!r} "
            "must be between 1 and 365"
        )

    # DNS servers – must be non-empty and all valid IPv4 addresses
    if not config.DEFAULT_DNS_SERVERS:
        errors.append("DEFAULT_DNS_SERVERS must contain at least one entry")
    else:
        for entry in config.DEFAULT_DNS_SERVERS:
            try:
                IPv4Address(entry)
            except ValueError:
                errors.append(
                    f"DEFAULT_DNS_SERVERS contains invalid IPv4 address: {entry!r}"
                )

    # Failover partner – must be non-empty
    if not config.DEFAULT_FAILOVER_PARTNER.strip():
        errors.append("DEFAULT_FAILOVER_PARTNER must not be empty")

    # Failover mode
    if config.DEFAULT_FAILOVER_MODE not in ("HotStandby", "LoadBalance"):
        errors.append(
            f"DEFAULT_FAILOVER_MODE={config.DEFAULT_FAILOVER_MODE!r} "
            "must be 'HotStandby' or 'LoadBalance'"
        )

    # Failover server role
    if config.DEFAULT_FAILOVER_SERVER_ROLE not in ("Active", "Standby"):
        errors.append(
            f"DEFAULT_FAILOVER_SERVER_ROLE={config.DEFAULT_FAILOVER_SERVER_ROLE!r} "
            "must be 'Active' or 'Standby'"
        )

    # Percentages
    if not (0 <= config.DEFAULT_FAILOVER_RESERVE_PERCENT <= 100):
        errors.append(
            f"DEFAULT_FAILOVER_RESERVE_PERCENT={config.DEFAULT_FAILOVER_RESERVE_PERCENT!r} "
            "must be between 0 and 100"
        )
    if not (0 <= config.DEFAULT_FAILOVER_LB_PERCENT <= 100):
        errors.append(
            f"DEFAULT_FAILOVER_LB_PERCENT={config.DEFAULT_FAILOVER_LB_PERCENT!r} "
            "must be between 0 and 100"
        )

    # MCLT
    if config.DEFAULT_FAILOVER_MCLT_MINUTES < 1:
        errors.append(
            f"DEFAULT_FAILOVER_MCLT_MINUTES={config.DEFAULT_FAILOVER_MCLT_MINUTES!r} "
            "must be at least 1"
        )

    # Shared secret – must be >= 8 chars when set
    if (
        config.DEFAULT_FAILOVER_SHARED_SECRET is not None
        and len(config.DEFAULT_FAILOVER_SHARED_SECRET) < 8
    ):
        errors.append(
            f"DEFAULT_FAILOVER_SHARED_SECRET must be at least 8 characters or None "
            f"(current length: {len(config.DEFAULT_FAILOVER_SHARED_SECRET)})"
        )

    # Exclusion offsets – basic structural checks
    if not config.DEFAULT_EXCLUSION_OFFSETS:
        errors.append("DEFAULT_EXCLUSION_OFFSETS must contain at least one entry")
    else:
        for i, off in enumerate(config.DEFAULT_EXCLUSION_OFFSETS):
            start = off.get("start_offset")
            end = off.get("end_offset")
            if start is None or end is None:
                errors.append(
                    f"DEFAULT_EXCLUSION_OFFSETS[{i}] must have 'start_offset' and 'end_offset' keys"
                )
            else:
                if start < 0:
                    errors.append(
                        f"DEFAULT_EXCLUSION_OFFSETS[{i}] start_offset={start} must not be negative"
                    )
                if end < 0:
                    errors.append(
                        f"DEFAULT_EXCLUSION_OFFSETS[{i}] end_offset={end} must not be negative"
                    )
                if start > end:
                    errors.append(
                        f"DEFAULT_EXCLUSION_OFFSETS[{i}] start_offset={start} must be <= end_offset={end}"
                    )

    # API key – must be set in environment (loaded from .env)
    if not os.getenv("DHCP_API_KEY", "").strip():
        errors.append("DHCP_API_KEY environment variable is not set — add it to .env")

    if errors:
        msg = "Invalid configuration — fix before starting the server:\n"
        msg += "\n".join(f"  • {e}" for e in errors)
        raise ValueError(msg)

    _logger.info("Configuration validated OK")
