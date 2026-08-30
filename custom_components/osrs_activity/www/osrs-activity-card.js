/*
 * OSRS Activity card.
 *
 * Shipped by the integration and registered with the frontend on setup, so it
 * arrives with the HACS download rather than as a second repository.
 *
 * Draws the same thing the Pixoo blueprint draws, from the same attributes,
 * and picks between the same three layouts. Colours come from the skill rows
 * themselves rather than being listed again here, so changing a skill colour
 * in the integration changes it in both places.
 */

const BG = "#05060a";
const PANEL = "#0d0f16";
const GRID = "rgba(226,226,255,0.05)";
const LINE = "#5a4a36";
const GOLD = "#ffd21f";
const DIM = "#8d8ba6";
const TEXT = "#c8bda8";
const IDLE = "#ffb400";

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

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
    if (!config.entity) {
      throw new Error("Pick the XP session sensor");
    }
    this._config = config;
    this._built = false;
  }

  getCardSize() {
    return 4;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _build() {
    // Once only. setConfig clears _built so the styles are rebuilt after an
    // edit, but a second attachShadow throws and the card stops updating
    // until the page is reloaded.
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          background: ${BG};
          border: none;
          overflow: hidden;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        }
        .panel {
          /* Faint grid, so it reads as an LED matrix like the panel it
             mirrors. */
          background:
            repeating-linear-gradient(0deg, ${GRID} 0 1px, transparent 1px 9px),
            repeating-linear-gradient(90deg, ${GRID} 0 1px, transparent 1px 9px),
            ${PANEL};
          padding: 14px 16px 16px;
        }
        .head {
          display: flex; align-items: baseline; gap: 8px;
          font-size: 15px; font-weight: 700; letter-spacing: .08em;
        }
        .style { color: ${GOLD}; text-transform: uppercase; }
        .level { color: ${TEXT}; font-size: 12px; }
        .gained { margin-left: auto; color: #ffdc00; font-size: 13px; }
        .badge {
          background: ${IDLE}; color: #3c2d06;
          font-size: 11px; font-weight: 700; letter-spacing: .1em;
          padding: 2px 7px; border-radius: 3px;
        }
        .rule { height: 1px; background: ${LINE}; margin: 10px 0 12px; }
        .row {
          display: grid; grid-template-columns: 18px 42px 1fr auto;
          align-items: center; gap: 8px; margin-bottom: 7px;
        }
        .row img { width: 18px; height: 18px; image-rendering: pixelated; }
        .chip { width: 10px; height: 10px; border-radius: 2px; margin: 0 4px; }
        .label { color: ${TEXT}; font-size: 12px; letter-spacing: .06em; }
        .track { background: #241d15; height: 9px; border-radius: 2px; overflow: hidden; }
        .fill { height: 100%; border-radius: 2px; transition: width .4s ease; }
        .amount { color: ${TEXT}; font-size: 12px; font-variant-numeric: tabular-nums; }
        .foot {
          display: flex; align-items: baseline; gap: 10px;
          margin-top: 12px; color: ${DIM}; font-size: 11px;
          font-variant-numeric: tabular-nums;
        }
        .foot .next { margin-left: auto; }
        .bar { margin-top: 6px; }
        .quiet { color: ${DIM}; font-size: 13px; padding: 6px 0 2px; }
        .err { padding: 16px; color: var(--error-color, #db4437); }
      </style>
      <ha-card><div class="panel"></div></ha-card>`;
    this._panel = this.shadowRoot.querySelector(".panel");
    this._built = true;
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this._built) this._build();

    const state = this._hass.states[this._config.entity];
    if (!state) {
      this._panel.innerHTML =
        `<div class="err">${esc(this._config.entity)} not found</div>`;
      return;
    }

    const a = state.attributes;
    if (a.window_skills === undefined) {
      // Almost certainly the "XP gained" sensor, which is one line away in the
      // picker and holds a total rather than the whole picture.
      this._panel.innerHTML = `<div class="err">${esc(
        this._config.entity,
      )} is not the Activity sensor</div>`;
      return;
    }
    const rows = a.skills || [];
    const idle = Boolean(a.idle);

    if (!rows.length) {
      this._panel.innerHTML = `
        <div class="head"><span class="style">OSRS</span>
          ${idle ? '<span class="badge">IDLE</span>' : ""}</div>
        <div class="rule"></div>
        <div class="quiet">Nothing training right now.</div>`;
      return;
    }

    const top = a.top || rows[0];
    // The same three-way choice the blueprint makes.
    const combat = a.combat && a.style;
    const heading = combat ? a.style : top.key;
    // The panel puts the level beside the skill name on the single-skill
    // screen and the slayer kill count beside the heading in combat. Same
    // information, same corner.
    const level = combat || rows.length > 1 ? "" : top.level;
    const kills = combat ? Number(a.slayer_kills) || 0 : 0;
    const perHour = Math.round((a.per_hour || 0) / 100) / 10;

    this._panel.innerHTML = `
      <div class="head">
        <span class="style">${esc(heading)}</span>
        ${kills ? `<span class="level">x${kills}</span>` : ""}
        ${level ? `<span class="level">${esc(level)}</span>` : ""}
        <span class="gained">+${esc(a.total_gained_short || "0")} XP</span>
      </div>
      <div class="rule"></div>
      ${rows.slice(0, 5).map((row) => this._row(row, rows.length > 1)).join("")}
      <div class="bar">
        <div class="track">
          <div class="fill" style="width:${Number(top.pct) || 0}%;
               background:${esc(top.color_hex || GOLD)}"></div>
        </div>
      </div>
      <div class="foot">
        <span>${esc(top.xp_short || "")} XP</span>
        ${idle ? '<span class="badge">IDLE</span>' : `<span>${perHour}k/h</span>`}
        ${
          top.next_level
            ? `<span class="next">${esc(top.to_go_short)} to L${esc(top.next_level)}</span>`
            : '<span class="next">200m</span>'
        }
      </div>`;
  }

  _row(row, showBar) {
    const colour = esc(row.color_hex || GOLD);
    // The bar is `share`, which the integration already scaled against the
    // biggest gainer in focus. A single skill has nothing to compare against,
    // so it gets its level progress instead of a bar that is always full.
    const width = showBar ? Number(row.share) || 1 : Number(row.pct) || 0;
    const icon = row.icon_url
      ? `<img src="${esc(row.icon_url)}" alt="">`
      : `<div class="chip" style="background:${colour}"></div>`;
    return `
      <div class="row">
        ${icon}
        <span class="label">${esc(row.label)}</span>
        <div class="track">
          <div class="fill" style="width:${width}%; background:${colour}"></div>
        </div>
        <span class="amount">${esc(row.gained_short)}</span>
      </div>`;
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
        schema.name === "entity" ? "XP session sensor" : schema.name;
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
    description: "What you are training, the way the Pixoo shows it.",
    preview: true,
    documentationURL: "https://github.com/Pondake/osrs-activity",
  });
}
