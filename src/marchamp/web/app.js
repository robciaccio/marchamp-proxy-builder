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

// ------------------------------------------------------------------------- start up

function main() {
  for (const link of document.querySelectorAll("[data-goto]")) {
    // FR-003a: a running generation never blocks navigation. It keeps running and keeps
    // updating, so stepping back to look at something and returning finds it further along
    // rather than reset — and starting another simply abandons this one (FR-003b).
    link.addEventListener("click", () => showStep(Number(link.dataset.goto)));
  }
  wireOptions();
  $("generate").addEventListener("click", generate);
  showStep(1);
  loadDecks();
}

main();
