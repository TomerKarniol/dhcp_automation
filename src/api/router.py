"""Aggregate router – includes all sub-routers."""

from fastapi import APIRouter

from api.routes import dns, exclusions, failover, health, scopes

router = APIRouter()

router.include_router(health.router)
router.include_router(scopes.router)
router.include_router(exclusions.router)
router.include_router(failover.router)
router.include_router(dns.router)
