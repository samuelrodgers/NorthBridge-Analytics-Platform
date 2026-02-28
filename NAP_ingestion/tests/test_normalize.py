# tests/test_normalize.py
import pytest
from datetime import datetime, timedelta, timezone
import pandas as pd
from pandas.api.types import is_string_dtype
import re

from transactions import generate_transactions
import noise


@pytest.fixture
def clean_transactions():
    """Generate clean transaction DataFrame for benchmarking."""
    start = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=10)
    return generate_transactions(start, end, n_transactions=1000, seed=42)

@pytest.fixture
def dirty_transactions(clean_transactions):
    """Add noise to the transactions for testing."""
    return noise.apply_noise(clean_transactions, noise_level="medium")



from pipeline import _rename_columns

class TestRenameColumns:
    """Test column name normalization."""

    def test_rename_restores_canonical_columns(self, clean_transactions, dirty_transactions):
        """All dirty column names are mapped back to canonical names after normalization."""
        result = _rename_columns(dirty_transactions)
        assert set(result.columns) == set(clean_transactions.columns)


from pipeline import _resolve_currencies
from config import CURRENCY_CODES

class TestResolveCurrencies:
    """Test currency code normalization."""

    def test_clean_currencies_pass_through(self, clean_transactions):
        """Valid ISO codes are returned unchanged."""
        result = _resolve_currencies(clean_transactions)
        assert result["base_cncy"].isin(CURRENCY_CODES).all()

    def test_dirty_currencies_are_resolved(self, clean_transactions, dirty_transactions):
        """All currency aliases and variants are mapped to valid ISO codes."""
        # Run normalizations we already tested
        renamed = _rename_columns(dirty_transactions)

        # Test this normalization
        result = _resolve_currencies(renamed)
        non_null = result["base_cncy"].dropna()
        assert non_null.isin(CURRENCY_CODES).all()

    def test_currency_noise_rate(self, clean_transactions, dirty_transactions):
        """Verify the dirty fixture actually contains some currency noise to resolve."""
        # Run normalizations we already tested
        renamed = _rename_columns(dirty_transactions)

        # Test this normalization
        changed = (renamed["base_cncy"] != clean_transactions["base_cncy"]).sum()
        assert changed >= 50  # ~10% of 1000 rows

    def test_null_currencies_remain_null(self, clean_transactions):
        """Null currency values are returned as None, not coerced to a string."""
        df = clean_transactions.copy()
        df.loc[0, "base_cncy"] = None
        result = _resolve_currencies(df)
        # Python None is different than Pandas Nan
        assert result.loc[0, "base_cncy"] is None or pd.isna(result.loc[0, "base_cncy"])


from pipeline import _resolve_currencies
from config import CURRENCY_CODES

class TestResolveCurrencies:
    """Test currency code normalization."""

    def test_clean_currencies_pass_through(self, clean_transactions):
        """Valid ISO codes are returned unchanged."""
        result = _resolve_currencies(clean_transactions)
        assert result["base_cncy"].isin(CURRENCY_CODES).all()

    def test_dirty_currencies_are_resolved(self, clean_transactions, dirty_transactions):
        """All currency aliases and variants are mapped to valid ISO codes."""
        # Run normalizations we already tested
        renamed = _rename_columns(dirty_transactions)

        # Test this normalization
        result = _resolve_currencies(renamed)
        non_null = result["base_cncy"].dropna()
        assert non_null.isin(CURRENCY_CODES).all()

    def test_currency_noise_rate(self, clean_transactions, dirty_transactions):
        """Verify the dirty fixture actually contains some currency noise to resolve."""
        # Run normalizations we already tested
        renamed = _rename_columns(dirty_transactions)

        # Test this normalization
        changed = (renamed["base_cncy"] != clean_transactions["base_cncy"]).sum()
        assert changed >= 50  # ~10% of 1000 rows

    def test_null_currencies_remain_null(self, clean_transactions):
        """Null currency values are returned as None, not coerced to a string."""
        df = clean_transactions.copy()
        df.loc[0, "base_cncy"] = None
        result = _resolve_currencies(df)
        # Python None is different than Pandas Nan
        assert result.loc[0, "base_cncy"] is None or pd.isna(result.loc[0, "base_cncy"])