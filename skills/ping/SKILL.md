---
name: ping
description: Manual boundary smoke test for the osrlib-referee MCP server. Use only when verifying the plugin-bundled server launches and the execute tool round-trips inside Claude Code — not part of normal play.
allowed-tools: mcp__plugin_osrlib-referee_osrlib__execute
---

# Ping

This skill is a one-shot smoke test. It exists to prove the MCP boundary works end to end, and to confirm the exposed tool name matches this file's `allowed-tools` entry character-for-character.

1. Call the `execute` tool exactly once, with this literal payload:

   ```json
   {"command_type": "set_flag", "key": "ping", "value": true}
   ```

2. Report the returned envelope verbatim to the user — do not summarize or reword it.

A correct result looks like `{"accepted": true, "rejections": [], "events": [{"event_type": "flag_set", "code": "session.flag.set", ...}]}`. If the tool call fails outright (not found, not authorized), report that too — that failure is exactly what this skill is designed to surface.
