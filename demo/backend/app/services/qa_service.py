"""One question: the system's steps, the evidence subgraph, the streamed answer, and (in parallel) the
chunk-RAG baseline and the English glosses, merged into one event stream.

The system's code is synchronous (LLM, embedding and Milvus clients), so the agent and the baseline
each run in a worker thread and hand their events to the event loop; `answer()` is the async
generator the router turns into SSE. It always ends with exactly one terminal event, `complete` or
`error` (docs/event-protocol.md). When the visitor stops the stream the workers stop sending.
"""
import asyncio
import re
import threading
import time
from collections.abc import AsyncIterator, Callable

from loguru import logger

from app import system  # noqa: F401
from app.config import Settings
from app.prompts.texts import CAMPUS_HINT, GLOSS, MONTHS
from app.schemas.chat import ChatRequest
from app.services import llm_probe
from app.services.runtime import STATE

from campusscope.llm import chat, parse_json

# messages shown to visitors are generic (details go to the log), in the language of the page
ERRORS = {
    "en": dict(generic="The service is temporarily unavailable. Please try again later.",
               baseline="The RAG baseline is temporarily unavailable."),
    "zh": dict(generic="服务暂时不可用，请稍后重试。", baseline="RAG 基线暂时不可用"),
}
GENERIC_ERROR = ERRORS["en"]["generic"]


def gloss(text: str, model: str) -> str:
    """English gloss of a reply (demo only; a separate call that never feeds back into the answer)."""
    if not text:
        return ""
    rec = chat([dict(role="system", content=GLOSS), dict(role="user", content=text)], model=model, max_tokens=400,
               tag="demo_gloss", retries=llm_probe.retries(model, 3))
    p = parse_json(rec["content"])
    en = str(p.get("en")) if isinstance(p, dict) and p.get("en") else rec["content"]
    return re.sub(r"(\d{1,2})月(\d{1,2})日", lambda m: f"{MONTHS[int(m.group(1)) - 1]} {int(m.group(2))}", en)


def safe_gloss(text: str, model: str) -> str | None:
    """The gloss is a convenience: if it fails, the answer stands without it."""
    try:
        return gloss(text, model)
    except Exception as e:  # noqa: BLE001
        logger.warning("gloss failed: {}", e)
        return None


CAMPUS_ALIAS = (("A校区", "中关村校区"), ("B校区", "通州校区"), ("Campus A", "中关村校区"), ("Campus B", "通州校区"),
                ("campus A", "中关村校区"), ("campus B", "通州校区"))


def campus_alias(text: str) -> str:
    """What a visitor types with the displayed campus names, in the notices' own names."""
    for shown, real in CAMPUS_ALIAS:
        text = text.replace(shown, real)
    return text


class QAService:
    def __init__(self, agents: Callable[[str], tuple], settings: Settings):
        self._agents = agents          # model -> (StreamingCampusScope, RAG)
        self.settings = settings

    @staticmethod
    def conversation(req: ChatRequest) -> list[dict]:
        conv = [t.model_dump() for t in req.conversation]
        # the interface shows the two campuses as A / B (deid.js); the notices, and so the system, name them
        conv = [dict(t, text=campus_alias(t["text"])) if t["role"] == "user" else t for t in conv]
        # the campus picked in the top bar counts as something the visitor said (the system only trusts the dialogue)
        if req.campus in CAMPUS_HINT and not any("校区" in t["text"] for t in conv if t["role"] == "user"):
            conv = [dict(role="user", text=CAMPUS_HINT[req.campus])] + conv
        return conv

    @staticmethod
    def _wait_ready(stop: threading.Event) -> None:
        while not STATE["ready"] and not STATE["error"] and not stop.is_set():
            time.sleep(0.3)
        if STATE["error"]:
            raise RuntimeError(STATE["error"])

    async def answer(self, req: ChatRequest) -> AsyncIterator[dict]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        stop = threading.Event()
        done = object()
        conv = self.conversation(req)
        result: dict = {}

        def emit(ev) -> None:
            if not stop.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, ev)

        def run_main() -> None:
            try:
                if not STATE["ready"]:
                    emit(dict(type="status", text="warming", stage=STATE["stage"]))
                self._wait_ready(stop)
                cand, _ = self._agents(req.model)
                for ev in cand.stream(conv, req.today):
                    if stop.is_set():
                        return
                    if ev["type"] == "summary":
                        result.update(ev)
                        continue
                    if ev["type"] == "answer":
                        result["answer"] = ev
                    emit(ev)
                if req.lang == "en" and result.get("answer"):
                    en = safe_gloss(result["answer"]["text"], req.model)
                    if en:
                        emit(dict(type="gloss", target="main", text=en))
            except Exception as e:  # noqa: BLE001
                logger.exception("answer failed")
                result["error"] = f"{type(e).__name__}: {e}"
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, done)

        def run_baseline() -> None:
            try:
                self._wait_ready(stop)
                if stop.is_set():
                    return
                _, rag = self._agents(req.model)
                t0 = time.perf_counter()
                emit(dict(type="baseline", status="running"))
                r = rag.respond(conv, req.today)
                emit(dict(type="baseline", status="done", text=r["text"], action=r["action"],
                          ms=round((time.perf_counter() - t0) * 1000),
                          retrieved=(r.get("trace") or {}).get("retrieved", [])))
                if req.lang == "en":
                    en = safe_gloss(r["text"], req.model)
                    if en:
                        emit(dict(type="gloss", target="baseline", text=en))
            except Exception as e:  # noqa: BLE001
                logger.warning("baseline failed: {}", e)
                emit(dict(type="baseline", status="error", message=ERRORS[req.lang]["baseline"]))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, done)

        workers = [run_main] + ([run_baseline] if req.compare else [])
        for w in workers:
            threading.Thread(target=w, daemon=True).start()
        pending = len(workers)
        try:
            yield dict(type="open", baseline=req.compare)
            while pending:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=self.settings.KEEPALIVE_S)
                except TimeoutError:
                    yield dict(type="ping")
                    continue
                if ev is done:
                    pending -= 1
                    continue
                yield ev
            if "error" in result or "answer" not in result:
                logger.error("terminal error: {}", result.get("error"))
                yield dict(type="error", message=ERRORS[req.lang]["generic"])
            else:
                yield dict(type="complete", answer=result["answer"]["text"], action=result["answer"]["action"],
                           rewritten=bool(result["answer"].get("rewritten")), calls=result.get("calls", 0),
                           latency=result.get("latency", 0.0), cached=bool(result.get("cached")))
        finally:
            stop.set()
