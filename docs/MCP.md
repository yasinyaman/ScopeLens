# Etki as an MCP server

Etki ships a [Model Context Protocol](https://modelcontextprotocol.io) server, so any
MCP client — Claude Desktop, Claude Code, or your own agent — can ask real scope questions
against your contract, code graph and effort history:

> *"Is SAML single sign-on in scope? What effort would it take?"*

and get the actual, evidence-backed Etki answer (decision + confidence + effort range +
the cited contract clause), not a guess.

## Tools

| Tool | What it returns |
|---|---|
| `triage_request(text)` | **The full decision tree**: in scope / out of scope / CR candidate / gray area / maintenance, with confidence, an effort **range**, cited clauses (incl. explicit exclusions, frozen in full text), impacted modules, reasoning. |
| `scope_lookup(query)` | The contract scope clauses closest to a query (included/excluded + similarity score). |
| `impact_analysis(module)` | Impacted code regions for a module hint, with a high-churn warning. |
| `similar_effort(description)` | Similar past work items and a ranged effort estimate by analogy. |
| `baseline_summary()` | Contract baseline + code graph summary (clause counts, modules, dependencies, index freshness). |
| `dependency_impact(package)` | Impact surface of a library add/upgrade: manifest declarations (raw version specs), modules importing it, the API symbols they call, one-hop blast radius, high-churn warnings, total LOC. Evidence only — the scope decision still comes from `triage_request`. |
| `dependency_api_check(package)` | API-level audit for a version change (up- or downgrade): the exact symbols the code calls per module; with `ETKI_DEPS_ONLINE`, which recent GitHub release notes mention those symbols (deterministic word-boundary intersection) **plus known vulnerabilities from OSV.dev** (version-precise when the spec is `==x.y.z`). |
| `dependency_version_diff(package, old, new, level="api")` | Downloads BOTH exact pypi versions (never installed or executed — hardened extraction, `ast` parse only). The summary diffs the **exported API** by default (`level="full"` for every definition). **Regardless of level, the `your_code` section checks this codebase's qualified import paths against the FULL definition surface** — Python doesn't enforce privacy, so a non-exported import breaking is still flagged (`broken`, with moved-symbol hints); dynamic/`getattr` access lands in `unresolved`, never silently in "ok". Requires `ETKI_DEPS_ONLINE`. |

Everything is **deterministic and read-only**: the server never calls an LLM itself (the MCP
client *is* the LLM), and `triage_request` does **not** persist a case file or audit event —
the approval workflow belongs to the web app. Treat MCP answers as exploration; decisions of
record go through the UI.

## Claude Code

```bash
claude mcp add etki -- uv run --directory /absolute/path/to/etki python -m etki.mcp_server
```

Then just ask: *"Use etki to check whether adding push notifications is in scope, and what effort it would take."*

## Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "etki": {
      "command": "uv",
      "args": [
        "run", "--directory", "/absolute/path/to/etki",
        "python", "-m", "etki.mcp_server"
      ]
    }
  }
}
```

## Which project does it answer for?

The server reads the same configuration as the app: the persisted index at
`ETKI_INDEX_PATH` (default `.etki/index.json`) if present, otherwise it builds one
live from `ETKI_CONNECTORS_PATH` (default `config/connectors.example.yaml` → the bundled
demo corpus) using the dependency-free AST engine — no Joern/JVM needed. Point it at another
corpus with environment variables in the MCP config:

```json
"env": {
  "ETKI_CONNECTORS_PATH": "config/connectors.docker.yaml",
  "ETKI_INDEX_PATH": ".etki/index-demo.json"
}
```

## Try it

With the bundled demo corpus, `triage_request("We need SAML single sign-on")` returns
`OUT_OF_SCOPE` with high confidence, citing the contract's explicit exclusion clause — plus
the effort range such a change request would take, estimated from similar past tickets.
