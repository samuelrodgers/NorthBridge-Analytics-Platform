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
from config import COMPANY_COLUMN_SCHEMAS

class TestRenameColumns:
    """Test column name normalization."""

    def test_renames_dirty_columns(self):
        """Dirty column names from a known company schema are mapped to canonical names."""
    pass

    def test_canonical_columns_pass_through(self):
        """A DataFrame already using canonical names is returned unchanged."""
    pass

    def test_unknown_columns_are_preserved(self):
        """Columns not in the map are left alone rather than dropped."""
    pass