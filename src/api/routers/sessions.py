from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import require_api_key
from src.api.schemas import SessionResponse, SessionStatsResponse
from src.db.connection import get_db_session
from src.db.repositories.session_repo import SessionRepository


router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    session_status: str | None = Query(default=None, alias="status", description="Filter by status: active | completed | manual_close"),
    plate: str | None = Query(default=None, description="Partial plate number filter"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> list[SessionResponse]:
    repo = SessionRepository(db)
    sessions = await repo.list_all(status=session_status, plate=plate, limit=limit, offset=offset)
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/active", response_model=list[SessionResponse])
async def list_active_sessions(db: AsyncSession = Depends(get_db_session)) -> list[SessionResponse]:
    repo = SessionRepository(db)
    sessions = await repo.list_active()
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/stats", response_model=SessionStatsResponse)
async def get_session_stats(db: AsyncSession = Depends(get_db_session)) -> SessionStatsResponse:
    repo = SessionRepository(db)
    data = await repo.stats()
    return SessionStatsResponse(**data)  # type: ignore[arg-type]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db_session)) -> SessionResponse:
    repo = SessionRepository(db)
    vehicle_session = await repo.get(session_id)
    if vehicle_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return SessionResponse.model_validate(vehicle_session)


@router.post("/{session_id}/close", response_model=SessionResponse)
async def manual_close_session(session_id: int, db: AsyncSession = Depends(get_db_session)) -> SessionResponse:
    repo = SessionRepository(db)
    vehicle_session = await repo.get(session_id)
    if vehicle_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    if vehicle_session.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="session is not active")
    closed = await repo.manual_close(vehicle_session)
    await db.commit()
    return SessionResponse.model_validate(closed)

