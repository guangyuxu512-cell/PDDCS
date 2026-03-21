"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import dotenv_values, find_dotenv, load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chat import router as chat_router
from backend.api.dashboard import router as dashboard_router
from backend.api.knowledge import router as knowledge_router
from backend.api.settings import router as settings_router
from backend.api.shops import router as shops_router
from backend.db import database as database_module
from backend.services.scheduler import configure_worker_manager
from backend.workers.worker_manager import WorkerManager


logger = logging.getLogger(__name__)
DEFAULT_DB_PATH = database_module.DB_PATH


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    dotenv_path = find_dotenv(usecwd=True)
    loaded_keys: list[str] = []
    if dotenv_path:
        for key in dotenv_values(dotenv_path):
            if key and key not in os.environ:
                loaded_keys.append(key)
        load_dotenv(dotenv_path, override=False)

    if "DATABASE_URL" in loaded_keys and database_module.DB_PATH != DEFAULT_DB_PATH:
        os.environ.pop("DATABASE_URL", None)
        loaded_keys.remove("DATABASE_URL")

    database_module.init_database()

    worker_manager: WorkerManager | None
    try:
        worker_manager = WorkerManager()
    except PermissionError:
        logger.warning("Worker multiprocessing is unavailable in this environment; falling back to local scheduler")
        worker_manager = None

    app.state.worker_manager = worker_manager
    app.state.shop_scheduler = configure_worker_manager(worker_manager)

    if worker_manager is not None:
        worker_count = worker_manager.required_worker_count(worker_manager.online_shop_count())
        worker_manager.start_workers(worker_count)
        worker_manager.start_status_listener()

    try:
        yield
    finally:
        if worker_manager is not None:
            worker_manager.shutdown()
        configure_worker_manager(None)
        for key in loaded_keys:
            os.environ.pop(key, None)


app = FastAPI(title="PDDCS API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(shops_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
