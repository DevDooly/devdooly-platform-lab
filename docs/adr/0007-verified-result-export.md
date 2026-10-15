# 0007 결과·실패 파일의 검증과 export 완료 경계

상태: 격리 구현·검증 및 기존 운영 보존 완료 · 2026-10-15 KST. 기본 verify 97개·실제 MariaDB/Garage IT 6개·child JVM 강제 종료 2회를 통과했다. 검토 브랜치의 내부 구현이며 운영에는 미배포다.

## 결정

DB 연산 완료와 객체 저장소 export 완료를 구분한다. `COMPLETED / PENDING` 작업의 결과 JSON과 실패 입력·이유 JSON을 생성하고 두 파일을 각각 전체 Get으로 확인한 뒤에만 기존 `LabJobService.completeExport`를 호출한다. 그 짧은 DB 트랜잭션이 export outbox 확인·`EXPORTED` 표시·완료 시각 기록·실행 슬롯 해제를 함께 확정한다.

두 객체와 DB는 원자적 트랜잭션이 아니다. 일부 객체만 남거나 두 객체가 확인돼도 DB 완료 처리가 실패할 수 있다. 이 경우 연산 결과·완료 시각은 그대로 두고 export `PENDING`·outbox·슬롯을 유지해 명시적 재시도를 허용한다. 단일 Put 응답, Head·ETag·SDK checksum만으로 저장 확인을 대신하지 않는다.

## 고정 입력과 파일 내용

첫 범위는 기존 `sensor-validation-v1`의 합성 입력 12개다. 일관된 짧은 DB snapshot에서 job·보관 원본·저장된 run·순번별 outcome을 읽는다. 원본의 전체 bytes·크기·SHA-256을 검증하고 순번과 실패 판정을 연결한다. 실패 파일에는 실제 실패한 입력 3개와 원래 입력 표현·실패 이유를 넣으며 업무상 중복 2개를 인프라 장애나 실패 입력으로 세지 않는다.

파일에는 schema/processor 버전·run·scenario·source hash·저장된 처리 시각·판정 건수를 담는다. 현재 시각·관측 시각·export 완료 시각·임의 UUID를 추가하지 않아 재시도가 같은 bytes를 만든다. 결정적인 경로와 content hash로 파일을 구분한다. 결과 계약 변경은 버전 변경으로 다루며 단일 writer의 한정된 내부 호출만 허용한다.

## 외부 저장과 재시도

외부 IO는 DB 트랜잭션 밖에서 실행한다. 각 파일은 먼저 bounded Get으로 읽는다. 정확히 `NoSuchKey / 404`인 경우만 Put하며 권한 오류·없는 bucket·timeout·서버 오류를 새 객체의 부재로 해석하지 않는다. 기존 객체의 declared/actual size·전체 bytes·SHA가 다르면 덮어쓰기나 삭제 없이 실패한다. Put 뒤에도 같은 전체 Get 검증을 수행한다.

첫 파일만 확인된 뒤 중단되면 재시도는 그 파일을 다시 확인하고 다음 파일로 진행한다. 두 파일 확인 뒤 DB 완료 전 중단돼도 같은 검증 뒤 DB 완료를 다시 시도한다. DB 작업은 이미 완료되어 있으므로 연산을 다시 실행하지 않는다. `EXPORTED` 재호출은 현재 파일 검증과 기존 완료 시각 보존을 확인하며, 다른 작업이 새로 점유한 슬롯을 해제하지 않는다.

## 운영과 보장 범위

기본 HTTP 앱에는 exporter bean·scheduler·공개 실행 endpoint를 등록하지 않는다. 이번 변경은 내부 adapter와 폐기 가능한 실제 MariaDB·Garage의 격리 검증이며 운영 image·GitOps pin·공개 UI/관측 계약은 갱신하지 않는다. 별도 Kafka 메시지 시험은 앞선 [ADR 0006](0006-explicit-kafka-dispatch.md)과 구분한다.

이 검증은 확인 시점의 객체 저장과 DB 완료 경계다. 저장소 복제·WORM·조건부 생성·다중 writer·이후 객체 삭제 방지·호스트/디스크 장애 복구·시스템 전체 exactly-once를 보장하지 않는다. 보존 기간과 자동 삭제는 후속이며 미완료 원본·파일을 자동 정리하지 않는다. 실제 진단 원본·접속 주소·credentials·child checkpoint는 Git 제외 경로에 남긴다.

[재실행 절차](../runbooks/result-export.md) · [실제 검증 근거](../evidence/result-export/README.md)

실제 문서별 상한은 4 MiB다. 경로는 `result/{runId}/sensor-validation-v1/{sourceSha256}/{result|failures}-v1-{documentSha256}.json`, processor 버전은 `sensor-processor-v1`이다. 실패 `rawLine`은 CR/LF separator를 제외한 원래 line text다. 기존 SDK의 전체 API 30초·attempt 10초·최초 포함 최대 3회는 각 SDK 호출에 적용된다. 없는 문서마다 Get+Put+Get을 사용하므로 전체 두 파일 export가 30초라는 보장은 아니다. 새 DB pair manifest는 추가하지 않았으며 불변 snapshot과 버전에서 문서/key를 재생성한다.
