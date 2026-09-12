from __future__ import annotations

"""Official STECH-MCP process wrapper.

Runs the authoritative MCP runtime plus the local Git mailbox bridge used by the
hourly scheduled ChatGPT research task. The bridge is started only when enabled
in Settings; failures are reported without preventing the MCP from starting.
"""

from stech_mcp import server_authoritative
from stech_mcp.chatgpt_bridge.runner import build_runner_from_environment, start_bridge_thread
from stech_mcp.config import Settings


_chatgpt_bridge_thread = None
_chatgpt_bridge_error: str | None = None


def _start_chatgpt_bridge() -> None:
    global _chatgpt_bridge_thread, _chatgpt_bridge_error
    if _chatgpt_bridge_thread is not None:
        return
    settings = Settings()
    if not settings.stech_chatgpt_bridge_enabled:
        return
    try:
        config, runner = build_runner_from_environment()
        _chatgpt_bridge_thread = start_bridge_thread(config, runner)
        _chatgpt_bridge_error = None
    except Exception as exc:
        _chatgpt_bridge_error = f"{type(exc).__name__}: {exc}"
        print(f"STECH ChatGPT Research Bridge startup error: {_chatgpt_bridge_error}")


def main() -> None:
    _start_chatgpt_bridge()
    server_authoritative.main()


if __name__ == "__main__":
    main()
