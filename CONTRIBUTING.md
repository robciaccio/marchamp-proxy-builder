# Contributing

This document defines the exact formats required by the **Version Control & Change Flow**
section of [`.specify/memory/constitution.md`](.specify/memory/constitution.md). The
constitution states the rules and wins any conflict; this file is the syntax reference.

## Workflow

Work follows the Spec Kit flow. Do not start implementing before a plan exists.

```
/speckit-specify  →  /speckit-plan  →  /speckit-tasks  →  /speckit-implement
```

`/speckit-specify` creates `specs/NNN-short-name/` and prints the matching branch name.
It does **not** create the branch — you do, using that name, plus a numeric suffix if an
earlier branch for the same feature has already been opened (see *Branch naming*).

## Branch naming

| Work type | Pattern | Example |
|---|---|---|
| Spec Kit feature | `NNN-short-name` (must equal the `specs/` directory) | `002-starter-deck-assembly` |
| Spec Kit feature, second and later branch | `NNN-short-name-N`, `N` counting from 2 | `002-starter-deck-assembly-2` |
| Everything else | `type/short-name` | `chore/ci-pipeline` |

```bash
git fetch origin
git switch -c 002-starter-deck-assembly origin/main      # the first branch
git switch -c 002-starter-deck-assembly-2 origin/main    # the next one
```

### The numeric suffix

One feature takes more than one branch. Refining a spec is the usual reason: a clarification
pass lands, the next question surfaces, and that is a second PR — small, reviewable in one
sitting, and merged on its own. The suffix is how those stay in sequence without inventing a
new descriptive name each time.

- **The part before the suffix MUST still equal the `specs/` directory.** That is what keeps a
  branch traceable to its feature. `002-starter-deck-assembly-2` is a branch for feature
  `002-starter-deck-assembly`; `002-plan-and-tasks` is not, however readable it looks.
- **Start at 2.** The first branch carries no suffix, so the numbers read as what they are —
  the second, third, and fourth pass over the same spec.
- **Never reuse a merged branch's name.** Take the next number instead. `main` is squash-merged,
  so a merged branch's commits are not ancestors of `main` and `git cherry` and
  `git branch --merged` will report it as unmerged forever; two branches sharing one name make
  that already-confusing history unreadable. To decide whether a branch holds real work, compare
  tree hashes (`git rev-parse <ref>^{tree}`) rather than trusting those commands.
- **The suffix does not license a long-lived branch.** Each one is still short-lived and still
  merges on its own. If a branch cannot merge within a few days, split it — the suffix is for
  work done *in sequence*, not for several branches carried in parallel.

> **Pending constitution amendment.** The constitution's *Version Control & Change Flow* section
> requires a feature branch to match the `specs/<feature>/` directory **exactly**, which the
> suffix does not. This document's preamble says the constitution wins any conflict, so that
> clause needs a MINOR amendment admitting the suffix before it is fully in force. The amendment
> must arrive in its own pull request, because a PR that amends the constitution may change
> nothing else.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/). Subject in imperative mood,
72 characters maximum, no trailing period.

```
<type>(<scope>): <subject>

<body — why, not what. Wrap at 72.>

<footer — Refs: #123 / BREAKING CHANGE: ...>
```

### Types

| Type | Use for |
|---|---|
| `feat` | New user-facing capability |
| `fix` | Bug fix |
| `docs` | Documentation only, including the constitution |
| `test` | Adding or correcting tests with no production change |
| `refactor` | Behavior-preserving restructuring |
| `perf` | Performance change |
| `build` | Build system, dependencies, packaging |
| `ci` | CI configuration and pipelines |
| `chore` | Tooling and repo maintenance with no src or test change |
| `revert` | Reverting a previous commit |

### Scope

Optional, lowercase, one word where a natural one exists — `pdf`, `catalog`, `assets`,
`api`, `ui`, `constitution`. Omit it rather than inventing one.

### Examples

```
feat(pdf): lay out resolved cards into printable sheets

The layout engine asserts page geometry against the values in
specs/001-assemble-printable-proxy/spec.md rather than hardcoding
them, so a format change is a spec change plus a fixture update.

Refs: #12
```

```
fix(assets): fail generation when a card image is missing

Generation previously dropped unreadable assets, producing a PDF that
was short a card with no error. Constitution principle V requires the
failure to name the card.
```

### Breaking changes

Append `!` after the type and explain under a `BREAKING CHANGE:` footer.

```
feat(api)!: version deck resolution endpoints under /v2

BREAKING CHANGE: /decks/{id}/resolve is removed. Use /v2/decks/{id}/resolve.
```

### Commit template

Enable the message scaffold once per clone:

```bash
git config commit.template .gitmessage
```

## One-time setup

```bash
brew install gitleaks                        # secret scanner
pipx install pre-commit && pre-commit install # runs it on staged changes
git config commit.template .gitmessage        # commit message scaffold
```

The pre-commit hook is a convenience, not a control — `--no-verify` bypasses it. The
enforceable controls are GitHub push protection and the `secret-scan` status check.

## Pull requests

1. Push the branch and open a PR against `main`.
2. Fill in [`.github/pull_request_template.md`](.github/pull_request_template.md) — the
   checklist is the constitution's merge gates, not decoration.
3. Confirm every gate. A gate that does not apply is marked N/A **with a reason**; it is
   never silently left unchecked.
4. **Complete the security review.** Every PR needs one. If the change touches auth,
   outbound network calls, file/image/PDF parsing, the asset adapter, the content store,
   dependencies, or CI workflows, write actual notes — a checked box is not a review.
   Runbook: [`SECURITY.md`](SECURITY.md).
5. Merge with **squash** or **rebase**. Merge commits must not land on `main`.
6. Delete the branch after merge.

Solo maintainer self-merge is fine. The PR still has to exist — the record is the point.

A PR that amends the constitution changes nothing else.

## Things that must never be committed

Enforced by review; `.gitignore` is the safety net, not the control.

- Card images or any part of the source asset library
- Generated PDFs, transcodes, resized renditions, or other cache output
- Secrets, credentials, API keys, service-account files, `.env`
