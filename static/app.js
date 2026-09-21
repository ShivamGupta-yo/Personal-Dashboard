/**
 * Morning brief: browser-side script (plain JavaScript, no build step, no libraries).
 *
 * It talks to the local Flask server (app.py) through JSON endpoints under /api/ and fills in the panels of
 * index.html. The code is grouped in the same order as the page (top to bottom, main column, then side rail):
 *
 *     1. Helpers             small utilities used everywhere (DOM builder, fetch wrapper, formatting, toast)
 *     2. State               what the page remembers while it is open
 *     3. Page header         greeting, one-sentence summary, weather
 *     4. Mail                main column
 *     5. News                main column
 *     6. Papers              main column
 *     7. Read later          main column
 *     8. Spotify             side rail: now playing
 *     9. Focus timer         side rail
 *    10. Today               side rail: Google Calendar events
 *    11. Tasks               side rail: task list and the "Push to Calendar" dialog
 *    12. Theme and start-up  dark mode, refresh-all, and start() which wires everything together
 */

"use strict";

/* -------------------------------------------------------------------------- */
/* 1. HELPERS                                                                 */
/* Small utilities used by every panel.                                       */
/* -------------------------------------------------------------------------- */

/** Shorthand for querySelector: $("#id") or $(".class", parentElement). */
const $ = (selector, root = document) => root.querySelector(selector);

/** Returns the URL only if it is http(s). Anything else (for example "javascript:") becomes "#". */
function safeUrl(url) {
  try {
    const parsed = new URL(url, location.href);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : "#";
  } catch {
    return "#";
  }
}

/**
 * Builds a DOM element without innerHTML, so text from feeds and emails can never run as code.
 *   h("a", { class: "x", href: url, text: "Label", onclick: fn }, child1, child2)
 * Special attribute names: class, text (sets textContent), href (checked by safeUrl) and on... event handlers.
 * Children can be nodes, strings/numbers or arrays; false and null are skipped, so `cond && h(...)` works.
 */
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    // false / null values are skipped, so callers can write: condition && value
    if (value === false || value == null) continue;
    // special attribute names first, everything else becomes a normal attribute
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "href") el.setAttribute("href", safeUrl(value));
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  // nodes are added as they are, everything else becomes a text node
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return el;
}

/**
 * fetch() wrapper that never throws. It always resolves to the parsed JSON,
 * or to { error: "..." } when the request fails, so callers only have to check `data.error`.
 */
async function api(path, options) {
  try {
    const res = await fetch(path, options);
    // an empty or invalid body still gives an object
    const data = await res.json().catch(() => ({}));
    if (!res.ok && !data.error) data.error = `Request failed (${res.status}).`;
    return data;
  } catch {
    // network failure: the server is probably not running
    return { error: "Could not reach the local server. Is app.py still running?" };
  }
}

/** Sends a JSON body (POST unless told otherwise) and returns the same result shape as api(). */
const sendJson = (path, body, method = "POST") =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

/** 5 -> "05" (two-digit numbers for clocks). */
const pad = (n) => String(n).padStart(2, "0");

/** Date -> "HH:MM". */
const clock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

/** Today's date as "YYYY-MM-DD" (local time), the same format tasks use for due dates. */
const todayKey = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

/** Epoch seconds -> "just now", "12m ago", "3h ago" or "2d ago". */
function timeAgo(epochSeconds) {
  const minutes = Math.round((Date.now() / 1000 - epochSeconds) / 60);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** Epoch seconds -> "HH:MM" if it was today, otherwise "5 Sep". */
function mailTime(epochSeconds) {
  const d = new Date(epochSeconds * 1000);
  return d.toDateString() === new Date().toDateString()
    ? clock(d)
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** Handle of the timer that hides the toast, so a new message restarts the countdown. */
let toastTimer;

/** Shows a short message at the bottom of the screen for a few seconds (errors, confirmations). */
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 4500);
}

/**
 * Shows a setup / disabled / error message inside a panel instead of its content.
 * Returns true if it handled the response (so the caller should stop), false if the data is fine.
 * `retry` is what the "Try again" button calls.
 */
function panelStatus(box, data, retry) {
  if (data.status === "setup_needed") {
    box.replaceChildren(
      h("div", { class: "note" },
        h("p", { text: data.message }),
        h("p", { class: "muted small", text: "Steps are in README.md under \"Connect Google\"." }))
    );
    return true;
  }
  if (data.status === "disabled") {
    box.replaceChildren(h("p", { class: "muted", text: "Turned off in config.json." }));
    return true;
  }
  if (data.error) {
    box.replaceChildren(
      h("div", { class: "note error" },
        h("p", { text: data.error }),
        h("button", { class: "link", type: "button", onclick: retry, text: "Try again" }))
    );
    return true;
  }
  return false;
}

/* -------------------------------------------------------------------------- */
/* 2. STATE                                                                   */
/* What the page remembers while it is open.                                  */
/* -------------------------------------------------------------------------- */

/** Fallback settings. Replaced by the real ones from /api/config when the page starts (see start()). */
let cfg = {
  user_name: "",
  greetings: [{ lang: "en", morning: "Good morning", afternoon: "Good afternoon", evening: "Good evening" }],
  timer: { focus_minutes: 25, break_minutes: 5, long_break_minutes: 15, sessions_before_long_break: 4 },
};

/** Latest data of the panels that other parts of the page need (for example the summary sentence). */
const S = { mail: null, events: null, tasks: null, news: null };

/** URLs already saved to "Read later", so their Save buttons can show "Saved". */
const savedUrls = new Set();

/** Which mail tab is open: "important" or "all". */
let mailMode = "important";

/** Which news tab is open ("All" or one of the categories from the server). */
let newsCategory = "All";

/** Position in cfg.greetings of the language currently shown in the header. */
let greetingIndex = 0;
let activeCalendarTask = null; // Stores the task being pushed to the calendar

/* -------------------------------------------------------------------------- */
/* 3. PAGE HEADER                                                             */
/* Greeting, one-sentence summary and weather (top of the page).              */
/* -------------------------------------------------------------------------- */

/** "morning" (before 12:00), "afternoon" (before 17:00) or "evening": picks the right word from the greeting config. */
function partOfDay() {
  const hour = new Date().getHours();
  return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
}

/**
 * Shows greeting number `index` (wraps around the list) in the header.
 * With animate = true the old text fades out for a moment (CSS class "swap") before the new one appears.
 */
function showGreeting(index, animate) {
  greetingIndex = index % cfg.greetings.length;
  const g = cfg.greetings[greetingIndex];
  const el = $("#greeting");
  const apply = () => {
    el.textContent = cfg.user_name ? `${g[partOfDay()]}, ${cfg.user_name}` : g[partOfDay()];
    el.setAttribute("lang", g.lang);
    el.classList.remove("swap");
    fitGreeting();
  };
  if (animate) {
    el.classList.add("swap");
    setTimeout(apply, 140);
  } else {
    apply();
  }
}

/**
 * Auto-fit: measures the greeting with the real font and hands the CSS its width in "em" (--fit).
 * The CSS then makes the text exactly as big as fits beside the weather (never bigger than its maximum),
 * so ANY language or length works without touching style.css. If JS is off, the per-language --fit values
 * in style.css still apply.
 */
function fitGreeting() {
  const el = $("#greeting");
  if (!el || !el.textContent) return;

  const probe = document.createElement("span");            // invisible copy of the text at a known size
  probe.textContent = el.textContent;
  probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap;font-size:60px;";
  el.append(probe);
  const em = probe.getBoundingClientRect().width / 60;      // text width in "em"
  probe.remove();

  let fit = em * 1.02;                                       // 2% safety margin
  el.style.setProperty("--fit", fit.toFixed(2));
  for (let i = 0; i < 8 && el.scrollWidth > el.clientWidth + 0.5; i++) {   // letters get slightly wider at smaller sizes
    fit *= 1.03;
    el.style.setProperty("--fit", fit.toFixed(2));
  }
}

/** Rebuilds the one-sentence summary under the header from whatever data has loaded so far. */
function updateSummary() {
  const parts = [];
  // unread mail that is important (or pinned)
  if (S.mail) {
    const n = S.mail.items.filter((m) => (m.important || m.state === "pinned") && m.unread).length;
    if (n) parts.push(`${n} unread important ${n === 1 ? "email" : "emails"}`);
  }
  // events that have not finished yet (all-day events always count)
  if (S.events) {
    const now = Date.now();
    const n = S.events.filter((e) => e.all_day || new Date(e.end) > now).length;
    if (n) parts.push(`${n} ${n === 1 ? "event" : "events"} still ahead today`);
  }
  // tasks that are due today or overdue
  if (S.tasks) {
    const today = todayKey();
    const n = S.tasks.filter((t) => !t.done && t.due && t.due <= today).length;
    if (n) parts.push(`${n} ${n === 1 ? "task" : "tasks"} due`);
  }
  // nothing to report: either nothing has loaded yet, or there is really nothing urgent
  const anyLoaded = S.mail || S.events || S.tasks;
  const text = parts.join(", ");
  $("#summary").textContent = text
    ? text.charAt(0).toUpperCase() + text.slice(1) + "."
    : anyLoaded
      ? "Nothing urgent right now. A good window for focused work."
      : "Gathering your brief…";
}

/** Fetches /api/weather and fills the temperature block in the header (shows a short note if it fails). */
async function loadWeather(refresh) {
  const box = $("#weather");
  const data = await api("/api/weather" + (refresh ? "?refresh=1" : ""));
  if (data.error || data.status) {
    box.replaceChildren(data.error ? h("span", { class: "muted small", text: "Weather unavailable" }) : "");
    return;
  }
  box.replaceChildren(
    h("span", { class: "temp", text: `${data.temp}°` }),
    h("span", { class: "wx-desc", text: data.description }),
    h("span", {
      class: "wx-more",
      text: `${data.label}: feels like ${data.feels}°, high ${data.high}°, low ${data.low}°, ${data.rain_chance}% chance of rain`
    })
  );
}

/* -------------------------------------------------------------------------- */
/* 4. MAIN COLUMN: MAIL                                                       */
/* -------------------------------------------------------------------------- */

/** Order of the mail list: pinned first, then highest score, then newest. (The server sorts the same way.) */
const mailSort = (a, b) => {
  if ((a.state === "pinned") !== (b.state === "pinned")) return a.state === "pinned" ? -1 : 1;
  return b.score - a.score || b.ts - a.ts;
};

/** Fetches /api/mail into S.mail and draws it. Setup and error messages are shown by panelStatus(). */
async function loadMail(refresh) {
  const box = $("#mailList");
  if (!S.mail) box.replaceChildren(h("p", { class: "muted", text: "Loading mail…" }));
  const data = await api("/api/mail" + (refresh ? "?refresh=1" : ""));
  if (panelStatus(box, data, () => loadMail(true))) {
    S.mail = null;
    $("#mailControls").hidden = true;
    $("#mailFoot").textContent = "";
    updateSummary();
    return;
  }
  S.mail = data;
  $("#mailControls").hidden = false;
  renderMail();
  updateSummary();
}

/** Draws the mail list for the open tab (Important / All), the tab counters and the note under the list. */
function renderMail() {
  const box = $("#mailList");
  const items = S.mail.items;
  const important = items.filter((m) => m.important || m.state === "pinned");
  $("#mailCountImportant").textContent = important.length;
  $("#mailCountAll").textContent = items.length;
  document.querySelectorAll("[data-mail-mode]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.mailMode === mailMode))
  );

  const shown = mailMode === "all" ? items : important;
  box.replaceChildren();
  if (!shown.length) {
    box.append(
      h("p", {
        class: "muted empty",
        text: mailMode === "all" ? "No mail from the last couple of days." : "Nothing important right now."
      })
    );
  }
  shown.forEach((m) => box.append(mailRow(m)));

  const foot = $("#mailFoot");
  foot.replaceChildren();
  if (S.mail.done_count) {
    foot.append(`${S.mail.done_count} marked done. `,
      h("button", { class: "link", type: "button", text: "Show them again", onclick: async () => {
        await sendJson("/api/mail/reset-done");
        loadMail(false);
      } }));
  }
  if (S.mail.stale) foot.append(" Showing the last successful fetch.");
}

/** Builds one mail row. Clicking it (or pressing Enter / Space) expands the preview and the "Why it is here" reasons. */
function mailRow(m) {
  const pinned = m.state === "pinned";
  const row = h("article", {
    class: `mail-row level-${m.level}${m.unread ? " unread" : ""}${pinned ? " pinned" : ""}`,
    tabindex: 0,
    "aria-expanded": "false",
  });
  // wraps a button handler so clicking the button does not also expand the row
  const stop = (fn) => (e) => { e.stopPropagation(); fn(); };

  row.append(
    h("div", { class: "bar", "aria-hidden": "true" }),
    h("div", {},
      h("div", { class: "mail-top" },
        h("span", { class: "sender", text: m.from_name }),
        h("time", { text: mailTime(m.ts) }),
        pinned && h("span", { class: "tag", text: "Pinned" })),
      h("a", {
        class: "subject",
        href: `https://mail.google.com/mail/u/1/#inbox/${m.id}`,
        target: "_blank",
        rel: "noopener",
        onclick: (e) => e.stopPropagation(),
        text: m.subject
      }),
      h("p", { class: "snippet", text: m.snippet }),
      m.reasons.length > 0 && h("p", { class: "why", text: `Why it is here: ${m.reasons.join(", ")}.` })),
    h("div", { class: "row-actions" },
      h("button", {
        class: "link",
        type: "button",
        text: pinned ? "Unpin" : "Pin",
        onclick: stop(() => setMailState(m, pinned ? null : "pinned"))
      }),
      h("button", {
        class: "link",
        type: "button",
        text: "Done",
        onclick: stop(() => setMailState(m, "done"))
      }))
  );

  const toggle = () => {
    const open = row.classList.toggle("open");
    row.setAttribute("aria-expanded", String(open));
  };
  row.addEventListener("click", toggle);
  row.addEventListener("keydown", (e) => {
    if (e.target === row && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      toggle();
    }
  });
  return row;
}

/**
 * Pins, unpins or marks a message as done. The screen updates immediately, then the server is told.
 * state is "pinned", "done" or null (null = back to normal).
 */
async function setMailState(m, state) {
  m.state = state;
  if (state === "done") {
    S.mail.items = S.mail.items.filter((x) => x.id !== m.id);
    S.mail.done_count += 1;
  }
  // optimistic update: change the screen first, save to the server afterwards
  S.mail.items.sort(mailSort);
  renderMail();
  updateSummary();
  const res = await sendJson(`/api/mail/${encodeURIComponent(m.id)}/state`, { state });
  if (res.error) toast(`Could not save that change: ${res.error}`);
}

/* -------------------------------------------------------------------------- */
/* 5. MAIN COLUMN: NEWS                                                       */
/* -------------------------------------------------------------------------- */

/** Fetches /api/news into S.news and draws it. */
async function loadNews(refresh) {
  const box = $("#newsList");
  if (!S.news) box.replaceChildren(h("p", { class: "muted", text: "Loading news…" }));
  const data = await api("/api/news" + (refresh ? "?refresh=1" : ""));
  if (panelStatus(box, data, () => loadNews(true))) {
    S.news = null;
    $("#newsTabs").replaceChildren();
    return;
  }
  S.news = data;
  if (!data.categories.includes(newsCategory)) newsCategory = "All";
  renderNews();
}

/** The "Save" button of a news story or paper (adds it to Read later). Shared by the news and papers panels. */
function saveButton(kind, item, source) {
  const btn = h("button", { class: "link", type: "button" });
  const paint = () => {
    btn.textContent = savedUrls.has(item.url) ? "Saved" : "Save";
    btn.disabled = savedUrls.has(item.url);
  };
  paint();
  btn.addEventListener("click", async () => {
    savedUrls.add(item.url);
    paint();
    const res = await sendJson("/api/bookmarks", { kind, title: item.title, url: item.url, source });
    if (res.error) {
      savedUrls.delete(item.url);
      paint();
      toast(res.error);
    } else {
      loadSaved();
    }
  });
  return btn;
}

/** Draws the category tabs and the ranked list of stories for the open tab. */
function renderNews() {
  const data = S.news;
  $("#newsTabs").replaceChildren(
    ...data.categories.map((c) =>
      h("button", { class: "chip", type: "button", "aria-pressed": String(c === newsCategory), text: c,
        onclick: () => { newsCategory = c; renderNews(); } })
    )
  );

  const list = h("ol", { class: "news" });
  (data.items[newsCategory] || []).forEach((it) => {
    list.append(
      h("li", {},
        h("div", {},
          h("a", { class: "headline", href: it.url, target: "_blank", rel: "noopener", text: it.title }),
          it.summary && h("p", { class: "summary-line", text: it.summary }),
          h("p", { class: "meta" },
            h("span", { class: "source", text: it.source }),
            h("span", { text: timeAgo(it.ts) }),
            it.also_in.length > 0 && h("span", { text: `Also covered by ${it.also_in.join(", ")}` }))),
        saveButton("news", it, it.source))
    );
  });
  $("#newsList").replaceChildren(list);

  const foot = $("#newsFoot");
  foot.textContent = data.warnings.length
    ? `${data.warnings.length} feed(s) could not be read: ${data.warnings.join("; ")}`
    : "";
}

/* -------------------------------------------------------------------------- */
/* 6. MAIN COLUMN: PAPERS                                                     */
/* -------------------------------------------------------------------------- */

/** Fetches /api/papers and draws the list; each paper has an Abstract toggle, a PDF link and a Save button. */
async function loadPapers(refresh) {
  const box = $("#papersList");
  if (!$("#papersList").children.length) box.replaceChildren(h("p", { class: "muted", text: "Loading papers…" }));
  const data = await api("/api/papers" + (refresh ? "?refresh=1" : ""));
  if (panelStatus(box, data, () => loadPapers(true))) return;

  box.replaceChildren();
  if (!data.papers.length) box.append(h("p", { class: "muted empty", text: "No new papers found for your topics." }));
  data.papers.forEach((p) => {
    const abstract = h("p", { class: "abstract", hidden: true, text: p.abstract });
    const toggle = h("button", { class: "link", type: "button", "aria-expanded": "false", text: "Abstract",
      onclick: (e) => {
        const opening = abstract.hidden;
        abstract.hidden = !opening;
        e.currentTarget.setAttribute("aria-expanded", String(opening));
        e.currentTarget.textContent = opening ? "Hide abstract" : "Abstract";
      } });
    const authors = p.authors.slice(0, 3).join(", ") + (p.authors.length > 3 ? " and others" : "");
    box.append(
      h("article", { class: "paper" },
        h("a", { class: "headline", href: p.url, target: "_blank", rel: "noopener", text: p.title }),
        h("p", { class: "meta" },
          h("span", { text: authors }),
          h("span", { text: p.published }),
          ...p.topics.map((t) => h("span", { class: "topic", text: t }))),
        h("div", { class: "paper-actions" },
          toggle,
          p.pdf && h("a", { class: "link", href: p.pdf, target: "_blank", rel: "noopener", text: "PDF" }),
          saveButton("paper", p, "arXiv")),
        abstract)
    );
  });
  $("#papersFoot").textContent = data.warnings.length ? `Some topics failed: ${data.warnings.join("; ")}` : "";
}

/* -------------------------------------------------------------------------- */
/* 7. MAIN COLUMN: READ LATER                                                 */
/* -------------------------------------------------------------------------- */

/** Fetches the saved links (/api/bookmarks) and draws the Read later list; also refreshes savedUrls. */
async function loadSaved() {
  const data = await api("/api/bookmarks");
  const box = $("#savedList");
  if (data.error) { box.replaceChildren(h("p", { class: "muted", text: data.error })); return; }
  savedUrls.clear();
  data.bookmarks.forEach((b) => savedUrls.add(b.url));
  box.replaceChildren();
  if (!data.bookmarks.length) {
    box.append(h("p", { class: "muted empty", text: "Nothing saved yet. Press Save on a news story or paper to keep it here." }));
    return;
  }
  data.bookmarks.forEach((b) =>
    box.append(
      h("div", { class: "saved-row" },
        h("span", {},
          h("a", { class: "headline", href: b.url, target: "_blank", rel: "noopener", text: b.title }),
          h("span", { class: "muted small", text: `  ${b.source || b.kind}` })),
        h("button", { class: "link", type: "button", text: "Remove", onclick: async () => {
          await sendJson(`/api/bookmarks/${b.id}`, {}, "DELETE");
          loadSaved();
        } }))
    )
  );
}

/* -------------------------------------------------------------------------- */
/* 8. SIDE RAIL: SPOTIFY (NOW PLAYING)                                        */
/* -------------------------------------------------------------------------- */

/** Not used at the moment (the 3-second polling interval is started in start()). Kept as it was. */
let spotifyPollTimer = null;

/**
 * Asks /api/spotify what is playing and draws the "Now playing" card with previous / play-pause / next buttons.
 * Hides the whole block if Spotify is turned off in config.json.
 */
async function loadSpotify() {
  const data = await api("/api/spotify");
  const container = $("#spotifyWidget");
  const dot = $("#spotifyStatusDot");

  if (data.status === "disabled") {
    $(".spotify-block").hidden = true;
    return;
  }

  if (data.error) {
    dot.classList.remove("active");
    // Show the actual Python error instead of a generic message
    container.replaceChildren(h("p", { class: "muted small", text: data.error }));
    return;
  }

  // Only hide the widget if Spotify is completely closed/empty
  if (!data.title) {
    dot.classList.remove("active");
    container.replaceChildren(h("p", { class: "muted small", text: "Not currently playing." }));
    return;
  }

  // Toggle the green dot based on whether it is actively playing or paused
  if (data.is_playing) {
    dot.classList.add("active");
  } else {
    dot.classList.remove("active");
  }

  const art = data.image
    ? h("img", { src: data.image, alt: "Album Art", class: "spotify-art" })
    : h("div", { class: "spotify-art", style: "background: var(--line);" });

  const content = h("a", { class: "spotify-content", href: data.url, target: "_blank", rel: "noopener" },
    art,
    h("div", { class: "spotify-meta" },
      h("span", { class: "spotify-track", text: data.title }),
      h("span", { class: "spotify-artist", text: data.artist })
    )
  );

  const prevBtn = h("button", {
    class: "spotify-btn",
    type: "button",
    text: "⏮",
    title: "Previous",
    onclick: async () => {
      prevBtn.disabled = true;
      await sendJson("/api/spotify/toggle", { action: "previous" });
      setTimeout(loadSpotify, 500);
    }
  });

  const toggleBtn = h("button", {
    class: "spotify-btn",
    type: "button",
    text: data.is_playing ? "⏸" : "▶",
    title: data.is_playing ? "Pause" : "Play",
    onclick: async () => {
      toggleBtn.disabled = true;
      await sendJson("/api/spotify/toggle", { action: data.is_playing ? "pause" : "play" });
      setTimeout(loadSpotify, 500);
    }
  });

  const nextBtn = h("button", {
    class: "spotify-btn",
    type: "button",
    text: "⏭",
    title: "Next",
    onclick: async () => {
      nextBtn.disabled = true;
      await sendJson("/api/spotify/toggle", { action: "next" });
      setTimeout(loadSpotify, 500);
    }
  });

  const controls = h("div", { class: "spotify-controls" }, prevBtn, toggleBtn, nextBtn);

  container.replaceChildren(content, controls);
}

/* -------------------------------------------------------------------------- */
/* 9. SIDE RAIL: FOCUS TIMER                                                  */
/* -------------------------------------------------------------------------- */

/** Length of the timer's progress ring (circle of radius 52 in the SVG). Used to animate stroke-dashoffset. */
const RING = 2 * Math.PI * 52;

/**
 * Live state of the focus timer. mode is "focus", "short" (short break) or "long" (long break).
 * While running, the time left is endsAt - now; while paused it is `remaining`.
 */
const timer = { mode: "focus", total: 0, remaining: 0, running: false, endsAt: 0, sessionsToday: 0 };

/** Reads a whole-number setting (timer lengths) from localStorage, or returns the fallback. */
const numberSetting = (key, fallback) => {
  const value = parseInt(localStorage.getItem(key), 10);
  return value > 0 ? value : fallback;
};

/** Length of each timer mode in seconds: the user's saved values, otherwise the ones from config.json. */
const lengthsInSeconds = () => ({
  focus: numberSetting("lenFocus", cfg.timer.focus_minutes) * 60,
  short: numberSetting("lenShort", cfg.timer.break_minutes) * 60,
  long: numberSetting("lenLong", cfg.timer.long_break_minutes) * 60,
});

/** Switches to a mode ("focus", "short" or "long"), stops the clock and resets it to the full length. */
function setMode(mode) {
  timer.mode = mode;
  timer.total = lengthsInSeconds()[mode];
  timer.remaining = timer.total;
  timer.running = false;
  renderTimer();
}

/** Redraws everything about the timer: digits, ring, button label, browser tab title and session dots. */
function renderTimer() {
  const secs = timer.running ? Math.max(0, Math.round((timer.endsAt - Date.now()) / 1000)) : timer.remaining;
  const label = timer.mode === "focus" ? "Focus" : timer.mode === "short" ? "Short break" : "Long break";
  const time = `${pad(Math.floor(secs / 60))}:${pad(secs % 60)}`;

  $("#timerTime").textContent = time;
  $("#timerMode").textContent = label;
  $("#ring").dataset.mode = timer.mode;
  // the ring empties as the time runs out
  $("#ringProgress").style.strokeDashoffset = String(RING * (1 - (timer.total ? secs / timer.total : 1)));
  $("#timerToggle").textContent = timer.running ? "Pause" : secs < timer.total ? "Resume" : "Start";
  document.title = timer.running ? `${time} ${label}` : "Shivam - Dashboard";

  const per = cfg.timer.sessions_before_long_break;
  const filled = timer.mode === "long" ? per : timer.sessionsToday % per;
  $("#timerDots").replaceChildren(...Array.from({ length: per }, (_, i) => h("i", { class: i < filled ? "on" : "" })));
}

/** Plays two short beeps when a timer ends (silently does nothing if the browser blocks audio). */
function chime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [660, 880].forEach((freq, i) => {
      const osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.frequency.value = freq;
      osc.connect(gain);
      gain.connect(ctx.destination);
      const t = ctx.currentTime + i * 0.25;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.25, t + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
      osc.start(t);
      osc.stop(t + 0.25);
    });
  } catch { /* audio is optional */ }
}

/** Shows a desktop notification if the user has allowed them. */
function notify(message) {
  if ("Notification" in window && Notification.permission === "granted") new Notification("Morning brief", { body: message });
}

/** Loads today's focus sessions from the server (/api/focus) and shows the totals. */
async function loadFocusStats() {
  const data = await api("/api/focus");
  if (data.error) return;
  timer.sessionsToday = data.sessions;
  $("#timerStats").textContent = data.sessions
    ? `Today: ${data.sessions} ${data.sessions === 1 ? "session" : "sessions"}, ${data.minutes} min focused`
    : "No focus sessions yet today.";
  renderTimer();
}

/**
 * Called when the countdown reaches zero: beeps, notifies, logs a finished focus session on the server
 * and moves on to the next mode (a long break after every Nth focus session, otherwise a short break).
 */
async function completeTimer() {
  const wasFocus = timer.mode === "focus";
  const minutes = Math.round(timer.total / 60);
  timer.running = false;
  chime();
  notify(wasFocus ? "Focus session finished. Time for a break." : "Break over. Ready for the next session?");

  if (wasFocus) {
    const res = await sendJson("/api/focus", { minutes, label: $("#timerLabel").value });
    if (res.error) toast(res.error);

    // Clear the input field for the next session
    $("#timerLabel").value = "";

    await loadFocusStats();
  }

  const per = cfg.timer.sessions_before_long_break;
  // after a focus session: long break every Nth session, otherwise a short break; after a break: focus again
  setMode(wasFocus ? (timer.sessionsToday > 0 && timer.sessionsToday % per === 0 ? "long" : "short") : "focus");
}

/** Start / pause / resume button. */
function toggleTimer() {
  if (timer.running) {
    timer.remaining = Math.max(0, Math.round((timer.endsAt - Date.now()) / 1000));
    timer.running = false;
  } else {
    if (timer.remaining <= 0) timer.remaining = timer.total;
    timer.endsAt = Date.now() + timer.remaining * 1000;
    timer.running = true;
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  }
  renderTimer();
}

/** Runs four times a second: redraws the digits, or completes the timer when time is up. */
function tickTimer() {
  if (!timer.running) return;
  if (timer.endsAt - Date.now() <= 0) completeTimer();
  else renderTimer();
}

/** One-time setup of the timer: length inputs, buttons and the ticking interval. */
function initTimer() {
  // fill the length inputs with the saved values (or the defaults)
  $("#lenFocus").value = numberSetting("lenFocus", cfg.timer.focus_minutes);
  $("#lenShort").value = numberSetting("lenShort", cfg.timer.break_minutes);
  $("#lenLong").value = numberSetting("lenLong", cfg.timer.long_break_minutes);
  [["lenFocus", "focus"], ["lenShort", "short"], ["lenLong", "long"]].forEach(([key, mode]) =>
    $("#" + key).addEventListener("change", (e) => {
      const value = parseInt(e.target.value, 10);
      if (value > 0) localStorage.setItem(key, String(value));
      if (!timer.running && timer.mode === mode) setMode(mode);
    })
  );
  // buttons
  $("#timerToggle").addEventListener("click", toggleTimer);
  $("#timerReset").addEventListener("click", () => setMode(timer.mode));
  $("#timerSkip").addEventListener("click", () => setMode(timer.mode === "focus" ? "short" : "focus"));
  // start in focus mode and keep the display up to date
  setMode("focus");
  setInterval(tickTimer, 250);
  loadFocusStats();
}

/* -------------------------------------------------------------------------- */
/* 10. SIDE RAIL: TODAY (CALENDAR)                                            */
/* -------------------------------------------------------------------------- */

/** Fetches today's Google Calendar events (/api/calendar) and draws them. */
async function loadEvents(refresh) {
  const box = $("#eventsList");
  const data = await api("/api/calendar" + (refresh ? "?refresh=1" : ""));
  if (panelStatus(box, data, () => loadEvents(true))) { S.events = null; updateSummary(); return; }
  S.events = data.events;
  renderEvents();
  updateSummary();
}

/** Draws today's events. The current event is highlighted, finished ones are dimmed, each has a Delete button. */
function renderEvents() {
  const box = $("#eventsList");
  if (!S.events.length) { box.replaceChildren(h("p", { class: "muted", text: "No events today." })); return; }
  const now = Date.now();
  const list = h("ul", {});

  S.events.forEach((e) => {
    const start = new Date(e.start), end = new Date(e.end);
    const live = !e.all_day && start <= now && now < end;
    const past = !e.all_day && end <= now;

    // Create the delete button
    const deleteBtn = h("button", {
      class: "link small",
      type: "button",
      text: "Delete",
      onclick: async () => {
        if (!confirm(`Delete "${e.title}" from your calendar?`)) return;

        // POST /api/calendar/remove, event id in the JSON body
        deleteBtn.disabled = true;
        const res = await sendJson("/api/calendar/remove", { event_id: e.id });
        deleteBtn.disabled = false;

        if (res.error) {
          toast(res.error);
        } else {
          toast("Event deleted");
          loadEvents(true);
        }
      }
    });

    list.append(
      h("li", { class: `event${live ? " live" : ""}${past ? " past" : ""}` },
        h("span", { class: "when", text: e.all_day ? "All day" : `${clock(start)}–${clock(end)}` }),
        h("span", { class: "what" },
          h("strong", { text: e.title }),
          e.location && h("span", { class: "muted small", text: e.location }),
          e.join_url && h("a", { class: "small", href: e.join_url, target: "_blank", rel: "noopener", text: "Join call" })
        ),
        // Only show the delete button if the event has an ID from Google Calendar
        e.id && h("div", { class: "controls", style: "margin-left: auto;" }, deleteBtn)
      )
    );
  });
  box.replaceChildren(list);
}

/* -------------------------------------------------------------------------- */
/* 11. SIDE RAIL: TASKS                                                       */
/* Includes the "Push to Calendar" dialog.                                    */
/* -------------------------------------------------------------------------- */

/** Fetches the task list (/api/tasks) into S.tasks and draws it. */
async function loadTasks() {
  const data = await api("/api/tasks");
  if (data.error) { $("#tasksList").replaceChildren(h("li", { class: "muted", text: data.error })); return; }
  S.tasks = data.tasks;
  renderTasks();
  updateSummary();
}

/** Opens the "Push to Calendar" dialog for a task (start time, end time and repeat are optional). */
function openCalendarModal(task) {
  activeCalendarTask = task;
  $("#calendarModalTitle").textContent = "Push to Calendar";
  $("#calendarModalTask").textContent = task.title;
  $("#calStart").value = "";
  $("#calEnd").value = "";
  $("#calRecurrence").value = "";
  $("#calendarModal").showModal();
}

/** Closes the "Push to Calendar" dialog. */
function closeCalendarModal() {
  activeCalendarTask = null;
  $("#calendarModal").close();
}

/** "Push to Calendar" button in the dialog: creates a Google Calendar event for the task and refreshes the panels. */
async function confirmCalendarPush() {
  if (!activeCalendarTask) return;
  const t = activeCalendarTask;

  const start_time = $("#calStart").value || null;
  const end_time = $("#calEnd").value || null;
  const recurrence = $("#calRecurrence").value || null;

  const btn = $("#calConfirm");
  btn.disabled = true;
  btn.textContent = "Pushing...";

  const res = await sendJson(`/api/tasks/${t.id}/calendar`, { start_time, end_time, recurrence }, "POST");

  btn.disabled = false;
  btn.textContent = "Push to Calendar";

  if (res.error) {
    toast(res.error);
  } else {
    toast("Added to Calendar!");
    loadEvents(true); // Force refresh the calendar panel
    closeCalendarModal();
    loadTasks(); // Refresh tasks so they display correctly
  }
}

/** Draws the task list: checkbox, title, due-date label (overdue / today / date), and the To Calendar and Delete buttons. */
function renderTasks() {
  const list = $("#tasksList");
  const today = todayKey();
  list.replaceChildren();
  if (!S.tasks.length) list.append(h("li", { class: "muted small", text: "No tasks. Add one above." }));

  S.tasks.forEach((t) => {
    let dueLabel = null, dueClass = "";
    if (t.due) {
      if (!t.done && t.due < today) { dueLabel = `Overdue since ${t.due}`; dueClass = " overdue"; }
      else if (t.due === today) { dueLabel = "Due today"; dueClass = " today"; }
      else dueLabel = `Due ${new Date(t.due + "T00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" })}`;
    }
    const box = h("input", { type: "checkbox", "aria-label": `Mark "${t.title}" as done` });
    box.checked = t.done;
    box.addEventListener("change", async () => {
      const res = await sendJson(`/api/tasks/${t.id}`, { done: box.checked }, "PATCH");
      if (res.error) toast(res.error);
      loadTasks();
    });

    // Wrap both buttons in a single controls div to maintain the 3-column grid layout
    const actions = h("div", { class: "controls" },
      h("button", {
        class: "link small",
        type: "button",
        text: "To Calendar",
        "aria-label": `Add "${t.title}" to calendar`,
        onclick: () => openCalendarModal(t)
      }),
      h("button", {
        class: "link small",
        type: "button",
        text: "Delete",
        "aria-label": `Delete "${t.title}"`,
        onclick: async () => {
          await sendJson(`/api/tasks/${t.id}`, {}, "DELETE");
          loadTasks();
        }
      })
    );

    list.append(
      h("li", { class: `task${t.done ? " done" : ""}` },
        box,
        h("span", {},
          h("span", { class: "task-title", text: t.title }),
          dueLabel && h("span", { class: `task-due${dueClass}`, text: dueLabel })),
        actions
      )
    );
  });
  $("#tasksClear").hidden = !S.tasks.some((t) => t.done);
}

/** Adds the task typed in the input box (with the optional due date) and reloads the list. */
async function addTask() {
  const title = $("#taskTitle").value.trim();
  if (!title) { toast("Write a task title first."); $("#taskTitle").focus(); return; }
  const res = await sendJson("/api/tasks", { title, due: $("#taskDue").value || null });
  if (res.error) { toast(res.error); return; }
  $("#taskTitle").value = "";
  $("#taskDue").value = "";
  loadTasks();
}

/* -------------------------------------------------------------------------- */
/* 12. THEME, REFRESH AND START-UP                                            */
/* start() runs once at the very bottom, after everything above is defined.   */
/* -------------------------------------------------------------------------- */

/** Dark / light mode: applies the saved choice and wires the theme button (choice is kept in localStorage). */
function initTheme() {
  const root = document.documentElement;
  const button = $("#theme");
  const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
  const paint = () => (button.textContent = isDark() ? "Light mode" : "Dark mode");
  try {
    const stored = localStorage.getItem("theme");
    if (stored) root.dataset.theme = stored;
  } catch { /* storage can be blocked */ }
  paint();
  button.addEventListener("click", () => {
    root.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch { /* ignore */ }
    paint();
  });
}

/** Loads every panel at the same time. `refresh` = true asks the server to skip its cache. */
async function loadAll(refresh) {
  const button = $("#refresh");
  button.disabled = true;
  button.textContent = "Refreshing…";
  // all panels load in parallel; one failing panel does not stop the others
  await Promise.allSettled([
    loadMail(refresh), loadNews(refresh), loadPapers(refresh),
    loadWeather(refresh), loadEvents(refresh), loadTasks(), loadSaved(), loadSpotify()
  ]);
  $("#updated").textContent = `Updated ${clock(new Date())}`;
  button.disabled = false;
  button.textContent = "Refresh";
}

/** Page start-up: loads the settings, then wires up all buttons and starts the loading and refresh timers. */
async function start() {
  // 1. settings from config.json (via the server)
  const loaded = await api("/api/config");
  if (!loaded.error) cfg = loaded;
  $("#demo").hidden = !cfg.demo;
  $("#dateline").textContent = new Date().toLocaleDateString(undefined, {
    weekday: "long", day: "numeric", month: "long", year: "numeric"
  });

  // 2. header: random language to start with; clicking the greeting shows the next one
  showGreeting(Math.floor(Math.random() * cfg.greetings.length), true);
  $("#greeting").addEventListener("click", () => showGreeting(greetingIndex + 1, true));
  if (document.fonts) document.fonts.ready.then(fitGreeting);   // the web font arrives after first paint
  // re-fit the greeting when the window size changes (waits until the resizing pauses)
  let fitTimer;
  window.addEventListener("resize", () => { clearTimeout(fitTimer); fitTimer = setTimeout(fitGreeting, 120); });

  // 3. controls: mail tabs, refresh, tasks, calendar dialog, menu
  document.querySelectorAll("[data-mail-mode]").forEach((b) =>
    b.addEventListener("click", () => { mailMode = b.dataset.mailMode; if (S.mail) renderMail(); })
  );
  $("#refresh").addEventListener("click", () => loadAll(true));
  $("#taskAdd").addEventListener("click", addTask);
  $("#taskTitle").addEventListener("keydown", (e) => { if (e.key === "Enter") addTask(); });
  $("#tasksClear").addEventListener("click", async () => { await sendJson("/api/tasks/clear-done"); loadTasks(); });

  // Bind Calendar Modal buttons
  $("#calCancel").addEventListener("click", closeCalendarModal);
  $("#calConfirm").addEventListener("click", confirmCalendarPush);

  // Hamburger menu: opens / closes the side drawer and turns the icon into an X
  $("#menuToggle").addEventListener("click", (e) => {
    $("#sideDrawer").classList.toggle("open");
    e.currentTarget.classList.toggle("open"); // Triggers the fixed positioning
    $(".burger-icon").classList.toggle("open");
    fitGreeting(); // the button leaves/enters the row, so re-measure the greeting
  });

  // 4. theme, timer and the first load of all panels
  initTheme();
  initTimer();
  loadAll(false);

  // 5. keep everything fresh
  setInterval(() => loadAll(false), 10 * 60 * 1000); // served from the server cache, so this is cheap
  setInterval(() => { if (S.events) { renderEvents(); updateSummary(); } }, 60 * 1000);
  loadSpotify();
  setInterval(loadSpotify, 3000);
}

// CLOCK
function updateClock() {
  const clockElement = document.getElementById('digitalClock');
  if (!clockElement) return;

  const now = new Date();
  // Formats time as "12:03 PM"
  clockElement.textContent = now.toLocaleTimeString([], { 
    hour: '2-digit', 
    minute: '2-digit' 
  });
}

// Update immediately, then every second
updateClock();
setInterval(updateClock, 1000);

/* Go. */
start();