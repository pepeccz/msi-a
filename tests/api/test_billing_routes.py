"""
Unit tests for Billing API routes — Task 8.

Coverage:
  - Router has all 10 routes registered
  - Webhook endpoint has NO auth dependency
  - All non-webhook endpoints have admin dependency
  - fiscal_details returns values from settings
  - Route prefixes and methods are correct
  - generate_invoice returns status_code=201

Import strategy:
  - Load api.routes.billing via importlib.util.spec_from_file_location to bypass
    api/routes/__init__.py which pulls heavy transitive deps (jose, passlib, etc.)
  - All external modules (stripe, structlog, database, shared) are stubbed in
    sys.modules BEFORE loading the target module.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# Stubs — injected BEFORE billing module is loaded
# =============================================================================

def _stub_if_missing(name: str, obj=None) -> ModuleType:
    if name not in sys.modules:
        m = obj if obj is not None else MagicMock()
        if not isinstance(m, ModuleType):
            m = MagicMock()
        sys.modules[name] = m
    return sys.modules[name]


# structlog
if "structlog" not in sys.modules:
    _sl = ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: MagicMock()
    sys.modules["structlog"] = _sl

# stripe
if "stripe" not in sys.modules:
    _stripe = ModuleType("stripe")
    _stripe.api_key = None
    _stripe.error = ModuleType("stripe.error")
    _stripe.error.StripeError = type("StripeError", (Exception,), {})
    sys.modules["stripe"] = _stripe
    sys.modules["stripe.error"] = _stripe.error

# database stubs
for _mod_name in (
    "database",
    "database.connection",
    "database.models",
):
    _stub_if_missing(_mod_name)

sys.modules["database.connection"].get_async_session = MagicMock()
sys.modules["database.models"].AdminUser = MagicMock()
sys.modules["database.models"].Invoice = MagicMock()

# shared stubs
for _mod_name in ("shared", "shared.config"):
    _stub_if_missing(_mod_name)
_mock_settings = MagicMock()
_mock_settings.COMPANY_LEGAL_NAME = "MSI Automotive SL"
_mock_settings.COMPANY_NIF = "B12345678"
_mock_settings.COMPANY_FISCAL_ADDRESS = "Calle Mayor 1, Madrid"
_mock_settings.CLIENT_COMPANY_NAME = "Acme Corp SL"
_mock_settings.CLIENT_NIF = "A87654321"
_mock_settings.CLIENT_FISCAL_ADDRESS = "Avenida Real 2, Barcelona"
_mock_settings.STRIPE_CUSTOMER_ID = ""
_mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
sys.modules["shared.config"].get_settings = MagicMock(return_value=_mock_settings)

# api.routes.admin stub (require_role)
_API_ROOT = Path(__file__).parent.parent.parent / "api"

if "api" not in sys.modules:
    _api_pkg = ModuleType("api")
    _api_pkg.__path__ = [str(_API_ROOT)]
    _api_pkg.__package__ = "api"
    sys.modules["api"] = _api_pkg

if "api.routes" not in sys.modules:
    _api_routes_pkg = ModuleType("api.routes")
    _api_routes_pkg.__path__ = [str(_API_ROOT / "routes")]
    _api_routes_pkg.__package__ = "api.routes"
    sys.modules["api.routes"] = _api_routes_pkg
if "api.routes.admin" not in sys.modules:
    _admin = ModuleType("api.routes.admin")

    def _require_role(role: str):
        def _dependency():
            pass
        _dependency.__name__ = f"require_role_{role}"
        return _dependency

    _admin.require_role = _require_role
    _admin.get_current_user = MagicMock()
    sys.modules["api.routes.admin"] = _admin

# api.models.billing — load directly via spec to avoid heavy __init__.py imports.
# We deliberately do NOT stub "api.models" here: if the real package isn't loaded
# yet, we create a minimal package stub. If it IS already loaded (e.g. from another
# test that ran first), we leave it alone so the real package stays intact.
if "api.models" not in sys.modules:
    _api_models_stub = ModuleType("api.models")
    # Must set __path__ so Python treats it as a package (allows sub-module imports)
    _api_models_stub.__path__ = [str(Path(__file__).parent.parent.parent / "api" / "models")]
    _api_models_stub.__package__ = "api.models"
    _api_models_stub.__spec__ = None
    sys.modules["api.models"] = _api_models_stub

if "api.models.billing" not in sys.modules:
    _MODELS_PATH = Path(__file__).parent.parent.parent / "api" / "models" / "billing.py"
    _models_spec = importlib.util.spec_from_file_location("api.models.billing", _MODELS_PATH)
    _models_mod = importlib.util.module_from_spec(_models_spec)
    sys.modules["api.models.billing"] = _models_mod
    _models_spec.loader.exec_module(_models_mod)  # type: ignore[union-attr]

# api.services.billing_service stub
if "api.services" not in sys.modules:
    sys.modules["api.services"] = ModuleType("api.services")
_bs = ModuleType("api.services.billing_service")
_bs.BillingService = MagicMock()
sys.modules["api.services.billing_service"] = _bs


# =============================================================================
# Load the billing routes module directly
# =============================================================================

_ROUTES_PATH = Path(__file__).parent.parent.parent / "api" / "routes" / "billing.py"
_routes_spec = importlib.util.spec_from_file_location("api.routes.billing", _ROUTES_PATH)
_routes_mod = importlib.util.module_from_spec(_routes_spec)
sys.modules["api.routes.billing"] = _routes_mod
_routes_spec.loader.exec_module(_routes_mod)  # type: ignore[union-attr]

_router = _routes_mod.router


# =============================================================================
# Helpers
# =============================================================================


def _get_route_map(router):
    """Return a dict of {(method, path): route} for inspection."""
    route_map = {}
    for route in router.routes:
        for method in route.methods or []:
            route_map[(method, route.path)] = route
    return route_map


# =============================================================================
# Route Registration Tests
# =============================================================================


class TestBillingRouterRegistration:
    """The billing router must register exactly 10 routes."""

    def test_router_prefix(self) -> None:
        """Billing router prefix must be /api/billing."""
        assert _router.prefix == "/api/billing"

    def test_router_has_ten_routes(self) -> None:
        """Billing router must expose exactly 10 routes."""
        routes = _router.routes
        assert len(routes) == 10, (
            f"Expected 10 routes, got {len(routes)}: "
            + ", ".join(f"{list(r.methods)} {r.path}" for r in routes)
        )

    def test_list_invoices_route_exists(self) -> None:
        """GET /invoices must be registered."""
        assert ("GET", "/api/billing/invoices") in _get_route_map(_router)

    def test_get_invoice_route_exists(self) -> None:
        """GET /invoices/{invoice_id} must be registered."""
        assert ("GET", "/api/billing/invoices/{invoice_id}") in _get_route_map(_router)

    def test_generate_invoice_route_exists(self) -> None:
        """POST /invoices/generate must be registered."""
        assert ("POST", "/api/billing/invoices/generate") in _get_route_map(_router)

    def test_current_estimate_route_exists(self) -> None:
        """GET /current-estimate must be registered."""
        assert ("GET", "/api/billing/current-estimate") in _get_route_map(_router)

    def test_download_pdf_route_exists(self) -> None:
        """GET /invoices/{invoice_id}/pdf must be registered."""
        assert ("GET", "/api/billing/invoices/{invoice_id}/pdf") in _get_route_map(_router)

    def test_void_invoice_route_exists(self) -> None:
        """POST /invoices/{invoice_id}/void must be registered."""
        assert ("POST", "/api/billing/invoices/{invoice_id}/void") in _get_route_map(_router)

    def test_fiscal_details_route_exists(self) -> None:
        """GET /fiscal-details must be registered."""
        assert ("GET", "/api/billing/fiscal-details") in _get_route_map(_router)

    def test_stripe_setup_session_route_exists(self) -> None:
        """POST /stripe/setup-session must be registered."""
        assert ("POST", "/api/billing/stripe/setup-session") in _get_route_map(_router)

    def test_stripe_status_route_exists(self) -> None:
        """GET /stripe/status must be registered."""
        assert ("GET", "/api/billing/stripe/status") in _get_route_map(_router)

    def test_stripe_webhook_route_exists(self) -> None:
        """POST /stripe/webhook must be registered."""
        assert ("POST", "/api/billing/stripe/webhook") in _get_route_map(_router)


# =============================================================================
# Webhook Has No Auth Dependency
# =============================================================================


class TestWebhookNoAuth:
    """The webhook endpoint must not have auth dependencies."""

    def test_webhook_has_no_route_level_dependencies(self) -> None:
        """POST /stripe/webhook must have zero route-level dependencies."""
        route_map = _get_route_map(_router)
        webhook_route = route_map.get(("POST", "/api/billing/stripe/webhook"))
        assert webhook_route is not None, "Webhook route not found"

        # Route-level deps (from @router.post(..., dependencies=[...]))
        assert webhook_route.dependencies == [], (
            f"Webhook must have no auth dependencies, got: {webhook_route.dependencies}"
        )


# =============================================================================
# Non-Webhook Routes Have Admin Dependency
# =============================================================================


class TestAdminDependencies:
    """All non-webhook endpoints must require admin role via dependant."""

    PROTECTED_ROUTES = [
        ("GET", "/api/billing/invoices"),
        ("GET", "/api/billing/invoices/{invoice_id}"),
        ("POST", "/api/billing/invoices/generate"),
        ("GET", "/api/billing/current-estimate"),
        ("GET", "/api/billing/invoices/{invoice_id}/pdf"),
        ("POST", "/api/billing/invoices/{invoice_id}/void"),
        ("GET", "/api/billing/fiscal-details"),
        ("POST", "/api/billing/stripe/setup-session"),
        ("GET", "/api/billing/stripe/status"),
    ]

    def test_protected_routes_have_dependant_deps(self) -> None:
        """All protected routes must have at least one dependency (admin guard)."""
        route_map = _get_route_map(_router)

        for method, path in self.PROTECTED_ROUTES:
            route = route_map.get((method, path))
            assert route is not None, f"Route {method} {path} not found"

            # FastAPI registers endpoint-level Depends via route.dependant
            has_deps = (
                bool(route.dependencies)
                or (hasattr(route, "dependant") and bool(route.dependant.dependencies))
            )
            assert has_deps, (
                f"{method} {path} has no dependencies — admin guard is missing"
            )


# =============================================================================
# Fiscal Details Returns Settings Values
# =============================================================================


class TestFiscalDetailsLogic:
    """fiscal_details endpoint must return settings values."""

    def test_fiscal_details_returns_settings_data(self) -> None:
        """fiscal_details must read COMPANY_* and CLIENT_* from settings."""
        fiscal_details = _routes_mod.fiscal_details

        mock_admin_user = MagicMock()

        result = asyncio.run(fiscal_details(_=mock_admin_user))

        assert result.company.name == "MSI Automotive SL"
        assert result.company.nif == "B12345678"
        assert result.company.address == "Calle Mayor 1, Madrid"
        assert result.client.name == "Acme Corp SL"
        assert result.client.nif == "A87654321"
        assert result.client.address == "Avenida Real 2, Barcelona"


# =============================================================================
# Generate Invoice status code
# =============================================================================


class TestGenerateInvoiceStatusCode:
    """POST /invoices/generate must return 201."""

    def test_generate_invoice_returns_201(self) -> None:
        """generate_invoice route must declare status_code=201."""
        route_map = _get_route_map(_router)
        route = route_map.get(("POST", "/api/billing/invoices/generate"))
        assert route is not None, "POST /api/billing/invoices/generate not found"
        assert route.status_code == 201, (
            f"Expected status_code=201, got {route.status_code}"
        )
