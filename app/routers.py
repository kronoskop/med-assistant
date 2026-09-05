import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.answer import confirmed_sources, last_question, refusal_text, support_documents, weave_citations
from app.corpus.service import Grounding, Retrieval, Retriever, get_retriever, render_fragments
from app.llm import LLMClient, ensure_structured_output, get_llm
from app.prompt import DISCLAIMER
from app.schemas import AppError, ChatMessage, ChatRequest, ChatResponse

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(llm: LLMClient = Depends(get_llm)):
    try:
        await llm.ping()
        await ensure_structured_output(llm)
    except AppError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "code": exc.code,
                "message": exc.message,
            },
        )
    return {"status": "ready"}


@router.post("/api/v1/chat")
async def chat(
    body: ChatRequest,
    llm: LLMClient = Depends(get_llm),
    retriever: Retriever = Depends(get_retriever),
):
    retrieval = retriever(last_question(body.messages))

    # Без фрагментов основы модель не зовём вовсе: отказ формулирует сервер,
    # иначе ответ пришёл бы из памяти модели.
    if not retrieval.is_grounded:
        text = refusal_text(retrieval.status)
        if body.stream:
            return StreamingResponse(_sse_refusal(text, retrieval), media_type="text/event-stream")
        return _response(text, retrieval, [])

    fragments = render_fragments(retrieval.hits)
    if body.stream:
        claimed: list[str] = []
        chunks = await llm.start_chat_stream(body.messages, fragments, claimed)
        return StreamingResponse(_sse(chunks, claimed, retrieval), media_type="text/event-stream")

    answer = await llm.complete(body.messages, fragments)
    woven, inline = weave_citations(answer.text, retrieval.hits)
    claimed = [s.id for s in inline] or list(answer.source_ids)
    sources, grounded, _ = _settle(woven, retrieval, claimed)
    if not grounded:
        return _response(refusal_text(Grounding.NO_MATCH), retrieval, [])
    return _response(woven, retrieval, claimed)


def _response(text: str, retrieval: Retrieval, claimed) -> ChatResponse:
    sources, grounded, status = _settle(text, retrieval, claimed)
    return ChatResponse(
        message=ChatMessage(role="assistant", content=text),
        disclaimer=DISCLAIMER,
        grounded=grounded,
        grounding=status,
        sources=sources,
        support=support_documents(retrieval),
    )


def _settle(text: str, retrieval: Retrieval, claimed):
    """Заземлён ли ответ, решает не близость, а цитирование.

    Косинусная оценка не отделяет профильный вопрос от постороннего: у обоих
    она одинаковая. Судит модель, прочитавшая фрагменты: если она не сослалась
    ни на один, подтверждать нечего.
    """
    sources = confirmed_sources(claimed, retrieval.hits)
    if not retrieval.is_grounded:
        return sources, False, retrieval.status.value
    if not sources:
        return [], False, Grounding.NO_MATCH.value
    return sources, True, retrieval.status.value


def _sources_event(retrieval: Retrieval, claimed) -> str:
    sources, grounded, status = _settle("", retrieval, claimed)
    payload = {
        "grounded": grounded,
        "grounding": status,
        "sources": [s.model_dump() for s in sources],
        "support": [d.model_dump() for d in support_documents(retrieval)],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _sse(chunks: AsyncIterator[str], claimed: list[str], retrieval: Retrieval) -> AsyncIterator[str]:
    async for text in chunks:
        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
    yield _sources_event(retrieval, claimed)
    yield "data: [DONE]\n\n"


async def _sse_refusal(text: str, retrieval: Retrieval) -> AsyncIterator[str]:
    yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
    yield _sources_event(retrieval, [])
    yield "data: [DONE]\n\n"
