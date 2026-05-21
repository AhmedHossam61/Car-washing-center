<<<<<<< HEAD
"""Standalone session-flow smoke test.

Simulates both session flows using an **in-memory SQLite database** — no
PostgreSQL or Docker required.

FLOW A — Single camera (role='both'):
  1. Plate confirmed (≥ MIN_CONFIRMATION_HITS frames) → entry stored.
  2. Camera keeps seeing the car                      → last_seen_at updated.
  3. Car leaves; no detection for PRESENCE_TIMEOUT_MINUTES → exit auto-stored.

FLOW B — Two cameras (role='entry' + role='exit'):
  1. Entry camera confirms plate                      → entry stored.
  2. Exit camera confirms same plate                  → exit stored.

Run:
    uv run python scripts/test_session_flow.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from src.db.models import Base, VehicleSession
from src.db.repositories.session_repo import SessionRepository
from src.session.duplicate_guard import DuplicateGuard
from src.session.manager import SessionEvent, SessionManager

# ---------------------------------------------------------------------------
# Scenario config — edit these to try different cases
# ---------------------------------------------------------------------------
PLATE_NUMBER  = "هقح 3327 HGJ"
PLATE_DIGITS  = "3327"
CAMERA_ID     = 1

ENTRY_TIME          = datetime(2026, 5, 21, 9, 14, 32, tzinfo=timezone.utc)
REDETECT_TIMES      = [ENTRY_TIME + timedelta(minutes=m) for m in (2, 4, 6, 8)]
PRESENCE_TIMEOUT    = timedelta(minutes=5)   # mirrors PRESENCE_TIMEOUT_MINUTES in .env
# ---------------------------------------------------------------------------


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") + " UTC"


def _print_session(stored: VehicleSession) -> None:
    duration = stored.duration_seconds or 0
    h, rem = divmod(duration, 3600)
    m, s = divmod(rem, 60)
    print(f"  ID              : {stored.id}")
    print(f"  Plate           : {stored.plate_number}")
    print(f"  Status          : {stored.status}")
    print(f"  Entry time      : {_fmt(stored.entry_time)}")
    if stored.last_seen_at:
        print(f"  Last seen at    : {_fmt(stored.last_seen_at)}")
    if stored.exit_time:
        print(f"  Exit time       : {_fmt(stored.exit_time)}")
        print(f"  Duration        : {h:02d}:{m:02d}:{s:02d}")
    print(f"  Camera          : {stored.entry_camera_id}")


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def flow_a_single_camera() -> None:
    """Single-camera (role='both'): entry on first confirmation, exit by presence timeout."""
    engine, Factory = await _make_db()
    guard = DuplicateGuard(window_seconds=30)

    print("=" * 60)
    print("  FLOW A — Single camera (role='both')")
    print("=" * 60)

    def _event(at: datetime) -> SessionEvent:
        return SessionEvent(
            event_type="both",
            camera_id=CAMERA_ID,
            plate_number=PLATE_NUMBER,
            plate_raw="3327HGJ",
            confidence=0.71,
            detected_at=at,
            plate_digits=PLATE_DIGITS,
        )

    # ── Step 1: First confirmed detection → entry
    async with Factory() as db:
        sm = SessionManager(db, guard)
        existing = await sm.sessions.find_active_by_plate(PLATE_DIGITS)
        if existing is None:
            await sm.handle_entry(_event(ENTRY_TIME))
        await db.commit()
    print(f"\n[ENTRY]  Car {PLATE_DIGITS!r}  entered  at  {_fmt(ENTRY_TIME)}")
    print(f"         (plate confirmed after MIN_CONFIRMATION_HITS frames — stored as entry)")

    # ── Step 2: Car still visible — re-detections update last_seen_at
    for t in REDETECT_TIMES:
        async with Factory() as db:
            repo = SessionRepository(db)
            session = await repo.find_active_by_plate(PLATE_DIGITS)
            if session:
                await repo.update_last_seen(session, t)
                await db.commit()
        print(f"[SEEN ]  Car {PLATE_DIGITS!r}  still visible  at  {_fmt(t)}")

    last_seen = REDETECT_TIMES[-1]
    exit_time = last_seen + PRESENCE_TIMEOUT
    print(f"\n         → No detection for {int(PRESENCE_TIMEOUT.total_seconds() // 60)} min after {_fmt(last_seen)}")
    print(f"         → Presence timeout fires at {_fmt(exit_time)}")

    # ── Step 3: Presence timeout fires → exit stored
    async with Factory() as db:
        repo = SessionRepository(db)
        session = await repo.find_active_by_plate(PLATE_DIGITS)
        if session:
            await repo.close_session(
                session,
                exit_time=exit_time,
                exit_camera_id=CAMERA_ID,
                status="completed",
            )
            await db.commit()
    print(f"[EXIT ]  Car {PLATE_DIGITS!r}  exited   at  {_fmt(exit_time)}  (auto-closed by timeout)")

    # ── Print stored record
    async with Factory() as db:
        result = await db.execute(select(VehicleSession).order_by(VehicleSession.id.desc()).limit(1))
        stored = result.scalar_one_or_none()

    print()
    print("─" * 60)
    print("  Stored session record")
    print("─" * 60)
    if stored:
        _print_session(stored)

    await engine.dispose()


async def flow_b_two_cameras() -> None:
    """Two-camera (role='entry' + role='exit'): explicit entry and exit events."""
    engine, Factory = await _make_db()
    guard = DuplicateGuard(window_seconds=30)

    ENTRY_CAM, EXIT_CAM = 1, 2
    t_entry = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
    t_exit  = t_entry + timedelta(minutes=20)

    print()
    print("=" * 60)
    print("  FLOW B — Two cameras (role='entry' + role='exit')")
    print("=" * 60)

    async with Factory() as db:
        sm = SessionManager(db, guard)
        await sm.handle_entry(SessionEvent(
            event_type="entry", camera_id=ENTRY_CAM,
            plate_number=PLATE_NUMBER, plate_raw="3327HGJ",
            confidence=0.72, detected_at=t_entry, plate_digits=PLATE_DIGITS,
        ))
        await db.commit()
    print(f"\n[ENTRY]  Car {PLATE_DIGITS!r}  entered  at  {_fmt(t_entry)}  (camera {ENTRY_CAM})")

    async with Factory() as db:
        sm = SessionManager(db, guard)
        await sm.handle_exit(SessionEvent(
            event_type="exit", camera_id=EXIT_CAM,
            plate_number=PLATE_NUMBER, plate_raw="3327HGJ",
            confidence=0.69, detected_at=t_exit, plate_digits=PLATE_DIGITS,
        ))
        await db.commit()
    print(f"[EXIT ]  Car {PLATE_DIGITS!r}  exited   at  {_fmt(t_exit)}  (camera {EXIT_CAM})")

    async with Factory() as db:
        result = await db.execute(select(VehicleSession).order_by(VehicleSession.id.desc()).limit(1))
        stored = result.scalar_one_or_none()

    print()
    print("─" * 60)
    print("  Stored session record")
    print("─" * 60)
    if stored:
        _print_session(stored)

    # ── Duplicate guard check
    print()
    print("─" * 60)
    print("  Duplicate guard (same plate, 10 s after entry — must be blocked)")
    print("─" * 60)
    async with Factory() as db:
        sm = SessionManager(db, guard)
        await sm.handle_entry(SessionEvent(
            event_type="entry", camera_id=ENTRY_CAM,
            plate_number=PLATE_NUMBER, plate_raw="3327HGJ",
            confidence=0.70, detected_at=t_entry + timedelta(seconds=10),
            plate_digits=PLATE_DIGITS,
        ))
        await db.commit()
        result = await db.execute(select(VehicleSession))
        count = len(result.scalars().all())
    status = "✓  blocked" if count == 1 else "✗  NOT blocked — duplicate created"
    print(f"  Sessions in DB: {count}  ({status})")

    await engine.dispose()


async def run() -> None:
    await flow_a_single_camera()
    await flow_b_two_cameras()
    print()
    print("=" * 60)
    print("  All smoke tests complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())

=======
"""Standalone session-flow smoke test.

Simulates both session flows using an **in-memory SQLite database** — no
PostgreSQL or Docker required.

FLOW A — Single camera (role='both'):
  1. Plate confirmed (≥ MIN_CONFIRMATION_HITS frames) → entry stored.
  2. Camera keeps seeing the car                      → last_seen_at updated.
  3. Car leaves; no detection for PRESENCE_TIMEOUT_MINUTES → exit auto-stored.

FLOW B — Two cameras (role='entry' + role='exit'):
  1. Entry camera confirms plate                      → entry stored.
  2. Exit camera confirms same plate                  → exit stored.

Run:
    uv run python scripts/test_session_flow.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from src.db.models import Base, VehicleSession
from src.db.repositories.session_repo import SessionRepository
from src.session.duplicate_guard import DuplicateGuard
from src.session.manager import SessionEvent, SessionManager

# ---------------------------------------------------------------------------
# Scenario config — edit these to try different cases
# ---------------------------------------------------------------------------
PLATE_NUMBER  = "هقح 3327 HGJ"
PLATE_DIGITS  = "3327"
CAMERA_ID     = 1

ENTRY_TIME          = datetime(2026, 5, 21, 9, 14, 32, tzinfo=timezone.utc)
REDETECT_TIMES      = [ENTRY_TIME + timedelta(minutes=m) for m in (2, 4, 6, 8)]
PRESENCE_TIMEOUT    = timedelta(minutes=5)   # mirrors PRESENCE_TIMEOUT_MINUTES in .env
# ---------------------------------------------------------------------------


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") + " UTC"


def _print_session(stored: VehicleSession) -> None:
    duration = stored.duration_seconds or 0
    h, rem = divmod(duration, 3600)
    m, s = divmod(rem, 60)
    print(f"  ID              : {stored.id}")
    print(f"  Plate           : {stored.plate_number}")
    print(f"  Status          : {stored.status}")
    print(f"  Entry time      : {_fmt(stored.entry_time)}")
    if stored.last_seen_at:
        print(f"  Last seen at    : {_fmt(stored.last_seen_at)}")
    if stored.exit_time:
        print(f"  Exit time       : {_fmt(stored.exit_time)}")
        print(f"  Duration        : {h:02d}:{m:02d}:{s:02d}")
    print(f"  Camera          : {stored.entry_camera_id}")


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def flow_a_single_camera() -> None:
    """Single-camera (role='both'): entry on first confirmation, exit by presence timeout."""
    engine, Factory = await _make_db()
    guard = DuplicateGuard(window_seconds=30)

    print("=" * 60)
    print("  FLOW A — Single camera (role='both')")
    print("=" * 60)

    def _event(at: datetime) -> SessionEvent:
        return SessionEvent(
            event_type="both",
            camera_id=CAMERA_ID,
            plate_number=PLATE_NUMBER,
            plate_raw="3327HGJ",
            confidence=0.71,
            detected_at=at,
            plate_digits=PLATE_DIGITS,
        )

    # ── Step 1: First confirmed detection → entry
    async with Factory() as db:
        sm = SessionManager(db, guard)
        existing = await sm.sessions.find_active_by_plate(PLATE_DIGITS)
        if existing is None:
            await sm.handle_entry(_event(ENTRY_TIME))
        await db.commit()
    print(f"\n[ENTRY]  Car {PLATE_DIGITS!r}  entered  at  {_fmt(ENTRY_TIME)}")
    print(f"         (plate confirmed after MIN_CONFIRMATION_HITS frames — stored as entry)")

    # ── Step 2: Car still visible — re-detections update last_seen_at
    for t in REDETECT_TIMES:
        async with Factory() as db:
            repo = SessionRepository(db)
            session = await repo.find_active_by_plate(PLATE_DIGITS)
            if session:
                await repo.update_last_seen(session, t)
                await db.commit()
        print(f"[SEEN ]  Car {PLATE_DIGITS!r}  still visible  at  {_fmt(t)}")

    last_seen = REDETECT_TIMES[-1]
    exit_time = last_seen + PRESENCE_TIMEOUT
    print(f"\n         → No detection for {int(PRESENCE_TIMEOUT.total_seconds() // 60)} min after {_fmt(last_seen)}")
    print(f"         → Presence timeout fires at {_fmt(exit_time)}")

    # ── Step 3: Presence timeout fires → exit stored
    async with Factory() as db:
        repo = SessionRepository(db)
        session = await repo.find_active_by_plate(PLATE_DIGITS)
        if session:
            await repo.close_session(
                session,
                exit_time=exit_time,
                exit_camera_id=CAMERA_ID,
                status="completed",
            )
            await db.commit()
    print(f"[EXIT ]  Car {PLATE_DIGITS!r}  exited   at  {_fmt(exit_time)}  (auto-closed by timeout)")

    # ── Print stored record
    async with Factory() as db:
        result = await db.execute(select(VehicleSession).order_by(VehicleSession.id.desc()).limit(1))
        stored = result.scalar_one_or_none()

    print()
    print("─" * 60)
    print("  Stored session record")
    print("─" * 60)
    if stored:
        _print_session(stored)

    await engine.dispose()


async def flow_b_two_cameras() -> None:
    """Two-camera (role='entry' + role='exit'): explicit entry and exit events."""
    engine, Factory = await _make_db()
    guard = DuplicateGuard(window_seconds=30)

    ENTRY_CAM, EXIT_CAM = 1, 2
    t_entry = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
    t_exit  = t_entry + timedelta(minutes=20)

    print()
    print("=" * 60)
    print("  FLOW B — Two cameras (role='entry' + role='exit')")
    print("=" * 60)

    async with Factory() as db:
        sm = SessionManager(db, guard)
        await sm.handle_entry(SessionEvent(
            event_type="entry", camera_id=ENTRY_CAM,
            plate_number=PLATE_NUMBER, plate_raw="3327HGJ",
            confidence=0.72, detected_at=t_entry, plate_digits=PLATE_DIGITS,
        ))
        await db.commit()
    print(f"\n[ENTRY]  Car {PLATE_DIGITS!r}  entered  at  {_fmt(t_entry)}  (camera {ENTRY_CAM})")

    async with Factory() as db:
        sm = SessionManager(db, guard)
        await sm.handle_exit(SessionEvent(
            event_type="exit", camera_id=EXIT_CAM,
            plate_number=PLATE_NUMBER, plate_raw="3327HGJ",
            confidence=0.69, detected_at=t_exit, plate_digits=PLATE_DIGITS,
        ))
        await db.commit()
    print(f"[EXIT ]  Car {PLATE_DIGITS!r}  exited   at  {_fmt(t_exit)}  (camera {EXIT_CAM})")

    async with Factory() as db:
        result = await db.execute(select(VehicleSession).order_by(VehicleSession.id.desc()).limit(1))
        stored = result.scalar_one_or_none()

    print()
    print("─" * 60)
    print("  Stored session record")
    print("─" * 60)
    if stored:
        _print_session(stored)

    # ── Duplicate guard check
    print()
    print("─" * 60)
    print("  Duplicate guard (same plate, 10 s after entry — must be blocked)")
    print("─" * 60)
    async with Factory() as db:
        sm = SessionManager(db, guard)
        await sm.handle_entry(SessionEvent(
            event_type="entry", camera_id=ENTRY_CAM,
            plate_number=PLATE_NUMBER, plate_raw="3327HGJ",
            confidence=0.70, detected_at=t_entry + timedelta(seconds=10),
            plate_digits=PLATE_DIGITS,
        ))
        await db.commit()
        result = await db.execute(select(VehicleSession))
        count = len(result.scalars().all())
    status = "✓  blocked" if count == 1 else "✗  NOT blocked — duplicate created"
    print(f"  Sessions in DB: {count}  ({status})")

    await engine.dispose()


async def run() -> None:
    await flow_a_single_camera()
    await flow_b_two_cameras()
    print()
    print("=" * 60)
    print("  All smoke tests complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())

>>>>>>> 0b51e9811058d73267f663c69338d377595aea4a
