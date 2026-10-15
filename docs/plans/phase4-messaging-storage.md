# 4단계 준비 조사: Kafka와 원본 객체 보관

최초 조사: 2026-10-12 KST. DB 작업/outbox·단일 슬롯을 격리 MariaDB에서 검증한 뒤, 2026-10-14에는 Garage 2.4.1·Java SDK 2.55.16 원본 adapter를 추가했다. 기본 checksum의 실제 실패와 Garage 전용 설정의 교정, 전체 원본 검증·재시도·컨테이너 재생성 후 Get-only 보존을 확인했다. [DB 기반 근거](../evidence/db-job-foundation/README.md), [S3 검증 근거](../evidence/s3-source-storage/README.md), [선정 ADR](../adr/0005-verified-raw-source-storage.md)을 연결한다. 2026-10-15에는 Kafka 발행·수신·수동 offset과 실제 중단 후 재전달을 격리 검증했다. 기본 78개·실제 IT 4개와 기존 운영 보존 결과는 [Kafka 근거](../evidence/kafka-redelivery/README.md), plain client 선택과 현재 envelope는 [ADR 0006](../adr/0006-explicit-kafka-dispatch.md)을 따른다. 같은 날 결과·실패 파일 export와 두 파일 검증 뒤 슬롯 해제도 구현했고 기본 97개·실제 IT 6개 및 두 JVM 중단 후 회복을 통과했다. [export 근거](../evidence/result-export/README.md), [ADR 0007](../adr/0007-verified-result-export.md)을 연결한다. 같은 날 명시적 상시 실행기·V3 영속 정지/재개·작업/export 관측을 추가하고 기본 120개·실제 IT 4개·웹 34개를 통과했다. [상시 실행/관측 근거](../evidence/continuous-runtime/README.md), [ADR 0008](../adr/0008-continuous-runtime-observation.md)을 연결한다. 이는 격리 검증 당시의 범위다. 이후 사용자 요청으로 미니 PC K3s에 Kafka·Garage·상시 worker를 배포하고 고정 fixture 두 작업·파일 4개 확인·슬롯 해제·Kafka lag 0과 실제 배포 job 관측의 Pages 게시를 확인했다. 현재 결과와 source/image·기존 환경 보존은 [실제 배포 근거](../evidence/runtime-deployment/README.md)를 따른다. 아래 제품 조사는 최초 시점의 기록이며 이후 확정한 조합은 ADR을 따른다.

새 job의 원래 timer 자동 수집·Pages 게시 2회와 공개 JSON 전체의 원본 일치를 확인했다. 서비스 완료 간격은 1개·1809.371239초였으며 [후속 검증 근거](../evidence/runtime-recovery/README.md)는 과거 플랫폼 collector 11회와 구분한다. 공개 화면은 실시간 API가 아니라 약 30분 주기의 기록이며 heartbeat 5분 경고를 별도로 표시한다. 공개 POST는 없고 내부 `--lab-runtime=stage`로 `lab-fixture-` run ID의 고정 12개만 접수한다. 단일 노드·partition 1/RF1이며 최대 1,000개·장기간 운영·고가용성은 검증하지 않았다.

실제 배포 후에는 작업이 없는 worker Pod 하나를 UID 조건·300초 grace로 정상 교체했다. 종료 marker·기존 STOPPED·exit 143과 같은 image/source의 새 RUNNING·restartCount 0·heartbeat 전진을 확인했다. 관측 절차는 17.808초였으며 기존 두 작업의 전체 SQL/시각·파일 4개와 Kafka offset 2·log end 2·lag 0 및 다른 서비스·PVC를 보존했다. [후속 실제 재시작 근거](../evidence/runtime-recovery/README.md)를 연결한다. 최초 격리 crash IT·idle 정상 TERM 교체·아래 전용 PVC 복원·아직 수행하지 않은 진행 중 crash는 각각 다른 범위다. 이후 교체 worker가 새 고정 fixture를 처리해 전체 3작업·파일 6개·offset 3/log end 3/lag 0과 빈 슬롯을 확인했다. 새 파일 2개를 실제 Get·크기·SHA로 검증하고 원래 두 작업의 전체 SQL·시각·파일/HTTP 요약은 보존했다.

이후 Kafka/Garage 전용 PVC 3개를 정상 정지 구간에서 보관하고 AES-256-GCM 외부 사본의 인증·반환 해시를 확인한 뒤 새 namespace/PVC로 복원했다. 전체 file manifest와 Kafka 3 record/offset, Garage 9개 GET을 대조했다. 기존 9개는 모두 metadata inline 객체여서, 별도 clone에만 128KiB canary를 한 번 PUT하고 실제 data 블록 1개를 추가 새 PVC 2개로 복원했다. 대체 Garage Pod 교체 전후 각 GET10과 복제 Kafka 정상 재시작 후 record/offset 보존도 확인했다. [PVC 복원 근거](../evidence/runtime-pvc-restore/README.md), [실행 절차](../runbooks/runtime-pvc-recovery.md)를 연결한다. 원본 객체 쓰기·운영 PVC 덮어쓰기·다중 노드 HA·용량/성능 검증으로 확대하지 않는다.

## 최초 권장 범위

**Apache Kafka JVM 브로커 1개와 Garage 객체 저장소 1개를 우선 후보로 삼는다.** 기존 Java 처리 코드를 재사용하고, 합성 원본의 보관 → Kafka 작업 전달 → MariaDB 결과 저장 → 같은 원본 재처리까지 구현한다. Garage는 필요한 Java SDK 기능을 실제 검증한 뒤 ADR로 확정한다.

새 목표는 기술 이름을 늘리는 일이 아니라 다음 질문에 근거로 답하는 것이다.

- 어떤 원본에서 이 결과가 나왔는가?
- 업무상 중복 입력과 Kafka의 재전달을 어떻게 구분했는가?
- 저장 직후 프로세스가 중단되어도 결과가 두 번 생기지 않는가?
- Kafka 보존 기간이 지난 뒤에도 원본에서 같은 판정을 재현할 수 있는가?

첫 구현에 ZooKeeper, Kafka operator, Schema Registry, Kafka Connect, Debezium, Redis, 별도 Kafka 관리 UI, Spark·Trino·Airflow를 추가하지 않는다. 현재 공개 POST는 계속 비활성화한다. 공개 Pages와 기존 관측 계약은 유지하며, Kafka·S3 연결 완료 표시는 실제 검증 뒤에만 추가한다.

## 최초 조사 당시 코드에서 확인한 출발점

실제 API 경로는 `apps/api/`이다. Java 21·Spring Boot 4.1.1, JPA·Flyway·MariaDB를 사용하며 Kafka·S3 의존성은 없다. `DemoService.ensureSample()`은 최초 시작에 고정 run을 한 번 저장하고, `SensorProcessor.process(List<SensorEvent>)`는 한 묶음을 순서대로 판정한다. 처리기의 중복 ID 집합과 센서별 마지막 성공 시각은 호출 안의 메모리 상태다.

독립 시나리오 `tests/scenarios/sensor-validation-v1.json`의 기준은 **입력 12 = 성공 7 + 실패 3 + 업무상 중복 2 + 대기 0**이다. 실패 이유는 잘못된 시각, 센서별 역순 시각, 범위 초과다. 구조가 유효한 이벤트 ID는 시간 검증에 실패해도 사용된 ID로 취급하며, 실패 입력은 센서 watermark를 앞으로 옮기지 않는다. 같은 Instant는 허용한다. 기존 단위 테스트가 이 차이를 확인한다.

Flyway V1에는 `(run_id, input_sequence)` unique 제약과 전체 건수 CHECK가 이미 있다. 그러나 `existsById()` 확인만으로 다중 worker의 원자적 작업 선점까지 보장하지는 않는다. 현재 `COMPLETED` 고정 응답과 `completed_at NOT NULL`도 비동기 진행 상태에는 그대로 쓸 수 없다. 비동기 작업 상태는 별도 작은 테이블로 관리하고, 완료된 결과만 기존 결과 테이블에 원자적으로 저장하는 쪽이 변경 범위가 작다. `DemoRun` 생성자의 고정 run ID·seed·scenario와 detail의 고정 설명도 새 작업 메타데이터를 받도록 분리해야 하며, 기존 seed 샘플의 동작은 유지한다.

참고한 로컬 자료: `AGENTS.md`, `README.md`, `docs/START_HERE.md`, `docs/ROADMAP.md`, `apps/api/README.md`, `apps/api/pom.xml`, `SensorProcessor.java`, `DemoService.java`, `DemoRun.java`, `SyntheticScenario.java`, `V1__create_demo_evidence.sql`, `SensorProcessorTest.java`, `ApiIntegrationTest.java`, `infra/charts/platform-lab/values.yaml`, 합성 시나리오와 안내.

## 첫 구현에서 유지할 계약

첫 수정은 Kafka·S3 연결에 앞서 원본 schema·작업/outbox·DB 멱등 경계를 격리 환경에서 구현하는 범위로 잡는다. 기존 Flyway `V1__create_demo_evidence.sql`과 seed 결과 행·처리 시각을 보존하고, 새 작업/outbox와 전체 실행 슬롯은 **V2 migration**으로 추가한다. 미리 생성한 singleton 슬롯 행의 DB 잠금과 작업 고유 키로 동시 작업 1개를 보장하며, `existsById()`나 프로세스 내 변수만으로 제한하지 않는다.

`GET /api/demo/runs`와 상세 조회는 완료된 결과 계약을 유지한다. 진행 중 작업은 향후 별도 job 조회 계약으로 분리한다. 이번 foundation에는 job HTTP 조회를 추가하지 않았다. 기존 웹의 `isRun()`은 유효한 `completedAt`을 요구하며, `lab-observation v1`은 `synthetic-v1-seed-42`·seed 42·12/7/3/2/0과 입력별 판정을 고정 검증한다. 새 비동기 작업을 이 정적 샘플 관측본에 넣거나 nullable 완료 시각을 기존 run 응답에 섞지 않는다. 별도 job 관측 계약을 만들고, 기존 고정 샘플 조회·`lab-observation v1`·`platform-observation v1`을 유지한다. 공개 POST는 계속 제공하지 않는다.

최초 조사 당시 `SampleBootstrap`은 모든 profile에서 실행됐다. 이번 foundation은 `worker`·`admin` profile에서 자동 bootstrap을 제외했고, `DemoRun`에 별도 작업 메타데이터 생성 경로와 공유 결과 저장 경로를 추가해 기존 seed 경로를 유지했다. 현재 작업도 같은 고정 시나리오이므로 detail 설명은 유지한다. foundation 당시에는 실행기와 migration 주체 설정이 후속이었다. 이후 명시적 runtime 명령은 worker profile·비웹 실행·Flyway 비활성화·사전 V3 확인을 강제했고 내부 고정 fixture stage 명령을 추가했다. 기본 API는 migration을 적용하지만 worker/profile 선택만으로 자동 실행기를 만들지는 않는다. 범용 시나리오 설명 분리는 후속이다.

잠금·트랜잭션의 합격 근거는 **실제 MariaDB 격리 검증**으로 남긴다. 동시 제출 2개, 같은 run+같은 hash 재요청, 같은 run+다른 hash 거부, 결과 commit 전 rollback, commit 뒤 같은 작업 재전달에서 DB 효과 1회와 기존 완료 시각·seed 전체 행 보존을 확인한다. H2 결과만으로 MariaDB 동시성·잠금까지 검증했다고 기록하지 않는다. 이번 foundation에서 기존 V1 업그레이드·빈 DB 초기화·반복 시작 조건 각각의 실제 MariaDB 17개 검증을 통과했다. 비UTC JVM 완료 시각 일치와 이전 image 호환성도 확인했다. [실제 결과와 검증 실패·교정 기록](../evidence/db-job-foundation/README.md)을 연결한다. 이후 실제 MariaDB·Garage 결합의 rollback·원본 보존과 Kafka 발행·수신·offset 중단 후 재전달을 별도 격리 검증했다. [결합 근거](../evidence/mariadb-s3/README.md), [Kafka 근거](../evidence/kafka-redelivery/README.md)를 연결한다. 결과 export·상시 실행기와 실제 운영 배포는 이후 단계의 [현재 근거](../evidence/runtime-deployment/README.md)로 구분한다.

## 제품과 공식 배포 상태

아래는 조사일의 공개 자료 확인 결과다. 릴리스 활동 확인과 장기 지원 보장은 구분한다.

| 후보 | 확인한 릴리스·유지보수 상태 | 라이선스·공식 배포 경로 | 이번 판단 |
| --- | --- | --- | --- |
| Apache Kafka | 공식 supported 목록은 4.3.1·4.2.2·4.1.2. 최고 버전 4.3.1은 2026-06-25, 날짜상 가장 최근 patch 4.2.2는 2026-09-29 | Apache-2.0. 프로젝트가 공식 JVM 이미지 `apache/kafka:4.3.1`을 연결한다 | 4.3.1 JVM을 잠정 기준으로 잡고 현재 Boot BOM의 client와 실제 통합 검증 후 고정 |
| Garage | 공식 release builds 최상단 v2.4.1, 2026-09-08. 공식 문서에 해당 태그의 단일 노드 구성이 있다 | AGPLv3. 프로젝트 공식 문서가 `dxflrs/garage:v2.4.1`과 Docker Hub를 연결한다 | 단순 원본 Put/Get 중심의 우선 후보. SDK 호환성·재시작·보존 검증 전 확정하지 않음 |
| SeaweedFS | 프로젝트 latest release는 4.48. 현재 공개 변경 기록에서 개발 활동 확인 | Apache-2.0. 프로젝트 README가 `chrislusf/seaweedfs` 이미지를 안내한다 | Garage 기능 검증이 실패하거나 Apache-2.0 요구가 생기면 비교할 2순위. 동시 설치하지 않음 |
| MinIO community | 공식 GitHub 저장소가 **2026-04-25 archive / read-only**. latest release 링크는 `RELEASE.2025-10-15T17-29-55Z` | AGPLv3. 현재 README는 community source-only, 사전 빌드 binary 미제공, 과거 binary 미유지보수를 명시 | 새 Lab의 기본 설치 후보에서 제외. 기존 실무 MinIO 경험과 별개로 현재 신규 운영 판단을 기록 |

Kafka 근거: [공식 다운로드·supported 목록](https://kafka.apache.org/community/downloads/), [프로젝트 LICENSE](https://github.com/apache/kafka/blob/trunk/LICENSE), [공식 이미지 태그 화면](https://hub.docker.com/layers/apache/kafka/4.3.1).

Garage 근거: [공식 release builds](https://garagehq.deuxfleurs.fr/_releases.html), [단일 노드·컨테이너 안내](https://garagehq.deuxfleurs.fr/documentation/quick-start/), [v2.4.1 LICENSE](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/LICENSE), [프로젝트가 연결한 이미지 저장소](https://hub.docker.com/r/dxflrs/garage).

SeaweedFS 근거: [4.48 release](https://github.com/seaweedfs/seaweedfs/releases/tag/4.48), [프로젝트 README의 라이선스·Docker·단일 노드 안내](https://github.com/seaweedfs/seaweedfs).

MinIO 근거: [공식 저장소의 archive 표시·현재 README](https://github.com/minio/minio), [latest release가 연결한 태그](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z). community 저장소의 상태만 확인했으며, 상용 AIStor까지 유지보수가 끝났다는 뜻으로 확대하지 않는다. 과거 README의 지원 문구나 남아 있는 이미지 태그만으로 현재 community 보안 업데이트를 보장하지 않는다.

여기서 공식 이미지란 프로젝트가 직접 안내한 배포 경로라는 뜻이다. Docker Official Image 프로그램 참여와 같은 의미로 사용하지 않는다. Garage·SeaweedFS의 버전 태그에 대한 registry manifest 조회는 이번 조사에서 완료하지 못했다. Kafka의 Hub 화면에서 digest가 보이지만 배포 pin으로 복사하지 않았으며, 구현 시 registry에서 index와 linux/amd64 manifest를 새로 조회해 대조하고 digest로 고정한다. 태그 확인만으로 pull·기동 검증을 완료 처리하지 않는다.

## Garage를 우선 확인할 이유와 한계

Garage 공식 문서는 의존성 없는 단일 binary와 단일 노드 구성을 안내한다. 공식 사이트의 요구량은 RAM 1 GB, 디스크 최소 16 GB이므로 아주 작은 메모리 한도로 억지 배치하지 않는다. 단일 노드 모드는 복제하지 않는다. 또한 quick start의 임시 경로·volume 없는 예제는 그대로 운영 구성에 옮기지 않고 metadata와 object data를 모두 영속화한다. [요구량](https://garagehq.deuxfleurs.fr/), [단일 노드·영속 경로 주의](https://garagehq.deuxfleurs.fr/documentation/quick-start/).

필요한 것은 S3의 일부 기능이다. 공식 호환 표에는 SigV4·path-style, PutObject·GetObject·HeadObject·ListObjectsV2·DeleteObject가 구현으로 표시된다. 반면 versioning 미지원과 lifecycle 일부 구현이 명시되어 있어 이를 전제로 한 불변 보관·자동 만료를 주장하지 않는다. 실제 고정 버전과 SDK 조합에서 다시 시험한다. [Garage S3 호환 표](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/).

SeaweedFS도 한 프로세스의 `weed mini` 구성이 있지만 내부에 master·volume·filer 등 여러 역할이 있다. 단일 프로세스라는 이유만으로 운영 요소가 더 적다고 단정하지 않는다. 이번 목표에는 두 저장소를 동시에 비교 운영할 필요가 없다. [프로젝트 단일 노드 설명](https://github.com/seaweedfs/seaweedfs).

## 가장 작은 처리 흐름

첫 버전은 **한 run의 원본 묶음 하나를 Kafka 작업 메시지 하나로 전달**한다. 12개 입력을 Kafka 메시지 12개로 나누면 현재 처리기의 `seen`·watermark를 영속 상태로 재설계해야 한다. 묶음 단위는 현재 판정 규칙을 재사용하면서 저장·전달 경계의 장애를 먼저 증명할 수 있다.

1. 관리자 전용 1회 실행 경로에서 허용한 합성 시나리오와 run ID를 만든다. JSON/NDJSON 원본은 입력 순번을 유지하고 잘못된 시각과 중복 ID까지 그대로 포함한다.
2. MariaDB에 `runId + payloadSha256 + scenarioVersion`을 갖는 작업을 `STAGING`으로 등록한다. 같은 run ID에 다른 hash가 들어오면 거부한다. 전체 진행 작업은 DB 제약·잠금으로 1개만 허용한다.
3. 전용 비공개 bucket에 원본을 Put하고, Get으로 읽어 SHA-256과 입력 수를 확인한다. 성공한 뒤 DB 트랜잭션에서 작업을 `QUEUED`로 바꾸고 outbox 행을 함께 등록한다. S3 실패 때 완료·접수 성공이나 Kafka 발행 성공으로 기록하지 않는다.
4. 최초 계획은 원본 object key·hash·입력 수·scenarioVersion·run ID 전달이었으나, 실제 구현은 [ADR 0006](../adr/0006-explicit-kafka-dispatch.md)에 따라 schemaVersion·run ID·scenarioVersion·sourceSha256 네 필드만 보낸다. object key·입력 수는 불변 DB 작업에서 대조한다. 격리 시험은 UUID 전용 topic을 사용했고 실제 배포 topic은 `platform-lab-dispatch-v1`로 명시 생성했다. partition 1, key run ID, consumer 1로 시작한다. 발행 ACK 뒤 outbox 표시 전에 중단되면 같은 작업이 재전달될 수 있게 설계한다.
5. worker는 DB의 고유 run과 row lock으로 선점하고, S3 원본 hash를 검증한 뒤 기존 `SensorProcessor`로 전체 묶음을 판정한다. 결과와 12개 outcome, 작업 완료 상태를 같은 DB 트랜잭션으로 저장한다. 그 뒤 Kafka offset을 commit한다.
6. 이미 완료된 run의 재전달은 hash를 대조하고 결과를 추가하지 않는다. 저장 당시 처리 시각도 덮어쓰지 않는다. Kafka 전달 횟수와 재전달 억제 횟수는 업무상 중복 2건과 다른 항목으로 기록한다.
7. 결과 JSON과 실패 입력·실패 이유 JSON은 DB 완료 후 별도 export outbox로 S3에 저장한다. 연산 완료와 export 상태를 분리하고, export 장애를 연산 실패로 바꾸지 않고 `RESULT_EXPORT_PENDING`으로 드러낸다. 같은 hash·결과 버전의 결정적 key로 재시도하고, 실제 export 확인 뒤에만 결과 파일 보관 완료로 표시한다. **최초 정책은 결과·실패 파일의 export 완료까지 전체 실행 슬롯을 보유**한다. export 대기·운영자 정지 중에는 후속 작업을 받지 않아 미완료 작업 누적을 억제한다. 복구 불가능한 작업의 슬롯 해제는 원본·결과 보존을 확인한 명시적 운영자 종료 절차에서만 수행한다.

새로 필요한 것은 작은 작업/outbox 테이블과 producer·consumer 코드다. outbox용 별도 제품은 없다. 최초 producer는 현재 Java image의 관리자 전용 일회 실행 기능으로, worker는 같은 처리 코드를 쓰는 별도 profile의 Pod 1개로 두면 조회 API와 장애 시험을 분리할 수 있다. API의 기존 자동 sample bootstrap을 worker profile에서 실행하지 않도록 구분한다. 기존 완료 샘플을 새 작업의 결과처럼 재사용하지 않는다.

S3 object key 예시는 `raw/{runId}/{sha256}.ndjson`, `results/{runId}/{processorVersion}/{sha256}.json`이다. 이는 애플리케이션의 덮어쓰기 방지 규칙이며 S3 Object Lock/WORM 보장을 뜻하지 않는다. ETag를 SHA-256이나 항상 MD5라고 가정하지 않는다. 동시 writer는 최초 범위에서 허용하지 않으며, 자격증명도 단일 Lab bucket의 필요한 권한만 부여한다.

Kafka idempotent producer와 ACK 설정은 사용하되 **Kafka·MariaDB·S3 전체에 대한 exactly-once**라고 표현하지 않는다. 목표는 at-least-once 전달을 받아도 DB 효과가 한 번만 생기는 멱등 처리다. 장애 직후 S3와 DB 사이에 남은 미완료 작업은 STAGING 상태와 원본 hash로 복구하거나, 보존 정책에 따라 정리할 수 있어야 한다.

한 작업 안의 12개 이벤트 순서·역순 판정과 Kafka 작업 재전달을 확인하는 버전이다. 이벤트별 Kafka ordering·watermark 복구까지 검증했다고 주장하지 않는다. 그 증명이 필요해지면 다음 작은 확장에서 run ID key의 이벤트별 메시지와 영속 seen-ID·watermark를 추가하고, `(run_id, input_sequence)` 기준의 전달 멱등을 별도로 검증한다.

## 구현 전 Java S3 호환성 관문

AWS SDK for Java v2의 S3 client 하나로 아래를 확인한다. endpointOverride와 region을 명시하고 path-style·SigV4를 사용한다. SDK/BOM 버전은 구현 시 공식 릴리스를 확인해 고정한다. 최초 조사에서는 `spring-boot-starter-kafka`를 검토했으나 실제 구현은 [ADR 0006](../adr/0006-explicit-kafka-dispatch.md)에 따라 자동 listener 없이 plain `kafka-clients`를 Boot BOM으로 관리한다. 브로커와 client 버전을 같은 숫자로 억지 고정하지 않는다. [Spring Kafka 의존성 안내](https://docs.spring.io/spring-kafka/reference/quick-tour.html), [AWS Java v2 endpoint·region 안내](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/endpoint-config.html).

| 시험 | 합격 기준 |
| --- | --- |
| Put → Head → Get | UTF-8 원본 byte와 SHA-256, content length·metadata가 일치 |
| ListObjectsV2 | 전용 prefix와 pagination으로 같은 시험 object를 빠짐없이 확인 |
| 인증 실패·권한 경계 | 잘못된 key는 거부, 다른 bucket 접근은 거부, 원본·오류에 비밀값 출력 없음 |
| 같은 run의 재시도 | 같은 hash는 같은 결과, 다른 hash는 명시적으로 거부 |
| timeout·중단 | 제한 시간과 재시도 횟수가 유한하며 STAGING/PENDING 상태로 설명 가능 |
| 저장소 Pod 재생성 | 영속 metadata와 object data에서 같은 원본·hash를 다시 조회 |
| Delete와 보존 | 시험 prefix만 삭제 가능, 보존 중 원본·실패 파일은 정리 대상에서 제외 |

최초 원본 묶음은 1 MiB 이하로 제한하여 단일 Put을 쓴다. multipart·presigned URL·bucket versioning·Object Lock·브라우저 직접 업로드는 최초 요구에 포함하지 않는다. 기본 SDK checksum/header 동작은 실제 후보와 시험하며, 호환성 문제를 자격증명·TLS 검증의 전역 해제로 회피하지 않는다.

## 단일 미니 PC 자원과 보존

최초 조사 조건은 RAM 32 GiB 단일 노드와 실행 중인 기존 Docker 컨테이너 23개였다. 아래는 **미측정 초기 제안값**으로, 신규 구성의 실사용량이나 처리 성능 수치가 아니다. 뒤의 자원 사전 점검은 현재 여유를 한 시점에 관측한 결과이며 이 제안 예산의 부하 검증이나 자원 예약을 뜻하지 않는다.

| 추가 구성 | 초기 CPU request / limit 제안 | 메모리 request / limit 제안 | 영속 디스크 제안 |
| --- | --- | --- | --- |
| Kafka broker+controller 1개 | 500m / 2 | 1 GiB / 2 GiB, JVM heap 512 MiB부터 확인 | 8 GiB, KRaft metadata·로그 모두 영속 |
| Garage 1개 | 250m / 1 | 1 GiB / 1536 MiB | 총 20 GiB, data·metadata 모두 영속 |
| Java worker 1개 | 100m / 1 | 256 MiB / 768 MiB | DB·S3 재사용 |

추가 Pod의 메모리 limit 합계는 약 4.25 GiB다. CPU·heap·page cache 사용은 12건과 1,000건 실험에서 조정한다. Kafka의 단일 combined KRaft는 개발 환경용이며 고가용성 구성이 아니다. 단일 디스크의 Kafka RF1·Garage 복제 없는 운영은 호스트·디스크 장애를 견디는 복제나 외부 백업을 대신하지 않는다. [Kafka combined mode 범위](https://kafka.apache.org/43/operations/kraft/).

2026-10-12 10:37:36 KST의 [읽기 전용 자원 사전 점검](../evidence/messaging-storage/README.md)에서 available memory `20,781,006,848` bytes(약 19.35 GiB), Lab 파일시스템 여유 `244,923,068,416` bytes(약 228.10 GiB)를 확인했다. Docker는 전체 35개 중 실행 23개·재시작 중 0개, Kubernetes는 Pod 11개·Ready node 1개였다. available memory 6 GiB·해당 파일시스템 여유 40 GiB의 **잠정 관문은 그 시점에 통과**했다. peak 부하·지속 여유·신규 Pod 스케줄링과 PV 용량 예약은 확인하지 않았다. 이 점검에서 서비스는 설치하지 않았고 Kafka·Garage·SDK 조합은 여전히 미확정이다. 허용 필드만 공개한 [원본 수치 요약](../evidence/messaging-storage/preflight.json)을 연결한다.

실제 설치 직전 기존 서비스·노드 사용량, available memory, inode·파일시스템 여유와 PV 실사용량을 다시 확인한다. 잠정 관문보다 부족하면 축소 설치 대신 구축을 보류하고 예산부터 다시 정한다. 과거의 200 GB나 이번 한 시점의 여유를 설치 시점 여유로 간주하지 않는다. Jenkins build·백업·큰 이미지 빌드와 장애 실험을 겹치지 않는다.

- Lab 전용 리소스와 새 PV 경로만 추가하고 기존 Docker daemon·볼륨·프록시·방화벽 설정은 유지한다. Kafka/S3는 ClusterIP로만 연결하며 외부 포트·Ingress·NodePort는 만들지 않는다.
- Kafka topic은 partition 1·RF1로 명시 생성한다. 짧은 실습 보존 시간과 per-partition byte 상한·segment 크기를 고정하고, 비동기 정리 때문에 실제 디스크를 감시한다. 보존 만료 전 완료되지 않은 작업은 원본을 기준으로 복구할 수 있어야 한다.
- 제안 보존 정책은 완료 raw·결과·실패 파일 7일, 공개할 검증 증거의 hash·요약은 별도 보존이다. 미완료·재처리 중 원본은 삭제하지 않는다. 첫 정리 작업은 dry-run 목록을 확인하고 전용 prefix만 대상으로 한다. Garage lifecycle 전체 지원을 전제로 자동 삭제하지 않는다.
- 전체 동시 실행 1개, 최대 이벤트 1,000개, 원본 1 MiB, 제한 시간·유한 재시도를 DB 작업 상태와 함께 검증한다. 처음에는 12개 fixture만 허용한다.
- PV 재생성·namespace 삭제가 복구 수단이 되지 않도록 retain/백업 범위를 검토하고, 새 Kafka·S3 데이터도 외부 백업 범위와 복원 시험에 추가한다.

## 보여줄 검증 시나리오

아래는 최초 계획의 합격 조건이다. 이후 격리 환경에서 통과한 DB/S3·Kafka·결과 export 범위는 상단의 실제 근거를 따른다. 별도 원본 replay·최대 1,000개·운영 Pod 재생성 등은 완료 표시하지 않는다.

| 상황 | 반드시 남길 근거 |
| --- | --- |
| 고정 seed 42 첫 처리 | 원본 12개·hash, 독립 기대 판정 12개와 일치, 7/3/2/0, DB outcome 12개 |
| 같은 작업 두 번 발행 | Kafka 전달 횟수는 증가 가능, DB run 1개·outcome 12개·완료 시각 동일, 업무중복은 계속 2 |
| DB commit 직후·offset commit 전 worker 중단 | 재전달 후 결과 수·전체 행·기존 처리 시각 동일, 누락 없음, 실제 offset 전후 |
| 결과 DB commit 전 worker 중단 | 부분 완료 행 없음, 같은 원본에서 회복 후 12개 판정 일치 |
| Kafka ACK 뒤 outbox 표시 전 중단 | outbox 재발행은 발생해도 결과 중복 없음 |
| 원본 Put 실패 / 원본 hash 불일치 | 완료 처리·잘못된 결과 없음, 작업 상태와 고정 오류 코드, 비밀값 없는 실패 요약 |
| Kafka 잠시 불가 | 원본·DB queued/outbox 유지, 복구 뒤 처리, 무제한 busy retry 없음 |
| S3 결과 export 실패 | DB 결과·처리 시각 보존, export pending 동안 실행 슬롯 보유·후속 작업 거부, 회복 후 결과·실패 파일 hash 일치와 슬롯 해제 |
| Kafka·S3 Pod 재생성 | 기존 PV 보존, 원본 Get hash·작업 결과·broker 기록을 다시 확인 |
| 원본에서 별도 재처리 | 새 run에 `replayOf` 기록, 원본 hash 동일, 시간·ID를 제외한 판정 12개 동일; 기존 run 결과 불변 |
| 1,000개·동시 2회 요청·상한 초과 | 허용 작업 1개, 초과 거부, 입력 회계식 유지, export 완료 또는 보존 확인한 명시적 운영자 종료 때만 슬롯 해제 |
| 기존 환경 보존 | Docker 23개 identity·start time·mount, DB/PVC·공개 Pages와 마지막 관측 기록 보존 |

업무상 FAILED 3개는 영구 입력 오류로 결과에 기록하며 Kafka 재시도하지 않는다. S3·DB·broker의 일시 장애는 작업 단위의 유한 재시도 대상으로 구분한다. 반복 인프라 오류는 `PAUSED_OPERATOR` 등 고정 상태로 남기고 자동 재시도를 멈춘다. 첫 버전은 전체 작업 1개여서 해당 작업이 정지하면 후속 작업도 대기하는 한계를 공개한다. 실패 raw를 임의 삭제하거나 실패 이벤트를 성공 건수에 포함하지 않는다.

lag는 묶음 작업 메시지 수이며 센서 입력 건수가 아니다. 화면에 입력 회계식, 업무중복 수, Kafka 재전달 억제 수, 작업 상태와 lag 단위를 각각 표시한다. 묶음 단위 원자적 저장 전에는 전체 입력을 대기로, 완료 후에는 기존 처리기의 판정 합계로 설명한다. 큐에 넣지 못한 접수 오류는 작업 오류로 표시하며 정상 완료 결과로 보이지 않게 한다. 종료 처리 시간·CPU·RSS·디스크·lag는 실제 관측 시각·source SHA·image digest·시나리오 hash와 함께 남기며 성능 개선율은 비교 실험 전 작성하지 않는다.

## 3단계 이후 실행 순서

1. 3단계의 outbound 게시·실제 공개 화면·실패 보존·중단 후 회복 근거를 현재 검증 문서와 일치시킨다. 정적 관측과 실시간 연결을 계속 구분한다.
2. 로컬/격리 CI에서 원본 schema·V2 작업/outbox·singleton 실행 슬롯·멱등 키·보존 정책을 먼저 확정한다. 실제 MariaDB에서 잠금·동시 제출·rollback·재전달을 검증하고, 기존 V1·seed 전체 행과 처리 시각·12개 판정·read-only API를 보존한다. bootstrap/profile을 구분하고 새 job 조회/관측 계약을 기존 고정 샘플 계약과 분리한다.
3. Garage Java SDK 관문을 통과한 뒤 S3 선정 ADR을 작성한다. 고정 Kafka image/client 조합, 저장소 image, 태그·digest·라이선스와 필요한 권한을 기록한다.
4. 읽기 전용 자원 재점검과 새 볼륨·백업 범위를 확정하고, 기존 Helm/GitOps 흐름으로 새 Lab 전용 구성을 배포한다. 최초 준비 조사에서는 설치하지 않았고, 이후 명시적 사용자 요청에 따라 실제 K3s 배포·기존 환경 보존을 별도로 검증했다.
5. 12건 정상 → 재전달 → 각 장애 경계 → 재시작 → 원본 replay → 1,000건 제한 순서로 한 번씩 검증한다. 실제 실패와 회복을 포함한 근거만 공개한다.
6. 정적 관측에 허용한 처리 요약·실측 시각·출처만 추가한다. 비공개 endpoint·관리 주소·credentials·Pod 이름·raw error를 public JSON에 넣지 않는다. 기존 platform-observation v1에 임의 필드를 끼우지 않고 별도 계약으로 추가한다.
7. 공개 실행은 모든 상한·동시성·인증/빈도 제한·중단/정리 시험 후 별도 판단한다. 4단계 원본·재처리 증명을 위해 공개 POST를 먼저 열 필요는 없다.

완료 시 이력서·포트폴리오에는 실제 확인한 범위인 Kafka 비동기 작업, 원본 보관, DB 멱등 처리와 장애 후 재처리 근거를 연결한다. 단일 노드 실습을 실무 대용량 처리나 고가용성 구축 성과로 바꾸어 적지 않는다.
