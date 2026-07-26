// 예측 모델(ml/train.py, backend/predict/services/prediction_service.py)은 뉴욕 현지시간
// (America/New_York) 기준 hour를 피처로 쓴다. 그래프 시간축을 브라우저 로컬시간(getHours())으로
// 찍으면 라벨과 모델이 실제로 예측한 시각이 어긋난다(2026-07-24/25 발견, B-7) — 뉴욕 밤 11시
// 예측값이 한국시간 낮 12시로 잘못 표시되는 식. 파드수 그래프·날씨 스트립 둘 다 이 함수로 통일한다.
const nycHourFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour: 'numeric',
  hourCycle: 'h23',
})

export function nycHourLabel(date: Date): string {
  return `${nycHourFormatter.format(date)}시`
}
