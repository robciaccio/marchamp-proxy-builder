## What and why

<!-- What changes, and why it is needed. Link the spec or issue. -->

Refs:

## Principles engaged

<!--
Required by the constitution. Name the principles this PR touches and how it satisfies
them. Delete rows that do not apply.
-->

| Principle | How this PR satisfies it |
|---|---|
| I. Test-First | |
| II. Interface-First | |
| III. Content and Assets Are External Data | |
| IV. Simplicity & YAGNI | |
| V. Observability & Reproducibility | |

## Merge gates

<!-- Every box checked, or marked N/A with a reason. Never silently left blank. -->

- [ ] Full test suite green, including output-geometry assertions (Principle I)
- [ ] Content schema and referential-integrity validation green
- [ ] API contract check green — OpenAPI document matches the running service
- [ ] No card images or generated PDFs added to version control
- [ ] No storage backend, provider SDK, or image-format assumption outside the asset adapter
- [ ] Secret scan green over full history, dependency review green
- [ ] No unpinned GitHub Action; no workflow granting write scope it does not need

## Security review

<!--
Required on EVERY PR. Green scanners are the mechanical half; this is the judgment
half, and it is not satisfied by checking a box.
-->

- [ ] No credentials, keys, or tokens are added by this PR — in source, tests, or fixtures

**Does this PR touch any of the following?** — if yes, written notes below are mandatory,
not optional.

- [ ] Authentication or authorization
- [ ] Any outbound network call
- [ ] File, image, or PDF parsing
- [ ] The asset adapter or the content store
- [ ] Dependency additions
- [ ] CI workflow definitions
- [ ] None of the above

**Review notes** <!-- What you considered and what you concluded. Cite ASVS where it applies. -->

<!--
Reminders for the areas most load-bearing here:
  egress allowlist + no redirect-following   (13.2.4, 13.2.5, 15.3.2)
  content-based binary validation + limits   (5.2.1, 5.2.2, 5.2.6)
  isolated parsing, no ambient credentials   (15.2.5)
  cost bounds on expensive endpoints         (2.4.1, 15.1.3, 15.2.2)
  fail closed, generic client errors         (16.5.1-16.5.3)
-->

N/A — no security-relevant surface touched.

## Complexity justification

<!--
Required by Principle IV if this PR adds a dependency, service, cache, queue, or
abstraction layer. Justify against a requirement that exists today. "We will need it
later" is not a justification. Write "None" if nothing was added.
-->

None

## Determinism

<!--
Required if this PR touches generation. Confirm the same selection against the same
content and asset revisions still produces a byte-identical PDF. Write "N/A" otherwise.
-->
