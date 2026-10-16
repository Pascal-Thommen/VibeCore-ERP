"""
Tests for Mandanten-Zuordnung (TenantResolver) across all routing strategies.
"""

from app.config import Settings
from app.tenant import TenantResolver


def test_tenant_resolved_by_organization_mapping():
    settings = Settings(
        tenant_organization_mapping={"pascal@vibecore.org": "tenant_vibecore_hq"},
        default_tenant_id="tenant_default",
    )
    resolver = TenantResolver(app_settings=settings)

    tenant_id = resolver.resolve("pascal@vibecore.org")
    assert tenant_id == "tenant_vibecore_hq"

    # Case-insensitive
    tenant_id_upper = resolver.resolve("PASCAL@VIBECORE.ORG")
    assert tenant_id_upper == "tenant_vibecore_hq"


def test_tenant_resolved_by_domain_mapping():
    settings = Settings(
        tenant_domain_mapping={"custom-corp.py": "tenant_custom_corp"},
        default_tenant_id="tenant_default",
    )
    resolver = TenantResolver(app_settings=settings)

    tenant_id = resolver.resolve("finance@custom-corp.py")
    assert tenant_id == "tenant_custom_corp"


def test_tenant_resolved_by_org_hint():
    settings = Settings(default_tenant_id="tenant_default")
    resolver = TenantResolver(app_settings=settings)

    tenant_id = resolver.resolve("user@anydomain.com", org_hint="branch_asuncion")
    assert tenant_id == "tenant_branch_asuncion"

    # Hint already with tenant_ prefix
    tenant_id2 = resolver.resolve("user@anydomain.com", org_hint="tenant_branch_ciudad")
    assert tenant_id2 == "tenant_branch_ciudad"


def test_tenant_resolved_for_public_email_providers():
    settings = Settings(
        public_tenant_prefix="tenant_user_",
        tenant_organization_mapping={},  # empty org mapping
    )
    resolver = TenantResolver(app_settings=settings)

    # Gmail user gets personal tenant hash
    t1 = resolver.resolve("freelancer1@gmail.com")
    assert t1.startswith("tenant_user_")

    # Consistent resolution for same user
    t2 = resolver.resolve("freelancer1@gmail.com")
    assert t1 == t2

    # Different users get different personal tenants
    t3 = resolver.resolve("freelancer2@gmail.com")
    assert t1 != t3


def test_tenant_resolved_for_unmapped_corporate_domain():
    settings = Settings(tenant_domain_mapping={}, tenant_organization_mapping={})
    resolver = TenantResolver(app_settings=settings)

    t = resolver.resolve("audit@holding-empresa.com.py")
    assert t == "tenant_holding_empresa_com_py"


def test_tenant_resolution_fallback_on_invalid_email():
    settings = Settings(default_tenant_id="tenant_fallback_global")
    resolver = TenantResolver(app_settings=settings)

    assert resolver.resolve("") == "tenant_fallback_global"
    assert resolver.resolve("not-an-email") == "tenant_fallback_global"
    assert resolver.resolve(None) == "tenant_fallback_global"


def test_tenant_metadata():
    settings = Settings(default_tenant_id="tenant_default", public_tenant_prefix="tenant_user_")
    resolver = TenantResolver(app_settings=settings)

    d1 = resolver.get_tenant_details("tenant_default")
    assert d1["is_default"] is True
    assert d1["is_personal"] is False

    d2 = resolver.get_tenant_details("tenant_user_abc123")
    assert d2["is_default"] is False
    assert d2["is_personal"] is True
