import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.llm import LLMClient, get_llm
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
):
    if body.stream:
        chunks = await llm.start_chat_stream(body.messages)
        return StreamingResponse(
            _sse(chunks),
            media_type="text/event-stream",
        )
    content = await llm.complete(body.messages)
    return ChatResponse(
        message=ChatMessage(role="assistant", content=content),
        disclaimer=DISCLAIMER,
    )


async def _sse(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    async for text in chunks:
        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
