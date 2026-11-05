"""POST /api/chat: one question as an SSE stream. Only protocol conversion here; the flow is QAService."""
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger

from app.deps import get_qa_service
from app.schemas.chat import ChatRequest
from app.services.qa_service import ERRORS, QAService
from app.utils.sse import SSE_DONE, SSE_HEADERS, sse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", summary="Ask CampusScope (SSE)")
async def chat(req: ChatRequest, qa: Annotated[QAService, Depends(get_qa_service)]) -> StreamingResponse:
    """`text/event-stream`: one `data: {json}` frame per event, ended by `data: [DONE]`
    (event types: docs/event-protocol.md)."""

    async def generate() -> AsyncIterator[str]:
        try:
            async for event in qa.answer(req):
                yield sse(event)
        except Exception:  # noqa: BLE001
            logger.exception("SSE stream failed")
            # the stream has started (HTTP 200 is out): errors can only be events, with a generic message
            yield sse({"type": "error", "message": ERRORS[req.lang]["generic"]})
        yield SSE_DONE

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
