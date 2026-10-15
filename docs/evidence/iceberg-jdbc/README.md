# Trino·JDBC catalog의 작은 합성 실증

**기록 기준: 2026-10-15 19:05:20 UTC.** 별도 실험에서 Trino 483·PostgreSQL 17.11 JDBC V1 catalog·Garage backing store를 연결했습니다. 고정 합성 원본을 두 번 추가하고, Trino 정상 재시작 뒤에도 같은 행·metadata pointer·객체 전체 bytes를 읽었습니다. 마지막에는 새 PostgreSQL·Trino workload를 모두 중지하고 PVC 두 개와 warehouse를 보관했습니다. 현재 가용성을 조회한 결과나 전체 Phase6 완료 표시는 아닙니다.

이 기록의 정적 표시 데이터는 [iceberg.latest.json](https://devdooly.github.io/devdooly-platform-lab/observations/iceberg.latest.json), 공개 요약은 [summary.json](summary.json), 재실행 경계는 [runbook](../../runbooks/iceberg-jdbc-native.md)에 연결합니다. 이미 게시된 정적 검증 기록이며 현재 가용성이나 실시간 상태와 구분합니다. [초기 준비 당시 문서](PREPARED.md)는 원문 그대로 보존했으며 현재 완료 상태와 구분합니다.

## 확인한 결과

원본은 **1,100 bytes·12행**의 공개 V1 fixture입니다. 순서와 값을 그대로 저장하므로 중복 event ID·잘못된 시각·범위 밖 값도 남습니다. Java/Spark Silver의 성공 7·실패 3·중복 2 처리와는 집계 기준이 다릅니다.

| 시점 | 원본 행 | distinct event ID | sensor-a / sensor-b | snapshot summary의 added-records |
| --- | ---: | ---: | ---: | --- |
| 초기 빈 append | 0 | 0 | 0 / 0 | key 없음 → null |
| 고정 INSERT1 뒤 | 6 | 5 | 5 / 1 | 6 |
| 고정 INSERT2 뒤 | 12 | 10 | 8 / 4 | 6 |

**총 snapshot은 3개이며, 데이터 append는 2개**입니다. 초기 snapshot ID는 `2998009981322509692`, 다음 두 ID는 `12640090016022793`, `4204764411108512937`입니다. 양의 BIGINT를 문자열로 보존하고 바로 앞 snapshot을 parent로 연결했습니다. 실제 시점 조회도 각각 0·6·12행이었습니다. 초기 summary에 없던 `added-records` 값을 `0`으로 만들지 않았습니다.

- Trino의 정상 종료를 관측한 뒤 새 Pod·container로 시작해 행·snapshot·history·data file 결과를 다시 비교했습니다. PostgreSQL은 같은 프로세스를 유지했습니다.
- 재시작 전후 warehouse의 **12개 객체**를 각각 전체 GET·size·SHA로 대조했습니다. 초기 metadata·빈 manifest list 두 객체도 그대로 남았습니다.
- 원래 애플리케이션의 **8개 작업과 객체 24개**를 보존했습니다. Baseline7과 final에서 같은 24개 집합을 각각 전체 bytes로 비교한 두 pass이며, 서로 다른 객체 48개라는 뜻은 아닙니다. 원본 객체 DELETE는 0회입니다. 업무 SQL·기존 서비스와 저장소 식별자도 보존 범위에 포함했습니다.
- 명시적인 일곱 번째 실행의 catalog·query·restart·stop·final과 detached supervisor가 모두 통과했습니다. 종료 후 실험 workload는 0, 자체 PVC 두 개의 정책은 Retain입니다.

## 실패와 후속 실행의 관계

여섯 번째 실행에서는 CREATE SCHEMA·CREATE TABLE이 완료됐습니다. 이어진 초기 snapshot 조회가 없는 map key를 `summary['added-records']`로 읽어 실패했고, **INSERT는 아직 시도되지 않았습니다.** 당시 query·전체 supervisor 실패는 그대로 보존했습니다. PostgreSQL·Trino 중지는 통과했습니다.

일곱 번째 실행은 완료된 DDL과 초기 객체를 채택했습니다. Current/초기 시점 0행·JDBC pointer·초기 warehouse 전체 bytes와 미시도 INSERT 흔적 부재를 확인한 뒤 고정 INSERT 두 개만 각각 한 번 실행했습니다. Snapshot inspection은 없는 key를 NULL로 읽는 `element_at`으로 교정했습니다. Frozen SQL plan 파일 자체는 바꾸지 않았으므로 **파일 보존과 실제 inspection SQL 교정**을 구분합니다. [Trino map 처리](https://trino.io/docs/current/functions/map.html#subscript-operator), [Iceberg 1.11의 양수 added-records만 기록하는 조건](https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/core/src/main/java/org/apache/iceberg/SnapshotSummary.java#L247-L260)을 근거로 삼았습니다.

공개 projection 준비도 두 번 거절됐습니다. 첫 collector는 정렬해 저장한 dict를 원래 열 순서에 의존하는 해시로 다시 계산했고, 둘째는 실제 query receipt에 없는 `initialState` 필드를 가정했습니다. 두 소스·실패 기록은 남겼습니다. 셋째 collector는 이미 저장된 Trino 열·값 배열과 query identity, 별도 초기 SELECT·객체 파일을 읽어 계약을 검증했습니다. **SQL·native 작업·새 clock을 실행하지 않고** 실제 projection을 만들었습니다. 원본 행 값과 해시 상수는 바꾸지 않았습니다.

## 출처와 한계

보존 대상 애플리케이션 source는 `3e0d85be2f529026cb44812602e31c0e18797b45`, GitOps revision은 `75eb569b016c38c9cc1b1f5819a611b830f2b83d`입니다. 별도 실행 도우미는 당시 커밋되지 않은 private 준비본이므로 `privateExecutorCommit:null`과 실제 파일 SHA를 따로 기록했습니다. 위 애플리케이션 커밋을 도우미·Trino 이미지의 소스 커밋이라고 표시하지 않습니다. Prepare3·capability3·DDL6의 채택과 native7의 실제 결과도 [요약](summary.json)에서 구분합니다.

이 시험은 PostgreSQL 재시작·호스트 재부팅·장애 복구·HA·대용량 처리·처리량 SLA를 검증하지 않았습니다. Spark/Silver 호환 성공, compaction, snapshot expiration, Airflow, 공개 SQL 접속도 이 증거에 포함하지 않습니다. Git에 게시하지 않았던 초기 17파일 준비본의 `s3.max-error-retries=0`·두 snapshot 가정은 실제 native7 실행 조건이 아니었습니다.

이후 [PR50](https://github.com/DevDooly/devdooly-platform-lab/pull/50)에서 교정을 반영한 [공개 계획 2](../../../infra/iceberg-lab/README.md) 21파일을 게시했습니다. 이 계획은 **PREPARED_NOT_RUN**인 오프라인 생성기·검증기이며 실제 리소스 배포·SQL 제출 실행기는 없습니다. [Runbook의 초기 준비본과 공개 계획 구분](../../runbooks/iceberg-jdbc-native.md#초기-준비본과-게시된-공개-계획-2)은 현재 공개 소스와 과거 실증의 관계를 설명합니다. 새 계획의 게시는 private native7 도우미를 Git에 커밋했거나 새 runtime 시험을 통과했다는 뜻이 아닙니다.
