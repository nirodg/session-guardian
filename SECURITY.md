# Security Policy

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's "Report a vulnerability" (Security → Advisories) on this repository, rather than in a public issue. Include the affected version (`session-guardian --version`), impact, and a safe reproduction. Do not publish exploit details before a fix is released. You should receive an acknowledgement within a week.

## What SessionGuardian protects, and what it does not

- **Secrets:** memory must never contain credentials. `checkpoint` refuses when it detects high-confidence credentials (private keys, cloud/API tokens, JWTs); `audit` reports them, plus lower-confidence `password = …` style assignments as warnings. Detection is pattern-based and cannot find everything.
- **Permissions:** set `security.private_permissions` to restrict memory and checkpoints to the owner (POSIX).
- **Integrity:** checkpoints are SHA-256 manifested and verified before use; imported checkpoints are verified, including project identity. Hashes detect corruption and accidental edits; they are not signatures and do not prove authorship.
- **Repository instructions:** memory files are written by agents and collaborators. The recovery report frames them as data, not instructions, and demotes their headings so they cannot impersonate report sections. Agents must still treat repository content as untrusted, and the user's explicit instructions take precedence.
- **Scope protection** is a guardrail against agent drift, not a security boundary: anything with shell access can edit `SCOPE.md` or run `scope approve`. Approvals are logged.
- **Installers** never overwrite files they did not create and never touch project memory. Inspect them before running if you prefer (`curl -fsSLO …; less install.sh`).
