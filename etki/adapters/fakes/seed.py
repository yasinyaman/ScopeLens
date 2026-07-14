"""Phase 0 fake (seed) data.

Document extraction and code indexing don't exist yet; the baseline + code modules +
historical work items are seeded by hand. Consistent with the live-assistant example in
the architecture document (report filter IN SCOPE, SSO OUT OF SCOPE).
"""

from __future__ import annotations

from etki.core.enums import Polarity
from etki.core.models import (
    Baseline,
    Churn,
    CodeModule,
    Complexity,
    DocumentRef,
    ScopeItem,
    ScopeLimit,
    WorkItem,
)

CONTRACT_ID = "CTR-2026-001"

# The code index's freshness stamp (fake) — attached to every triage decision.
INDEX_FRESHNESS = "2026-06-21"

SEED_BASELINE = Baseline(
    contract_id=CONTRACT_ID,
    version=1,
    locked=True,
    scope_items=[
        ScopeItem(
            id="SCOPE-014",
            contract_id=CONTRACT_ID,
            description="Aylık rapor üretimi (en fazla 5 rapor) ve rapor filtreleri",
            category="reporting",
            polarity=Polarity.INCLUDED,
            limits=ScopeLimit(quantity=5, period="monthly"),
            effort_pool_hours=40,
            source_clause="Madde 4.2.1",
            mapped_modules=["reporting_module"],
        ),
        ScopeItem(
            id="SCOPE-007",
            contract_id=CONTRACT_ID,
            description="Kullanıcı girişi ve oturum yönetimi (yerel kimlik doğrulama)",
            category="auth",
            polarity=Polarity.INCLUDED,
            effort_pool_hours=24,
            source_clause="Madde 3.1",
            mapped_modules=["auth_module"],
        ),
        ScopeItem(
            id="SCOPE-022",
            contract_id=CONTRACT_ID,
            description="SSO ve üçüncü taraf kimlik sağlayıcı (IdP) entegrasyonu kapsam dışıdır",
            category="auth",
            polarity=Polarity.EXCLUDED,
            source_clause="Madde 7.1",
            mapped_modules=[],
        ),
    ],
)

SEED_MODULES: list[CodeModule] = [
    CodeModule(
        id="reporting_module",
        path="src/reporting/",
        responsibilities=["rapor", "filtre", "export"],
        depends_on=["db_module"],
        depended_by=[],
        mapped_scope_items=["SCOPE-014"],
        complexity=Complexity(loc=820, cyclomatic=12, files=5),
        churn=Churn(commits_last_6mo=8),
    ),
    CodeModule(
        id="auth_module",
        path="src/auth/",
        responsibilities=["login", "session", "token"],
        depends_on=["db_module", "config_module"],
        depended_by=["api_gateway", "reporting_module"],
        mapped_scope_items=["SCOPE-007"],
        complexity=Complexity(loc=1240, cyclomatic=18, files=8),
        churn=Churn(commits_last_6mo=23),  # high churn = risky area
    ),
    CodeModule(
        id="api_gateway",
        path="src/gateway/",
        responsibilities=["routing", "rate-limit"],
        depends_on=["auth_module"],
        depended_by=[],
        mapped_scope_items=[],
        complexity=Complexity(loc=600, cyclomatic=9, files=4),
        churn=Churn(commits_last_6mo=5),
    ),
    CodeModule(
        id="db_module",
        path="src/db/",
        responsibilities=["persistence"],
        depends_on=[],
        depended_by=["reporting_module", "auth_module"],
        mapped_scope_items=[],
        complexity=Complexity(loc=400, cyclomatic=6, files=3),
        churn=Churn(commits_last_6mo=3),
    ),
]

SEED_WORK_ITEMS: list[WorkItem] = [
    WorkItem(
        id="WI-101",
        title="Rapora yeni filtre eklendi",
        description="reporting modülüne tarih filtresi eklendi",
        category="reporting",
        status="closed",
        effort_seconds=6 * 3600,
    ),
    WorkItem(
        id="WI-102",
        title="Rapor export formatı genişletildi",
        description="reporting modülü export seçenekleri",
        category="reporting",
        status="closed",
        effort_seconds=5 * 3600,
    ),
    WorkItem(
        id="WI-201",
        title="SSO entegrasyonu (başka proje)",
        description="auth modülüne SAML tabanlı SSO entegrasyonu",
        category="auth",
        status="closed",
        effort_seconds=28 * 3600,
    ),
    WorkItem(
        id="WI-202",
        title="OAuth2 IdP bağlantısı",
        description="üçüncü taraf kimlik sağlayıcı entegrasyonu",
        category="auth",
        status="closed",
        effort_seconds=24 * 3600,
    ),
]

SEED_DOCUMENTS: list[DocumentRef] = [
    DocumentRef(
        id="DOC-1",
        name="Sozlesme_CTR-2026-001.pdf",
        path="/contracts/CTR-2026-001.pdf",
        mime="application/pdf",
    ),
    DocumentRef(
        id="DOC-2",
        name="Sartname_v2.docx",
        path="/contracts/sartname_v2.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
]
