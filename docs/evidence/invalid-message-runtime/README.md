# 잘못된 Kafka 메시지 뒤의 정상 작업 보호

2026-10-20 13:40:24 UTC, 새 hosted Linux의 [실제 시험 39432070400](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39432070400)이 통과했습니다. 첫 record가 잘못된 JSON일 때 런타임이 영속 중지하고, 뒤의 정상 작업을 처리·commit하지 않는 동작을 확인했습니다. 입력을 수리하지 않은 명시 resume 뒤에도 새 worker가 다시 중지됐습니다.

## 실제 결과

| 경계 | 관측한 결과 |
| --- | --- |
| 실제 입력 순서 | 잘못된 JSON의 producer ACK offset 0, 실제 `DispatchPublisher`로 발행한 정상 작업의 ACK offset 1, read-committed end 2 |
| 첫 worker | 새 JVM의 실제 daemon이 `PAUSED_OPERATOR / CONSUME / INVALID_MESSAGE`를 저장하고 종료 |
| 일반 run 거부 | 원 CLI의 실행이 거부되고 전체 journal·시각·업무 baseline 보존 |
| 명시 resume | 원 CLI가 `STOPPED`를 기록했으나 입력을 고치지는 않음 |
| 두 번째 worker | 같은 group의 새 JVM도 같은 실제 오류로 영속 중지. 두 번째 일반 run 거부에서도 전체 journal 보존 |
| 정상 작업 | `QUEUED / NOT_REQUESTED`, 업무 처리 0·업무 결과 0·EXPORT outbox 0, 슬롯 점유 유지 |
| commit 관측 | 두 worker 종료 뒤 모두 실제 `NO_COMMIT / null`. end 2로부터 lag 2를 계산하지 않음 |
| 보존·종료 | job 모든 컬럼·시각/BLOB·raw/source bytes·DISPATCH ACK·policy·slot 보존, child clients 종료·lease 해제·동일 target·소스 불변·소유 자원 정리 통과 |

정상 source는 합성 입력 12건이며 실제 staging·raw 전체 GET 검증을 거쳤습니다. worker 시작 전에 별도 READ_COMMITTED observer가 수동 assign으로 record 0/1과 정상 DispatchMessage를 대조하고 닫혔습니다. 이 observer는 group join·commit을 하지 않았습니다. `INVALID_MESSAGE`는 가짜 예외 주입이 아니라 실제 잘못된 JSON을 받은 production decode 경로의 결과입니다.

JUnit은 지정 IT 1개·실패 0·오류 0·skip 0입니다. [PR140 CI 39431817069](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39431817069)의 Python 경계 검사 31개와 fresh API107 compile-only를 먼저 통과한 뒤, 병합 main에서 첫 수동 opt-in 시험 한 번을 실행했습니다.

## 원문과 고정 출처

- [실제 summary 원문](summary.json), [실행 metadata](run-metadata.json)
- source: [`15def179`의 실제 IT](https://github.com/DevDooly/devdooly-platform-lab/blob/15def17943f89975b22d9634cdeab2ec38b113fe/infra/invalid-message-runtime-ci/InvalidMessageRuntimeIT.java), [실행기·검증 조건](https://github.com/DevDooly/devdooly-platform-lab/blob/15def17943f89975b22d9634cdeab2ec38b113fe/infra/invalid-message-runtime-ci/README.ko.md)
- raw summary SHA-256: `ad1a16a81a6df9c7127b5673c06982f5dd5eaa94cc997eb50e47ab36eb91eca2`
- source manifest SHA-256: `675df469740b103e8c45e46c49f3b2b02c34f2d1d73c8da3ca94321f1ec1d887`
- JUnit XML SHA-256: `a0c09825cb8bb16b3242bcf84427f23ba073e78d0d248ded2bb85be46bac090b`

유한 summary의 18개 필드와 `protectionResult` 31개 필드를 실제 타입·값으로 대조했습니다. 원문을 기대값으로 재작성하지 않았으며 `synthetic: true`는 합성 입력을 뜻합니다.

## 해석과 공개 연결

이 PASS는 정상 작업을 진행시키지 않는 보호 동작의 통과입니다. 처리·export·슬롯 해제·복구 완료가 아닙니다. DLQ·skip·offset reset·입력 수리·record/topic 삭제 정책을 구현하지 않았고 `automaticRepairPerformed`는 false입니다. 남아 있는 잘못된 입력을 운영에서 어떻게 처리할지는 별도 정책입니다.

새 Kafka·MariaDB·Garage·JVM 4개와 내부 네트워크만 사용하고 CPU·메모리·PID·단일 deadline과 full-ID 정리를 유지했습니다. 기존 API106·Probe·이전 manifest·미니 PC 운영 서비스·자료·PVC는 변경하지 않았습니다. 토큰 교체·예산 정책·PR102는 보류합니다.

공개 사이트의 기술별 근거 목록에 연결을 준비했습니다. Pages 게시 후 실제 항목과 링크를 확인할 예정입니다.
