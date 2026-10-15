# 최대 합성 입력과 동시 접수 검증

2026-10-15. [`5a1495be4973d43b34dc5c169dbf66bec7459968`](https://github.com/DevDooly/devdooly-platform-lab/commit/5a1495be4973d43b34dc5c169dbf66bec7459968)의 기본 검증 140개·실제 격리 기능 IT 5개를 통과했다. [ADR 0010](../adr/0010-versioned-bounded-input.md)에 따라 V1 12건과 V2 1,000건만 허용한다. [DB 작업 기반 절차](db-job-foundation.md)와 [상시 실행 절차](continuous-runtime.md)의 과거 시험 결과는 당시 범위로 유지한다.

## 코드와 배포 경계

기본 seed와 시나리오 미지정 stage는 `sensor-validation-v1`이다. V2는 `sensor-validation-v2`라는 별도 버전이며 고정 공개 합성 입력 1,000건·성공 500·실패 300·중복 200·대기 0이다. 1~1,000건을 자유롭게 받거나 회사·개인 데이터를 넣는 경로가 아니다.

원본 전체는 UTF-8 NDJSON 1 MiB 이하이고, 지정된 필드 4개·내용·순서를 검증한다. 중복 JSON key·추가 필드·trailing token·알 수 없는 버전·시나리오 불일치를 거부한다. 공백 등 허용된 표현 차이는 원본 bytes와 SHA에 그대로 남긴다. Kafka에는 원본 대신 최대 1,024-byte 포인터를 보낸다. 결과·실패 문서는 각각 4 MiB 이하이고 기존 문서 schema v1을 유지한다.

운영에서 V2를 처음 접수하기 전 API와 worker를 모두 V2 지원 image로 갱신하고 source/digest·schema V3·기존 완료 작업을 확인한다. 이전 image의 V1 호환성과 V2에 대한 전방 호환성을 혼동하지 않는다. 이전 worker는 V2를 처리하지 못하며 이전 API의 작업 export 관측도 V2를 수용하지 못한다. rollback은 저장된 V2 작업·파일·offset과 조회 경계를 검토한 별도 절차다.

## 격리 기능 IT 준비

아래 명령은 이미 준비한 **폐기 가능한 별도 환경**에서만 실행한다. numeric loopback 이름 검사는 운영과 실제로 분리됐다는 확인을 대신하지 않는다. 기존 운영 DB·bucket·topic을 연결하거나 운영 namespace에 이 시험을 배포하지 않는다.

Java 21과 JVM 기본 시간대 `Asia/Seoul`, 전용 MariaDB 11.8.9·Kafka 4.3.1·Garage 2.4.1을 준비한다. 실제 통과한 구성은 Windows Java 드라이버와 Linux Docker backend를 SSH tunnel의 numeric loopback으로 연결했으며, Docker backend는 host published port 없이 별도 project/network/volume을 사용했다. Windows 프로세스의 기능 시험을 Linux worker의 CPU·메모리 성능으로 기록하지 않는다.

| 비공개 환경변수 | 조건 |
| --- | --- |
| `DB_TEST_URL` | 정확히 `jdbc:mariadb://127.0.0.1:<전용 포트>/platform_lab_runtime_it`, query option 없음 |
| `DB_TEST_USERNAME`, `DB_TEST_PASSWORD` | 이 전용 DB의 자격증명 |
| `LAB_S3_TEST_ENDPOINT` | `http://127.0.0.1:<전용 포트>` |
| `LAB_S3_TEST_BUCKET` | `platform-lab-s3-test-` 접두어의 전용 시험 bucket |
| `LAB_S3_TEST_ACCESS_KEY`, `LAB_S3_TEST_SECRET_KEY` | 해당 시험 bucket의 권한만 가진 자격증명 |
| `LAB_KAFKA_TEST_BOOTSTRAP` | `127.0.0.1:<전용 포트>` 한 곳 |
| `LAB_KAFKA_TEST_CLUSTER_ID` | 실제로 확인한 전용 단일 broker cluster ID |
| `SOURCE_COMMIT` | 실행 코드와 대응하는 실제 40자리 Git SHA |

접속정보·credentials·실제 host·완성된 URL은 Git·채팅·공개 artifact·shell tracing에 남기지 않는다. 위 값은 비공개 실행 환경에서 주입한다. Flyway 전에 DB URL guard가 적용되고, 접속 후 실제 MariaDB/catalog와 migration V1/V2/V3·빈 job/outbox/결과 테이블·빈 슬롯·trigger 부재를 확인한다. topic/group과 run ID는 매 시험의 소유 UUID로 만든다.

```sh
cd apps/api
./mvnw -B -ntp -DargLine=-Duser.timezone=Asia/Seoul verify
./mvnw -B -ntp -Dlab.maximum.tests=true \
  -Dtest=MaximumInputConcurrencyIT \
  -DargLine=-Duser.timezone=Asia/Seoul test
```

Windows에서는 `mvnw.cmd`를 사용한다. 기본 verify는 이 실제 IT를 자동 실행하지 않는다. 다른 opt-in IT flag를 함께 설정하거나 같은 schema에서 두 실행기를 동시에 돌리지 않는다. 허용 요약을 비공개 파일로 추가 기록하려면 `-Dlab.maximum.evidence.file=<준비한 비공개 파일 경로>`를 지정한다.

## 실제 통과한 다섯 사례

| 사례 | 확인한 경계 |
| --- | --- |
| 동일 daemon의 최대 입력 3회와 V1 보존 | V1 작업 1개와 정확히 1 MiB인 V2 작업 3개를 별도로 접수. 자동 발행·수신·처리·export 후 각각 슬롯 해제. V1 SQL·시각 보존, 전체 outcome 3,012개·export 8개, Kafka committed 4/log end 4/lag 0 |
| 서로 다른 run 2개 동시 접수 | 1개 승인·1개 슬롯 충돌. 패자의 DB 작업·outbox·원본 없음. 승인 작업 1,000건·export 2개·committed 1/log end 1 |
| 서로 다른 run 8개 동시 접수 | 1개 승인·7개 슬롯 충돌. 같은 DB/S3 무부작용 확인 후 승인 작업 완료·export 2개·committed 1/log end 1 |
| 초과·불일치 거부 | 1,001건·1,048,577 bytes·V1 선언/V2 내용 불일치의 세 호출을 접수 전에 거부. 작업·outbox·결과·원본 없음, 빈 슬롯·Kafka log end 0 |
| 재요청·충돌·후속 슬롯 보존 | 같은 원본 재요청의 기존 행·시각 보존, 다른 hash와 이미 손상된 원본의 자동 덮어쓰기 거부. 완료된 이전 작업의 재요청/export가 다음 작업 슬롯을 해제하지 않음. 이후 두 작업 완료·export 4개·committed 2/log end 2 |

최대 입력 사례는 실제 S3 raw 및 결과/실패 파일을 전체 GET하고 bytes·크기·SHA를 비교했다. 실제 HTTP `GET /api/jobs/observation`의 완료 건수·파일 근거·빈 슬롯도 대조했다. Kafka 포인터 전체를 group 없는 partition 직접 할당 consumer로 읽었으며 auto commit을 끄고 기존 offset 불변을 확인했다. 관측 HTTP 자체가 S3를 재검증한다는 뜻은 아니다.

동시 접수 사례는 worker를 시작하기 전, 승자의 짧은 DB 접수 트랜잭션이 끝난 뒤 외부 저장 경계에서 대기시켜 슬롯 점유를 유지했다. barrier는 DB connection 획득 전에 두므로 기존 pool 5개를 늘리지 않고 8개 호출을 시험한다. worker가 먼저 완료해 슬롯을 푼 경우의 합법적인 후속 승인을 억지로 충돌 처리하지 않는다. 이 결과는 요청률 제한기·공개 HTTP 부하 시험·동시 처리 용량·SLA가 아니다.

손상 원본은 소유 시험 fixture를 명시적으로 복구한 뒤 다음 처리를 확인했다. 애플리케이션이 손상 객체를 자동 복구한 결과로 기록하지 않는다. S3 저장의 조건부 생성·WORM·동일 작업 동시 재시도의 단일 PUT 보장도 포함하지 않는다.

## 정리와 실패 진단

성공한 사례만 소유 UUID의 topic/group·raw/export 객체·DB 행을 정리한다. 다른 슬롯 소유자나 다른 작업이 있으면 정리를 거부한다. migration V1/V2/V3와 singleton은 유지한다. 이 쓰기 정리 코드를 운영 환경에서 실행하지 않는다.

첫 실패에서는 시험이 만든 child process만 종료하고 DB·S3 객체·topic/group은 보존한다. 비공개 임시 디렉터리의 `failure-resources.json`과 child log를 확인하며, 후속 사례는 자동 재시도나 정리 없이 중단한다. 실패를 숨기기 위해 bucket 전체 삭제·offset reset·Flyway clean·임의 resume을 하지 않는다. 원인을 확인한 뒤 소유 자원만 별도 절차로 다룬다.

## 내부 고정 fixture 접수

API/worker의 지원 버전·source·schema·별도 환경을 확인한 관리 절차에서만 사용한다. 기존 [상시 실행 설정](continuous-runtime.md)의 DB/S3 환경과 허용 run ID를 사용하며, 파일·URL·임의 count를 전달하지 않는다.

```sh
export LAB_RUNTIME_STAGE_RUN_ID=lab-fixture-my-v2-check
export LAB_RUNTIME_STAGE_SCENARIO=sensor-validation-v2
java -jar apps/api/target/platform-lab-api-0.1.0.jar --lab-runtime=stage
```

V1 접수에는 `LAB_RUNTIME_STAGE_SCENARIO`를 설정하지 않거나 정확히 `sensor-validation-v1`을 사용한다. 빈 문자열은 기본값으로 취급하지 않는다. stage는 Kafka worker를 시작하거나 영속 `PAUSED_OPERATOR`를 자동 해제하지 않는다. 공개 페이지와 HTTP에는 실행 POST·resume·credentials를 연결하지 않는다.

Linux에서 실제 worker 제한을 적용한 측정과 운영 보존 결과는 [별도 실행 근거](../evidence/input-concurrency-load/README.md)에 기록한다. 이번 기능 IT의 성공 건수로 CPU·메모리 여유·처리량·운영 적용 완료를 추정하지 않는다.
