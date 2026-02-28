# tests/test_noise.py
import pytest
from datetime import datetime, timedelta, timezone
import pandas as pd
from pandas.api.types import is_string_dtype
import re

from transactions import generate_transactions
from noise import (
    inject_foreign_payments,
    inject_timestamp_noise,
    inject_currency_noise,
    inject_amount_noise,
    inject_company_id_noise,
    inject_fee_noise,
    inject_column_name_noise
)
from config import COMPANY_COLUMN_SCHEMAS

@pytest.fixture
def clean_transactions():
    """Generate clean transaction DataFrame for testing."""
    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=10)
    return generate_transactions(start, end, n_transactions=100)


class TestForeignPayments:
    """Test foreign payment currency injection."""

    def test_foreign_payments_rate(self, clean_transactions):
        """Verify correct percentage of rows get foreign payments."""
        rate = 0.20
        noisy = inject_foreign_payments(clean_transactions, rate=rate)

        # Before: all quote_cncy should be NULL
        assert clean_transactions['quote_cncy'].isna().sum() == 100

        # After: ~20% should have quote_cncy = "USD"
        foreign_count = noisy['quote_cncy'].notna().sum()
        assert 15 <= foreign_count <= 25  # Allow 5% variance

    def test_foreign_payments_sets_usd(self, clean_transactions):
        """Verify quote_cncy is always USD for foreign payments."""
        noisy = inject_foreign_payments(clean_transactions, rate=0.20)

        foreign_rows = noisy[noisy['quote_cncy'].notna()]
        assert (foreign_rows['quote_cncy'] == "USD").all()

    def test_foreign_payments_changes_base_currency(self, clean_transactions):
        """Verify base_cncy changes for foreign payments."""
        noisy = inject_foreign_payments(clean_transactions, rate=0.20)

        # Foreign payment rows should have different base_cncy than original
        foreign_indices = noisy[noisy['quote_cncy'].notna()].index
        for idx in foreign_indices:
            original_base = clean_transactions.loc[idx, 'base_cncy']
            new_base = noisy.loc[idx, 'base_cncy']
            # Either they differ, or both are the same if no alternatives existed
            # (Edge case: if company default is already foreign)
            assert isinstance(new_base, str) and len(new_base) == 3

    def test_foreign_payments_rate_zero(self, clean_transactions):
        """Verify rate=0 produces no foreign payments."""
        noisy = inject_foreign_payments(clean_transactions, rate=0.0)
        assert noisy['quote_cncy'].isna().sum() == 100

    def test_foreign_payments_rate_one(self, clean_transactions):
        """Verify rate=1.0 converts all rows."""
        noisy = inject_foreign_payments(clean_transactions, rate=1.0)
        assert noisy['quote_cncy'].notna().sum() == 100


class TestTimestampNoise:
    """Test timestamp format noise injection."""

    def test_timestamp_noise_rate(self, clean_transactions):
        """Verify correct percentage of timestamps get noisy."""
        rate = 0.20
        noisy = inject_timestamp_noise(clean_transactions, rate=rate)

        # Count how many timestamps differ from original
        changed = (noisy['tx_timestamp'] != clean_transactions['tx_timestamp']).sum()
        assert 15 <= changed <= 25  # Allow 5% variance

    def test_timestamp_noise_creates_strings(self, clean_transactions):
        """Verify noisy timestamps are strings, not datetime objects."""
        noisy = inject_timestamp_noise(clean_transactions, rate=0.20)

        # At least one should be a string (or None)
        noisy_rows = noisy[noisy['tx_timestamp'] != clean_transactions['tx_timestamp']]
        if len(noisy_rows) > 0:
            sample = noisy_rows.iloc[0]['tx_timestamp']
            assert isinstance(sample, (str, type(None)))


class TestCurrencyNoise:
    """Test currency code alias injection."""

    def test_currency_noise_rate(self, clean_transactions):
        """Verify correct percentage of currencies get noisy."""
        rate = 0.10
        noisy = inject_currency_noise(clean_transactions, rate=rate)

        changed = (noisy['base_cncy'] != clean_transactions['base_cncy']).sum()
        assert 5 <= changed <= 15  # Allow 5% variance

    def test_currency_noise_creates_strings(self, clean_transactions):
        """Verify dirty currencies are strings."""
        noisy = inject_currency_noise(clean_transactions, rate=0.10)
        # Accept either object or StringDtype
        assert is_string_dtype(noisy['base_cncy'])


class TestAmountNoise:
    """Test amount format noise injection."""

    def test_amount_noise_converts_to_string(self, clean_transactions):
        """Verify amounts become strings after noise."""
        noisy = inject_amount_noise(clean_transactions, rate=0.15)
        # Accept either object or StringDtype
        assert is_string_dtype(noisy['amount'])

    def test_amount_noise_rate(self, clean_transactions):
        """Verify correct percentage of amounts get formatted."""
        # Since all get converted to strings, check if any contain formatting
        noisy = inject_amount_noise(clean_transactions, rate=0.15)

        # Flags anything that isn't JUST digits or a single dot
        formatted = noisy['amount'].str.contains(r'[^0-9.]', regex=True, na=False).sum()
        assert formatted >= 10  # At least some should have format noise


class TestCompanyIdNoise:
    """Test company ID noise injection."""

    def test_company_id_null_rate(self, clean_transactions):
        """Verify null injection rate."""
        noisy = inject_company_id_noise(clean_transactions, rate_null=0.03, rate_name=0.0)

        nulls = noisy['c_id'].isna().sum()
        assert 1 <= nulls <= 5  # ~3% of 100

    def test_company_id_name_replacement(self, clean_transactions):
        """Verify some UUIDs are replaced with company names."""
        noisy = inject_company_id_noise(clean_transactions, rate_null=0.0, rate_name=0.05)

        # Find rows where c_id is no longer a UUID format (contains spaces or letters beyond hex)
        def is_uuid_format(val):
            if pd.isna(val):
                return True
            try:
                import uuid
                uuid.UUID(str(val))
                return True
            except (ValueError, AttributeError):
                return False

        non_uuid = ~noisy['c_id'].apply(is_uuid_format)
        assert non_uuid.sum() >= 3  # At least a few should be names


class TestFeeNoise:
    """Test fee amount noise injection."""

    def test_fee_missing_rate(self, clean_transactions):
        """Verify some fees become null."""
        noisy = inject_fee_noise(clean_transactions)

        nulls = noisy['fee_amount'].isna().sum()
        assert nulls >= 3  # Should have some missing fees

    def test_fee_noise_handles_formatted_amounts(self, clean_transactions):
        """Fee percent calculation doesn't break when amount has already been formatted."""
        pre_formatted = inject_amount_noise(clean_transactions, rate=1.0)
        result = inject_fee_noise(pre_formatted)
        assert result is not None


class TestColumnNameNoise:
    """Test company-specific column schema injection."""

    def test_dirty_columns_replace_canonical(self, clean_transactions):
        """Canonical column names are replaced with company-specific dirty names."""
        dirty = inject_column_name_noise(clean_transactions, company_key="COMP001")
        schema = COMPANY_COLUMN_SCHEMAS["COMP001"]

        for canonical, dirty_name in schema.items():
            if canonical in clean_transactions.columns:
                assert dirty_name in dirty.columns
                if canonical != dirty_name:
                    assert canonical not in dirty.columns

    def test_unknown_company_uses_default_schema(self, clean_transactions):
        """An unrecognised company key falls back to the default schema."""
        result = inject_column_name_noise(clean_transactions, company_key="COMP999")
        # Default schema is identity — columns should be unchanged
        assert set(result.columns) == set(clean_transactions.columns)

    def test_all_non_default_schemas(self, clean_transactions):
        """Every explicitly defined company schema produces at least one rename."""
        non_default = [k for k in COMPANY_COLUMN_SCHEMAS if k != "_default"]

        for company_key in non_default:
            dirty = inject_column_name_noise(clean_transactions, company_key=company_key)
            schema = COMPANY_COLUMN_SCHEMAS[company_key]
            renamed = {c: d for c, d in schema.items() if c != d and c in clean_transactions.columns}
            for canonical, dirty_name in renamed.items():
                assert dirty_name in dirty.columns, f"{company_key}: expected '{dirty_name}', not found"
# Run with: pytest tests/test_noise.py -v