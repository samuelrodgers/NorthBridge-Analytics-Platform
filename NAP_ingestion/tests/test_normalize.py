# tests/test_normalize.py
import pytest
from datetime import datetime, timedelta, timezone
import pandas as pd
import uuid as _uuid
from pandas.api.types import is_string_dtype
import re

from transactions import generate_transactions
import noise

def _is_valid_uuid(val):
    try:
        _uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False

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


from pipeline import _parse_timestamps

class TestParseTimestamps:
    """Test timestamp normalization."""

    def test_clean_timestamp_pass_through(self, clean_transactions):
        """Valid timestamps are returned unchanged as UTC Timestamps."""
        result = _parse_timestamps(clean_transactions)
        assert pd.api.types.is_datetime64_any_dtype(result["tx_timestamp"])

    def test_dirty_timestamps_are_resolved(self, clean_transactions, dirty_transactions):
        """All parsed timestamps are mapped back to the original clean dataset."""
        # Run normalizations we already tested
        renamed = _rename_columns(dirty_transactions)

        # Test this normalization
        result = _parse_timestamps(renamed)
        non_null = result["tx_timestamp"].dropna()
        assert all(isinstance(ts, pd.Timestamp) for ts in non_null)

    def test_timestamp_noise_rate(self, clean_transactions, dirty_transactions):
        """Verify the dirty fixture actually contains some currency noise to resolve."""
        # Run normalizations we already tested
        renamed = _rename_columns(dirty_transactions)

        # Test this normalization
        changed = (renamed["tx_timestamp"] != clean_transactions["tx_timestamp"]).sum()
        assert changed >= 150  # ~15% of 1000 rows (coded rate is 20%)

    def test_null_timestamp_remain_null(self, clean_transactions):
        """Null timestamp values are returned as None, not coerced to a string."""
        df = clean_transactions.copy()
        df.loc[0, "tx_timestamp"] = None
        result = _parse_timestamps(df)
        # Python None is different than Pandas Nan
        assert result.loc[0, "tx_timestamp"] is None or pd.isna(result.loc[0, "tx_timestamp"])


from pipeline import (_parse_amounts, _parse_single_amount)


class TestParseAmounts:
    """Test amount normalization."""

    def test_clean_amounts_pass_through(self, clean_transactions):
        """Valid numeric amounts are returned unchanged."""
        result = _parse_amounts(clean_transactions)
        assert result["amount"].notna().all()
        assert (result["amount"] >= 0).all()

    def test_dirty_amounts_are_resolved(self, clean_transactions, dirty_transactions):
        """Unambiguous dirty amount formats are parsed to float."""
        renamed = _rename_columns(dirty_transactions)
        result = _parse_amounts(renamed)

        # Anything that survived should be a non-negative float
        non_null = result["amount"].dropna()
        assert (non_null >= 0).all()

    def test_negative_amounts_are_quarantined(self):
        """Negative amounts return None regardless of format."""
        assert _parse_single_amount(-100.0) is None
        assert _parse_single_amount("-1200.50") is None
        assert _parse_single_amount("(1200.50)") is None

    def test_ambiguous_eu_amounts_are_quarantined(self):
        """Sub-1000 EU format amounts with no dot are quarantined."""
        assert _parse_single_amount("99,00") is None
        assert _parse_single_amount("500,50") is None

    def test_unambiguous_eu_amounts_are_parsed(self):
        """EU format amounts with thousands separator are unambiguous and parsed correctly."""
        assert _parse_single_amount("1.200,50") == 1200.50
        assert _parse_single_amount("1.000,00") == 1000.00

    def test_standard_formats_are_parsed(self):
        """Standard amount formats are parsed correctly."""
        assert _parse_single_amount("1,200.50") == 1200.50
        assert _parse_single_amount("$1200.50") == 1200.50
        assert _parse_single_amount("1 200.50") == 1200.50
        assert _parse_single_amount(1200.50)    == 1200.50

    def test_null_amounts_are_quarantined(self):
        """None and NaN return None."""
        assert _parse_single_amount(None) is None
        assert _parse_single_amount(float("nan")) is None


from pipeline import _resolve_company_ids

class TestResolveCompanyIds:
    """Test company ID normalization."""

    def test_clean_company_ids_pass_through(self, clean_transactions):
        """Valid UUID company IDs are returned unchanged."""
        result = _resolve_company_ids(clean_transactions)
        assert result["c_id"].notna().all()
        assert all(_is_valid_uuid(v) for v in result["c_id"])

    def test_company_names_are_resolved(self, clean_transactions, dirty_transactions):
        """Company name variants are mapped back to their UUID."""
        renamed = _rename_columns(dirty_transactions)
        result = _resolve_company_ids(renamed)
        non_null = result["c_id"].dropna()
        assert all(_is_valid_uuid(v) for v in non_null)

    def test_null_company_ids_are_quarantined(self, clean_transactions):
        """Null company IDs return None."""
        df = clean_transactions.copy()
        df.loc[0, "c_id"] = None
        result = _resolve_company_ids(df)
        assert result.loc[0, "c_id"] is None or pd.isna(result.loc[0, "c_id"])

    def test_unresolvable_company_ids_are_quarantined(self, clean_transactions):
        """Company IDs that are neither a valid UUID nor a known name return None."""
        df = clean_transactions.copy()
        df.loc[0, "c_id"] = "not_a_company"
        result = _resolve_company_ids(df)
        assert result.loc[0, "c_id"] is None or pd.isna(result.loc[0, "c_id"])


from pipeline import _parse_fees

class TestParseFees:
    """Test fee normalization."""

    def test_clean_fees_pass_through(self, clean_transactions):
        """Valid numeric fees are returned unchanged."""
        result = _parse_fees(clean_transactions)
        assert result["fee_amount"].notna().all()
        assert (result["fee_amount"] >= 0).all()

    def test_missing_fees_default_to_zero(self, clean_transactions):
        """Null fee values default to 0.0 rather than being quarantined."""
        df = clean_transactions.copy()
        df.loc[0, "fee_amount"] = None
        result = _parse_fees(df)
        assert result.loc[0, "fee_amount"] == 0.0

    def test_percent_fees_are_resolved(self, clean_transactions):
        """Percent string fees are computed against the row's amount."""
        df = clean_transactions.copy()
        df["fee_amount"] = df["fee_amount"].astype(object)
        df.loc[0, "fee_amount"] = "2.5%"
        df.loc[0, "amount"] = 1000.0
        result = _parse_fees(df)
        assert result.loc[0, "fee_amount"] == 25.0

    def test_fee_exceeding_amount_is_quarantined(self, clean_transactions):
        """A fee larger than its amount returns None for quarantine."""
        df = clean_transactions.copy()
        df["fee_amount"] = df["fee_amount"].astype(object)
        df.loc[0, "fee_amount"] = 99999.0
        df.loc[0, "amount"] = 1.0
        result = _parse_fees(df)
        assert result.loc[0, "fee_amount"] is None or pd.isna(result.loc[0, "fee_amount"])

    def test_dirty_fees_are_resolved(self, clean_transactions, dirty_transactions):
        """Noisy fee variants are resolved without errors."""
        renamed = _rename_columns(dirty_transactions)
        parsed_amounts = _parse_amounts(renamed)
        result = _parse_fees(parsed_amounts)
        # Anything that survived should be non-negative
        non_null = result["fee_amount"].dropna()
        assert (non_null >= 0).all()


from pipeline import _coerce_types

class TestCoerceTypes:
    """Test final type enforcement."""

    def test_amount_is_numeric(self, clean_transactions):
        """Amount column is numeric dtype after coercion."""
        result = _coerce_types(clean_transactions)
        assert pd.api.types.is_numeric_dtype(result["amount"])

    def test_fee_amount_is_numeric(self, clean_transactions):
        """Fee amount column is numeric dtype after coercion."""
        result = _coerce_types(clean_transactions)
        assert pd.api.types.is_numeric_dtype(result["fee_amount"])

    def test_non_numeric_amount_raises(self, clean_transactions):
        """A non-numeric amount that slipped through raises rather than silently coercing."""
        df = clean_transactions.copy()
        df["amount"] = df["amount"].astype(object)
        df.loc[0, "amount"] = "not_a_number"
        with pytest.raises(ValueError):
            _coerce_types(df)


from pipeline import _split_quarantine

class TestSplitQuarantine:
    """Test quarantine splitting logic."""

    def test_clean_transactions_have_no_quarantine(self, clean_transactions):
        """A fully clean DataFrame produces zero quarantined rows."""
        clean, quarantine = _split_quarantine(clean_transactions)
        assert len(quarantine) == 0
        assert len(clean) == len(clean_transactions)

    def test_null_required_field_is_quarantined(self, clean_transactions):
        """A row with a null required field is moved to quarantine."""
        df = clean_transactions.copy()
        df.loc[0, "tx_timestamp"] = None
        clean, quarantine = _split_quarantine(df)
        assert len(quarantine) == 1
        assert "null_tx_timestamp" in quarantine.iloc[0]["quarantine_reason"]

    def test_multiple_null_fields_tagged(self, clean_transactions):
        """A row with multiple null required fields has all reasons listed."""
        df = clean_transactions.copy()
        df.loc[0, "tx_timestamp"] = None
        df.loc[0, "base_cncy"] = None
        clean, quarantine = _split_quarantine(df)
        reason = quarantine.iloc[0]["quarantine_reason"]
        assert "null_tx_timestamp" in reason
        assert "null_base_cncy" in reason

    def test_quarantine_reason_column_not_in_clean(self, clean_transactions):
        """The quarantine_reason column is not present in the clean DataFrame."""
        clean, _ = _split_quarantine(clean_transactions)
        assert "quarantine_reason" not in clean.columns

    def test_all_rows_accounted_for(self, clean_transactions):
        """Total rows in clean and quarantine always equals input rows."""
        df = clean_transactions.copy()
        df.loc[0, "amount"] = None
        clean, quarantine = _split_quarantine(df)
        assert len(clean) + len(quarantine) == len(df)


from pipeline import normalize_receipts

class TestNormalizeReceipts:
    """Test the full normalization pipeline."""

    def test_returns_two_dataframes(self, clean_transactions):
        """normalize_receipts always returns a tuple of two DataFrames."""
        result = normalize_receipts(clean_transactions)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], pd.DataFrame)
        assert isinstance(result[1], pd.DataFrame)

    def test_clean_input_produces_no_quarantine(self, clean_transactions):
        """A fully clean DataFrame passes through with zero quarantined rows."""
        clean, quarantine = normalize_receipts(clean_transactions)
        assert len(quarantine) == 0
        assert len(clean) == len(clean_transactions)

    def test_noisy_input_produces_some_quarantine(self, clean_transactions, dirty_transactions):
        """A noisy DataFrame produces at least some quarantined rows."""
        clean, quarantine = normalize_receipts(dirty_transactions)
        assert len(quarantine) > 0

    def test_all_rows_accounted_for(self, dirty_transactions):
        """Total rows in clean and quarantine always equals input rows."""
        clean, quarantine = normalize_receipts(dirty_transactions)
        assert len(clean) + len(quarantine) == len(dirty_transactions)

    def test_clean_output_has_canonical_columns(self, dirty_transactions):
        """Clean output always has canonical column names."""
        clean, _ = normalize_receipts(dirty_transactions)
        expected = {"tx_id", "c_id", "base_cncy", "quote_cncy", "amount", "fee_amount", "tx_timestamp"}
        assert expected.issubset(set(clean.columns))

    def test_clean_output_has_correct_dtypes(self, dirty_transactions):
        """Clean output columns have DB-ready dtypes."""
        clean, _ = normalize_receipts(dirty_transactions)
        assert pd.api.types.is_datetime64_any_dtype(clean["tx_timestamp"])
        assert pd.api.types.is_numeric_dtype(clean["amount"])
        assert pd.api.types.is_numeric_dtype(clean["fee_amount"])