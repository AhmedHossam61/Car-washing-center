from __future__ import annotations

import asyncio
import logging
from queue import Empty

from src.camera.frame_buffer import FrameBuffer
from src.config import CameraConfig, Settings
from src.db.connection import AsyncSessionFactory
from src.detection.confirmation import ConfirmationFilter
from src.detection.ocr_engine import OCREngine
from src.detection.pipeline import ALPRPipeline
from src.detection.plate_detector import PlateDetector
from src.reporting.google_sheets import SheetSessionRow, session_writer_from_settings
from src.session.duplicate_guard import DuplicateGuard
from src.session.manager import SessionEvent, SessionManager
from src.utils.image_utils import save_snapshot, snapshot_path

logger = logging.getLogger(__name__)


class AIWorker:
    """
    Async worker that continuously reads frames from the FrameBuffer,
    runs the ALPR pipeline, and dispatches entry/exit events to SessionManager.

    Call ``run()`` as an asyncio task.  Call ``stop()`` to request shutdown.
    """

    def __init__(
        self,
        settings: Settings,
        frame_buffer: FrameBuffer,
        camera_configs: dict[int, CameraConfig],
        duplicate_guard: DuplicateGuard,
    ) -> None:
        self.settings = settings
        self.frame_buffer = frame_buffer
        self.camera_configs = camera_configs
        self.duplicate_guard = duplicate_guard
        self._running = False
        self._pipeline: ALPRPipeline | None = None
        self._sheets_writer = session_writer_from_settings(settings)

    # ------------------------------------------------------------------
    # Pipeline initialisation (blocking – run in executor)
    # ------------------------------------------------------------------

    def _build_pipeline(self) -> ALPRPipeline:
        detector = PlateDetector(
            weights_path=self.settings.yolo_plate_weights,
            confidence_threshold=self.settings.plate_confidence,
            imgsz=self.settings.yolo_imgsz,
        )
        ocr = OCREngine(
            use_gpu=self.settings.ocr_use_gpu,
            confidence_threshold=self.settings.ocr_confidence,
            backend=self.settings.ocr_backend,
            fallback=self.settings.ocr_fallback,
            paddle_text_recognition_model_name=self.settings.paddle_text_recognition_model_name,
        )
        return ALPRPipeline(
            detector,
            ocr,
            detect_width=self.settings.yolo_imgsz,
            preprocess_variant=self.settings.preprocess_variant,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()

        logger.info("AI worker: loading models …")
        pipeline = await loop.run_in_executor(None, self._build_pipeline)
        logger.info("AI worker: models ready, entering processing loop")

        confirmation = ConfirmationFilter(
            min_hits=self.settings.min_confirmation_hits,
            fuzzy_threshold=self.settings.confirmation_fuzzy_threshold,
        )

        while self._running:
            # --- fetch next frame (blocking get, non-async) ---
            try:
                item = await loop.run_in_executor(None, lambda: self.frame_buffer.get(timeout=0.1))
            except Empty:
                await asyncio.sleep(0)
                continue
            except Exception:
                logger.exception("Error reading from FrameBuffer")
                await asyncio.sleep(0.1)
                continue

            camera_config = self.camera_configs.get(item.camera_id)
            if camera_config is None:
                continue

            # --- run ALPR pipeline (CPU/GPU bound) ---
            try:
                captured_at = item.captured_at
                frame = item.frame
                camera_id = item.camera_id
                plate_events = await loop.run_in_executor(
                    None,
                    lambda: pipeline.process_frame(
                        camera_id=camera_id,
                        frame=frame,
                        captured_at=captured_at,
                    ),
                )
            except Exception:
                logger.exception("ALPR pipeline error for camera %d", item.camera_id)
                continue

            if not plate_events:
                confirmation.update(item.camera_id, [])  # clears streaks for this camera
                continue

            plate_events = confirmation.update(item.camera_id, plate_events)
            if not plate_events:
                continue

            # --- persist detections in one DB transaction ---
            async with AsyncSessionFactory() as db:
                async with db.begin():
                    sm = SessionManager(db, self.duplicate_guard)
                    for event in plate_events:
                        snap: str | None = None
                        try:
                            p = snapshot_path(
                                base_dir=self.settings.snapshot_dir,
                                event_type=camera_config.role,
                                plate_number=event.plate_number,
                                detected_at=event.detected_at,
                            )
                            crop = event.crop
                            await loop.run_in_executor(None, lambda: save_snapshot(crop, p))
                            snap = str(p)
                        except Exception:
                            logger.exception("Snapshot save failed for plate %s", event.plate_number)

                        session_event = SessionEvent(
                            event_type=camera_config.role,
                            camera_id=item.camera_id,
                            plate_number=event.plate_number,
                            plate_raw=event.plate_raw,
                            confidence=event.confidence,
                            detected_at=event.detected_at,
                            snapshot_path=snap,
                            plate_digits=event.numeric_part,
                        )

                        if camera_config.role == "entry":
                            await sm.handle_entry(session_event)
                        elif camera_config.role == "exit":
                            await sm.handle_exit(session_event)
                        else:
                            # "both" (single camera): create entry on first sight;
                            # on every subsequent detection just refresh last_seen_at
                            # so the presence-timeout checker knows the car is still there.
                            lookup_key = event.numeric_part or event.plate_number
                            existing = await sm.sessions.find_active_by_plate(lookup_key)
                            if existing is None:
                                await sm.handle_entry(session_event)
                            else:
                                await sm.sessions.update_last_seen(existing, event.detected_at)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Presence-timeout checker (single-camera "both" role)
    # ------------------------------------------------------------------

    async def run_presence_timeout_checker(self) -> None:
        """Close sessions whose last_seen_at is older than presence_timeout_minutes.

        Run this as a parallel asyncio task alongside ``run()``.  It only
        matters when cameras are configured with role='both'; entry/exit camera
        setups are unaffected.
        """
        timeout_minutes = self.settings.presence_timeout_minutes
        check_interval = 30  # seconds between sweeps

        logger.info(
            "Presence timeout checker started (timeout=%d min, interval=%ds)",
            timeout_minutes,
            check_interval,
        )

        while self._running:
            await asyncio.sleep(check_interval)
            try:
                async with AsyncSessionFactory() as db:
                    async with db.begin():
                        from src.db.repositories.session_repo import SessionRepository
                        from datetime import datetime, timezone

                        repo = SessionRepository(db)
                        timed_out = await repo.find_timed_out_sessions(timeout_minutes)
                        for session in timed_out:
                            now = datetime.now(timezone.utc)
                            await repo.close_session(
                                session,
                                exit_time=now,
                                exit_camera_id=None,
                                status="completed",
                            )
                            if self._sheets_writer is not None:
                                row = SheetSessionRow(
                                    source="camera",
                                    plate_number=session.plate_number,
                                    entry_time=session.entry_time,
                                    last_seen_at=session.last_seen_at,
                                    exit_time=session.exit_time,
                                    duration_seconds=session.duration_seconds,
                                    visible_duration_seconds=session.duration_seconds,
                                    status=session.status,
                                )
                                await asyncio.get_running_loop().run_in_executor(
                                    None,
                                    lambda: self._sheets_writer.append_sessions([row]),
                                )
                            logger.info(
                                "Presence timeout: closed session %d plate=%s (last_seen=%s)",
                                session.id,
                                session.plate_number,
                                session.last_seen_at or session.entry_time,
                            )
            except Exception:
                logger.exception("Error in presence timeout checker")
