"""Canonical exact numeric types for future Core and Shell models."""

from sqlalchemy import Numeric

# These types are deliberately shared. Monetary values, quantities, and exchange
# rates must never be represented by floating-point columns or Python floats.
MONEY_NUMERIC = Numeric(20, 6)
QUANTITY_NUMERIC = Numeric(20, 6)
EXCHANGE_RATE_NUMERIC = Numeric(24, 12)
TAX_RATE_NUMERIC = Numeric(5, 2)
