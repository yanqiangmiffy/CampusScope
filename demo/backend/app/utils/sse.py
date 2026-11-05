"""SSE frames: one `data: {json}` line per event, ended by `data: [DONE]`. See docs/event-protocol.md.
A `ping` event becomes an SSE comment (keeps proxies from closing a quiet stream; clients ignore it)."""
import json
from typing import Any

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # tell nginx not to buffer this response
}
SSE_DONE = "data: [DONE]\n\n"


def sse(event: dict[str, Any]) -> str:
    if event.get("type") == "ping":
        return ": keep-alive\n\n"
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
