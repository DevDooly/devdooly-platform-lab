# 공개 조회 운영 재확인 — 2026-10-20 UTC

기존 공개 조회 경로를 유지한 상태에서 선택한 운영 상태와 HTTPS 응답을 다시 확인했습니다. [허용 필드 요약](summary.json)은 서로 다른 수집 시각의 결과를 모은 기록이며, 장기간 가용성이나 SLA를 증명하지 않습니다. 이전 [HTTPS 검증과 실패 이력](../README.md)은 그대로 보존합니다.

| 확인 대상 | 실제 관측 |
| --- | --- |
| 선택 운영 상태 | 노드 Ready, Lab Pod 7개 Running·컨테이너 Ready, Argo CD Synced·Healthy |
| DDNS 자연 실행 | timer active·enabled, 마지막 trigger와 연결된 UPDATE_ACCEPTED 1건. 수동 updater 실행 없이 읽기 전용으로 확인 |
| 표준 TLS | 기본 CA·SNI·호스트 검증 통과, TLS 1.3. 인증서 만료 2027-01-16 13:10:02 UTC, 수집 당시 88일 남음 |
| 공개 화면 | 실시간 API 연결, 작업 8개·export 8개, Kafka committed offset 8·LSO 8·lag 0 |
| 자격증명 | 각 역할의 지정 GitHub GET 2개가 각각 200 응답. 만료 시각은 UNKNOWN, 교체는 사용자 선택에 따라 보류 |

[GitHub 외부 runner의 실행 39400253632](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39400253632)는 09:23:41 UTC에 완료된 검사에서 공개 IPv4·표준 TLS와 허용 GET 6개의 200 응답·공개 DTO 검증을 통과했습니다. 지정한 잘못된 경로·Origin·method는 각각 404·403·405를 확인했습니다. 선택한 Lab 라우트 선언의 충돌 전제도 읽기 전용으로 대조했으며, 전체 provider의 실시간 동작을 일반화한 증명은 아닙니다.

이번 기록은 현재 공개 경로의 재부팅 시험이 아닙니다. 인증서 자연 갱신은 미검증이고, 토큰 GET 200은 해당 요청의 정상 응답 범위이며 만료일이나 전체 권한을 확인한 결과가 아닙니다. 자격증명 회전과 자원 예산·접수 gate 활성화는 보류합니다. 주소·비밀값·진단 원문·무관한 앱의 상태는 공개 요약에 포함하지 않았습니다.
