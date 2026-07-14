import pytest
from etki.core.enums import Polarity
from etki.core.models import EffortEstimate, ScopeItem
from pydantic import ValidationError


def test_effort_estimate_rejects_inverted_range():
    # Architecture invariant: an estimate must always be a valid range (low <= high).
    with pytest.raises(ValidationError):
        EffortEstimate(low=10, high=5)


def test_effort_estimate_allows_valid_range():
    est = EffortEstimate(low=5, high=10, basis="test")
    assert est.low <= est.high


def test_scope_item_defaults_to_included():
    item = ScopeItem(id="X", contract_id="C", description="bir madde")
    assert item.polarity is Polarity.INCLUDED


def test_polarity_has_excluded():
    assert Polarity.EXCLUDED == "EXCLUDED"
