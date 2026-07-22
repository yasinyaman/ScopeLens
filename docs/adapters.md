# Adapter reference — what each connector pulls

Every adapter implements one of three vendor-agnostic ports and **normalizes** vendor
fields into the core domain model; the decision engine never sees a vendor name. Which
adapter runs is configuration (`projects.yaml` → per-project `connectors`), never code.
Refresh cadence (what is fetched live vs. at index time) is covered in the
[RUNBOOK](RUNBOOK.md); how to add a new adapter is in
[Writing an adapter](writing-an-adapter.md).

**How the normalized fields are used downstream:**

| `WorkItem` field | Used for |
|---|---|
| `id`, `title`, `description`, `status` | similar-work evidence shown in the evidence chain |
| `effort_seconds` | the **effort-by-analogy** input to the PERT range ("4 similar jobs: 4h, 5h…") |
| `category` | **effort-pool consumption** — spent hours per contract category (`consumed_by_category`) |

A provider that cannot fill a field leaves it empty; the engine degrades gracefully
(e.g. no similars → effort falls back to code metrics; the vendor being unreachable at
triage time never fails the triage).

---

## Work-item providers (`WorkItemProvider`)

Builtin work-item adapters validate their options through the typed models in
`etki/adapters/options.py` (a missing key is a field-level Pydantic message, not a
KeyError) — the same mechanism plugins get via `AdapterFactory.options_model`. The
project settings UI renders its options form from these models' JSON schema; keep
the field lists below in sync with the models. Secret fields hold `env:VAR`
references, resolved only at adapter-build time.

### `file` — JSON export (vendor-agnostic)

- **Source:** a local JSON file (exported ticket data); no network.
- **Similar-work search:** local lexical scoring (`core/text.score`) over
  `title + description + category`.
- **Fields:** whatever the file provides, one-to-one (`effort_seconds` already in seconds).
- **Extras:** the only adapter with `all_items()` guaranteed cheap — effort-pool
  consumption is always complete. Declares `supports_enumeration=True`
  (etki-api 0.1.3); plugins with a cheap enumeration can declare the same and
  the conformance suite verifies the method.

### `jira` — Jira Cloud (REST v3)

- **Auth:** Basic (email + API token). **Similar-work search:** `GET /rest/api/3/search`
  with JQL `text ~ "<request text>"` (Jira searches title+description server-side);
  an optional `jql_extra` config narrows it (e.g. `project = ABC AND statusCategory = Done`).
- **Fields pulled** (deliberately minimal — `fields=summary,status,timespent,labels`):

| Jira field | → `WorkItem` | Note |
|---|---|---|
| `key` | `id` | |
| `summary` | `title` | |
| `status.name` | `status` | |
| `timespent` | `effort_seconds` | already seconds |
| `labels[0]` | `category` | first label = contract category → effort pool works (same convention as GitLab) |

- **Not pulled:** `description` (Jira v3 serves it as an ADF rich-text document),
  `issuetype`, worklog detail, comments, attachments. No issue-type filtering
  (story/task/bug all count) — use `jql_extra` to narrow if needed.

### `gitlab` — GitLab issues (REST v4)

- **Auth:** `PRIVATE-TOKEN` (scope `read_api`); gitlab.com and self-managed both work.
- **Similar-work search:** `GET /projects/{id}/issues?search=<text>&state=closed` —
  title+description search, **closed issues only** (they carry the real logged time).
- **Fields pulled:**

| GitLab field | → `WorkItem` | Note |
|---|---|---|
| `iid` | `id` | |
| `title` / `description` | `title` / `description` | |
| `labels[0]` | `category` | first label = contract category → effort pool works |
| `state` | `status` | |
| `time_stats.total_time_spent` | `effort_seconds` | native time tracking, already seconds |

- **Optional narrowing** (config, not code): `labels: [efor, musteri-x]` limits the
  search to issues carrying ALL of those labels (GitLab AND-semantics), and
  `issue_type: task` targets one type (`issue` | `incident` | `test_case` | `task`).
- **Not pulled:** merge requests, epics, `weight`, comments. GitLab **Tasks** (the
  newer work-item type) are not requested by default — teams that track effort on
  them can opt in via `issue_type: task`. Time must be logged with `/spend` to be seen.

### `redmine` — Redmine (REST)

- **Auth:** `X-Redmine-API-Key`. **Similar-work search:** `GET /search.json?q=<text>&issues=1`,
  then — because search hits carry no effort — up to `limit` detail calls to
  `GET /issues/{id}.json`.
- **Fields pulled:** `id`, `subject`→`title`, `description`, `tracker.name`→`category`,
  `status.name`→`status`, `spent_hours`×3600→`effort_seconds` (aggregated time entries).

### `azure_devops` — Azure DevOps Boards (REST 7.x)

- **Auth:** PAT (Basic, empty user). **Similar-work search:** WIQL —
  `SELECT [System.Id] WHERE [System.Title] CONTAINS '<text>' ORDER BY [System.ChangedDate] DESC`,
  then a batch field fetch.
- **Fields pulled:** `System.Title`→`title`, `System.Description`→`description`,
  `System.WorkItemType`→`category` (Task/Bug/User Story…), `System.State`→`status`,
  `Microsoft.VSTS.Scheduling.CompletedWork`×3600→`effort_seconds`.
- **Note:** WIQL matches the **title only** (not description); `CompletedWork` is
  usually maintained on task-level items.

### `linear` — Linear (GraphQL) — ships as a plugin

Since the plugin runtime (2026-07) Linear is **no longer builtin**: it is the
first-party plugin package
[`etki-plugin-linear`](https://github.com/yasinyaman/etki/tree/master/packages/etki-plugin-linear)
(depends only on `etki-api` + httpx). Config is unchanged — `adapter: linear`
resolves through the installed plugin; without it the name is rejected with the
list of available adapters.

- **Auth:** API key. **Similar-work search:** `searchIssues(term, first)`.
- **Fields pulled:** `identifier`→`id`, `title`, `description`, `labels[0].name`→`category`,
  `state.name`→`status`, `estimate` (**points**).
- **Effort convention:** Linear has **no native time tracking** — `effort_seconds` is 0
  unless the team opts into `hours_per_point` (e.g. 1 point ≈ 4h →
  `estimate × hours_per_point × 3600`); this is declared, not measured.
  **Zero-effort similars are dropped** so they can't collapse the PERT range;
  `supports_effort_tracking` is only reported when `hours_per_point` is set.

---

## Request intake + response (`RequestIntakeProvider` / `ResponseChannel`)

These two ports (etki-api 0.1.2) let Etki **pull** new client requests from a
tracker and **write the decision back** — the first WRITING integration. The
core owns the loop, dedup, audit and the write-back policy; the adapter is a
dumb transport. Configure via *Dosyalar → Talep Kanalı* or
`connectors.request_intake` / `connectors.response_channel`.

### `jira` — Jira Cloud (REST v3) — ships as a plugin

Package [`etki-plugin-jira`](https://github.com/yasinyaman/etki/tree/master/packages/etki-plugin-jira)
(depends only on `etki-api` + httpx). One options model + one credential set
drives both adapters.

- **Auth:** HTTP Basic (`email:api_token`, base64). **Options:** `base_url`,
  `email`, `api_token` (use `env:JIRA_TOKEN`), `project_key` **or** `jql`,
  `page_size` (20), `timeout` (30s).
- **Intake:** JQL search `GET /rest/api/3/search/jql` (enhanced endpoint;
  `project = "<key>"` unless an explicit `jql` is given). Fields pulled:
  `id`→`external_id`, `key`, `summary`→`title`, `description` (**ADF flattened**
  to plain text — tables/mentions dropped, only the words matter for triage),
  `creator.displayName`→`reporter`, `created`, `labels`, `browse/{key}`→`url`.
- **Cursor:** a **minute-precision `created` watermark** (`ORDER BY created ASC`).
  The boundary minute is re-queried with `>=` on purpose; the host's
  deterministic request-id dedup absorbs the overlap, so nothing is missed.
- **Write-back:** `POST /rest/api/3/issue/{id}/comment` with the host-composed,
  already-localized decision text wrapped in one ADF paragraph per line. Raises
  on failure so the host can record `RESPONSE_POSTED ok=false`. **Security:**
  `external_write=true` (declared and shown at install time).
- Requires a live Jira Cloud site → integration is CI-skipped; ADF/mapping/cursor
  math are unit-tested and the offline conformance doubles run credential-free.

---

## Document source providers (`DocumentSourceProvider`)

All of them only **list documents** and **fetch raw content**; text extraction
(docx/xlsx/pdf/csv/txt → text → scope clauses) happens centrally in
`extraction/parsers.py` at index time.

| Adapter | Listing | Content fetch | Notes |
|---|---|---|---|
| `filesystem` | directory walk of `doc_root` (uploaded files land here too) | file bytes | the default; powers the UI's upload/preview |
| `confluence` | Cloud REST content API for one `space_key`, paginated | `body.storage` HTML → tag-stripped text | Basic auth (email + API token) |
| `sharepoint` | MS Graph drive `children`, follows `@odata.nextLink` | `/content` (302 → pre-authenticated download), raw bytes | client-credentials (tenant/client id + secret) |
| `composite` | union of several child providers | delegated | proves pluggability; ids are namespaced per child |

---

## Code repository / code-graph engines (`CodeRepositoryProvider`)

All three engines emit the **same normalized `CodeIndex` JSON** (per file: LOC,
control-structure count, functions, imports), which `parse_code_index` turns into the
module graph: `CodeModule(loc, cyclomatic = control + functions, files, depends_on)`.
The engine choice is per repo (`engine:` in config; `ETKI_FORCE_CODE_ENGINE=ast`
overrides globally, e.g. in the JVM-free container).

| Engine | How | Trade-off |
|---|---|---|
| `joern` | live CPG (`pysrc2cpg` via `scripts/export_cpg.sc`) | production-grade; needs a JVM |
| `ast` | Python stdlib `ast` | dependency-free; Python sources only |
| `graphify` | tree-sitter, multi-language (`pip install "etki[graphify]"`) | LOC derived from line counts; control-structure counts unavailable → cyclomatic falls back to function count. Symbol-level API uses come from **graphify-mcp's `apis` engine** when installed (optional seam, `pip install "graphify-mcp[treesitter] @ git+https://github.com/yasinyaman/graphify-mcp"` until it is on PyPI): Python via stdlib ast, JS/TS/Go/Java via tree-sitter — same fidelity as the ast producer. Not installed → `package_apis` stays empty and effort estimation applies its unknown-surface widening. graphify's per-file imported-symbol NODES (label `FastAPI`, empty `source_file`) are skipped as import targets — they are symbols, not modules (previously leaked as phantom packages) |

Support pieces: `git_clone` (git URL → local clone; plain local paths also work),
`git_churn` (`git log` → per-module commit counts → the churn signal in risk/effort),
`MergedCodeRepository` (multi-repo projects; module ids namespaced `repo:module`).

---

## Package manifests (dependency impact)

At indexing time every code engine also parses the package manifests found at the
source root and its parent directory (`etki/adapters/manifests.py`, table-driven —
one parser per file name):

| Manifest | Ecosystem | Notes |
|---|---|---|
| `requirements.txt` | pypi | comments, `-r`/`-e`/option lines and `;` environment markers stripped; extras kept in the raw spec |
| `pyproject.toml` | pypi | `[project].dependencies` + `[project.optional-dependencies]` (flagged `dev`) |
| `package.json` | npm | `dependencies` + `devDependencies` (`dev`) |
| `pom.xml` | maven | default XML namespace handled via local-name matching; name = `groupId:artifactId`; `${property}` versions stay **raw** (no property resolution) |
| `go.mod` | go | `require` lines and blocks |
| `Cargo.toml` | cargo | `[dependencies]`/`[dev-dependencies]`, string and `{ version = … }` table forms |

Honest limitations: version specs are stored **verbatim** (no PEP 440 / semver / maven
range resolution — different languages, deliberately not compared); no lockfile parsing;
import-name ↔ package-name matching is heuristic (normalization + a small alias table
like `PyYAML→yaml` — an unmatched declared package renders as "declared, no import
seen", never an error); stdlib/node-builtin import names are filtered as noise. Not yet
parsed (follow-ups): `build.gradle` (Groovy/Kotlin code, not data), `composer.json`,
nuget `*.csproj`. Usage edges (which module imports which package) come from the code
graph itself — exact for Python (`ast`), multi-language via the `graphify` engine.

**Security evidence:** with `ETKI_DEPS_ONLINE`, known vulnerabilities come from
[OSV.dev](https://osv.dev) (free, deterministic, no key; ecosystems PyPI/npm/Maven/
Go/crates.io): `dependency_version_diff` reports them per EXACT version ("old has
CVE-…, new is clean" — the upgrade justification; the reverse warns against a
downgrade), `dependency_api_check` per declared `==` spec or package-level.
Independently of the online layer, a security-worded dependency request
("CVE/zafiyet/güvenlik…") **escalates the RISK layer** at triage time (probability
high, level ≥ HIGH, 24h PMO escalation + evidence note) while the SCOPE decision
still follows the contract — an out-of-scope security upgrade stays a CR, someone
pays, but deferral risk is flagged.

**API-change checks:** the ast producer also records *which symbols* of each package
the code calls (`from yaml import safe_load`, `requests.get`, alias-resolved
`np.array` → `numpy.array`) — the audit list for a version up-/downgrade. With
`ETKI_DEPS_ONLINE` the `dependency_api_check` tool cross-references those symbols
against the package's recent GitHub release notes (repo resolved from PyPI
`project_urls` / npm `repository`; unauthenticated GitHub API, 60 req/h — a token
story is a follow-up) using a deterministic word-boundary intersection: it reports
*which releases mention the APIs you use*, it does not interpret them. The graphify
producer emits symbol-level uses when graphify-mcp is installed (see the engine
table above); joern doesn't yet (documented limitation).

**Version diff (direct download):** `dependency_version_diff(package, old, new)`
downloads both exact pypi artifacts (pure wheel > any wheel > sdist), extracts them
under hardened rules (path-traversal and zip-bomb guards, per-artifact size cap
`ETKI_DEPS_MAX_DOWNLOAD_MB`, tar `filter="data"`), and parses the trees with `ast`
only — **downloaded code is never installed, imported or executed**. The report:
removed / added / signature-changed symbols, with the entries matching the
codebase's own used symbols flagged first. Two levels: **api** (default — the
EXPORTED interface: `__init__` re-exports/`__all__` plus exported classes' methods,
keyed by export path; internal helpers never exported don't count as breaking) and
**full** (every definition in the tree). Measured example: faker 24→25 shows
"1 removed" at code level but **0 removed at API level** — the class was never part
of the exported API, so consumers see no break. **The `your_code` section closes the
inverse gap:** Python doesn't enforce privacy, so if THIS codebase imports a
non-exported symbol (`from faker.providers.credit_card import CreditCard`), its
removal is still flagged — qualified import paths (captured by the ast indexer) are
checked against the FULL definition surface on both versions, with resolution tiers
exact → module-prefix → unique-suffix → `unresolved` (dynamic/`getattr` access and
C-extension symbols land there honestly, never silently in "ok"; broken entries carry
moved-symbol hints). sdist artifacts are rooted correctly (`package_root` descends the
versioned/`src` top dirs — without it two sdist versions share no dotted prefixes and
the diff degenerates). pypi only in v1 (npm/maven surface diffs need
language-specific parsers — follow-ups).

---

## AI layer (optional, off by default)

| Adapter | Endpoint | What is sent |
|---|---|---|
| `llm_anthropic` | Anthropic Claude API (official SDK) | on weak matches only: the request + candidate clause list + module ids, wrapped in prompt-injection guards; output is whitelist-validated |
| `llm_openai` | any OpenAI-compatible `/chat/completions` (Ollama, vLLM, LM Studio…) | same contract as above |
| `embedding_openai` | OpenAI-compatible `/embeddings` | request + clause texts; decision power limited to clear exclusion routing |
| `rerank_tei` | TEI-compatible `/rerank` | (request, clause) pairs, scored jointly |

Provider selection lives in **Settings → AI Assistant** (UI, `.etki/llm.json`) or env
(`ETKI_LLM_*`, `ETKI_EMBED_*`, `ETKI_RERANK_*`); with nothing configured the
whole layer is off and triage is fully deterministic.

---

## Capabilities

Every adapter declares `Capabilities` (`supports_webhooks`, `supports_realtime`,
`supports_effort_tracking`, `supports_incremental_diff`) so the system can degrade
gracefully. Today these are honest **declarations**: webhook listeners and incremental
diff are not implemented yet — sources refresh as described in the
[RUNBOOK](RUNBOOK.md) (work items live at triage time; code/documents at index time).
