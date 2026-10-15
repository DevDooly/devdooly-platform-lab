# 0005 원본 전체를 검증한 뒤 S3 보관을 작업 대기 상태에 연결

상태: 한정 채택 · 2026-10-14 KST. Garage 고정 이미지의 식별값·격리 기동, 호환성 교정 후 실제 SDK 시험 4개와 컨테이너 재생성 전 Put/Get·후 Get-only 보존 검증을 통과했다. 이 결정은 고정 12개 합성 원본의 내부 보관에 한정하며 운영 배포는 별도다. [실제 결과와 실패·교정](../evidence/s3-source-storage/README.md)을 연결한다.

## 배경

[DB 작업·outbox 기반 코드](../runbooks/db-job-foundation.md)는 원본·hash·단일 실행 슬롯을 `STAGING`에 저장하고, 원본 보관이 확인되면 `QUEUED`와 dispatch intent를 같은 DB 트랜잭션에 기록한다. S3와 DB를 하나의 트랜잭션으로 묶을 수 없으므로 원본이 없는 작업을 대기 상태로 바꾸거나 저장소 오류 뒤 원본을 지우지 않는 연결이 필요하다.

이번 범위는 공개 합성 시나리오 `sensor-validation-v1`의 순서가 고정된 12개 입력과 최대 1 MiB 원본이다. Kafka 발행·수신·offset, 결과 export와 공개 실행은 별도 후속 단계다.

## 채택한 구성

Garage 2.4.1 단일 노드를 한정된 원본 보관 대상으로 고정한다. 공식 release는 2026-09-08이며 프로젝트가 안내하는 컨테이너는 `dxflrs/garage:v2.4.1`이다. 라이선스는 AGPLv3다. AWS SDK for Java v2는 2026-10-13 release인 2.55.16으로 고정하고 동기 `S3Client`와 `url-connection-client`를 사용한다. Java 21은 SDK의 공식 지원 대상이다. [Garage release](https://garagehq.deuxfleurs.fr/_releases.html), [고정 버전 LICENSE](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/LICENSE), [AWS SDK release](https://github.com/aws/aws-sdk-java-v2/releases/tag/2.55.16), [Java 지원과 모듈 안내](https://github.com/aws/aws-sdk-java-v2)

| 이미지 식별값 | 고정값 |
| --- | --- |
| OCI index | `sha256:9c96caa2612d3411acc5b0e6701fb238dbfba33e533a6d7d3d811a4b12d0d020` |
| linux/amd64 manifest | `sha256:0d7c74fc8ca6fef68a5a941c0e7558c8b1e92ba3588fa7505400e1350456c796` |
| image config | `sha256:c7746d213b6809acdd57ab4b7c48f9e2636e4382a3a63e3ee845a1e82df40209` |

공개 Registry의 index·플랫폼 manifest 응답 hash를 직접 계산해 대조했고, 실제 격리 서버의 pull과 image config ID도 일치했다. 이 식별값은 이미지 출처 확인 근거이며 Java 호환성 통과를 뜻하지 않는다.

격리 서버는 RF1·sqlite를 사용하며 metadata와 object data를 모두 전용 볼륨에 보관한다. CPU 1개·메모리 1.5 GiB 상한의 작은 시험이며 성능 측정값이 아니다. Docker 내부 network만 사용하고 published port·Ingress·NodePort를 추가하지 않는다. 로컬 Java는 기존 SSH의 숫자 loopback 터널을 통해서만 접근한다. RF1은 복제나 고가용성·외부 백업을 제공하지 않는다. [Garage 단일 노드 구성과 영속 경로](https://garagehq.deuxfleurs.fr/documentation/quick-start/)

## 원본과 DB 경계

`SourceStagingService`는 자동 생성 bean이 아닌 명시적 내부 호출자다. 외부 DB 트랜잭션 안에서 호출하면 DB·S3 접근 전에 거부한다. 실행 순서는 다음과 같다.

1. 원본을 복사하고 UTF-8 NDJSON·고정 12개 입력·1 MiB 상한을 검증한다. 업무상 잘못된 시각·중복 ID도 원본 순서대로 보존한다.
2. 짧은 DB 트랜잭션으로 원본·SHA-256·크기·시나리오를 저장하고 `STAGING`과 실행 슬롯을 확정한다. 같은 run의 다른 원본은 거부한다.
3. DB 트랜잭션 밖에서 `raw/{runId}/{sha256}.ndjson`을 조회한다. 기존 객체가 정확하면 다시 쓰지 않는다. HTTP 404와 `NoSuchKey`가 함께 확인된 경우에만 단일 Put 후 Get으로 검증한다.
4. Get의 선언 길이와 제한된 전체 bytes를 확인하고 원본 bytes·크기·SHA-256을 대조한다. ETag·Head·사용자 metadata만으로 내용 검증을 대신하지 않는다.
5. 검증 후 짧은 DB 트랜잭션에서 `STAGING → QUEUED`와 `DISPATCH / PENDING` outbox를 함께 저장한다.

같은 크기의 손상·다른 객체, 권한 오류, 없는 bucket과 알 수 없는 404는 원본 부재로 해석하지 않는다. 관측한 충돌 객체는 adapter가 덮어쓰거나 삭제하지 않는다. Put 후 읽기나 DB 상태 전환이 실패해도 객체와 `STAGING`을 보존하며 다음 동일 요청에서 다시 검증한다. 이미 `QUEUED`·`COMPLETED`인 동일 요청도 S3를 확인하되 기존 처리 시각·outbox를 다시 만들지 않는다. 종료된 작업은 저장소 접근 전에 거부한다.

현재 처리 서비스는 기존 DB에 보관한 원본을 사용한다. S3 보관을 추가했다고 worker의 S3 재처리·Kafka 전달이 구현되는 것은 아니다.

## SDK 호환성과 제한 시간

endpoint와 credentials provider를 명시하고 기본 credential chain·metadata 탐색을 사용하지 않는다. region은 Garage 설정과 같은 `garage`이며 path-style과 SigV4를 사용한다. 일반 endpoint는 HTTPS, plain HTTP는 숫자 loopback의 격리 시험에 한정한다. [AWS endpoint 설정](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/endpoint-config.html)

SDK 2.30.0 이후 기본 요청 CRC32 checksum 경로를 먼저 시험했다. 실제 Garage 첫 4개 시험은 PutObject의 HTTP 400 `Invalid payload signature`로 3 error·1 failure가 발생했다. 원본 로그를 비공개로 보존하고 성공으로 계산하지 않는다. 이에 `createGarage()`에만 `requestChecksumCalculation(WHEN_REQUIRED)`를 적용한다. 일반 `create()`와 응답 checksum 검증의 SDK 기본값은 유지하고, 독립적인 전체 원본 SHA-256 검증도 유지한다. [AWS checksum 정책](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/s3-checksums.html)

전체 API 30초·attempt 10초·connect 3초·read 8초와 최초 시도를 포함한 최대 3회로 제한한다. Get body는 SDK가 관리하는 제한된 `ResponseTransformer` 안에서 끝까지 읽어 전체 deadline에 포함한다. 느린 body 시험과 실제 재시험을 통과한 결과만 검증 근거에 추가한다. [AWS timeout 범위](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html)

## 보관 보장의 한계

Garage는 Put·Get·Head·ListObjectsV2·Delete를 제공하지만 conditional write·`If-None-Match`·Object Lock·WORM과 bucket versioning을 제공하지 않는다. 이 adapter는 content-addressed key와 작업 hash 검증을 사용하며 다른 writer를 운영 정책으로 배제한다. 같은 허용 작업의 정상 재시도 두 개가 같은 bytes를 쓰는 경우는 생길 수 있다. 사전 Get과 이후 Put 사이에 외부 writer가 끼어들지 못한다는 원자적 CAS 보장은 없다. 다중 writer가 필요해지면 저장소 선택과 동시성 계약을 다시 검토한다. [S3 호환 범위](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/), [조건부 쓰기의 구조적 제한](https://garagehq.deuxfleurs.fr/documentation/reference-manual/known-issues/)

전용 access key에는 격리 인스턴스의 시험 bucket 읽기·쓰기만 부여한다. bucket owner 권한이나 운영 자격증명은 사용하지 않는다. credentials와 실행 원본은 Git에서 제외한 비공개 경로에 저장한다. 회사 코드·데이터·실제 수율 알고리즘은 사용하지 않는다.

## 검증과 채택 조건

[실행 절차](../runbooks/s3-source-storage.md)의 실제 SDK API·동일 요청·충돌 보존·상태 전환 전 실패와 재시도, 컨테이너 재생성 후 Get 검증을 통과해야 한다. mark 메서드 진입 전에 던진 모의 오류는 실제 DB 트랜잭션 내부 rollback의 근거가 아니며 [MariaDB 기존 검증](../evidence/db-job-foundation/README.md)과 구분한다.

기본 앱의 S3 client·adapter·coordinator bean은 0개이며 공개 `POST /api/demo/runs`는 405, 공개 실행은 비활성 상태를 유지한다. 운영 image·DB·GitOps/Helm은 이 실험으로 갱신하지 않는다. 최종 기본 verify 54개·실제 SDK 4개·재생성 전후 각 1개가 통과했다. 임시 자원을 정리한 뒤 기존 SQL·시각·PVC·Docker와 방화벽 보존을 비교했다. [실행 요약](../evidence/s3-source-storage/summary.json)을 확인할 수 있다.
