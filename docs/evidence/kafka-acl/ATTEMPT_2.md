# Kafka ACL 격리 시험 — 두 번째 실패 기록

2026-10-18의 [GitHub hosted 실행 39137979832](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39137979832)은 [소스 a58c5609](https://github.com/DevDooly/devdooly-platform-lab/commit/a58c5609bdc0cd29fec92610fe5233333e54c402)와 고정 runtime manifest `c80c1256`을 사용한 새 격리 시험입니다. [첫 실패](ATTEMPT_1.md)를 덮어쓰지 않고, 준비 단계의 operation과 오류 분류를 유한 값으로 기록했습니다.

| 항목 | 실제 결과 |
| --- | --- |
| 준비 단계 | `SUCCESS` |
| 격리 runtime | `FAILED` · `IT_FAILED` |
| 중단 단계·분류 | `SETUP` · `UNEXPECTED` |
| 선택 operation·오류 분류 | `OTHER_GROUP_OFFSETS` · `TIMEOUT` |
| 검증 완료 테스트 | 0 / 예정 1 |
| 실행 소유 자원 정리 | 확인됨 (`ownedResourcesRemoved: true`) |

[원본 유한 summary](attempt-2.summary.json)를 그대로 보존합니다. 이번 관측으로 실패 지점은 SETUP의 `OTHER_GROUP_OFFSETS` operation까지 좁혀졌습니다. coordinator 준비 상태가 원인이라는 설명은 아직 가설이며, 첫 실행의 원인까지 소급해 확정하지 않습니다. 후속 후보로 기존 준비 operation의 순서 재배치를 검토합니다.

관측 principal의 허용 조회·선택한 RPC 거부·잘못된 비밀번호 거부는 아직 통과 근거가 없습니다. 상태 보존·소스 보존 등 검증 필드의 false는 미검증을 뜻하며 실제 변경이 있었다는 판정이 아닙니다. 모든 쓰기 차단·TLS 기밀성·모든 JVM thread 종료도 증명하지 않습니다. 권한 확대나 운영 Kafka 변경으로 우회하지 않았고 공개 실행은 활성화하지 않았습니다. 주소·합성 비밀번호·원시 로그와 예외문은 이 공개 기록에 포함하지 않습니다.
