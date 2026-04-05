# backend/app/gateway/app.py
"""FastAPI application entry point."""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import chat, threads


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

    return app


app = create_app()
