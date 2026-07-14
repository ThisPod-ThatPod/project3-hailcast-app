# Call Router — Validation과 위임만 수행. Business Logic 금지.
#
# [복원 2026-07-13] B — 스키마(B1)가 pickup/destination을 텍스트로 단순화되면서
# backend/frontend-contract/call_router.py에 격리해뒀던 걸 반영해 다시 연결함.
# GET /call/{id}는 C(worker) 완료로 다시 실데이터를 반환한다.
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
        # Worker가 아직 처리하지 않았거나(QUEUED 상태는 기록 안 함) 존재하지 않는 요청
        raise HTTPException(status_code=404, detail="call not found (not processed yet)")
    return result


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
