# 0001. Durable run state lives on the filesystem, one directory per run

Date: 2026-08-16
Status: Accepted (2026-08-16)

## Context

Feature 002 ([spec.md](../../specs/002-starter-deck-assembly/spec.md)) introduces the first
durable state this project has ever had. Feature 001 kept generations in memory on the stated
grounds that nothing required durable output; 002 retires both halves of that premise — an
unfinished deck must be resumable on a later visit (FR-026b), and a finished PDF is kept and
reused rather than rebuilt (FR-026f, FR-026h).

Four kinds of state must survive an application restart:

| State | Shape | Size | Access pattern |
|---|---|---|---|
| Assembly run | Structured record: folder, pack, ~40–60 resolutions, report, state, pinned snapshot revision | ~8 KB | Created, mutated once per user answer across separate HTTP requests, listed, deleted |
| Uploaded card image | Binary | ~1–5 MB | Written once, read at compose time |
| Generated PDF | Binary | **~202 MB** (measured in 001) | Written once, re-downloaded, shared across runs by `(pack, snapshot revision)`, deleted to reclaim space |
| Pack snapshot | JSON, reduced to the fields this feature resolves against | ~100 KB | Written on first use of a pack, read by every later run, refreshed |

Constraints that bind:

- Single local process, loopback-only (`config.py` rejects a non-loopback host), **one human
  user**. Concurrency today is two render threads plus request threads.
- Constitution Principle IV: machinery must be justified against a requirement that exists
  today. Principle V: byte-identical regeneration, traceable to the revision that produced it.
- FR-026g: deleting a stored PDF **must reclaim the space it held**.
- SC-006h: a finished run's PDF must download **with the library folder unmounted**.
- The user's card library is a mounted Google Drive folder, named per run (FR-005).

Assumption stated rather than verified: run counts stay in the tens to low hundreds over the
application's life. Nothing in the spec bounds this, but one person assembling hero decks does
not plausibly reach four digits.

## Options Considered

**(a) Plain files — one directory per run.** `run.json` written by atomic replace, blobs
alongside, snapshots as `snapshots/<pack>.json`. Strongest case: a run is a self-contained
directory, so FR-026f ("depends on nothing outside itself") and FR-026g ("reclaim the space")
are structurally true rather than maintained — `rm -rf` is the whole of deletion. No second
store to disagree with the filesystem. Inspectable with `cat` and `jq`, by the maintainer and
by an AI agent with Read and Grep, which is how this project is actually maintained. Named
cost: no transaction spanning a record and its blobs, and no lost-update detection unless one
is built.

**(b) SQLite for metadata, blobs as files.** Strongest case: the incremental
read-modify-write of a run across separate HTTP requests is exactly the pattern file stores
get wrong; `BEGIN IMMEDIATE` plus a version column makes a lost update loud instead of silent,
and FR-026h's `(pack, snapshot_revision)` reuse key becomes an engine-enforced `UNIQUE`
constraint. `sqlite3` is stdlib, so Principle IV's dependency clause never fires. Named cost:
two stores to keep consistent, an orphan class that does not otherwise exist, a reconciliation
sweep, a schema to migrate on each of the follow-on features the spec already names, and state
the maintainer cannot read without a SQL client.

**(c) SQLite for everything, including blobs.** Rejected on measurement, not taste. SQLite's
own *Internal Versus External BLOBs* puts the filesystem ahead past roughly 100 KB; a 202 MB
PDF is three orders of magnitude beyond it, transits the WAL on write, and materialises as a
contiguous `bytes` on read. Decisively, `DELETE` returns pages to SQLite's freelist, not to the
operating system: satisfying FR-026g's "reclaim the space" would require `VACUUM`, a full
rewrite needing up to 2× the database size in free space. All four panellists rejected this.

## Decision

**Option (a), with three mechanisms adopted from the case for (b).**

Layout, under an app-owned state directory on local disk (`MARCHAMP_STATE_DIR`, defaulting to
the platform data directory) — never inside the named library folder and never inside a
Drive-synced path:

```text
runs/<run_id>/run.json          the record; atomic replace, never truncate-in-place
runs/<run_id>/uploads/<sha256>  bytes the user supplied for a named card
runs/<run_id>/deck.pdf          hardlink to the shared object below
pdfs/standard/<pack>@<rev>.pdf  a clean run's PDF, reused by later clean runs
pdfs/saved/<uuid>.pdf           a customized run's PDF, named by the user
snapshots/<pack>.json           one pack's card data, with its revision and validators
```

The three borrowed mechanisms:

1. **An optimistic `version` integer on `run.json`.** Every mutating request carries the
   version it read; a mismatch is a `409`, not a silent overwrite. This is what both advocates
   for (b) actually named as the fix for lost updates — the mechanism is the version field, not
   the engine. Writes are serialised per run by an in-process lock and committed by
   `os.replace`.
2. **Hardlinks for the shared PDF.** `os.link` gives kernel-maintained refcounting: the bytes
   return to the operating system when the last link goes, so FR-026g holds without a refcount
   anyone maintains, and `EEXIST` on `os.link` is a free atomic uniqueness primitive for the
   `(pack, revision)` key of FR-026h.
3. **Write ordering, and `F_FULLFSYNC` on macOS.** Blob durable before the record that
   references it; record updated before a blob is unlinked. Crash residue is therefore always an
   orphan file — sweepable at startup — and never a record pointing at a PDF that was never
   fully written. `fsync` on Darwin does not flush the drive's own write cache;
   `fcntl(fd, F_FULLFSYNC)` does, and `os.replace` needs the file `fsync`'d before the rename
   and the directory `fsync`'d after it.

`TODO(ASSET_TARGET)` is **not closed** by this plan, and is narrowed in writing: it covers
source assets and their encodings. The run store is app-owned state in a different category,
and does not sit behind `assets.Store` — that protocol is read-only, image-shaped
(`AssetInfo` carries `width_px`), and rooted at a boundary that changes every run.

## Consequences

Deletion, reclamation, and "a finished run depends on nothing outside itself" become
properties of the layout rather than invariants someone maintains. Backup is `cp -r`. A run
record is readable with `cat`, which keeps the diagnostic loop one step long for both the
maintainer and an agent. No new dependency, no schema, no migration tooling, and no
constitution amendment.

What becomes harder: there is no transaction across a record and its blobs, so a startup sweep
for orphaned uploads is owed. There is no query engine, so "which runs pinned revision X" is a
scan — nothing asks for that today. Schema evolution is Pydantic defaults over a
`schema_version` field, which is cheap but weakly enforced; a run written by a newer version
must be refused rather than misread.

The revisit trigger is concrete: **a second writer process.** An MCP server, a CLI beside the
running service, or a background refresh daemon breaks rename-based coordination, and at that
point option (b) is correct and migrating a few dozen JSON files into SQLite is an afternoon.

## Dissenting Opinions

Two of the four panellists recommended option (b), and both named the same load-bearing
reason.

The durability hardliner: *"Files-with-a-`threading.Lock` gives you mutual exclusion but not
lost-update detection, so tab B silently overwrites tab A's answer. That is a data-loss bug you
cannot see."* And on the ordering rules this ADR adopts: *"Mine is ~40 lines of fsync ordering
that will never be exercised by a test, because nobody writes a power-loss test. I am trading
proven crash-atomicity for hand-rolled crash-atomicity in exactly the code path where
hand-rolling is most often subtly wrong (the directory fsync is the line everyone omits)."*

The migration realist: *"What tips me anyway: incremental cross-request mutation of run state
under a thread pool. A lost update is silent and corrupting; an orphan blob is detectable in one
pass and costs disk. I will take the loud, bounded failure over the quiet one. But this is a
genuine 60/40, not a rout."* Their stated flip condition is met by this decision — *"I would
switch to plain files if the plan establishes that run state is only ever written by whole-record
replacement under one process-wide lock"* — which is what the version field plus per-run lock
plus `os.replace` establishes.

The dissent is vindicated if a lost update is ever observed in practice, or if the atomic-write
helper is found wrong in review — the hardliner is right that no test will exercise power loss,
so that helper must be reviewed as the load-bearing code it is rather than as plumbing.
