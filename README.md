# project3-hailcast-app
hailcast 앱·AI 소스 · 담당: 그룹 B (이창원·양재혁)

## 폴더 = 파드 단위
- call-api : 콜 접수(빠름)   - worker : 큐 처리(KEDA 대상)
- predict  : 예측 서비스(/metrics)   - simulator : 부하 생성
- weather-cron : 날씨 수집   - ml : 오프라인 학습(1회)
## 원칙
빌드→ECR push→EKS pull. AI는 LightGBM까지.
