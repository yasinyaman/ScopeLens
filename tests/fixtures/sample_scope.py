"""A small baseline independent of the seed — shows the engine works with injected data."""

from etki.core.enums import Polarity
from etki.core.models import Baseline, ScopeItem

MINI_BASELINE = Baseline(
    contract_id="CTR-TEST",
    scope_items=[
        ScopeItem(
            id="S1",
            contract_id="CTR-TEST",
            description="rapor filtre export işlevleri",
            category="reporting",
            polarity=Polarity.INCLUDED,
            source_clause="Madde 1",
        ),
        ScopeItem(
            id="S2",
            contract_id="CTR-TEST",
            description="sso entegrasyonu kapsam dışıdır",
            category="auth",
            polarity=Polarity.EXCLUDED,
            source_clause="Madde 9",
        ),
    ],
)
