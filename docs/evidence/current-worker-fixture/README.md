# 현재 worker의 고정 V1 작업 처리

2026-10-21 UTC, 배포된 worker에 고정 seed42의 합성 입력 한 건을 새로 접수하고 Kafka·DB 처리·export까지 확인했습니다. 기존 작업의 과거 성과나 CI 성공을 새 작업의 처리 결과로 사용하지 않았습니다. [worker 이미지 교체 근거](../worker-image-rollout/README.md)에 이어 실제 신규 입력 경로를 확인한 단발 실행입니다.

## 실행 대상과 결과

| 항목 | 확인한 값 |
| --- | --- |
| worker source | `6f551a16a8ed536bb126403234c41b9e9b266d43` |
| worker image digest | `sha256:ee71389be27fa484284a517a324c52a9c827cd20db21f0b306c4dcfd52147aad` |
| 관측 API source | `245d61a5749760a20918ab091d9410ce6735b1c0` |
| 시나리오 | `sensor-validation-v1` · seed42 |
| 결과 | input12 · success7 · failure3 · duplicate2 · pending0 |
| 최종 업무 상태 | `COMPLETED / EXPORTED` · 빈 슬롯 · pending outbox0 |

스테이징은 기존 `--lab-runtime=stage` 분기를 한 번 사용했습니다. 이 분기는 DB 접수와 raw 객체 저장·재조회 확인만 수행하고, named lock이나 Kafka producer/consumer·export 실행기를 만들지 않습니다. 이후 기존 상시 worker가 처리해야 하므로 스테이징 Job의 성공만으로 worker 처리 완료를 인정하지 않았습니다.

검증 전후의 worker 관측 정체성과 runtime 시작 시각이 같았고, 두 시점의 현재 DB owner가 같은 worker에 연결되는 것을 확인했습니다. heartbeat는 전진했고 runtime은 `RUNNING`, 실패·중지 기록은 없었습니다. 이 관측과 아래 신규 결과를 결합해 해당 source의 처리 경로를 확인했습니다. 중간의 모든 순간에 같은 lease 연결이 끊김 없이 유지됐다는 증거는 아닙니다.

## 실제 확인 순서

아래 시각은 모두 2026-10-21 UTC입니다.

| 구간 | 시각 | 의미 |
| --- | --- | --- |
| 호스트 stage 실행기 | `02:02:32.318473` → `02:02:48.995953` | 생성·관측을 포함한 호스트 helper 전체 구간 |
| 처리 후 보존·결과 캡처 | `02:03:24.362514` → `02:03:29.522231` | 완료 후 DB·API·객체·Kafka의 제한된 읽기 검증 |
| 공개 Kafka 기록 | `02:06:41.969676675` 수집 완료 | 별도 공개 관측 snapshot |
| 공개 작업 화면 | `02:07:11` 관측 | 새 작업과 표시 상태 확인 |

stage 구간은 JVM의 실제 처리 시간이나 성능 측정값이 아닙니다. 공개 화면에는 생성 `02:02:43`, 처리 완료 `02:02:45`, export 확정 `02:02:46`이 초 단위로 표시됐습니다. 이 표시 차이를 정밀한 실행 시간이나 처리량으로 계산하지 않습니다.

## 원본과 export의 실제 파일 확인

새 raw 객체는 전체 GET한 bytes를 같은 고정 작업의 DB BLOB 전체 bytes와 비교했습니다. 새 result·failures 두 객체도 전체 GET했고, DB에서 재구성한 기대 size·SHA와 일치했습니다. 문서의 run·scenario·source·시각·counts, 결과12개와 실패3개의 입력·결과 identity도 DB 및 원본과 대조했습니다.

기대 export의 직렬화를 Python으로 새로 구현하지 않았습니다. 기존 읽기 전용 `/api/jobs/observation`이 일관된 DB snapshot에서 `ExportBundle.from`을 호출해 계산한 기대 size·SHA를 사용했습니다. API와 worker의 `ExportBundle`, `CanonicalSource`, `JobObservationService`, `SensorProcessor`, `SyntheticScenario` 생산 소스가 동일한 bytes임을 대조했고, 실제 API와 worker의 서로 다른 pin도 각각 확인했습니다. 기대 metadata만 확인한 결과와 실제 객체 전체를 읽어 대조한 결과를 구분합니다.

[공개 작업 화면](https://devdooly.github.io/devdooly-platform-lab/#job-observation)에서도 새 작업의 기대 result2,380 bytes·failures1,439 bytes, counts12/7/3/2/0, 빈 슬롯을 확인했습니다. 화면의 파일 정보는 DB 기반 기대값이며 그 화면 자체가 새 S3 GET을 수행한 것은 아닙니다. API source245와 runtime source6f55는 구분해 표시됐습니다. UI의 기록만으로 현재 프로세스 생존을 증명하지 않습니다.

## 기존 자료 보존과 Kafka 관측

새 작업을 기존 자료와 분리해, 선택한 기존 업무행·BLOB·시각의 지문과 기존8개 작업의 HTTP projection이 전후 같음을 확인했습니다. 기존24개 객체는 전후 각각 전체 GET하여 크기와 내용 해시를 비교했습니다. 신규 raw·export3개는 별도로 검증했으며, 새 작업이 추가된 전체 DB 지문이 이전과 같다고 주장하지 않습니다. admission 시각은 실제 접수 구간 안에서 전진했고 기존 cooldown30초를 유지했습니다.

같은 Kafka target·partition의 consumer-group CLI 관측에서 committed/end는8/8에서9/9로 전진했고 lag는0이었습니다. 여기의 CLI log end는 READ_COMMITTED LSO로 바꾸어 부르지 않습니다. 별도 공개 Kafka snapshot은 위 수집 시각에 committed9·READ_COMMITTED LSO9·lag0을 표시했습니다. 서로 다른 시각·경로의 관측을 한 번의 원자적 측정으로 합치지 않습니다.

## 자연 관측과 공개 게시

기존 관측 서비스의 `02:18:46~50Z` 실행에서 journal의 `DISPATCHED` 기록을 [Pages run 39532314754](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39532314754)와 연결했습니다. 서비스 시각은 초 단위 표기입니다. 해당 run은 main `9de51a5671becf73af102c8a29db56181c611524`의 첫 시도이며 build는 `02:20:13Z`, deploy는 `02:20:28Z`에 성공했습니다. timer·서비스 수동 시작이나 별도 수동 dispatch는 하지 않았습니다.

앞선 UI 확인과 별도로, `02:24:36~37Z`의 공개 정적 snapshot GET3개가 모두 HTTP200이며 해당 run artifact와 전체 바이트가 같음을 확인했습니다.

| 공개 snapshot | 바이트 | SHA-256 |
| --- | ---: | --- |
| platform | 1355 | `66d46758af77a880ab74eec65795516f7c6582e85bce0df14802dcc1d6b14b2e` |
| jobs | 6474 | `b2626c0f008480de123041452b105af6b5a61ca1f396ca89c0051ec2a026beeb` |
| kafka | 562 | `1678452f64037e18e582a638eb7d86963375daf6f0c1edb243bc029e3f4972a5` |

jobs는 `02:18:48.680068007Z`에 수집된9건으로, 이전 자연 회차의8개 작업 projection을 유지하며 새 작업의12/7/3/2/0·export2380/1439바이트·API245/runtime6f55·빈 slot을 반영했습니다. 별도 Kafka snapshot은 `02:18:49.038774648Z`의 READ_COMMITTED LSO9·commit9·lag0입니다. 한 회차의 수집·게시·공개 GET 대응이며, 수집 이후 현재 worker 생존이나 장기 가용성을 증명하지 않습니다.

## 범위와 정리 결과

고정 합성 입력 한 건이 정상 처리된 근거입니다. 운영 장애를 주입하지 않았으며, Kafka record 본문·일반적인 exactly-once·연속 lease 소유·OOM 복구·HA·전체 SLA·부하 용량을 검증한 결과가 아닙니다. 기존 자료 보존도 선택한 행·객체·관측 범위에 한정됩니다.

완료된 이번 임시 스테이징 Job에 TTL 정리 설정을 한 번 적용했고, `02:15:12.985898Z`까지 해당 Job과 소유 Pod의 부재를 확인했습니다. 뒤이은 별도 읽기 검증에서 선택한 기존·신규 업무자료와 객체가 정리 전과 같고, worker 식별 정보·시작 시각은 유지되며 heartbeat가 전진했음을 확인했습니다. 새 업무 DB·객체·Kafka 자료는 검증 기록으로 보존합니다. 기동 복원·토큰 교체·예산 정책·PR102는 계속 보류합니다.
