from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.api.dependencies import require_api_key
from src.api.schemas import CameraListResponse
from src.camera.manager import CameraManager


router = APIRouter(prefix="/cameras", tags=["cameras"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[CameraListResponse])
async def list_cameras(request: Request) -> list[CameraListResponse]:
    manager: CameraManager = request.app.state.camera_manager
    statuses = {s.camera_id: s for s in manager.statuses()}

    result: list[CameraListResponse] = []
    for camera in manager.settings.cameras_json:
        cam_status = statuses.get(camera.id)
        result.append(
            CameraListResponse(
                id=camera.id,
                name=camera.name,
                role=camera.role,
                location=camera.location,
                is_active=camera.is_active,
                running=cam_status.is_running if cam_status else False,
                connected=cam_status.is_connected if cam_status else False,
                last_frame_at=cam_status.last_frame_at if cam_status else None,
                last_error=cam_status.last_error if cam_status else None,
            )
        )
    return result

