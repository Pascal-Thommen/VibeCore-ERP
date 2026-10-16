"""
VibeCore ERP Auth Adapter - Mandanten-Zuordnung (Tenant Resolver).
Resolves and assigns authenticated users to isolated tenants based on:
1. Exact organization-to-user email mapping.
2. Verified email domain mapping (e.g. @vibecore.org -> tenant_vibecore).
3. Public email domain handling (personal tenant isolation).
4. Dynamic domain slug derivation for business domains.
5. Deterministic fallback to configured default tenant.
"""

import hashlib
import re
from typing import Any

from app.audit import log_audit_event
from app.config import Settings
from app.config import settings as default_settings

PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "protonmail.com",
    "proton.me",
    "mail.com",
    "gmx.de",
    "web.de",
}


class TenantResolver:
    """
    Resolves tenant identifiers for authenticated identities in the VibeCore ecosystem.
    """

    def __init__(self, app_settings: Settings | None = None):
        self.settings = app_settings or default_settings

    @staticmethod
    def _sanitize_slug(text: str) -> str:
        """Sanitizes domain or text into a clean alphanumeric underscore identifier."""
        cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", text).strip("_").lower()
        return cleaned or "default"

    def resolve(self, email: str, org_hint: str | None = None) -> str:
        """
        Resolves the tenant ID for a given user email address and optional organization hint.
        """
        clean_email = email.strip().lower() if email else ""
        if not clean_email or "@" not in clean_email:
            log_audit_event(
                "tenant.resolution_fallback",
                "Invalid email provided for tenant resolution; falling back to default",
                data={"provided_email": email},
            )
            return self.settings.default_tenant_id

        # 1. Exact user email organization mapping
        org_map = {k.strip().lower(): v for k, v in self.settings.tenant_organization_mapping.items()}
        if clean_email in org_map:
            tenant_id = org_map[clean_email]
            log_audit_event(
                "tenant.resolved_by_org_map",
                f"Resolved tenant '{tenant_id}' by organization mapping for {clean_email}",
                data={"email": clean_email, "tenant_id": tenant_id},
            )
            return tenant_id

        # 2. Organization hint validation (if provided)
        if org_hint:
            clean_hint = self._sanitize_slug(org_hint)
            if clean_hint:
                tenant_id = (
                    clean_hint
                    if clean_hint.startswith("tenant_")
                    else f"tenant_{clean_hint}"
                )
                log_audit_event(
                    "tenant.resolved_by_hint",
                    f"Resolved tenant '{tenant_id}' by provided organization hint",
                    data={"email": clean_email, "hint": org_hint, "tenant_id": tenant_id},
                )
                return tenant_id

        # 3. Extract domain
        _, domain = clean_email.split("@", 1)
        domain = domain.strip().lower()

        # 4. Check domain mapping
        domain_map = {
            k.strip().lower(): v for k, v in self.settings.tenant_domain_mapping.items()
        }
        if domain in domain_map:
            tenant_id = domain_map[domain]
            log_audit_event(
                "tenant.resolved_by_domain_map",
                f"Resolved tenant '{tenant_id}' by domain mapping for @{domain}",
                data={"email": clean_email, "domain": domain, "tenant_id": tenant_id},
            )
            return tenant_id

        # 5. Public email domains: isolate into personal user tenant
        if domain in PUBLIC_EMAIL_DOMAINS:
            # Deterministic hash of user email for personal workspace tenant
            email_hash = hashlib.sha256(clean_email.encode("utf-8")).hexdigest()[:12]
            tenant_id = f"{self.settings.public_tenant_prefix}{email_hash}"
            log_audit_event(
                "tenant.resolved_public_user_tenant",
                f"Assigned personal tenant '{tenant_id}' for public domain user",
                data={"email": clean_email, "tenant_id": tenant_id},
            )
            return tenant_id

        # 6. Corporate domain derivation
        clean_domain_slug = self._sanitize_slug(domain)
        tenant_id = f"tenant_{clean_domain_slug}"
        log_audit_event(
            "tenant.resolved_by_corporate_domain",
            f"Derived corporate tenant '{tenant_id}' from domain @{domain}",
            data={"email": clean_email, "domain": domain, "tenant_id": tenant_id},
        )
        return tenant_id

    def get_tenant_details(self, tenant_id: str) -> dict[str, Any]:
        """Returns standard metadata dictionary for a tenant identifier."""
        return {
            "tenant_id": tenant_id,
            "is_default": tenant_id == self.settings.default_tenant_id,
            "is_personal": tenant_id.startswith(self.settings.public_tenant_prefix),
            "isolation_level": "multi_tenant_schema",
        }


tenant_resolver = TenantResolver()
