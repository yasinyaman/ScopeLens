# Security Policy

## Supported versions

Etki is in **alpha** (0.1.x). Only the latest release receives security
fixes. It is intended for pilot/evaluation deployments, not yet for production —
see `docs/RUNBOOK.md` for the current hardening posture (session login, RBAC,
non-root container, prompt-injection guards).

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

- Preferred: use GitHub's private vulnerability reporting
  ("Security" tab → "Report a vulnerability") on this repository.
- Alternatively, email **yasnyaman@gmail.com** with a description, reproduction
  steps and impact.

You can expect an acknowledgement within a few days. Since the data this project
handles (client contracts, effort history) is sensitive by nature, reports about
data exposure, access-control bypass (RBAC/project isolation) and prompt-injection
paths around the LLM seam are especially valuable.
