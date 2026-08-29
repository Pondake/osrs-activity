# OSRS Activity

[![HACS: custom repository](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Validate](https://github.com/Pondake/osrs-activity/actions/workflows/validate.yml/badge.svg)](https://github.com/Pondake/osrs-activity/actions/workflows/validate.yml)
[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Pondake&repository=osrs-activity&category=integration)

A Home Assistant integration that answers one question: **what is this Old
School RuneScape player doing right now?**

The [RuneLite integration](https://github.com/db1996/homeassistant_runelite)
already gives you a sensor per skill, but those report a *total* — how much XP
you have, not how much you just earned. Everything you would actually want to
show is a delta, and a delta needs memory. This keeps that memory: which skills
have a live counter, how fast each is climbing, which one you are focused on,
and — when it is all combat — which attack style you are using, read off from
which of attack, strength and defence are ticking.

Nothing here knows about any particular display. It publishes sensors; what you
do with them is up to you. There is [a blueprint for a Pixoo 64](#the-pixoo-64-screens)
in this repo because that is what it was built for, but a dashboard card is
just as valid a consumer.

---

## What you get

One device per player, with six entities.

| Entity | State | Good for |
|---|---|---|
| `sensor.<player>_xp_session` | how many skills have a live counter | everything — the full picture is in its attributes |
| `sensor.<player>_focus_skill` | `mining`, `slayer`, … | "what am I training" |
| `sensor.<player>_session_xp` | XP gained this sitting | a graph of your evening |
| `sensor.<player>_xp_per_hour` | rate, from the start of the sitting | is this method actually faster |
| `sensor.<player>_combat_style` | `AGGRESSIVE`, `RANGED`, `Slayin'`, … | switching a light when you switch styles |
| `binary_sensor.<player>_idle` | on when you are standing around | a nudge when you have been afk for a while |

The XP session sensor is the one to template against. Its attributes carry
`skills` (what is happening now), `window_skills` (everything with a counter
still running), `top`, `combat`, `style`, `slayer_kills`, `total_gained_short`
and the idle state — and every skill row comes with a label that fits in four
characters, a colour, a percentage through the current level, and a path to its
icon.

```jinja
{{ state_attr('sensor.player_xp_session', 'top').gained_short }}   → "12.3k"
{{ state_attr('sensor.player_xp_session', 'style') }}              → "AGGRESSIVE"
{{ state_attr('sensor.player_xp_session', 'skills')
   | map(attribute='label') | join(' ') }}                          → "STR ATT HP"
```

---

## Two windows, two jobs

They were one number at first and it felt sluggish, so they are separate.

**Session window** (minutes, default 5) is how long a skill keeps its counter
after the last gain. Pick the pickaxe back up inside it and `gained` carries on
where it was; come back later and the next gain starts a fresh sitting. It
doubles as the reset threshold on purpose — that way "gained" always means
exactly one thing, the XP of *this* sitting.

**Focus window** (seconds, default 25) is a different question: what is
happening *now*. Step off combat onto mining and the combat rows drop out after
this, not after the whole session window. If the focus falls empty during a
short pause, everything inside the session window comes back — an empty screen
is worse than a slightly stale one.

Both are on the integration's options, so you can change them without editing
anything.

---

## Requirements

- [`db1996/homeassistant_runelite`](https://github.com/db1996/homeassistant_runelite),
  set up with at least one player. **HACS will not install this for you** — add
  it first, or the config flow here has nothing to offer you.
- The matching RuneLite plugin, with **Skill XP** enabled so XP arrives live
  instead of once per hiscores poll. Idle detection is optional; its threshold
  lives in the plugin's own panel, and this integration deliberately keeps no
  second threshold of its own.

## Install

Two separate things get installed, and it is worth knowing that before you
start. **The integration** publishes the sensors and asks only which player to
follow. **The blueprint** draws them on a Pixoo and asks only which panel to
draw on. They are installed in different places and neither knows about the
other — so if you are here for the sensors and have no Pixoo, stop after
step 4.

**1. Add the repository to HACS.** Click the badge at the top, or by hand:
HACS → the three dots, top right → *Custom repositories* → paste
`https://github.com/Pondake/osrs-activity`, type **Integration** → *Add*.

**2. Download it.** Adding a custom repository only tells HACS the repository
exists; it does not install anything. Search HACS for **OSRS Activity**, open
it, and press **Download**. This is the step people miss.

**3. Restart Home Assistant.** New integrations are only picked up at startup.
*Settings → System → top right → Restart*.

**4. Add the integration.** *Settings → Devices & services → + Add integration*
→ **OSRS Activity** → pick your player from the dropdown, and set the two
windows (the defaults are fine).

You now have six entities under a device named after your player. If the
dropdown is empty, the RuneLite integration is not set up yet — see
[Requirements](#requirements).

**5. Fetch the skill icons.** *Developer tools → Actions* →
`osrs_activity.download_skill_icons` → *Perform action*. Once, and only again
when a new skill comes out. Skip this and every icon is a blank square.

**6. Only if you have a Pixoo 64:** import the blueprint. *Settings →
Automations & scenes → Blueprints → Import blueprint*, and paste:

```
https://github.com/Pondake/osrs-activity/blob/main/blueprints/script/osrs_pixoo64.yaml
```

Then *Create script* from it. That is where you pick your Pixoo, your XP
session sensor, and optionally your health and prayer sensors. Call the
resulting script from an automation whenever you want the panel redrawn — a
state trigger on the XP session sensor is the obvious one.

<details>
<summary>Why the badge cannot do all of this for you</summary>

The badge is a [My Home Assistant](https://my.home-assistant.io) link. It works
for custom repositories as well as for ones in the default store — that is what
the `category` parameter in it is for — but all it does is open HACS on your own
instance and offer to add the repository. Downloading, restarting and
configuring are still steps 2 to 4.

On HACS 2.0.5 that confirmation dialog can come up with no text and an
unlabelled button, because HACS asks for it before its own translations have
loaded. The unlabelled button is *Add*. This happens with any custom
repository and is nothing to do with this one.
</details>

The player list in step 4 comes from the RuneLite integration rather than a text
box on purpose: a typo would silently match no skill sensors at all, and the
result would look like an integration that just does not work.

## Skill icons

Run this once:

```yaml
action: osrs_activity.download_skill_icons
```

It pulls the 24 skill icons from the OSRS wiki into
`config/www/osrs_activity/icons/`, each one normalised onto a 25×25 canvas,
right-aligned. After that nothing that draws them ever touches the network —
for a dashboard that is a nicety, but for an LED panel it is a requirement,
because a render that waits on an HTTP request is a render that can hang.

Straight from the wiki rather than hand-drawn, incidentally, because a
hand-pixelled pickaxe at 24px reads as a hammer.

Every row then carries both `icon_path` (a file, for anything using PIL) and
`icon_url` (a `/local/` URL, for the frontend). A skill with no icon resolves to
a transparent square rather than to a path that does not exist — the second one
is not a missing picture, it is a dead page.

---

## The Pixoo 64 screens

`blueprints/script/osrs_pixoo64.yaml` is a script blueprint that draws the
whole thing on a [Divoom Pixoo 64](https://github.com/Faisalthe01/divoom_pixoo).
Import it, pick your panel and your XP session sensor, and you are done — no
YAML to copy and no entity IDs to find and replace. See step 6 of
[Install](#install) for where to paste the URL.

Three screens, chosen automatically:

| When | Screen |
|---|---|
| everything gaining XP is a combat skill | attack style, total gained, rate, HP and prayer bars |
| one skill in focus | that skill, gained, rate, and the bar to the next level |
| anything else | up to five skills, bars scaled against the biggest gainer |

The bars scale against the biggest gainer *inside the focus* rather than
against an absolute figure. That makes a combat sitting read as a ratio
(2:1:1 strength/attack/hitpoints) and makes the same scale work for Wintertodt
and for Zulrah without a special case for either.

Health and prayer are optional inputs; leave them empty and those bars are
simply not drawn. Background and accent are colour pickers.

When nothing is gaining XP the script does nothing at all and leaves the panel
alone, so it can sit inside your own priority ladder without fighting it for the
screen.

> **Before you raise the refresh rate:** [docs/pixoo.md](docs/pixoo.md) has the
> measured limits of the device. Short version — it does not crash under load,
> it *freezes*, and it does so silently: it keeps answering HTTP with
> `error_code: 0` while nothing on screen changes any more. Home Assistant
> cannot see that happen.

---

## What it does not do yet

**Idle only clears on your next XP drop.** The plugin sends an idle event but
has no "active again" counterpart, so a gain is the only thing that can clear
it. On a slow skill that can take a while. There is a PR open for this
upstream; when it lands, the fix here is a second event listener.

**Slayer kills are derived, not read.** Slayer XP arrives in a fixed amount per
kill, so a run of equal chunks counts kills. The moment one differs — a
barrage, a mixed task, a kill that lands together with something else — the
division stops meaning anything and the count is hidden rather than shown
wrong. A task name and a real counter need the plugin to send them, which is
also a PR away. Worth keeping the derivation as a fallback either way: it works
on tasks the plugin knows nothing about.

**The idle event has no payload,** so with two accounts logged in there is no
telling which one went idle. Fine as long as only one plays at a time; fixable
only on the plugin side.

---

## Publishing guard

This was carved out of a private Home Assistant config, so the risk was never
really API keys — it is the ordinary detail that rides along: an entity named
after a room, a device name, a LAN address, a path off someone's own disk.
Harmless individually, permanent once pushed.

```bash
python tools/scan_leaks.py
```

It checks every tracked file for that, plus tokens, private keys and AI
attribution, and exits non-zero on a finding. CI runs it on every push
alongside [gitleaks](https://github.com/gitleaks/gitleaks), which is the gate a
local git config cannot skip. Names specific to one setup live in
`tools/private_words.txt`, so adding one does not mean touching code. When a
match is genuinely fine, `scan-leaks: allow` on the line says so.

To run it before every commit, point git at a hooks directory and drop in a
hook that calls it with `--staged`.

---

## Credit

Built on [**db1996/homeassistant_runelite**](https://github.com/db1996/homeassistant_runelite)
and its RuneLite plugin, which do all the actual talking to the game. This
integration only remembers what they already told you.

Pixoo drawing goes through
[**Faisalthe01/divoom_pixoo**](https://github.com/Faisalthe01/divoom_pixoo).

Icons are from the [OSRS Wiki](https://oldschool.runescape.wiki), used under
their licence. Old School RuneScape is a trademark of Jagex Ltd; this is an
unofficial hobby project and is not affiliated with or endorsed by Jagex.

MIT licensed.
