# Kafka ACL 격리 시험 — 첫 실패 기록

2026-10-18의 [GitHub hosted 실행 39136790510](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39136790510)은 [소스 dfa4b2c](https://github.com/DevDooly/devdooly-platform-lab/commit/dfa4b2c83b5a4a8c6a6bd7d41e0e9842f4c590db)에서 새 격리 Kafka와 합성 자격증명을 사용했습니다. 전용 관측 principal의 허용 조회와 선택한 쓰기·다른 대상 접근 거부를 확인하려는 시험이며, 운영 Kafka의 권한이나 TLS를 검증하는 실행이 아닙니다.

| 항목 | 실제 결과 |
| --- | --- |
| 준비 단계 | `SUCCESS` |
| 격리 runtime | `FAILED` · `IT_FAILED` |
| 중단 단계·분류 | `SETUP` · `UNEXPECTED` |
| 검증 완료 테스트 | 0 / 예정 1 |
| 실행 소유 자원 정리 | 확인됨 (`ownedResourcesRemoved: true`) |

[원본 유한 summary](attempt-1.summary.json)를 그대로 보존합니다. SETUP에서 종료됐으므로 관측 principal의 권한, 선택한 RPC 거부와 잘못된 비밀번호 거부는 통과 근거가 없습니다. `selectedAdminStatePreserved`·`sourceAndArtifactsUnchanged` 등 검증 필드의 false는 **확인하지 못했다는 뜻**이며, 해당 상태나 소스가 실제로 바뀌었다는 뜻이 아닙니다. 모든 쓰기 차단·TLS 기밀성·모든 JVM thread 종료도 증명하지 않습니다.

정확한 실패 원인은 아직 확인하지 않았습니다. 후속 유한 진단은 별도로 준비하며, 이 첫 실행을 덮어쓰거나 같은 실행을 재시도하지 않았습니다. 권한 확대·운영 Kafka 변경·공개 실행 활성화는 수행하지 않았습니다. 주소·합성 비밀번호·원시 로그와 예외문은 이 공개 기록에 포함하지 않습니다.
