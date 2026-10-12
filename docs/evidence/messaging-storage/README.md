# 4단계 읽기 전용 자원 사전 점검

관측 시각: **2026-10-12 10:37:36 KST** (`2026-10-12T01:37:36.094751Z`). [구현 전 계획](../../plans/phase4-messaging-storage.md)의 잠정 자원 관문을 한 시점에 확인했다. **available memory 6 GiB·Lab 파일시스템 여유 40 GiB 기준은 통과**했다.

| 항목 | 실제 관측값 |
| --- | --- |
| 논리 CPU | 16 |
| 전체 / available 메모리 | 32,998,993,920 / 20,781,006,848 bytes (available 약 19.35 GiB) |
| Lab 파일시스템 전체 / available | 502,392,610,816 / 244,923,068,416 bytes (available 약 228.10 GiB) |
| load average (1 / 5 / 15분) | 1.1494140625 / 1.47900390625 / 1.5625 |
| 기존 Docker 전체 / 실행 / restarting | 35 / 23 / 0 |
| Kubernetes Pod / Ready node | 11 / 1 |

[preflight.json](preflight.json)은 점검 보고서의 `publicSummary`에서 명시적으로 허용한 필드만 추출했다. Docker identity·mount, Pod·node 상세와 실제 경로·접속 주소·비밀값은 공개본에 포함하지 않았다.

이 결과는 **point-in-time 관문 통과**다. peak 부하·지속 여유·신규 구성의 성능·스케줄링·PV 용량 예약은 검증하지 않았다. 기존 제안 request/limit은 실측 사용량으로 바꾸지 않는다. 실제 설치 직전 자원·inode·PV와 기존 서비스 상태를 다시 점검한다.

이번 점검은 읽기 전용이며 **서비스 설치를 수행하지 않았다**. Kafka·Garage·Java SDK 조합과 배포 digest는 미확정이고, Kafka 전달·S3 호환성·DB 잠금·재전달·복구 시험은 아직 수행하지 않았다. 다음 수정 범위는 격리 환경의 V2 작업/outbox·실행 슬롯과 기존 계약 보존이며, 공개 실행 POST는 계속 비활성화한다.
