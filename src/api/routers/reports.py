from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import require_api_key


router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_api_key)])


@router.get("")
async def list_reports() -> dict[str, str]:
    return {"status": "not_implemented"}
