from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.api.routers import cameras, health, reports, sessions
from src.config import get_settings
from src.camera.manager import CameraManager
from src.config import get_settings
from src.detection.worker import AIWorker
from src.session.duplicate_guard import DuplicateGuard
from src.utils.logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)

    # Camera streams
    manager = CameraManager(settings)
    app.state.camera_manager = manager
    manager.start_all()

    # Shared duplicate-guard (in-memory, scoped to this process)
    duplicate_guard = DuplicateGuard(window_seconds=settings.duplicate_guard_seconds)

    # Build camera-config lookup for the AI worker
    camera_configs = {cam.id: cam for cam in settings.cameras_json if cam.is_active}

    # Launch AI worker tasks (one per ai_worker_count)
    workers: list[AIWorker] = []
    tasks: list[asyncio.Task[None]] = []
    for _ in range(settings.ai_worker_count):
        worker = AIWorker(
            settings=settings,
            frame_buffer=manager.frame_buffer,
            camera_configs=camera_configs,
            duplicate_guard=duplicate_guard,
        )
        workers.append(worker)
        tasks.append(asyncio.create_task(worker.run()))
        tasks.append(asyncio.create_task(worker.run_presence_timeout_checker()))

    yield

    # Shutdown
    for worker in workers:
        worker.stop()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    manager.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(title="Smart Car Wash Monitoring API", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(cameras.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")

    _dashboard_template = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> HTMLResponse:
        settings = get_settings()
        html = _dashboard_template.replace(
            "__API_KEY_PLACEHOLDER__", settings.api_key or ""
        )
        return HTMLResponse(html)

    return app

