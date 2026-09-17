# OSRS Activity

## Backlog

The backlog is **not in this repo**; it lives in the Obsidian vault as `OSRS Activity backlog.md` in
the project folder, found via the `repo:` field in its frontmatter, which points at this checkout. Read it there
before starting work and keep it up to date there.

Do not create `docs/backlog.md`, `BACKLOG.md` or anything like it here — that
path is gitignored, so the file would silently get lost.

## OSRS game facts — use the `osrs` MCP server

Anything about how the game itself behaves — the literal wording of a chat
message, drop tables, item and NPC ids, interface or varbit ids, GE prices,
hiscores — comes from the `osrs` MCP server (tools `mcp__osrs__*`, from
https://github.com/JayArrowz/mcp-osrs) or straight from the OSRS Wiki's
`api.php`. Look it up; do not reason from what sounds plausible. The wiki
documents this level of detail, including exact chat lines, which is the only
way to tell a real game message from one a plugin printed.
