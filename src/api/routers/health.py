from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from src.api.schemas import CameraHealth, HealthResponse
from src.db.connection import AsyncSessionFactory


router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    database_status = "ok"
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"

    manager = request.app.state.camera_manager
    cameras = [
        CameraHealth(
            id=status.camera_id,
            name=status.name,
            role=status.role,
            running=status.is_running,
            connected=status.is_connected,
            last_frame_at=status.last_frame_at,
            last_error=status.last_error,
        )
        for status in manager.statuses()
    ]
    app_status = "ok" if database_status == "ok" else "degraded"
    return HealthResponse(
        status=app_status,
        database=database_status,
        configured_cameras=len(cameras),
        cameras=cameras,
    )
