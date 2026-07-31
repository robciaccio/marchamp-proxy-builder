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
It does **not** create the branch — you do, using that exact name.

## Branch naming

| Work type | Pattern | Example |
|---|---|---|
| Spec Kit feature | `NNN-short-name` (must equal the `specs/` directory) | `001-assemble-printable-proxy` |
| Everything else | `type/short-name` | `chore/ci-pipeline` |

```bash
git switch -c 001-assemble-printable-proxy main
```

Branches are short-lived. If one cannot merge within a few days, split it.

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

## Pull requests

1. Push the branch and open a PR against `main`.
2. Fill in [`.github/pull_request_template.md`](.github/pull_request_template.md) — the
   checklist is the constitution's merge gates, not decoration.
3. Confirm every gate. A gate that does not apply is marked N/A **with a reason**; it is
   never silently left unchecked.
4. Merge with **squash** or **rebase**. Merge commits must not land on `main`.
5. Delete the branch after merge.

Solo maintainer self-merge is fine. The PR still has to exist — the record is the point.

A PR that amends the constitution changes nothing else.

## Things that must never be committed

Enforced by review; `.gitignore` is the safety net, not the control.

- Card images or any part of the source asset library
- Generated PDFs, transcodes, resized renditions, or other cache output
- Secrets, credentials, API keys, service-account files, `.env`
