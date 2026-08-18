/* Marchamp Proxy Builder — the browser client.
 *
 * Constitution Principle II: this file is a *client* of the HTTP API and reaches around it
 * into nothing. Every number shown here — page count, face count, progress, substitutions —
 * comes from a generation resource the API served, so a headless caller sees exactly what
 * the browser sees and an MCP layer would need no new application logic.
 */

"use strict";

const PREVIEW_WIDTH_PX = 600;
const POLL_INTERVAL_MS = 400;

const state = {
  decks: [],
  deckId: null,
  deckName: null,
  faceCount: null,
  pageSize: "LETTER",
  fitMode: "CROP",
  generationId: null,
  step: 1,
  /* Page number -> its <figure>, so a page already on screen is never torn down and
   * re-fetched while someone is looking at it. */
  pageFigures: new Map(),
  /* Bumped whenever the user changes settings or walks back a step. A poll loop belonging
   * to an older epoch stops touching the interface, which is how a generation can be
   * abandoned without a cancel control and without blocking anything (FR-003a, FR-003b). */
  epoch: 0,
};

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------------ requests

async function api(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const problem = await response.json();
      if (problem && problem.detail) detail = problem.detail;
    } catch {
      /* A non-JSON error body is still an error; the status line will have to do. */
    }
    throw new Error(detail);
  }
  return response.json();
}

// -------------------------------------------------------------------- step control

function refreshNav() {
  for (const link of document.querySelectorAll(".steps__link")) {
    const target = Number(link.dataset.goto);
    if (target === state.step) link.setAttribute("aria-current", "step");
    else link.removeAttribute("aria-current");
    // Steps 2 and 3 need a deck; step 3 needs a generation to look at.
    link.disabled = (target === 2 && !state.deckId) || (target === 3 && !state.generationId);
  }
}

function showStep(number) {
  state.step = number;
  for (const n of [1, 2, 3]) {
    $(`step-${n}`).hidden = n !== number;
  }
  refreshNav();
  // Moving focus to the heading is what makes the step change announce itself and what
  // keeps keyboard focus from being stranded on a now-hidden control (FR-003g).
  const heading = $(`step-${number}-title`);
  heading.tabIndex = -1;
  heading.focus({ preventScroll: false });
}

function banner(message, items) {
  const element = $("banner");
  if (!message) {
    element.hidden = true;
    element.textContent = "";
    return;
  }
  element.hidden = false;
  element.textContent = "";
  const p = document.createElement("p");
  p.style.margin = "0";
  p.textContent = message;
  element.append(p);
  if (items && items.length) {
    const list = document.createElement("ul");
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      list.append(li);
    }
    element.append(list);
  }
}

// --------------------------------------------------------------------- step 1: deck

async function loadDecks() {
  try {
    const health = await api("/api/health");
    if (health.problems.length) {
      banner(
        "The application is not configured yet.",
        health.problems.map((p) => p.detail),
      );
      $("deck-status").textContent = "No decks can be listed until that is fixed.";
      return;
    }
  } catch (error) {
    banner(`Could not reach the service: ${error.message}`);
    return;
  }

  try {
    const { decks } = await api("/api/decks");
    state.decks = decks;
    renderDecks();
  } catch (error) {
    banner("The catalog could not be read.", [error.message]);
    $("deck-status").textContent = "No decks are available.";
  }
}

function renderDecks() {
  const list = $("deck-list");
  list.textContent = "";
  $("deck-status").textContent = state.decks.length
    ? `${state.decks.length} deck${state.decks.length === 1 ? "" : "s"} in the catalog.`
    : "The catalog has no decks in it yet.";

  for (const deck of state.decks) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "deck";
    button.setAttribute("aria-pressed", String(deck.id === state.deckId));

    const name = document.createElement("span");
    name.className = "deck__name";
    name.textContent = deck.name;

    const meta = document.createElement("span");
    meta.className = "deck__meta";
    meta.textContent = `${deck.card_count} printed faces`;

    button.append(name, meta);
    button.addEventListener("click", () => selectDeck(deck));
    item.append(button);
    list.append(item);
  }
}

function selectDeck(deck) {
  // Exactly one deck per generation request (FR-002).
  if (state.deckId !== deck.id) invalidatePreview();
  state.deckId = deck.id;
  state.deckName = deck.name;
  state.faceCount = deck.card_count;
  renderDecks();
  $("options-deck-name").textContent = deck.name;
  $("options-face-count").textContent = String(deck.card_count);
  showStep(2);
}

// ------------------------------------------------------------------ step 2: options

/* FR-016c: a preview must not stay on screen describing settings that are no longer
 * selected. Rather than trying to keep a stale preview in step with the controls, the
 * preview is discarded outright and the user generates again — the two can then never
 * disagree, which is the property that actually matters before someone commits paper. */
function invalidatePreview() {
  state.epoch += 1;
  state.generationId = null;
  state.pageFigures.clear();
  $("pages").textContent = "";
  $("tally").hidden = true;
  $("subs").hidden = true;
  $("failures").hidden = true;
  $("download").hidden = true;
  refreshNav();
}

function wireOptions() {
  for (const input of document.querySelectorAll('input[name="page_size"]')) {
    input.addEventListener("change", () => {
      state.pageSize = input.value;
      invalidatePreview();
    });
  }
  for (const input of document.querySelectorAll('input[name="fit_mode"]')) {
    input.addEventListener("change", () => {
      state.fitMode = input.value;
      invalidatePreview();
    });
  }
}

// ------------------------------------------------------------------ step 3: preview

async function generate() {
  if (!state.deckId) return;
  invalidatePreview();
  const epoch = state.epoch;

  showStep(3);
  $("run-text").textContent = "Starting…";
  $("run-progress").hidden = false;
  $("run-progress").value = 0;
  $("generate").disabled = true;

  let created;
  try {
    const response = await fetch("/api/generations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deck_id: state.deckId,
        page_size: state.pageSize,
        fit_mode: state.fitMode,
      }),
    });
    created = await response.json();
    if (!response.ok) throw new Error(created.detail || response.statusText);
  } catch (error) {
    $("generate").disabled = false;
    if (epoch !== state.epoch) return;
    $("run-text").textContent = `Could not start: ${error.message}`;
    $("run-progress").hidden = true;
    return;
  }

  $("generate").disabled = false;
  if (epoch !== state.epoch) return; // abandoned while the request was in flight
  state.generationId = created.id;
  refreshNav();
  poll(created.id, epoch);
}

async function poll(generationId, epoch) {
  let generation;
  try {
    generation = await api(`/api/generations/${generationId}`);
  } catch (error) {
    if (epoch !== state.epoch) return;
    $("run-text").textContent = `Lost track of this generation: ${error.message}`;
    return;
  }
  // Someone changed a setting or walked back; this run is abandoned. It is bounded by the
  // service's own 120-second ceiling, so nothing needs cancelling (FR-003b).
  if (epoch !== state.epoch) return;

  render(generation);

  if (generation.status === "pending" || generation.status === "running") {
    setTimeout(() => poll(generationId, epoch), POLL_INTERVAL_MS);
  }
}

function render(generation) {
  const percent = Math.round((generation.progress ?? 0) * 100);
  $("run-progress").value = percent;

  if (generation.status === "succeeded") {
    $("run-text").textContent = "Ready to print.";
    $("run-progress").hidden = true;
  } else if (generation.status === "failed") {
    $("run-text").textContent = "This deck could not be generated.";
    $("run-progress").hidden = true;
  } else {
    $("run-progress").hidden = false;
    // FR-016a: advancement, not a spinner that conveys nothing for two minutes.
    $("run-text").textContent =
      generation.pages_ready > 0
        ? `Rendering — ${generation.pages_ready} page${generation.pages_ready === 1 ? "" : "s"} ready (${percent}%).`
        : `Preparing card images… (${percent}%)`;
  }

  renderPages(generation);
  renderTally(generation);
  renderSubstitutions(generation);
  renderFailures(generation);
}

/* FR-016b: pages appear as they are rendered rather than all at the end.
 *
 * Each page number owns one <figure> for the life of the generation. A page that is not
 * composed yet holds a placeholder of the same shape, so pages arriving does not reflow
 * what is already on screen, and a page that arrives replaces only its own placeholder. */
function renderPages(generation) {
  const container = $("pages");
  const ready = generation.pages_ready || 0;
  const total = Math.max(ready, generation.page_count || 0);

  for (let n = 1; n <= total; n += 1) {
    let figure = state.pageFigures.get(n);
    if (!figure) {
      figure = document.createElement("figure");
      figure.className = "page";
      figure.style.margin = "0";

      const label = document.createElement("figcaption");
      label.className = "page__label";
      label.textContent = `Page ${n}`;

      const pending = document.createElement("div");
      pending.className = "page__pending";
      pending.textContent = "Rendering…";

      figure.append(label, pending);
      state.pageFigures.set(n, figure);
      container.append(figure);
    }

    if (n <= ready && !figure.querySelector("img")) {
      const image = document.createElement("img");
      image.alt = `Preview of page ${n}`;
      image.loading = "lazy";
      image.src = `/api/generations/${generation.id}/pages/${n}?width=${PREVIEW_WIDTH_PX}`;
      figure.querySelector(".page__pending").replaceWith(image);
    }
  }
}

/* FR-018: page count and total printed faces, before the user commits to downloading. */
function renderTally(generation) {
  if (generation.status !== "succeeded") return;
  $("tally").hidden = false;
  $("tally-pages").textContent = String(generation.page_count ?? "—");
  $("tally-faces").textContent = String(generation.card_count ?? "—");
  $("tally-paper").textContent = generation.page_size === "A4" ? "A4" : "Letter";
  $("tally-fit").textContent = {
    CROP: "Crop",
    FIT: "Fit",
    STRETCH: "Stretch (distorted)",
  }[generation.fit_mode];

  const download = $("download");
  download.hidden = false;
  download.href = `/api/generations/${generation.id}/document`;
}

/* FR-005h / FR-018a: named alongside the preview, before paper is committed — not
 * afterwards in a log, where a user who already printed forty sheets would find them. */
function renderSubstitutions(generation) {
  const subs = generation.substitutions || [];
  $("subs").hidden = subs.length === 0;
  const list = $("subs-list");
  list.textContent = "";
  for (const sub of subs) {
    const li = document.createElement("li");
    li.textContent =
      `${sub.card_name} — printed with ${sub.used_pack || sub.used_printing_id} art ` +
      `instead of ${sub.wanted_pack || sub.wanted_printing_id}`;
    list.append(li);
  }
}

/* FR-020a: every failing card at once. Fixing one problem per attempt across repeated runs
 * is the experience this list exists to prevent. */
function renderFailures(generation) {
  const failures = generation.failures || [];
  $("failures").hidden = failures.length === 0;
  const list = $("failures-list");
  list.textContent = "";
  for (const failure of failures) {
    const li = document.createElement("li");
    li.textContent = failure.retryable
      ? `${failure.detail} (this one may clear on its own — try again)`
      : failure.detail;
    list.append(li);
  }
}


/* ======================================================== feature 002: pack assembly ==
 *
 * An assembly run is a resource with a lifecycle (FR-026a), not a form submission that
 * returns a PDF. So this half of the client has no step counter of its own: it renders
 * whatever state the run is in, which is also what makes coming back to an unfinished run
 * work without the browser remembering anything (FR-026b).
 *
 * Every mutating request carries `If-Match` with the version it last read. Two tabs
 * answering two different questions is the lost update ADR 0001's reviewers named, and a
 * 409 here means "re-read and try again" rather than "something broke".
 */

const assembly = {
  run: null,
  candidates: [],
};

function assemblyError(message) {
  const box = $("assembly-error");
  box.textContent = message;
  box.hidden = !message;
}

async function assemblyRequest(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  /* Sent on every mutating call, never only on the ones that felt risky. */
  if (options.method && options.method !== "GET" && assembly.run) {
    headers["If-Match"] = String(assembly.run.version);
  }
  const response = await fetch(path, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const problem = await response.json();
      /* The API's refusals name the card, the file, or the path at fault (FR-037, SC-008).
       * Showing that instead of a status code is the whole reason they are worded that way. */
      if (problem && problem.detail) detail = problem.detail;
    } catch (err) {
      /* A non-JSON error body is still an error; the status line stands in. */
    }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

async function startAssembly(event) {
  event.preventDefault();
  assemblyError("");
  assembly.run = null;
  const button = $("assembly-start");
  button.disabled = true;
  try {
    assembly.run = await assemblyRequest("/api/assemblies", {
      method: "POST",
      body: {
        library_root: $("library-root").value.trim(),
        hero_folder: $("hero-folder").value.trim(),
      },
    });
    renderAssembly();
  } catch (err) {
    assemblyError(err.message);
  } finally {
    button.disabled = false;
  }
}

function renderAssembly() {
  const run = assembly.run;
  if (!run) return;

  const identified = run.identification && run.identification.pack_code;
  const awaitingPack = run.state === "awaiting_pack" || run.state === "unidentified";

  /* ---- the pack, and the evidence for it (FR-012) */
  $("pack-step").hidden = !awaitingPack;
  if (awaitingPack) {
    $("pack-name").textContent = identified
      ? `${run.identification.pack_name} (${run.identification.pack_code})`
      : "No pack could be identified from this folder";
    $("pack-confidence").textContent =
      run.identification && run.identification.confidence != null
        ? `${Math.round(run.identification.confidence * 100)}% of the files match`
        : "";
    const evidence = $("pack-evidence");
    evidence.replaceChildren();
    for (const line of (run.identification && run.identification.evidence) || []) {
      const li = document.createElement("li");
      li.textContent = line;
      evidence.append(li);
    }
    $("pack-confirm").hidden = !identified;
    /* An unidentified folder opens the picker straight away: there is nothing to confirm,
     * and leaving the user to find the button would be a dead end (FR-012b). */
    if (!identified) showPackPicker();
  }

  /* ---- the decklist card (FR-013c, FR-013d) */
  const decklist = run.decklist_candidate;
  const resolved = !awaitingPack && run.state !== "identifying" && run.state !== "resolving";
  const noDecklist =
    resolved && !decklist && run.report && !run.report.decklist_printed;
  $("decklist-step").hidden = !(decklist || noDecklist);
  $("decklist-found").hidden = !decklist;
  $("decklist-missing").hidden = !noDecklist;
  $("decklist-confirm").hidden = !decklist;
  if (decklist) {
    $("decklist-ref").textContent = decklist.ref;
    const alternatives = $("decklist-alternatives");
    alternatives.replaceChildren();
    alternatives.hidden = !(decklist.alternatives && decklist.alternatives.length > 1);
    /* Two different files matched, so the user picks — the tool does not (FR-033). */
    for (const ref of decklist.alternatives || []) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn";
      button.textContent = ref;
      button.addEventListener("click", () => decideDecklist("select", ref));
      li.append(button);
      alternatives.append(li);
    }
  }
  if (noDecklist && run.report && run.report.decklist_source_url) {
    $("decklist-url").href = run.report.decklist_source_url;
  }

  /* ---- the report */
  const report = run.report;
  $("assembly-report").hidden = !report;
  if (report) {
    $("report-printed").textContent = report.cards_printed;
    $("report-in-pack").textContent = report.cards_in_pack;
    $("report-faces").textContent = report.faces_printed;
    $("report-decklist").textContent = report.decklist_printed ? "included" : "not included";

    const gaps = run.unresolved || [];
    $("gaps").hidden = gaps.length === 0;
    const gapList = $("gaps-list");
    gapList.replaceChildren();
    for (const gap of gaps) {
      const li = document.createElement("li");
      /* Named individually with where the tool looked, so the user can act on the report
       * alone rather than being handed a failed run to diagnose (FR-026d, SC-008). */
      li.textContent = `${gap.card_name} (${gap.card_code}, ${gap.group}, ${gap.side}) — looked in: ${gap.searched.join("; ")}`;
      gapList.append(li);
    }

    renderGroups(report);

    const subs = (report.resolutions || []).filter(
      (r) => r.provenance !== "folder_position",
    );
    $("substitutions").hidden = subs.length === 0;
    const subList = $("substitutions-list");
    subList.replaceChildren();
    for (const sub of subs) {
      const li = document.createElement("li");
      li.textContent = `${sub.card_name} (${sub.card_code}) — ${sub.provenance}: ${sub.file}`;
      subList.append(li);
    }

    /* FR-030b, SC-006e: a pack printed with a card left out never looks complete. */
    const omitted = report.omitted || [];
    $("omitted").hidden = omitted.length === 0;
    fillList("omitted-list", omitted, (card) =>
      `${card.card_name} (${card.card_code}, ${card.group}) — printed without`,
    );

    renderLibraryNotes(report);

    /* FR-026a: reaching `ready` does not print. The button is the confirmation. */
    $("assembly-confirm").hidden = run.state !== "ready";
    const download = $("assembly-download");
    download.hidden = run.state !== "complete";
    if (run.state === "complete") download.href = `/api/assemblies/${run.id}/document`;
    $("assembly-progress").textContent =
      run.state === "rendering" ? "Building the PDF…" : "";
    /* FR-036: null until the run is terminal, so nothing here reports a failure that has
     * not happened. Waiting on a card is the tool working, not the tool failing. */
    $("assembly-outcome").textContent = run.outcome ? OUTCOMES[run.outcome] || "" : "";
  }
}

/* FR-015e, SC-002b. FR-015d packs the four groups onto as few pages as will hold them with
 * no page break between them, so a page routinely carries the last player cards and the
 * first nemesis cards. This list is therefore the only thing a user who cannot recognise
 * the cards by sight can sort the cut stack by — which is why it is grouped and why every
 * group is named even when it holds one card. */
const GROUP_LABELS = {
  player: "Player cards",
  identity: "Identity card",
  nemesis: "Nemesis set",
  decklist: "Deck list",
};

/* FR-036, rendered for a person rather than for a consumer of the API. */
const OUTCOMES = {
  clean: "Assembled cleanly.",
  warnings: "Assembled, with notes below worth reading.",
  refused: "Refused — nothing was printed.",
};

function fillList(id, items, describe) {
  const list = $(id);
  list.replaceChildren();
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = describe(item);
    list.append(li);
  }
}

function renderGroups(report) {
  const resolutions = report.resolutions || [];
  const list = $("groups-list");
  list.replaceChildren();
  $("groups").hidden = resolutions.length === 0;

  for (const group of ["player", "identity", "nemesis", "decklist"]) {
    /* Fronts only: a double-sided card is one card to sort, not two, and listing its back
     * again would have the user hunting for a card that is not in the stack twice. */
    const cards = resolutions.filter((r) => r.group === group && r.side === "front");
    if (cards.length === 0) continue;
    const li = document.createElement("li");
    const heading = document.createElement("strong");
    heading.textContent = `${GROUP_LABELS[group]} (${cards.length})`;
    const names = document.createElement("span");
    names.textContent = ` — ${cards.map((c) => c.card_name).join(", ")}`;
    li.append(heading, names);
    list.append(li);
  }
}

function renderLibraryNotes(report) {
  const conflicts = report.conflicts || [];
  const warnings = report.low_resolution || [];
  const unused = report.unused_files || [];

  $("conflicts").hidden = conflicts.length === 0;
  $("warnings").hidden = warnings.length === 0;
  $("unused").hidden = unused.length === 0;
  $("library-notes").hidden =
    conflicts.length === 0 && warnings.length === 0 && unused.length === 0;

  const named = (entry) => `${entry.file} — ${entry.reason}`;
  fillList("conflicts-list", conflicts, named);
  fillList("warnings-list", warnings, named);
  fillList("unused-list", unused, named);
}

async function showPackPicker() {
  $("pack-picker").hidden = false;
  await loadPackCandidates("");
}

async function loadPackCandidates(query) {
  if (!assembly.run) return;
  const url = new URL(`/api/assemblies/${assembly.run.id}/packs`, window.location.origin);
  if (query) url.searchParams.set("q", query);
  try {
    const payload = await assemblyRequest(url.pathname + url.search);
    assembly.candidates = payload.candidates || [];
  } catch (err) {
    assemblyError(err.message);
    return;
  }
  const list = $("pack-candidates");
  list.replaceChildren();
  for (const candidate of assembly.candidates) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn";
    button.textContent = `${candidate.pack_name} (${candidate.pack_code})`;
    button.addEventListener("click", () => setPack("select", candidate.pack_code));
    li.append(button);
    list.append(li);
  }
}

async function setPack(action, packCode) {
  assemblyError("");
  try {
    assembly.run = await assemblyRequest(`/api/assemblies/${assembly.run.id}/pack`, {
      method: "POST",
      body: action === "select" ? { action, pack_code: packCode } : { action },
    });
    $("pack-picker").hidden = true;
    renderAssembly();
  } catch (err) {
    assemblyError(err.message);
  }
}

async function decideDecklist(action, ref) {
  assemblyError("");
  try {
    assembly.run = await assemblyRequest(`/api/assemblies/${assembly.run.id}/decklist`, {
      method: "POST",
      body: ref ? { action, ref } : { action },
    });
    renderAssembly();
  } catch (err) {
    assemblyError(err.message);
  }
}

async function confirmAssembly() {
  assemblyError("");
  $("assembly-progress").textContent = "Building the PDF…";
  try {
    /* `save_as` is omitted deliberately: an uncustomized run produces the pack's standard
     * PDF and the API refuses a name for it (FR-026h, FR-026i). A customized run is US4's
     * and US5's, and will pass one here. */
    assembly.run = await assemblyRequest(
      `/api/assemblies/${assembly.run.id}/confirmation`,
      { method: "POST", body: {} },
    );
    renderAssembly();
  } catch (err) {
    $("assembly-progress").textContent = "";
    assemblyError(err.message);
  }
}

function showMode(mode) {
  const isAssembly = mode === "assembly";
  $("assembly").hidden = !isAssembly;
  $("deck-steps").hidden = isAssembly;
  for (const id of ["step-1", "step-2", "step-3"]) {
    /* 001's steps are driven by `showStep`; hiding them wholesale here would fight it, so
     * the mode switch only ever hides, and returning to deck mode replays the step. */
    if (isAssembly) $(id).hidden = true;
  }
  for (const link of document.querySelectorAll("[data-mode]")) {
    const current = link.dataset.mode === mode;
    link.classList.toggle("is-current", current);
    link.setAttribute("aria-pressed", String(current));
  }
  if (!isAssembly) showStep(state.step);
}

function wireAssembly() {
  $("assembly-form").addEventListener("submit", startAssembly);
  $("pack-confirm").addEventListener("click", () => setPack("confirm"));
  $("pack-other").addEventListener("click", showPackPicker);
  $("pack-search").addEventListener("input", (event) =>
    loadPackCandidates(event.target.value.trim()),
  );
  $("decklist-confirm").addEventListener("click", () => decideDecklist("confirm"));
  $("decklist-skip").addEventListener("click", () => decideDecklist("skip"));
  $("assembly-confirm").addEventListener("click", confirmAssembly);
  for (const link of document.querySelectorAll("[data-mode]")) {
    link.addEventListener("click", () => showMode(link.dataset.mode));
  }
}

// ------------------------------------------------------------------------- start up

function main() {
  for (const link of document.querySelectorAll("[data-goto]")) {
    // FR-003a: a running generation never blocks navigation. It keeps running and keeps
    // updating, so stepping back to look at something and returning finds it further along
    // rather than reset — and starting another simply abandons this one (FR-003b).
    link.addEventListener("click", () => showStep(Number(link.dataset.goto)));
  }
  wireOptions();
  wireAssembly();
  $("generate").addEventListener("click", generate);
  showStep(1);
  showMode("deck");
  loadDecks();
}

main();
