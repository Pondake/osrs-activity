/*
 * OSRS Activity card.
 *
 * Shipped by the integration and registered with the frontend on setup, so it
 * arrives with the HACS download rather than as a second repository.
 *
 * This is not a dashboard card that happens to show the same numbers as the
 * Pixoo. It is the panel: a square 64x64 viewBox with every element at the
 * coordinates the blueprint draws it at, scaled up. Same four screens, same
 * choice between them, same colours -- read from the sensor rather than
 * repeated here. A position that changes in one has to change in the other,
 * which is the point: one design, two places.
 */

const BG = "#2a2218";
const ACCENT = "#ff981f";
const RULE = "#5a4a36";
const TEXT = "#c8aa78";
const DIM = "#8c785a";
const TRACK = "#483c2c";
const IDLE_BG = "#ffb400";
const IDLE_FG = "#3c2d0a";
const GOLD = "#ffdc00";
const PRAYER = "#8cc8ff";
const GREY = "#969ba0";

// PICO_8 is 4px per character and about 5px tall, and the panel positions text
// by its top-left corner. SVG positions it by the baseline, hence the offset;
// textLength pins each glyph into the same 4px cell the device uses.
const CELL = 4;
const BASELINE = 5;

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

/** A line of panel text. `anchor` "end" mirrors the device's align: right. */
function text(x, y, body, colour, anchor) {
  const content = String(body ?? "");
  if (!content) return "";
  const length = content.length * CELL;
  return `<text x="${anchor === "end" ? x - length : x}" y="${y + BASELINE}"
    fill="${colour}" textLength="${length}"
    lengthAdjust="spacingAndGlyphs">${esc(content)}</text>`;
}

const rect = (x, y, w, h, colour) =>
  w > 0 && h > 0
    ? `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${colour}"/>`
    : "";

/** Track plus fill, the pattern the panel uses for every bar it draws. */
const bar = (x, y, w, h, pct, colour) =>
  rect(x, y, w, h, TRACK) +
  rect(x, y, clamp(Math.round((pct / 100) * w), 0, w), h, colour);

const hpColour = (pct) =>
  pct < 0 ? BG : pct > 50 ? "#00dc3c" : pct > 25 ? "#ffb400" : "#ff2828";

const image = (href, x, y, size) =>
  href
    ? `<image href="${esc(href)}" x="${x}" y="${y}" width="${size}"
       height="${size}" style="image-rendering:pixelated"/>`
    : "";

class OsrsActivityCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("osrs-activity-card-editor");
  }

  static getStubConfig(hass) {
    // Found by what it carries rather than by what it is called: the entity id
    // depends on the player's name and on which release created it.
    const match = Object.keys(hass.states).find(
      (id) =>
        id.startsWith("sensor.") &&
        hass.states[id].attributes?.window_skills !== undefined,
    );
    return { entity: match || "" };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Pick the Activity sensor");
    this._config = config;
    this._built = false;
  }

  getCardSize() {
    return 5;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _build() {
    // Once only. setConfig clears _built so the styles are rebuilt after an
    // edit, but a second attachShadow throws and the card stops updating until
    // the page is reloaded.
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { background: ${BG}; border: none; overflow: hidden; }
        svg {
          display: block;
          width: 100%;
          /* Square, because the thing it mirrors is square. */
          aspect-ratio: 1 / 1;
        }
        text {
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 6px;
          font-weight: 700;
          /* The panel has no antialiasing and neither should this. */
          shape-rendering: crispEdges;
        }
        .err { padding: 16px; color: var(--error-color, #db4437); }
      </style>
      <ha-card><div class="host"></div></ha-card>`;
    this._host = this.shadowRoot.querySelector(".host");
    this._built = true;
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this._built) this._build();

    const state = this._hass.states[this._config.entity];
    if (!state) {
      this._host.innerHTML = `<div class="err">${esc(
        this._config.entity,
      )} not found</div>`;
      return;
    }
    const a = state.attributes;
    if (a.window_skills === undefined) {
      this._host.innerHTML = `<div class="err">${esc(
        this._config.entity,
      )} is not the Activity sensor</div>`;
      return;
    }

    const rows = a.skills || [];
    let body;
    if (!rows.length) body = this._standby(a);
    else if (a.combat && a.style) body = this._combat(a);
    else if (rows.length === 1) body = this._single(a, rows[0]);
    else body = this._bars(a, rows);

    this._host.innerHTML = `
      <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
        ${rect(0, 0, 64, 64, BG)}
        ${this._strip(a)}
        ${body}
      </svg>`;
  }

  /** The 2px health strip along the top of every screen. */
  _strip(a) {
    const hp = a.health_pct ?? -1;
    if (hp < 0) return "";
    return rect(0, 0, clamp(Math.round(hp * 0.64), 1, 64), 2, hpColour(hp));
  }

  _rule() {
    return rect(0, 13, 64, 1, RULE);
  }

  /** The idle plate: on the panel IDLE replaces the rate, not the XP. */
  _rate(a, y, perHourText) {
    const idle = Boolean(a.idle);
    return (
      rect(0, 27, 36, 10, idle ? IDLE_BG : BG) +
      text(2, y, idle ? "IDLE" : perHourText, idle ? IDLE_FG : TEXT)
    );
  }

  _vitals(a) {
    const hp = a.health_pct ?? -1;
    const pray = a.prayer_pct ?? -1;
    return (
      text(2, 45, "HP", TEXT) +
      bar(22, 44, 40, 7, hp < 0 ? 0 : hp, hpColour(hp)) +
      text(2, 55, "PRAY", TEXT) +
      bar(22, 54, 40, 7, pray < 0 ? 0 : pray, pray < 0 ? BG : PRAYER)
    );
  }

  _combat(a) {
    const kills = Number(a.slayer_kills) || 0;
    const perHour = `${Math.round((a.per_hour || 0) / 100) / 10}k/HR`;
    return (
      text(2, 5, a.style, ACCENT) +
      text(62, 5, kills ? `x${kills}` : "", GREY, "end") +
      this._rule() +
      image(a.style_icon_url, 38, 16, 25) +
      text(2, 19, `+${a.total_gained_short || "0"} XP`, GOLD) +
      this._rate(a, 30, perHour) +
      this._vitals(a)
    );
  }

  _single(a, row) {
    const idle = Boolean(a.idle);
    const colour = row.color_hex || ACCENT;
    return (
      text(2, 5, String(row.key).toUpperCase(), idle ? "#786950" : colour) +
      text(62, 5, row.level, TEXT, "end") +
      this._rule() +
      image(row.icon_url, 38, 16, 25) +
      text(2, 18, `+${row.gained_short || "0"} XP`, GOLD) +
      this._rate(a, 29, `${row.per_hour_short || "0"}/HR`) +
      bar(2, 47, 60, 6, Number(row.pct) || 0, colour) +
      text(2, 56, row.xp_short, TEXT) +
      text(62, 56, row.next_level ? `L${row.next_level}` : "", DIM, "end")
    );
  }

  _bars(a, rows) {
    const active = Number(a.active) || rows.length;
    const head = a.idle ? "IDLE" : `XP${active > 5 ? ` +${active - 5}` : ""}`;
    let out =
      text(2, 5, head, a.idle ? IDLE_BG : ACCENT) +
      text(62, 5, `+${a.total_gained_short || "0"}`, TEXT, "end") +
      this._rule();
    // Five rows nine pixels apart, which is what fits under the rule.
    rows.slice(0, 5).forEach((row, i) => {
      const y = 17 + i * 9;
      out +=
        text(2, y, row.label, i === 0 ? ACCENT : TEXT) +
        bar(20, y - 1, 20, 7, Number(row.share) || 1, row.color_hex || ACCENT) +
        text(62, y, row.gained_short, i === 0 ? TEXT : DIM, "end");
    });
    return out;
  }

  _standby(a) {
    const online = Boolean(a.online);
    return (
      text(2, 5, String(a.account || "OSRS").toUpperCase(), ACCENT) +
      this._rule() +
      text(
        2,
        22,
        online ? (a.idle ? "IDLE" : "ONLINE") : "OFFLINE",
        a.idle ? IDLE_BG : online ? PRAYER : DIM,
      ) +
      (online ? this._vitals(a) : "")
    );
  }
}

class OsrsActivityCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) =>
        schema.name === "entity" ? "Activity sensor" : schema.name;
      this._form.addEventListener("value-changed", (event) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: { ...this._config, ...event.detail.value } },
            bubbles: true,
            composed: true,
          }),
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      {
        name: "entity",
        required: true,
        selector: { entity: { integration: "osrs_activity", domain: "sensor" } },
      },
    ];
  }
}

if (!customElements.get("osrs-activity-card")) {
  customElements.define("osrs-activity-card", OsrsActivityCard);
  customElements.define("osrs-activity-card-editor", OsrsActivityCardEditor);

  // Puts it in the "add card" picker, so nobody has to know the type string.
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "osrs-activity-card",
    name: "OSRS Activity",
    description: "The Pixoo screen, on your dashboard.",
    preview: true,
    documentationURL: "https://github.com/Pondake/osrs-activity",
  });
}
