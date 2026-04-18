# backend/app/gateway/app.py
"""FastAPI application entry point."""
import asyncio
import logging

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import chat, threads

logger = logging.getLogger(__name__)


async def _prewarm_llm_connections() -> None:
    """Open TLS to each configured provider at boot so the first real user
    request doesn't eat the 10-15s cold handshake."""
    try:
        from core.models.factory import _load_config, create_chat_model
        from langchain_core.messages import HumanMessage

        cfg = _load_config() or {}
        roles = (cfg.get("model") or {}).get("roles") or {}
        default = (cfg.get("model") or {}).get("default")
        names = {n for n in {default, *roles.values()} if n}

        async def _warm(name: str) -> None:
            try:
                model = create_chat_model(name=name)
                try:
                    capped = model.bind(max_tokens=1)
                except Exception:
                    capped = model
                await asyncio.to_thread(capped.invoke, [HumanMessage(content="hi")])
                logger.warning("prewarm: %s ok", name)
            except Exception as e:  # noqa: BLE001
                logger.warning("prewarm: %s failed: %s", name, e)

        # Block startup on prewarm. uvicorn's "Application startup complete"
        # will appear only after all TLS pools are warm, guaranteeing the
        # first real request never eats the cold handshake cost.
        await asyncio.gather(*(_warm(n) for n in names))
    except Exception as e:  # noqa: BLE001
        logger.warning("prewarm setup failed: %s", e)


def create_app() -> FastAPI:
    app = FastAPI(title="TinyFlow", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat.router, prefix="/api")
    app.include_router(threads.router, prefix="/api")

    @app.on_event("startup")
    async def _on_startup() -> None:
        await _prewarm_llm_connections()

    return app


app = create_app()
