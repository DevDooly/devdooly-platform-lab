# S3 원본 보관과 컨테이너 재생성 검증

2026-10-14 KST. 공개 합성 센서 입력 12개를 Garage에 보관하고 전체 bytes·크기·SHA-256을 확인한 뒤 DB 작업을 대기 상태로 연결했다. 운영 image·DB·GitOps 선언은 갱신하지 않았으며, 검토 중인 브랜치의 내부 Java 기능이다.

[허용 필드 실행 요약](summary.json) · [선정과 설계 ADR](../../adr/0005-verified-raw-source-storage.md) · [재실행 절차](../../runbooks/s3-source-storage.md)

## 실제 결과

| 조건 | 확인한 결과 |
| --- | --- |
| Java 21·Asia/Seoul 기본 verify | 54개, 실패·오류·건너뜀 0, JAR 생성 |
| SDK 기본 요청 checksum의 최초 실제 시험 | 4개 중 3 error·1 failure. PutObject HTTP 400 `Invalid payload signature`로 실패 |
| Garage 전용 요청 checksum 호환 설정 후 | 실제 SDK 시험 4개 통과. 별도 재생성 메서드 1개는 이 실행에서 skip |
| 재생성 전 표식 | 전용 key 부재를 확인한 뒤 Put·Get으로 원본 검증, 1개 통과 |
| 재생성 후 표식 | 같은 image와 metadata/data 경로의 새 컨테이너에서 재Put 없이 Get·bytes·hash·크기 검증, 1개 통과 |
| 느린 응답 제한 | 로컬 HTTP가 100ms마다 1byte를 보내는 동안 API/attempt 1.5초 제한이 종료시킴. socket 1초 조건과 구분 |
| 기존 운영 보존 | 전체 SQL·Flyway·저장 시각·API 결과, 2개 PVC UID·바인딩, DB Pod image·mount, 실행 중 Docker 26개의 ID·시작 시각·mount 유지 |
| 정리 | 소유권 라벨을 확인한 임시 Garage 컨테이너·내부 network 제거. 비공개 원본·설정·진단 경로 보존 |

Garage 2.4.1 linux/amd64 manifest를 digest로 내려받아 image config ID를 대조했다. RF1·sqlite이며 metadata와 object data를 모두 전용 경로에 보관했다. 메모리 1.5 GiB·CPU 1개 제한은 시험 구성이고 실측 사용량·성능 보장이 아니다. 서비스 포트를 공개하지 않고 Java는 기존 SSH의 loopback 터널을 사용했다. S3에는 실제 Garage, DB에는 별도 H2를 사용했다. 기존 MariaDB 17개씩의 세 조건 검증은 [앞선 DB 기반 기록](../db-job-foundation/README.md)이다.

## 확인한 경계

실제 SDK Put·Get·Head·prefix ListObjectsV2·Delete, 동일 원본 재요청, QUEUED·COMPLETED 재요청의 시각·outbox 보존을 확인했다. 같은 크기의 손상 객체는 덮어쓰지 않았고 STAGING·슬롯·dispatch 부재를 유지했다. 검증 후 mark 호출 진입 전에 오류를 주입해 원본이 남고 동일 요청에서 재검증되는 것도 확인했다. 이 오류 주입은 실제 DB UPDATE 뒤 commit 실패나 트랜잭션 내부 rollback을 검증한 것이 아니다.

일반 `S3ClientFactory.create()`의 checksum 정책은 그대로 두고 `createGarage()`에만 요청 `WHEN_REQUIRED`를 선택했다. 응답 checksum 정책·TLS 검증을 변경하지 않았으며 전체 bytes의 독립 SHA-256 확인도 유지한다. Get body는 SDK 관리 transformer 안에서 제한적으로 읽고, standard retry는 최초 요청을 포함한 최대 3회다. 기본 앱에는 S3 client·adapter·coordinator bean이 없고 기존 POST 405·공개 실행 비활성 계약을 유지한다.

## 실패와 교정

첫 실제 SDK 실패는 원본 로그와 함께 보존했으며 후속 성공으로 덮어쓰지 않았다. 동일 조합의 요청 checksum 설정을 바꾼 뒤 Put·전체 읽기 시험이 통과했다. 이 관측 범위를 다른 S3 기능이나 모든 SDK 버전에 일반화하지 않는다.

Docker 내부 network에서 published port가 생성될 것이라고 가정한 첫 준비는 연결 정보 확인에서 중단됐다. 내부 컨테이너 주소로 향하는 SSH loopback 터널로 교정했으며 최종 구성에는 published port가 없었다. 재생성 확인 도구의 mount 배열 순서 비교도 값 비교와 분리했고, 실제 목적지별 metadata/data source 경로를 다시 대조한 뒤 Get-only 보존 시험을 통과했다.

## 남은 범위

조건부 쓰기·CAS·WORM·Object Lock을 보장하지 않는다. 다른 writer를 배제한 작은 관리 실행을 전제로 하며, 동시에 같은 작업을 재시도하면 같은 bytes의 Put은 중복될 수 있다. 실제 Kafka ACK/offset·worker의 S3 재처리·결과 export·운영 배포는 다음 작업이다. 업로드 ACK 유실·저장 도중 운영자 종료·다중 writer·디스크 손실 복원·성능은 검증하지 않았다. 원문 로그·endpoint·access key·secret·host 경로는 공개본에 포함하지 않는다.


## 실제 MariaDB 결합 후속

위 2026-10-14 SDK 시험의 DB는 H2다. 이후 [2026-10-15 MariaDB·Garage 결합 검증](../mariadb-s3/README.md)을 별도로 수행했다. 실제 DB의 QUEUED UPDATE 뒤 DISPATCH trigger 오류·rollback·원본 보존·재시도와 같은 DB 반복을 확인했으며 H2 결과를 실제 DB 결과로 바꾸어 표기하지 않았다.
