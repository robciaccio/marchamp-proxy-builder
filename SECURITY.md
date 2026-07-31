# Security

Operational companion to the **Security** section of
[`.specify/memory/constitution.md`](.specify/memory/constitution.md). The constitution
states the rules and wins any conflict; this file is the runbook.

## Reporting a vulnerability

Report privately via **GitHub Security Advisories** — repository → Security → Report a
vulnerability. Do not open a public issue for an exploitable finding.

Expect acknowledgement within 7 days. This is a hobby-scale project with no paid on-call;
that is stated plainly rather than promising a response time nobody is staffed to meet.

## Baseline

**OWASP ASVS v5.0.0** (May 2025) **Level 1 in full**, plus the named Level 2 uplift set:
`2.4.1, 5.1.1, 13.2.4, 13.2.5, 15.1.3, 15.2.2, 15.3.2, 16.3.1–16.3.4, 16.5.1–16.5.3`.

**OWASP Top 10:2025** supplies the vocabulary for describing risk in review. ASVS is the
normative reference; where they conflict, ASVS wins.

Next scheduled standards review: **2027-07-31**.

## Never commit

Credentials, access keys, tokens, private keys — in any file, including tests and
fixtures. There is no "it was only a test key" exemption.

`.gitignore` is a safety net, not a control. It does nothing about a force-added file
(`git add -f`) or a file that is already tracked.

## Scanning

Four layers. None substitutes for another, and only two are enforceable.

| Layer | Control | Enforceable? |
|---|---|---|
| Local | `pre-commit` hook on the staged diff | No — trivially bypassed |
| Remote | GitHub secret scanning **push protection** | **Yes** |
| CI | `secret-scan` required status check, full history | **Yes** |
| Periodic | Weekly TruffleHog verified-credential sweep | Detection only |

### Local setup (once per clone)

```bash
brew install gitleaks
pipx install pre-commit && pre-commit install
git config commit.template .gitmessage
```

### Manual scans

```bash
# Working tree
gitleaks dir . -v --redact

# Full history across every ref — this is what CI runs
gitleaks git . -v --redact --log-opts="--all"

# Which historical credentials are still LIVE (makes outbound API calls)
trufflehog git file://. --results=verified,unknown --fail
```

> `gitleaks detect --source .` is stale syntax, deprecated in v8.19.0 in favour of
> `gitleaks git` / `gitleaks dir`. Ignore tutorials that use it.

## If a secret is committed

**Ordering matters and most people get it backwards.**

### 1. Rotate first — before touching git

Revoke the credential at its issuer. Nothing else is remediation. Do this before you
rewrite anything, because every minute spent on git is a minute the key is live.

### 2. Understand what history rewriting does and does not do

**A pushed secret is compromised, permanently.** This is not caution, it is documented
GitHub behavior:

- Commits removed from all refs remain reachable **by SHA through the fork network**.
  Truffle Security recovered valid API keys from deleted forks this way; GitHub's
  response to the report was that this is *"an intentional design decision and is
  working as expected."*
- GitHub's own docs: *"You cannot remove sensitive data from other users' clones."*
- Prior clones, CI caches, mirrors, and third-party archives are outside your control.

So: **rotation is the fix; rewriting is hygiene.** A force-push is never the remediation
record.

### 3. Rewrite only if it is worth it

Use `git-filter-repo`. GitHub documents only this tool; `git filter-branch` is deprecated
by the git project, and BFG drags in a JVM for a strict subset of the capability.

```bash
brew install git-filter-repo
git clone --mirror git@github.com:robciaccio/marchamp-proxy-builder.git && cd marchamp-proxy-builder.git

# Remove a file from all history…
git filter-repo --sensitive-data-removal --invert-paths --path path/to/leaked.env

# …or redact a literal string in place
printf 'literal:THE_LEAKED_VALUE==>***REMOVED***\n' > ../replacements.txt
git filter-repo --sensitive-data-removal --replace-text ../replacements.txt

git push --force --mirror origin
```

Afterwards: every collaborator must **re-clone** (a rebased clone reintroduces the old
commits), forks must be coordinated or deleted, and GitHub Support must be asked to purge
cached views and PR refs.

### 4. Record it

Add a dated entry to the exceptions register below: what leaked, when, when it was
rotated, and whether history was rewritten.

## Exceptions register

Deviations from the baseline, per the constitution's requirement that they be dated and
owner-attributed. An undocumented deviation is a defect.

| Date | Item | Owner | Rationale | Review by |
|---|---|---|---|---|
| — | None recorded | — | — | — |

## Deferred controls

Tracked so they are not silently forgotten:

- **SBOM + SLSA v1.2 Build L2 provenance** — `TODO(SUPPLY_CHAIN_ATTESTATION)`. No build
  artifact exists to attest yet. Revisit at first deployable release.
- **CodeQL default setup** — language-specific; enable once `TODO(TECH_STACK)` resolves.
- **CIS Benchmark conformance** — platform-specific; select once the runtime is chosen.
- **Account security controls** — NIST SP 800-63B-4 password, MFA, and session rules land
  in the same change that introduces user accounts.
