# Call Router — Validation과 위임만 수행. Business Logic 금지.
from fastapi import APIRouter, Depends, HTTPException, status

from common.models.call import CallRequest, CallResponse, CallStatusResponse

from dependencies import get_call_query_service, get_call_service
from services.call_service import CallQueryService, CallService

router = APIRouter(tags=["call"])


@router.post("/call", response_model=CallResponse, status_code=status.HTTP_202_ACCEPTED)
def create_call(
    request: CallRequest,  # pydantic이 필수값/범위 검증 → 실패 시 공통 핸들러가 400 반환
    service: CallService = Depends(get_call_service),
) -> CallResponse:
    return service.accept_call(request)


@router.get("/call/{request_id}", response_model=CallStatusResponse)
def get_call_status(
    request_id: str,
    service: CallQueryService = Depends(get_call_query_service),
) -> CallStatusResponse:
    result = service.get_status(request_id)
    if result is None:
        # Worker가 아직 저장하지 않았거나 존재하지 않는 요청
        raise HTTPException(status_code=404, detail="call not found (not processed yet)")
    return result


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
