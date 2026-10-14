# S3 원본 보관 adapter의 격리 검증

공개 합성 원본을 Garage에 보관하고 전체 bytes·크기·SHA-256을 확인한 뒤 DB 작업을 `QUEUED`로 바꾸는 내부 연결을 검증한다. [ADR 0005](../adr/0005-verified-raw-source-storage.md)에 따라 한정 채택했다. 기본 verify 54개, 호환성 교정 후 실제 SDK 4개와 재생성 전후 각 1개가 통과했다. [실제 실행 근거](../evidence/s3-source-storage/README.md)에 첫 실패와 후속 결과를 구분했다.

## 범위와 실행 전 조건

구현은 `apps/api/src/main/java/io/github/devdooly/platformlab/jobs/`의 `RawSourceStore`, `S3RawSourceStore`, `S3ClientFactory`, `SourceStagingService`다. Java 21과 AWS SDK v2 2.55.16을 사용한다. 기본 앱에 S3 bean·controller·스케줄러는 추가하지 않았고 공개 POST 405와 기존 조회·관측 계약을 유지한다.

원본은 `sensor-validation-v1`의 순서가 고정된 12개 입력, 최대 1 MiB다. 표현이 달라 bytes가 바뀌면 hash도 달라진다. 회사 자료와 운영 bucket·DB·credentials는 시험에 사용하지 않는다. S3로부터 worker가 원본을 가져와 처리하거나 Kafka에 메시지를 보내는 기능은 이 절차에 포함하지 않는다.

Lab 관리자가 폐기 가능한 Garage와 전용 bucket·key를 준비한 후 Java 검증은 일반 사용자로 실행한다. Java에 호스트 root·운영 kubeconfig·DB root·Garage 관리 토큰을 넘기지 않는다. 준비 범위는 전용 컨테이너·내부 network·metadata/data 볼륨·시험 bucket·read/write access key다. 기존 서비스를 재설치하거나 운영 Helm을 적용하지 않는다.

Garage의 [공식 단일 노드 안내](https://garagehq.deuxfleurs.fr/documentation/quick-start/)와 [설정 설명](https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/)을 따른다. 이 실험은 RF1·sqlite이며 두 저장 경로를 모두 보존한다. CPU 1개·메모리 1.5 GiB로 제한하고 Docker published port는 만들지 않는다. 원격 Docker 내부 S3에 기존 SSH의 숫자 loopback 터널로 연결한다. 터널 종료 시 시험 연결도 종료된다.

이미지는 다음 linux/amd64 manifest로 고정한다. pull 결과의 config ID도 [ADR의 식별값](../adr/0005-verified-raw-source-storage.md)과 대조한다.

```text
dxflrs/garage@sha256:0d7c74fc8ca6fef68a5a941c0e7558c8b1e92ba3588fa7505400e1350456c796
```

## 전용 시험 환경

`GarageRawSourceIT`는 이미 준비한 bucket에만 접속하며 bucket을 생성·삭제하지 않는다. 다음 환경변수 이름이 모두 필요하다.

| 환경변수 | 조건 |
| --- | --- |
| `LAB_S3_TEST_ENDPOINT` | `http://127.0.0.1:<전용 숫자 포트>`. 포트는 1~65535이며 SSH tunnel이 연결된 상태여야 한다. |
| `LAB_S3_TEST_BUCKET` | `platform-lab-s3-test-` 접두어와 소문자·숫자·하이픈의 전용 시험 이름 |
| `LAB_S3_TEST_ACCESS_KEY` | 해당 시험 bucket의 전용 access key |
| `LAB_S3_TEST_SECRET_KEY` | 해당 key의 secret |

credentials·로그·컨테이너명·실제 접속정보는 Git에서 제외한 비공개 디렉터리에 둔다. 아래 `.local/.private/s3-source-storage/`는 예시 경로다. 디렉터리는 `0700`, 환경 파일·원본 로그는 `0600`으로 관리하며 비밀값을 출력하지 않는다. 접두어와 loopback 검사는 운영 자원 실행 허가를 대신하지 않는다.

준비한 환경 파일에는 위 네 변수만 설정한다. Bash에서 `apps/api`를 기준으로 다음처럼 읽을 수 있다. 파일은 신뢰하는 본인 자료여야 하며 내용을 CI artifact나 채팅으로 옮기지 않는다.

```sh
set +x
set -a
. ../../.local/.private/s3-source-storage/test.env
set +a
: "${LAB_S3_TEST_ENDPOINT:?전용 loopback endpoint 필요}"
: "${LAB_S3_TEST_BUCKET:?전용 시험 bucket 필요}"
: "${LAB_S3_TEST_ACCESS_KEY:?전용 access key 필요}"
: "${LAB_S3_TEST_SECRET_KEY:?전용 secret 필요}"
```

## 기본 검증과 실제 Garage 시험

Java 21의 `apps/api`에서 기본 검증을 실행한다. Windows는 `mvnw.cmd`를 사용한다.

```sh
./mvnw -B -ntp verify
```

기본 verify는 외부 Garage를 자동으로 시작하거나 `GarageRawSourceIT`를 선택하지 않는다. mock S3 검증은 전체 bytes·선언 길이·hash·상한·권한 오류와 정확한 `404 / NoSuchKey` 구분을 검사한다. H2 통합 검증은 외부 I/O 동안 DB 트랜잭션이 없는지, 실패 시 `STAGING`·슬롯을 보존하는지, 동일 재요청의 시각·outbox가 유지되는지 확인한다. 기본 context에서 S3 client·adapter·coordinator bean이 모두 0개인지도 확인한다.

전용 환경이 준비된 상태에서 실제 Garage 시험을 명시적으로 선택한다.

```sh
./mvnw -B -ntp -Dlab.s3.tests=true -Dtest=GarageRawSourceIT test
```

이 클래스는 S3에는 실제 SDK로 접속하고 DB에는 전용 H2 `garage_raw_source_it`를 사용한다. 해당 결과를 실제 MariaDB+S3 결합 시험으로 기록하지 않는다. persistence 옵션이 없으면 아래 4개 시험을 실행하고 재생성 표식 시험은 건너뛴다.

| 실제 시험 | 확인할 내용 |
| --- | --- |
| `realSdkPutGetHeadListDeleteAndStoreRetryVerifyActualBytes` | Put·Get·Head·전용 prefix ListObjectsV2·Delete와 같은 원본 재검증 |
| `realCoordinatorStagesAndRepeatPreservesQueuedAndCompletedMetadata` | 외부 원본을 검증한 QUEUED 전환, 동일 요청·완료 후 요청의 DB 시각·outbox 보존 |
| `realExistingCorruptionIsRetainedAndDbRemainsStagingWithoutDispatch` | 같은 크기의 손상 객체를 덮어쓰지 않음, STAGING·슬롯·dispatch 부재 보존 |
| `realObjectSurvivesFailedDbMarkAndIsReverifiedOnRetry` | 원본 Get 검증 뒤 mark 호출 진입 전 오류 주입, 객체 보존과 동일 요청 재검증 |

시험은 `s3-it-<UUID>` run별 prefix와 자신이 등록한 key만 정리한다. 테스트가 의도적으로 만든 손상 객체는 시험 코드가 지운 후 재시도하며 adapter가 자동 삭제하는 동작은 아니다. H2의 해당 run 행과 슬롯도 정리한다. bucket 전체 삭제·다른 prefix 정리·운영 DB 정리는 수행하지 않는다.

## 컨테이너 재생성 후 원본 보존

같은 시험 bucket·credentials·metadata/data 볼륨을 유지하며 별도로 수행한다. 정상 4개 시험을 모두 통과한 뒤 다음 메서드 하나를 선택한다. 최초 `before`는 고정 표식 key가 `404 / NoSuchKey`인지 검사하므로 남은 표식이 있으면 임의 덮어쓰기 대신 원인을 확인한다.

```sh
./mvnw -B -ntp -Dlab.s3.tests=true -Dlab.s3.persistence=before \
  '-Dtest=GarageRawSourceIT#objectPersistsAcrossContainerRecreation' test
```

`before`는 `s3-it-persistence-check` 원본을 한 번 보관·조회하고 표식을 남긴다. 이후 전용 시험 컨테이너만 제거·재생성하되 같은 image manifest·TOML·metadata/data mount를 사용한다. 볼륨 삭제나 새 저장 경로 사용은 보존 검증이 아니다. 기존 Docker 서비스와 운영 Pod에는 적용하지 않는다. 기존 SSH tunnel을 같은 시험 S3에 다시 연결한 후 실행한다.

```sh
./mvnw -B -ntp -Dlab.s3.tests=true -Dlab.s3.persistence=after \
  '-Dtest=GarageRawSourceIT#objectPersistsAcrossContainerRecreation' test
```

`after`의 검증은 **Get만 사용하며 Put을 호출하지 않는다.** 읽은 전체 원본·hash·크기가 `before`와 같은지 비교한다. 이 검증이 성공한 뒤 시험 코드가 해당 고정 표식 한 개만 Delete하여 정리한다. DB 상태나 추가 Put으로 사라진 원본을 다시 만드는 재생성 시험은 인정하지 않는다. 이는 같은 볼륨을 사용한 컨테이너 재생성 검증이며, 디스크 손실·외부 백업 복원·호스트 재부팅 검증과 구분한다.

## 실패 시 판단과 보존

| 상황 | 유지할 상태와 다음 확인 |
| --- | --- |
| 정확한 `404 / NoSuchKey` | 기존 객체 부재로 해석하고 단일 Put 후 전체 Get 검증 |
| `403`, `NoSuchBucket`, 알 수 없는 404·500 | Put하지 않고 오류 유지. 전용 권한·bucket·연결 확인 |
| 기존 객체 길이·bytes·hash 불일치 | 덮어쓰기·삭제 금지. STAGING·슬롯·충돌 객체 보존 |
| Put 후 Get 실패 | 객체를 남기고 동일 요청에서 먼저 Get 재검증 |
| 원본 검증 뒤 mark 호출 진입 전 실패 | STAGING·슬롯 유지, dispatch 없음. 객체 재검증 후 mark 재시도 |
| outer DB 트랜잭션에서 stage 호출 | DB·S3 접근 전에 거부 |
| 종료된 작업 재요청 | 저장소 접근 전에 거부 |

mark 진입 전 오류 주입은 **실제 DB 트랜잭션 중간 rollback 검증이 아니다.** DB 결과·작업 상태·outbox의 원자적 rollback과 MariaDB 잠금은 [DB 기반 시험](db-job-foundation.md)과 [실제 MariaDB 근거](../evidence/db-job-foundation/README.md)를 별도로 확인한다. 이번 Garage 시험의 H2 결과로 migration 업그레이드나 실제 MariaDB 장애까지 검증했다고 기록하지 않는다.

원본 Get은 최대 1 MiB와 선언 길이를 확인하고 SDK 관리 transformer 안에서 끝낸다. 전체 30초·attempt 10초·connect 3초·read 8초, 최초 시도 포함 최대 3회 제한을 적용한다. 느린 body 시험은 전체 deadline 적용을 확인하는 별도 기본 검사다. ETag를 SHA-256·항상 MD5라고 가정하지 않는다.

첫 실제 4개 시험은 기본 요청 checksum 경로에서 PutObject HTTP 400 `Invalid payload signature`로 실패했다(3 error·1 failure). Garage 전용 `createGarage()`의 요청 checksum만 `WHEN_REQUIRED`로 바꾸며 응답 checksum·일반 `create()`·TLS 검증은 기본대로 유지한다. 호환성 조정 후 기본 verify 54개·실제 4개·재생성 before/after 각 1개가 통과했고 기존 운영 보존도 비교했다. 실패 원문과 후속 성공을 같은 결과로 덮어쓰지 않는다.

공개 근거에는 source SHA·SDK·image 식별값·시험 조건·실행 시각·실제 통과 수·보존 비교만 남긴다. 원본 로그와 endpoint·credentials·host 경로는 비공개로 보관한다. S3 실험 통과 뒤에도 운영 배포, Kafka ACK/offset, 결과 export·원본 replay는 [4단계 계획](../plans/phase4-messaging-storage.md)의 별도 관문이다.
