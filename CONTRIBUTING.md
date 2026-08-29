# Contributing

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

## Checks

```bash
pytest -q                    # the engine, and the guard's own rules
ruff check .
python tools/scan_leaks.py
```

CI runs those plus hassfest, HACS validation and gitleaks on every push.

## Regenerating the icon

`assets/icon.svg` is the source. `python tools/render_icon.py` rasterises it
into the sizes Home Assistant and GitHub want. It is not a general SVG
renderer — the artwork is rounded rectangles and one blur, which is the subset
Pillow can reproduce without cairo or a headless browser.
