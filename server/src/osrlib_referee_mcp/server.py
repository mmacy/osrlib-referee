"""The FastMCP server: one session, one tool.

Phase 0 exposes a single tool, `execute`, over the fixed-seed fixture in
[`content.py`][osrlib_referee_mcp.content]. There is no lock: `GameSession` is not
thread-safe by contract, but a single stdio server serves one client and Phase 0
exposes one tool, so commands cannot interleave. The lock returns with the real
lifecycle in Phase 1.
"""

from mcp.server.fastmcp import FastMCP
from osrlib.crawl.commands import parse_command

from osrlib_referee_mcp.content import build_session

mcp = FastMCP("osrlib-referee")
_session = build_session()


@mcp.tool()
def execute(command: dict) -> dict[str, object]:
    """Parse one command payload and execute it against the session.

    Args:
        command: A serialized osrlib command, keyed on `command_type`.

    Returns:
        `{accepted, rejections, events}`. An unknown `command_type` returns
        `{accepted: False, error: "unknown_command_type", command_type}` instead of
        raising. A known but malformed payload raises a tool error (`osrlib`'s
        `ContentValidationError` propagates).
    """
    parsed = parse_command(command)
    if parsed is None:
        return {
            "accepted": False,
            "error": "unknown_command_type",
            "command_type": command.get("command_type"),
        }
    result = _session.execute(parsed)
    return {
        "accepted": result.accepted,
        "rejections": [r.model_dump(mode="json") for r in result.rejections],
        "events": [e.model_dump(mode="json") for e in result.events],
    }


def main() -> None:
    """Run the server over stdio."""
    mcp.run()
