# 미니 PC 상시 worker/export 배포

2026-10-15의 사용자 요청으로 실제 배포를 진행합니다. 이 준비 commit 시점에는 실행기 배포·공개 관측 게시를 완료로 표시하지 않습니다.

## 준비 검증

- 기존 Docker 38개/실행 26개, Lab Pod 3개, Argo Synced·Healthy 읽기 확인
- 사용 가능한 메모리 약 18.6GiB, 디스크 약 208GiB
- 기존 MariaDB single-transaction dump와 K3s SQLite online backup 생성
- 외부 AES-256-GCM 암호화 사본의 인증·SHA-256 read-back 검증
- Kafka 공식 고정 image의 UID/GID 1000 확인
- Java·Helm·관측 자동화 검증 결과는 실제 실행 완료 후 최종 기록에 추가

[배포 결정](../../adr/0009-mini-pc-runtime-deployment.md)에 따라 저장소 bootstrap → 동일 SHA CI gate → API migration → worker → 실제 내부 합성 작업 → Pages 관측 순서로 진행합니다. 실제 배포·게시가 확인되면 이 문서를 관측 시각과 근거로 갱신합니다.
