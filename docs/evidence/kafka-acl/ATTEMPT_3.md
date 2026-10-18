# Kafka ACL 격리 시험 — 세 번째 실패 기록

2026-10-18의 [GitHub hosted 실행 39138559079](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39138559079)은 [소스 6999c168](https://github.com/DevDooly/devdooly-platform-lab/commit/6999c1684135a0c01aaa5aca5f59dd243fd9f9c1)와 고정 runtime manifest `8b5a61b0`을 사용한 새 격리 시험입니다. [첫 실패](ATTEMPT_1.md)와 [두 번째 실패](ATTEMPT_2.md)는 그대로 보존합니다.

| 항목 | 실제 결과 |
| --- | --- |
| 준비 단계 | `SUCCESS` |
| 격리 runtime | `FAILED` · `IT_FAILED` |
| 중단 단계·분류 | `SETUP` · `UNEXPECTED` |
| 선택 operation·오류 분류 | `OTHER_GROUP_DESCRIBE` · `TIMEOUT` |
| 검증 완료 테스트 | 0 / 예정 1 |
| 실행 소유 자원 정리 | 확인됨 (`ownedResourcesRemoved: true`) |

[원본 유한 summary](attempt-3.summary.json)를 그대로 보존합니다. 현재 시험 순서에서는 primary group의 join·produce·commit과 다른 그룹의 초기 오프셋 기록가 describe보다 먼저 성공했고, 이후 `OTHER_GROUP_DESCRIBE`에서 timeout으로 중단됐습니다. 이는 준비 operation의 진행 범위이며 관측 principal의 전체 ACL 시험이 통과했다는 뜻은 아닙니다.

coordinator 준비 상태나 client fallback·retry budget의 영향은 추가 조사 대상입니다. 운영 Admin 설정의 retries=1과 격리 fixture의 retries=0 차이만으로 이번 원인을 확정하지 않으며, 첫째·둘째 실패의 원인도 소급해 확정하지 않습니다. 같은 실행을 재시도하거나 운영 권한을 확대해 우회하지 않았습니다.

허용 조회·선택 RPC 거부·잘못된 비밀번호 거부, 상태·소스 보존 등 false 필드는 미검증을 뜻하며 실제 변경이 있었다는 판정이 아닙니다. 모든 쓰기 차단·TLS 기밀성·모든 JVM thread 종료도 증명하지 않습니다. 운영 Kafka 변경과 공개 실행은 없으며 주소·합성 비밀번호·원시 로그·예외문은 이 공개 기록에 포함하지 않습니다.
