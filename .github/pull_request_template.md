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
