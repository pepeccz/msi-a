"""
Tests for Billing Models — Task 2 (Invoice + Payment)

Requirements verified:
  - Invoice and Payment can be instantiated
  - Correct __tablename__ values
  - Monetary columns are Numeric type
  - Invoice.payments relationship exists
  - status is String(20), NOT an enum
  - Invoice.payments uses lazy="selectin" with cascade
  - Payment.invoice back-reference exists
"""

from __future__ import annotations

import uuid
from decimal import Decimal


class TestInvoiceInstantiation:
    """Invoice model must be instantiatable with required fields."""

    def test_invoice_can_be_instantiated(self) -> None:
        """Invoice can be created with required fields."""
        from database.models import Invoice

        invoice = Invoice(
            invoice_number="MSI-2025-001",
            year=2025,
            month=1,
            maintenance_amount_eur=Decimal("50.00"),
            token_amount_eur=Decimal("10.00"),
            subtotal_eur=Decimal("60.00"),
            iva_rate=Decimal("21.00"),
            iva_amount_eur=Decimal("12.60"),
            total_eur=Decimal("72.60"),
        )
        assert invoice is not None

    def test_invoice_tablename(self) -> None:
        """Invoice.__tablename__ must be 'invoices'."""
        from database.models import Invoice

        assert Invoice.__tablename__ == "invoices", (
            f"Expected 'invoices' but got {Invoice.__tablename__!r}"
        )


class TestPaymentInstantiation:
    """Payment model must be instantiatable with required fields."""

    def test_payment_can_be_instantiated(self) -> None:
        """Payment can be created with required fields."""
        from database.models import Payment

        payment = Payment(
            invoice_id=uuid.uuid4(),
            amount_eur=Decimal("72.60"),
            status="pending",
        )
        assert payment is not None

    def test_payment_tablename(self) -> None:
        """Payment.__tablename__ must be 'payments'."""
        from database.models import Payment

        assert Payment.__tablename__ == "payments", (
            f"Expected 'payments' but got {Payment.__tablename__!r}"
        )


class TestInvoiceMonetaryColumns:
    """All monetary columns on Invoice must be Numeric type."""

    def test_maintenance_amount_eur_is_numeric(self) -> None:
        """maintenance_amount_eur column must be Numeric."""
        from database.models import Invoice
        from sqlalchemy import Numeric

        col = Invoice.__table__.c["maintenance_amount_eur"]
        assert isinstance(col.type, Numeric), (
            f"Expected Numeric but got {type(col.type)}"
        )

    def test_token_amount_eur_is_numeric(self) -> None:
        """token_amount_eur column must be Numeric."""
        from database.models import Invoice
        from sqlalchemy import Numeric

        col = Invoice.__table__.c["token_amount_eur"]
        assert isinstance(col.type, Numeric), (
            f"Expected Numeric but got {type(col.type)}"
        )

    def test_subtotal_eur_is_numeric(self) -> None:
        """subtotal_eur column must be Numeric."""
        from database.models import Invoice
        from sqlalchemy import Numeric

        col = Invoice.__table__.c["subtotal_eur"]
        assert isinstance(col.type, Numeric), (
            f"Expected Numeric but got {type(col.type)}"
        )

    def test_iva_rate_is_numeric(self) -> None:
        """iva_rate column must be Numeric."""
        from database.models import Invoice
        from sqlalchemy import Numeric

        col = Invoice.__table__.c["iva_rate"]
        assert isinstance(col.type, Numeric), (
            f"Expected Numeric but got {type(col.type)}"
        )

    def test_iva_amount_eur_is_numeric(self) -> None:
        """iva_amount_eur column must be Numeric."""
        from database.models import Invoice
        from sqlalchemy import Numeric

        col = Invoice.__table__.c["iva_amount_eur"]
        assert isinstance(col.type, Numeric), (
            f"Expected Numeric but got {type(col.type)}"
        )

    def test_total_eur_is_numeric(self) -> None:
        """total_eur column must be Numeric."""
        from database.models import Invoice
        from sqlalchemy import Numeric

        col = Invoice.__table__.c["total_eur"]
        assert isinstance(col.type, Numeric), (
            f"Expected Numeric but got {type(col.type)}"
        )


class TestPaymentMonetaryColumns:
    """All monetary columns on Payment must be Numeric type."""

    def test_amount_eur_is_numeric(self) -> None:
        """amount_eur column must be Numeric."""
        from database.models import Payment
        from sqlalchemy import Numeric

        col = Payment.__table__.c["amount_eur"]
        assert isinstance(col.type, Numeric), (
            f"Expected Numeric but got {type(col.type)}"
        )

    def test_fee_eur_is_numeric(self) -> None:
        """fee_eur column must be Numeric."""
        from database.models import Payment
        from sqlalchemy import Numeric

        col = Payment.__table__.c["fee_eur"]
        assert isinstance(col.type, Numeric), (
            f"Expected Numeric but got {type(col.type)}"
        )


class TestInvoiceStatusColumn:
    """status must be String(20), NOT an enum."""

    def test_status_is_string_not_enum(self) -> None:
        """Invoice.status column type must be String, not Enum."""
        from database.models import Invoice
        from sqlalchemy import String
        from sqlalchemy import Enum as SAEnum

        col = Invoice.__table__.c["status"]
        assert isinstance(col.type, String), (
            f"Expected String but got {type(col.type)} — status must NOT be an Enum"
        )
        assert not isinstance(col.type, SAEnum), (
            "status must not be declared as Enum"
        )

    def test_status_string_length_is_20(self) -> None:
        """Invoice.status must be String(20)."""
        from database.models import Invoice

        col = Invoice.__table__.c["status"]
        assert col.type.length == 20, (
            f"Expected String(20) but got String({col.type.length})"
        )

    def test_payment_status_is_string_not_enum(self) -> None:
        """Payment.status column type must be String, not Enum."""
        from database.models import Payment
        from sqlalchemy import String
        from sqlalchemy import Enum as SAEnum

        col = Payment.__table__.c["status"]
        assert isinstance(col.type, String), (
            f"Expected String but got {type(col.type)}"
        )
        assert not isinstance(col.type, SAEnum), (
            "Payment.status must not be declared as Enum"
        )


class TestInvoicePaymentsRelationship:
    """Invoice must have a 'payments' relationship to Payment."""

    def test_invoice_has_payments_relationship(self) -> None:
        """Invoice must expose a 'payments' attribute (relationship)."""
        from database.models import Invoice

        assert hasattr(Invoice, "payments"), (
            "Invoice model is missing the 'payments' relationship"
        )

    def test_invoice_payments_relationship_property(self) -> None:
        """Invoice.payments must be a SQLAlchemy relationship descriptor."""
        from database.models import Invoice
        from sqlalchemy.orm import RelationshipProperty

        rel = Invoice.__mapper__.relationships.get("payments")
        assert rel is not None, (
            "No 'payments' relationship found on Invoice mapper"
        )

    def test_invoice_payments_uses_selectin_lazy(self) -> None:
        """Invoice.payments must use lazy='selectin' for async safety."""
        from database.models import Invoice

        rel = Invoice.__mapper__.relationships["payments"]
        assert rel.lazy == "selectin", (
            f"Expected lazy='selectin' but got lazy={rel.lazy!r}"
        )

    def test_invoice_payments_cascade_includes_delete(self) -> None:
        """Invoice.payments must include cascade='all, delete-orphan'."""
        from database.models import Invoice

        rel = Invoice.__mapper__.relationships["payments"]
        assert "delete" in rel.cascade, (
            f"Expected 'delete' in cascade, got: {rel.cascade}"
        )


class TestPaymentInvoiceRelationship:
    """Payment must have an 'invoice' back-reference to Invoice."""

    def test_payment_has_invoice_relationship(self) -> None:
        """Payment must expose an 'invoice' attribute (relationship)."""
        from database.models import Payment

        assert hasattr(Payment, "invoice"), (
            "Payment model is missing the 'invoice' back-reference"
        )

    def test_payment_invoice_uses_selectin_lazy(self) -> None:
        """Payment.invoice must use lazy='selectin'."""
        from database.models import Payment

        rel = Payment.__mapper__.relationships["invoice"]
        assert rel.lazy == "selectin", (
            f"Expected lazy='selectin' but got lazy={rel.lazy!r}"
        )


class TestInvoiceUUIDPrimaryKey:
    """Invoice must use UUID as primary key."""

    def test_invoice_pk_is_uuid_column(self) -> None:
        """Invoice primary key must be a UUID column."""
        from database.models import Invoice
        from sqlalchemy.dialects.postgresql import UUID

        pk_col = Invoice.__table__.c["id"]
        assert pk_col.primary_key is True
        assert isinstance(pk_col.type, UUID), (
            f"Expected UUID type but got {type(pk_col.type)}"
        )


class TestPaymentUUIDPrimaryKey:
    """Payment must use UUID as primary key."""

    def test_payment_pk_is_uuid_column(self) -> None:
        """Payment primary key must be a UUID column."""
        from database.models import Payment
        from sqlalchemy.dialects.postgresql import UUID

        pk_col = Payment.__table__.c["id"]
        assert pk_col.primary_key is True
        assert isinstance(pk_col.type, UUID), (
            f"Expected UUID type but got {type(pk_col.type)}"
        )
