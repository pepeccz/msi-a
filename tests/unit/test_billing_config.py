"""
Tests for Billing System Config Settings — Task 1

Verifies all 21 new billing fields exist on Settings with correct defaults.

Fields covered:
  Billing & Invoicing (5): MONTHLY_MAINTENANCE_EUR, INVOICE_PREFIX, IVA_RATE,
                            INVOICES_DIR, PAYMENT_DUE_DAYS
  Stripe (5):              STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY,
                            STRIPE_WEBHOOK_SECRET, STRIPE_TAX_RATE_ID,
                            STRIPE_CUSTOMER_ID
  Fiscal Compliance (6):   COMPANY_NIF, COMPANY_LEGAL_NAME, COMPANY_FISCAL_ADDRESS,
                            CLIENT_NIF, CLIENT_COMPANY_NAME, CLIENT_FISCAL_ADDRESS
  Email / SMTP (5):        OPERATOR_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER,
                            SMTP_PASSWORD
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any
from unittest.mock import patch


def _make_settings(**overrides: Any):
    """Return a fresh Settings instance with given env var overrides.

    Bypasses lru_cache and skips .env file to guarantee isolation.
    """
    from shared.config import Settings

    billing_keys = {
        "MONTHLY_MAINTENANCE_EUR",
        "INVOICE_PREFIX",
        "IVA_RATE",
        "INVOICES_DIR",
        "PAYMENT_DUE_DAYS",
        "STRIPE_SECRET_KEY",
        "STRIPE_PUBLISHABLE_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_TAX_RATE_ID",
        "STRIPE_CUSTOMER_ID",
        "COMPANY_NIF",
        "COMPANY_LEGAL_NAME",
        "COMPANY_FISCAL_ADDRESS",
        "CLIENT_NIF",
        "CLIENT_COMPANY_NAME",
        "CLIENT_FISCAL_ADDRESS",
        "OPERATOR_EMAIL",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
    }

    base_env = {k: v for k, v in os.environ.items() if k not in billing_keys}
    base_env.update({k: str(v) for k, v in overrides.items()})

    with patch.dict(os.environ, base_env, clear=True):
        return Settings(
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
            REDIS_URL="redis://localhost:6379/0",
            CHATWOOT_API_URL="http://localhost",
            CHATWOOT_API_TOKEN="test",
            CHATWOOT_ACCOUNT_ID="1",
            CHATWOOT_INBOX_ID="1",
            CHATWOOT_WEBHOOK_TOKEN="test",
            ADMIN_JWT_SECRET="a" * 32,
            _env_file=None,
        )


# =============================================================================
# Field Declaration Tests
# =============================================================================


class TestBillingFieldsExistInModel:
    """All 21 billing fields must be declared in Settings.model_fields."""

    def test_monthly_maintenance_eur_field_exists(self) -> None:
        from shared.config import Settings

        assert "MONTHLY_MAINTENANCE_EUR" in Settings.model_fields

    def test_invoice_prefix_field_exists(self) -> None:
        from shared.config import Settings

        assert "INVOICE_PREFIX" in Settings.model_fields

    def test_iva_rate_field_exists(self) -> None:
        from shared.config import Settings

        assert "IVA_RATE" in Settings.model_fields

    def test_invoices_dir_field_exists(self) -> None:
        from shared.config import Settings

        assert "INVOICES_DIR" in Settings.model_fields

    def test_payment_due_days_field_exists(self) -> None:
        from shared.config import Settings

        assert "PAYMENT_DUE_DAYS" in Settings.model_fields

    def test_stripe_secret_key_field_exists(self) -> None:
        from shared.config import Settings

        assert "STRIPE_SECRET_KEY" in Settings.model_fields

    def test_stripe_publishable_key_field_exists(self) -> None:
        from shared.config import Settings

        assert "STRIPE_PUBLISHABLE_KEY" in Settings.model_fields

    def test_stripe_webhook_secret_field_exists(self) -> None:
        from shared.config import Settings

        assert "STRIPE_WEBHOOK_SECRET" in Settings.model_fields

    def test_stripe_tax_rate_id_field_exists(self) -> None:
        from shared.config import Settings

        assert "STRIPE_TAX_RATE_ID" in Settings.model_fields

    def test_stripe_customer_id_field_exists(self) -> None:
        from shared.config import Settings

        assert "STRIPE_CUSTOMER_ID" in Settings.model_fields

    def test_company_nif_field_exists(self) -> None:
        from shared.config import Settings

        assert "COMPANY_NIF" in Settings.model_fields

    def test_company_legal_name_field_exists(self) -> None:
        from shared.config import Settings

        assert "COMPANY_LEGAL_NAME" in Settings.model_fields

    def test_company_fiscal_address_field_exists(self) -> None:
        from shared.config import Settings

        assert "COMPANY_FISCAL_ADDRESS" in Settings.model_fields

    def test_client_nif_field_exists(self) -> None:
        from shared.config import Settings

        assert "CLIENT_NIF" in Settings.model_fields

    def test_client_company_name_field_exists(self) -> None:
        from shared.config import Settings

        assert "CLIENT_COMPANY_NAME" in Settings.model_fields

    def test_client_fiscal_address_field_exists(self) -> None:
        from shared.config import Settings

        assert "CLIENT_FISCAL_ADDRESS" in Settings.model_fields

    def test_operator_email_field_exists(self) -> None:
        from shared.config import Settings

        assert "OPERATOR_EMAIL" in Settings.model_fields

    def test_smtp_host_field_exists(self) -> None:
        from shared.config import Settings

        assert "SMTP_HOST" in Settings.model_fields

    def test_smtp_port_field_exists(self) -> None:
        from shared.config import Settings

        assert "SMTP_PORT" in Settings.model_fields

    def test_smtp_user_field_exists(self) -> None:
        from shared.config import Settings

        assert "SMTP_USER" in Settings.model_fields

    def test_smtp_password_field_exists(self) -> None:
        from shared.config import Settings

        assert "SMTP_PASSWORD" in Settings.model_fields


# =============================================================================
# Default Value Tests
# =============================================================================


class TestBillingDefaults:
    """All billing fields must have correct defaults when no env vars are set."""

    # Billing & Invoicing
    def test_monthly_maintenance_eur_default(self) -> None:
        """MONTHLY_MAINTENANCE_EUR must default to Decimal('50.00')."""
        settings = _make_settings()
        assert settings.MONTHLY_MAINTENANCE_EUR == Decimal("50.00"), (
            f"Expected Decimal('50.00') but got {settings.MONTHLY_MAINTENANCE_EUR!r}"
        )

    def test_invoice_prefix_default(self) -> None:
        """INVOICE_PREFIX must default to 'MSI'."""
        settings = _make_settings()
        assert settings.INVOICE_PREFIX == "MSI", (
            f"Expected 'MSI' but got {settings.INVOICE_PREFIX!r}"
        )

    def test_iva_rate_default(self) -> None:
        """IVA_RATE must default to Decimal('21.00')."""
        settings = _make_settings()
        assert settings.IVA_RATE == Decimal("21.00"), (
            f"Expected Decimal('21.00') but got {settings.IVA_RATE!r}"
        )

    def test_invoices_dir_default(self) -> None:
        """INVOICES_DIR must default to './invoices'."""
        settings = _make_settings()
        assert settings.INVOICES_DIR == "./invoices", (
            f"Expected './invoices' but got {settings.INVOICES_DIR!r}"
        )

    def test_payment_due_days_default(self) -> None:
        """PAYMENT_DUE_DAYS must default to 15."""
        settings = _make_settings()
        assert settings.PAYMENT_DUE_DAYS == 15, (
            f"Expected 15 but got {settings.PAYMENT_DUE_DAYS}"
        )

    # Stripe
    def test_stripe_secret_key_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.STRIPE_SECRET_KEY == ""

    def test_stripe_publishable_key_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.STRIPE_PUBLISHABLE_KEY == ""

    def test_stripe_webhook_secret_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.STRIPE_WEBHOOK_SECRET == ""

    def test_stripe_tax_rate_id_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.STRIPE_TAX_RATE_ID == ""

    def test_stripe_customer_id_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.STRIPE_CUSTOMER_ID == ""

    # Fiscal Compliance
    def test_company_nif_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.COMPANY_NIF == ""

    def test_company_legal_name_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.COMPANY_LEGAL_NAME == ""

    def test_company_fiscal_address_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.COMPANY_FISCAL_ADDRESS == ""

    def test_client_nif_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.CLIENT_NIF == ""

    def test_client_company_name_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.CLIENT_COMPANY_NAME == ""

    def test_client_fiscal_address_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.CLIENT_FISCAL_ADDRESS == ""

    # Email / SMTP
    def test_operator_email_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.OPERATOR_EMAIL == ""

    def test_smtp_host_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.SMTP_HOST == ""

    def test_smtp_port_default(self) -> None:
        """SMTP_PORT must default to 587."""
        settings = _make_settings()
        assert settings.SMTP_PORT == 587, (
            f"Expected 587 but got {settings.SMTP_PORT}"
        )

    def test_smtp_user_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.SMTP_USER == ""

    def test_smtp_password_default_is_empty(self) -> None:
        settings = _make_settings()
        assert settings.SMTP_PASSWORD == ""


# =============================================================================
# Type Tests
# =============================================================================


class TestBillingFieldTypes:
    """Billing fields must have correct Python types."""

    def test_monthly_maintenance_eur_is_decimal(self) -> None:
        settings = _make_settings()
        assert isinstance(settings.MONTHLY_MAINTENANCE_EUR, Decimal), (
            f"Expected Decimal but got {type(settings.MONTHLY_MAINTENANCE_EUR)}"
        )

    def test_iva_rate_is_decimal(self) -> None:
        settings = _make_settings()
        assert isinstance(settings.IVA_RATE, Decimal), (
            f"Expected Decimal but got {type(settings.IVA_RATE)}"
        )

    def test_payment_due_days_is_int(self) -> None:
        settings = _make_settings()
        assert isinstance(settings.PAYMENT_DUE_DAYS, int), (
            f"Expected int but got {type(settings.PAYMENT_DUE_DAYS)}"
        )

    def test_smtp_port_is_int(self) -> None:
        settings = _make_settings()
        assert isinstance(settings.SMTP_PORT, int), (
            f"Expected int but got {type(settings.SMTP_PORT)}"
        )

    def test_invoice_prefix_is_str(self) -> None:
        settings = _make_settings()
        assert isinstance(settings.INVOICE_PREFIX, str)

    def test_invoices_dir_is_str(self) -> None:
        settings = _make_settings()
        assert isinstance(settings.INVOICES_DIR, str)


# =============================================================================
# get_settings() Integration Test
# =============================================================================


class TestGetSettingsBillingFields:
    """Billing fields must be accessible via the get_settings() cached instance."""

    def test_get_settings_has_monthly_maintenance_eur(self) -> None:
        """get_settings() must expose MONTHLY_MAINTENANCE_EUR."""
        from shared.config import get_settings

        settings = get_settings()
        assert hasattr(settings, "MONTHLY_MAINTENANCE_EUR")
        assert isinstance(settings.MONTHLY_MAINTENANCE_EUR, Decimal)

    def test_get_settings_has_iva_rate(self) -> None:
        """get_settings() must expose IVA_RATE."""
        from shared.config import get_settings

        settings = get_settings()
        assert hasattr(settings, "IVA_RATE")
        assert isinstance(settings.IVA_RATE, Decimal)

    def test_get_settings_has_smtp_port(self) -> None:
        """get_settings() must expose SMTP_PORT."""
        from shared.config import get_settings

        settings = get_settings()
        assert hasattr(settings, "SMTP_PORT")
        assert isinstance(settings.SMTP_PORT, int)

    def test_get_settings_has_payment_due_days(self) -> None:
        """get_settings() must expose PAYMENT_DUE_DAYS."""
        from shared.config import get_settings

        settings = get_settings()
        assert hasattr(settings, "PAYMENT_DUE_DAYS")
        assert isinstance(settings.PAYMENT_DUE_DAYS, int)
