# SqsInjectService — call-api를 거치지 않고 SQS에 CallMessage를 직접 발행한다 (C3).
# FE "SQS 메시지 유입" 버튼용: 큐 적체 → KEDA 확장 → worker 소비 경로를 수동으로
# 자극하는 데모/테스트 도구. 메시지 스키마는 call-api 발행분과 동일(CallMessage)이라
# worker가 구분 없이 소비한다. call-api를 우회하므로 트래픽 집계(A1)에는 잡히지 않는다.
import uuid
from datetime import datetime, timezone

from common.aws.sqs_adapter import SqsAdapter
from common.core.constants import SOURCE_SIMULATOR
from common.core.logger import get_logger
from common.models.call import CallMessage, CallRequest, SqsInjectResponse

logger = get_logger("sqs_inject_service")


class SqsInjectService:
    def __init__(self, sqs: SqsAdapter):
        # SQS 접근은 공통 어댑터로만 한다 (boto3 직접 호출 금지 — 팀 규칙).
        # 어느 큐로 보낼지(queue_name/url)는 어댑터 생성 시점에 이미 정해져 있다.
        self._sqs = sqs

    def inject(self, count: int) -> SqsInjectResponse:
        # count는 라우터에서 상한(SQS_INJECT_MAX_COUNT) 검증을 마치고 들어온다.
        now = datetime.now(timezone.utc)
        request_ids: list[str] = []
        for _ in range(count):
            # request_id: 콜 1건의 고유 ID. call-api의 accept_call과 같은 방식(uuid4).
            # worker가 이 ID로 calls/<id>.json을 만들므로, 응답으로 돌려주면
            # 호출자가 GET /call/{id}로 처리 여부를 추적할 수 있다.
            request_id = str(uuid.uuid4())

            # CallMessage = SQS 메시지 봉투(스키마 버전·발행시각 포함).
            # data에 실제 콜 내용(CallRequest)이 들어간다 — call-api 발행분과
            # 형태가 완전히 같아야 worker가 구분 없이 역직렬화할 수 있다.
            message = CallMessage(
                request_id=request_id,
                timestamp=now,  # 발행 시각 — worker가 큐 대기시간(queue_latency) 계산에 씀
                data=CallRequest(
                    # 실사용 값이 아니라 "직접 유입분"임을 로그/DB에서 알아볼 수 있는 고정 마커
                    user_id="sqs-inject",
                    pickup="sqs-inject-pickup",
                    destination="sqs-inject-destination",
                    requested_at=now,
                    source=SOURCE_SIMULATOR,  # 출처 표시: api가 아닌 simulator발
                ),
            )
            # 봉투를 JSON(dict)으로 바꿔 큐에 발행 — 여기가 실제 SQS SendMessage 지점
            self._sqs.send_message(message.to_body())
            request_ids.append(request_id)

        logger.info(
            f"sqs injected ({count})",
            extra={"event": "queue_publish", "count": count},
        )
        # 몇 건을, 어떤 ID로, 언제 넣었는지 호출자(FE/curl)에게 돌려준다
        return SqsInjectResponse(injected=count, request_ids=request_ids, queued_at=now)
