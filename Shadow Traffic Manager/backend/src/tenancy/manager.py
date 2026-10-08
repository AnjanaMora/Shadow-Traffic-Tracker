"""
Shadow Traffic — Tenant & Multi-Site Manager
Role in Architecture:
    Maintains registered sites under a tenant organization. Generates per-site
    ingestion API keys, enforces authentication scoping, and provisions isolated
    baselines, thresholds, and dedicated alert webhooks.
"""

import json
import logging
from pathlib import Path
import secrets
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import (
    RegisteredSiteRecord,
    SiteRegistrationRequest,
    SiteRegistrationResponse,
    SiteUpdateRequest,
    TenantProfile,
)

logger = logging.getLogger("backend.tenancy.manager")


class TenantManager:
    """
    Manages tenant organization websites, API keys, and configuration overrides.
    Persists registered sites to disk so they survive restarts.
    """

    def __init__(self):
        self.data_file = Path(__file__).resolve().parent.parent.parent / "data" / "tenant_sites.json"
        # site_id -> RegisteredSiteRecord
        self.sites: Dict[str, RegisteredSiteRecord] = {}
        self.deleted_sites: set[str] = set()
        self.profile = TenantProfile()

        if self.data_file.exists():
            self._load_from_disk()
        else:
            self._seed_default_sites()
            self._save_to_disk()

    def _load_from_disk(self) -> None:
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    data = []
                else:
                    data = json.loads(content)
                for item in data:
                    rec = RegisteredSiteRecord(**item)
                    self.sites[rec.site_id] = rec
            self.profile.registered_sites_count = len(self.sites)
            logger.info(f"Loaded {len(self.sites)} tenant sites from {self.data_file}")
        except Exception as e:
            logger.error(f"Failed to load tenant sites from {self.data_file}: {e}")
            # Do not reseed if data file exists to respect user deletion of default sites

    def _save_to_disk(self) -> None:
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                data = [rec.model_dump(mode="json") for rec in self.sites.values()]
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save tenant sites to {self.data_file}: {e}")

    def _seed_default_sites(self) -> None:
        defaults = [
            RegisteredSiteRecord(
                site_id="shadow-ecommerce-prod",
                name="E-Commerce Storefront & Checkout",
                target_url="https://store.shadowtraffic.demo",
                api_key="shadow-dev-key-123",
                warning_threshold=60.0,
                critical_threshold=80.0,
                alert_webhook_url=None,
                alert_email="checkout-team@shadowtraffic.demo",
            ),
            RegisteredSiteRecord(
                site_id="shadow-payment-gateway",
                name="Payment Processing API Gateway",
                target_url="https://payments.shadowtraffic.demo",
                api_key="st_live_pay_9a2f1c84",
                warning_threshold=50.0,
                critical_threshold=75.0,
                alert_webhook_url=None,
                alert_email="payments-ops@shadowtraffic.demo",
            ),
            RegisteredSiteRecord(
                site_id="shadow-auth-service",
                name="Identity & SSO Authentication Service",
                target_url="https://auth.shadowtraffic.demo",
                api_key="st_live_auth_3d8e5b20",
                warning_threshold=55.0,
                critical_threshold=70.0,
                alert_webhook_url=None,
                alert_email="security-oncall@shadowtraffic.demo",
            ),
        ]
        for site in defaults:
            self.sites[site.site_id] = site
        self.profile.registered_sites_count = len(self.sites)

    def get_profile(self) -> TenantProfile:
        """Returns the organization profile and site count."""
        self.profile.registered_sites_count = len(self.sites)
        return self.profile

    def list_sites(self) -> List[RegisteredSiteRecord]:
        """Returns all registered sites belonging to the tenant."""
        return [s for s in self.sites.values() if s.is_active]

    def get_site(self, site_id: str) -> Optional[RegisteredSiteRecord]:
        """Retrieves a specific site by identifier."""
        site = self.sites.get(site_id)
        if site and site.is_active:
            return site
        return None

    def register_site(
        self,
        req: SiteRegistrationRequest,
        base_backend_url: str = "http://localhost:8080"
    ) -> SiteRegistrationResponse:
        """
        Registers a new independent website under the tenant organization,
        generates an isolated cryptographic API ingestion key, and constructs
        the agent startup snippet.
        """
        if req.site_id in self.sites and self.sites[req.site_id].is_active:
            raise ValueError(f"Site with identifier '{req.site_id}' is already registered.")

        # Generate per-site cryptographic ingestion key
        generated_key = f"st_live_{secrets.token_hex(12)}"

        record = RegisteredSiteRecord(
            site_id=req.site_id,
            name=req.name,
            target_url=req.target_url,
            api_key=generated_key,
            warning_threshold=req.warning_threshold,
            critical_threshold=req.critical_threshold,
            alert_webhook_url=req.alert_webhook_url,
            alert_email=req.alert_email,
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )

        self.deleted_sites.discard(req.site_id)
        self.sites[req.site_id] = record
        self.profile.registered_sites_count = len(self.sites)
        self._save_to_disk()

        # Build ready-to-run collector startup command
        cmd = (
            f"python -m collector.src.agent --site-id {req.site_id} "
            f"--backend-url {base_backend_url} --api-key {generated_key}"
        )

        logger.info(
            f"Tenant registered new site '{req.site_id}' ('{req.name}') with key prefix '{generated_key[:10]}...'"
        )

        return SiteRegistrationResponse(
            site_id=record.site_id,
            name=record.name,
            target_url=record.target_url,
            api_key=generated_key,
            warning_threshold=record.warning_threshold,
            critical_threshold=record.critical_threshold,
            alert_webhook_url=record.alert_webhook_url,
            alert_email=record.alert_email,
            collector_command=cmd,
            created_at=record.created_at,
        )

    def update_site(self, site_id: str, req: SiteUpdateRequest) -> RegisteredSiteRecord:
        """Updates configurations for an existing site."""
        site = self.get_site(site_id)
        if not site:
            raise KeyError(f"Site '{site_id}' not found.")

        if req.name is not None:
            site.name = req.name
        if req.target_url is not None:
            site.target_url = req.target_url
        if req.warning_threshold is not None:
            site.warning_threshold = req.warning_threshold
        if req.critical_threshold is not None:
            site.critical_threshold = req.critical_threshold
        if req.alert_webhook_url is not None:
            site.alert_webhook_url = req.alert_webhook_url
        if req.alert_email is not None:
            site.alert_email = req.alert_email

        self._save_to_disk()
        logger.info(f"Updated configuration for site '{site_id}'")
        return site

    def delete_site(self, site_id: str) -> bool:
        """Marks a site as deregistered."""
        self.deleted_sites.add(site_id)
        if site_id in self.sites:
            del self.sites[site_id]
            self.profile.registered_sites_count = len(self.sites)
            self._save_to_disk()
            logger.info(f"Deregistered site '{site_id}'")
            return True
        return False

    def is_site_deleted(self, site_id: str) -> bool:
        """Returns True if site was deregistered / deleted."""
        return site_id in self.deleted_sites

    def validate_api_key_for_site(
        self,
        site_id: str,
        api_key: str,
        master_keys: Optional[set] = None
    ) -> bool:
        """
        Enforces tenant authorization:
        1. Accepts the site-specific generated API key.
        2. Accepts tenant master API keys (e.g. from environment).
        """
        if master_keys and api_key in master_keys:
            return True

        site = self.get_site(site_id)
        if site and site.api_key == api_key:
            return True

        return False
