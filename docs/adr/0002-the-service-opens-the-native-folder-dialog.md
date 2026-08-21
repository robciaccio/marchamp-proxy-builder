# 0002. The service opens the platform's native folder dialog, and never enumerates the filesystem

Date: 2026-08-21
Status: Proposed

## Context

Feature 005 ([spec.md](../../specs/005-folder-picker-hero-list/spec.md)) removes the two
free-text path boxes that begin every pack run. The user asked for a button that opens "the
computer's Finder dialog", followed by a list of heroes read from `<library root>/Heros/`.

**A web page cannot learn the absolute path of a directory the user chooses.** This was
verified, not assumed, and all four browser-side escapes are closed:

- `showDirectoryPicker()` — not implemented in any Safari, including Technical Preview;
  Firefox's standards position is "harmful". Where it does work, `FileSystemDirectoryHandle`
  exposes `name` and `kind` — the last path component, never the path.
- `<input webkitdirectory>` — `webkitRelativePath` is rooted at the chosen ancestor. It also
  materialises a `File` for every file in the tree, which against a 4,447-entry Drive-synced
  library is a pathology rather than a picker.
- Folder drag-and-drop — `webkitGetAsEntry()` yields a *virtual* path rooted at the drop.
  `File.path` is Electron, not a browser.
- A `--library` flag or a startup chooser — forbidden by 005 FR-016, and it only relocates the
  typing to the terminal.

So the local service must be involved. The question is how.

### Constraints that bind

- Loopback-only by design (001 FR-0A2); `Settings` rejects a non-loopback bind address.
- Runtime dependencies are deliberately lean — eight packages. The constitution's Technology
  paragraph requires an amendment to add "a component of comparable weight".
- Constitution I (Test-First) is NON-NEGOTIABLE and requires tests be *observed failing*.
- Constitution IV is Simplicity & YAGNI.
- The scan library is never written to (002 FR-001); no egress beyond MarvelCDB (002 FR-002).
- One developer, one primary user, both on macOS. CI is Linux. No packaging story.

### Two findings that reshaped the question

**1. `tkinter` is disqualified outright — measured, not argued.** It *is* present in the
uv-managed CPython 3.13 (Tk 9.0), so availability was never the objection. The objection is
that Tk on macOS is main-thread-only, and Starlette runs sync `def` endpoints on the AnyIO
worker threadpool — which is 53 of the 57 routes in `src/marchamp/api/`. Called from there it
raises an **ObjC exception that terminates the process**, uncatchable by Python:

```
NSWindow drag regions should only be invalidated on the Main Thread!
libc++abi: terminating due to uncaught exception of type NSException
```

Moving it to the main thread is worse: `askdirectory()` runs Tk's modal loop, freezing the
single-process event loop for the dialog's lifetime. "The user leaves the chooser open" becomes
"the application is hung, including the page that would say so." Any native-dialog option here
means a **subprocess**, not an in-process toolkit.

**2. The API is already a filesystem oracle, and it is already reachable cross-origin.**
Verified against the running app:

```
GET /api/health   with Host: evil.example        -> 200      (no middleware installed at all)
POST /api/assemblies  /etc + ssh                 -> 503 "cups/certs: Permission denied ..."
POST /api/assemblies  /etc + nosuch-xyz          -> 400 "not a directory inside library_root"
POST /api/assemblies  /   + Users                -> 503 "usr/sbin/authserver: Permission denied ..."
```

`AssemblyRequest.library_root` (`src/marchamp/api/schemas.py:187`) is an unconstrained absolute
path that gets walked (`src/marchamp/library/index.py:270`). Three pre-existing leaks: a
directory-existence oracle (400 vs 503), **path fragments discovered by walking an
attacker-named root**, and raw errno in a client-facing body against the constitution's
fail-closed clause. There is no `TrustedHostMiddleware` and no Origin check, which is the
textbook DNS-rebinding precondition. Chrome shipped Local Network Access in 142 (Oct 2025);
**WebKit has not implemented it**, and the user is on macOS.

This is a live defect independent of this decision. It is recorded here because it is the
reason the security ranking below is not the obvious one — and it is **not** discharged by this
ADR.

## Options Considered

### A — the service opens the platform's native folder dialog (`osascript`)

**Strongest case**: literally what was asked for. Zero new dependencies — `/usr/bin/osascript`
is first-party macOS, measured at 44 ms startup, cancel returning exit 1 / `-128`. It is a
subprocess, so the Tk threading crash does not apply and a hung dialog is **killable on
timeout**. Critically, it **enumerates nothing**: the OS hands back one path that a human
deliberately selected, so 005 FR-019 survives intact and no new capability is added to the
service. Process-spawning and platform-branching are both established idioms here —
`render/workers.py` already spawns children via `multiprocessing` and already carries measured
`sys.platform` branches at `:37` and `:123`.

**Named cost**: macOS-only in practice. Its core interaction cannot run in Linux CI. AppleScript
`choose folder` is documented to open *behind* other windows with no indication it appeared,
needing an explicit activate that may cross into TCC Automation consent attributed to Terminal.
A dialog that is never dismissed pins an AnyIO worker thread (40 by default). macOS TCC can
grant the panel access while the *server* still cannot read the folder.

### B — an in-page folder browser over a directory-listing endpoint

**Strongest case**: this is the paved road, and the survey was unambiguous — Syncthing
(`/rest/system/browse`), NiceGUI's `local_file_picker` with an `upper_limit`, Plex's "Browse for
Media Folders", Gradio's `FileExplorer`, JupyterLab's Contents API, Radarr/Sonarr all browse
server-side. **No comparable tool ships a server-opened native dialog**; the ones that have a
native dialog are desktop apps. It is a pure function of a directory tree, so every one of
FR-006–FR-014 and SC-004/SC-006/SC-009 becomes an ordinary `tmp_path` test that runs on every
push. Identical on every platform. No subprocess, no TCC, no window ordering.

**Named cost**: it requires **amending FR-019**, which forbids exactly this — to navigate *to*
the library root, the service must list above it. It converts an incidental leak into a
designed, stable, JSON-typed enumeration API with no human in the loop: under a rebound origin
an attacker walks `/Users/*`, `~/Library/Application Support/*`, `~/Development/*`, `~/.ssh`
existence, silently and instantly. It also adds roughly 350 lines of breadcrumb/list/keyboard
JS to a 1,112-line unbuilt `app.js`. And the picker it produces is worse at the job: this
user's library is a Google Drive mount, one sidebar click in Finder and a long descent through
`~/Library/CloudStorage/` in a hand-rolled browser.

### C — A with B as a fallback

**Rejected unanimously by all four panellists**, which no other position achieved. It is B's
permanent enumeration endpoint *plus* A's platform branch, two implementations of one step, and
it guarantees the tested path is the one the primary user never runs. Principle IV names this
directly. The fallback for "no native dialog" already exists, is already tested, and is called
the text box (FR-020).

### D — pywebview / desktop wrapper

Makes the native dialog correct and trivial, at the cost of pywebview + pyobjc as runtime
dependencies, a packaging story this project does not have, and the premise that the user opens
the wizard in their normal browser. Not worth it to remove two text boxes.

## Decision

**Option A: a macOS-gated `osascript` subprocess that opens the native folder dialog, with the
existing typed path (FR-020) as the only fallback. Option B's listing endpoint is explicitly
not built, and FR-019 stands unamended.**

The panel split 2–2. Three things broke the tie.

**First, the constitutional argument against A does not survive inspection.** Option B's
advocates rested heavily on Principle II — that the API must "remain sufficient to drive the
entire product without a browser, so that an MCP server or an autonomous agent can be layered
on top." An agent does not need a picker. `AssemblyRequest` takes `library_root` and
`hero_folder` as plain strings (`api/schemas.py:187-188`); an agent passes the paths directly
and always has. A dialog endpoint removes no capability an agent has today, so it adds nothing
to drive around. II is satisfied by the endpoint that already exists, under either option.

**Second, A is the only option that does not require weakening a security requirement written
this week.** B cannot be built without amending FR-019, and the amendment is not cosmetic — the
whole purpose of the browser is to reach a folder whose location is unknown, so no meaningful
upward bound exists. Set against a service with no Host validation, on a platform whose browser
has no Local Network Access protection, a permanent typed enumeration API is the wrong thing to
add. A adds no capability at all: the OS returns one human-selected path.

**Third, the testability objection is real but smaller than argued, and it is the kind of cost
this repo already carries.** Constitution I is non-negotiable and A's core interaction — a real
panel appears, comes to the front, returns a usable POSIX path — cannot run on Linux CI. But
the argv construction, the exit-1/`-128` cancel parse, the timeout, the single-flight guard, the
platform gate, and the post-dialog readability probe are all ordinary CI tests. The uncoverable
residue is one human-verified interaction, which is precisely what the existing `physical`
marker exists for, and `render/workers.py:123` is already an accepted uncovered platform branch
(`# pragma: no cover - unsupported target`). B's own browser half is equally untested today:
`tests/integration/test_web_ui.py:63-70` asserts by regexing the served text of `app.js`.

Against that: the user asked for the native dialog by name, from real use, and both B advocates
conceded they were overriding a stated preference on engineering grounds. Where the engineering
grounds turn out to be a constitutional argument that does not apply and a security requirement
that would have to be repealed, the user's stated preference wins.

### Conditions attached to the decision

1. **The Host/Origin hardening lands first, in its own PR, before this feature.**
   `TrustedHostMiddleware(allowed_hosts=["127.0.0.1", "localhost"])` plus Origin /
   `Sec-Fetch-Site` rejection on non-GET. All four panellists rated this the highest-value
   change on the table, and it is overdue regardless of OD-001.
2. **The pre-existing oracle is fixed while in there**: generic client-facing text for the walk
   failure, errno to the log and out of the response body (`assembly/service.py:113`).
3. **`tkinter` is forbidden.** Any native dialog is a subprocess.
4. **No interpolation of any stored or user-supplied string into AppleScript source, ever** —
   list argv, no `shell=True`, enforced by a test. This matters because Story 3's remembered
   root is exactly the change that will want to break it.
5. **Single-flight and a hard timeout** on the dialog: one outstanding dialog per process, 409
   on a second, `subprocess.run(timeout=…)` then kill.
6. **A readability probe runs immediately after the dialog returns** (FR-004), because TCC can
   grant the panel access the server does not have.
7. **User Story 3 is promoted from P3 to ship with Stories 1 and 2.** Two panellists reached
   this independently: a remembered root turns the chooser from a per-run action into a
   per-machine one, and `GET /api/assemblies` already returns `library_root` for every run
   while `app.js:978-982` already writes both fields back into the form.

### The falsifiable trigger that reverses this

Both A advocates named the same flip condition, and it is **not yet verified**: whether the
`osascript` dialog reliably comes to the front from a uvicorn worker thread without an
Automation TCC prompt attributed to Terminal. A dialog that opens behind the browser and stays
there is worse than B, and A's entire value is that it works when a human is present.

**This MUST be verified by hand on the target machine before implementation begins.** If it
fails, this ADR is superseded in favour of B with a bounded listing endpoint, and FR-019 is
amended at that point rather than now.

## Consequences

**Committed to**: a `darwin`-gated subprocess primitive in a service that has never spawned one
via `subprocess`; one hand-verified interaction outside CI; a worse experience on Linux and
Windows, where the typed box remains the route; and a small permanent maintenance surface
tracking AppleScript and TCC behaviour across macOS releases.

**Becomes harder**: supporting Linux or Windows as first-class platforms for this feature. If
that is ever wanted, B is the answer and this ADR should be revisited rather than extended —
extending it produces C, which the panel rejected unanimously.

**Becomes possible**: the feature ships as the user described it, with no new enumeration
capability, no dependency, no FR-019 amendment, and no repeal of a security requirement. And
the conditions attached mean the loopback service ends up *more* hardened than it is today,
which is a strictly better outcome than either option delivered on its own.

## Dissenting Opinions

**Maintenance realist — B, high confidence.** In its own words: *"A test that cannot be executed
cannot be observed failing. This is not a coverage argument — it is that A's core path cannot
satisfy the literal wording of the NON-NEGOTIABLE principle."* And on the escape hatch:
*"Marking input plumbing physical is category drift: it converts a marker that means 'verifiable
only on paper' into one that means 'untested,' and it does so for code that had a testable
alternative sitting right there."* It also observed that even a funded CI effort would test the
wrong dialog — tkinter uses native NSOpenPanel on macOS and a pure-Tcl dialog on Unix, so *"A's
tested path and A's shipped path are different code, permanently."*

**Vindicated if**: the dialog proves flaky in front-most behaviour or TCC, and the untestable
path becomes a recurring triage cost — "is the dialog behind Chrome?" as a permanent first
question on every bug report.

**Ecosystem pragmatist — B, high vs tkinter / medium vs osascript.** *"Every tool with a native
dialog is a desktop app. Every tool served over a browser either browses server-side or makes
you type."* It surveyed ten projects and found no counter-example. Its own strongest
counter-argument is recorded and was persuasive here: *"the ecosystem's caution is about hosted
deployments... where the server's filesystem is someone else's. Here the server and the Finder
are the same machine, the same user, loopback-only by design. The constraint that produced the
convention does not apply."*

**Vindicated if**: a production local-first browser-UI tool is found that ships server-opened
native dialogs successfully — the pragmatist looked and did not find one, and its absence
across ten mature projects is weak evidence that the road is unpaved for a reason.

**Both dissenters and both A advocates agreed on**: rejecting C, forbidding tkinter, promoting
Story 3, and landing the Host-header fix first. That agreement is load-bearing and is written
into the conditions above.
