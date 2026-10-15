# DB에 보관하는 내부 승인 간격 검증

기본 30초의 서로 다른 새 작업 승인 간격을 구현하고 기본 검사 **157/157**, 실제 MariaDB·Garage 선택 검사 **19/19(실패·오류·skip 0)**와 외부 사본 SQL 복원 후 binary 호환 검사 **8/8**을 통과했습니다. 기능 검증 소스는 `9926bd2f714954bcd8d43fa9c5333e503958fd92`입니다. 같은 source의 [GitHub CI 38720179414](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38720179414)도 completed/success입니다. [공개 요약](summary.json), [ADR](../../adr/0011-durable-admission-cooldown.md), [운영 절차](../../runbooks/admission-cooldown.md)를 연결합니다.

운영 V4 배포 전의 격리 검증입니다. 당시 운영 API·worker의 source `6c5aff94`와 7개 작업은 변경하지 않았습니다. 기존 5개 부하/중단 시험 작업이 있는 schema도 migrate하지 않고 새 schema·전용 DB 사용자·새 bucket/전용 key를 사용했습니다. Windows Java 21·Asia/Seoul JVM에서 숫자 loopback의 SSH 터널로 Linux backend에 연결했습니다. credentials와 원문 로그는 비공개 보관합니다.

## 확인한 계약

- slot과 별개로, 정상 export 뒤 slot이 비어도 다음 승인 시각 전의 새 작업은 거부합니다. 새 DB 행·outbox·raw 객체와 저장소 호출은 0입니다.
- 같은 run·같은 원본의 재시도는 승인 시각을 바꾸지 않습니다. 충돌·busy·잘못된 입력도 새 승인을 소비하지 않습니다.
- gate·job·slot의 DB 오류 rollback, 승인 후 S3 실패의 동일 ID 재시도, terminate 뒤 gate 보존을 확인했습니다.
- 2·8개 경합의 단일 승자와 cooldown 중 전부 거부, 설정 1~3,600초·singleton 누락의 fail-closed를 검증했습니다.
- 실제 S3 객체를 쓰는 8개 동시 접수는 승자 raw 한 개만 남겼습니다. 결과·실패 파일 저장 후 slot이 비었어도 다음 새 작업은 거부됐고 탈락자 raw/outbox는 없었습니다.
- 격리 MariaDB의 단일 test 세션 시각으로 deadline 1µs 전 거부·정확히 같을 때 승인·1µs 후 승인을 확인했습니다. 세션 시각은 finally에서 원복했고 호스트/운영 DB 시각은 바꾸지 않았습니다.
- slot lock을 기다리는 사이 deadline이 지난 경우 lock 해제 후 **새 SQL statement의 DB 시각**으로 승인했습니다.
- 새 JVM의 동일 생산 LabJobService admission 경계가 DB에 남은 cooldown을 읽어 거부하고 저장소를 호출하지 않았습니다. 전체 Spring/RuntimeMain 재시작 시험으로 확대해 해석하지 않습니다.

공통 H2·MariaDB 계약은 15개이며 실제 S3·microsecond·lock 대기·새 JVM 4개를 더해 선택 검사는 19개입니다. 기본 suite는 기존 140개 + H2 계약 15개 + H2 V3→V4/빈 DB·반복 migration 2개 = 157개입니다. H2 migration 성공을 실제 이전 이미지 호환성으로 표시하지 않습니다.

## 외부 SQL 사본과 실제 이전 binary 호환

운영의 기존 7개 작업·원본 7개/export 14개를 새 private checkpoint로 확보하고 외부 AES-256-GCM 사본의 인증과 readback 해시를 확인했습니다. archive SHA-256은 `fa82a2d77c5ddfffadf03325b9031b3126a5bb81a4d43f520dc3634d602eca98`입니다. 인증한 외부 archive의 catalog-neutral SQL member만 전용 schema로 복원했습니다. 운영 PVC·S3 객체를 복원하거나 덮어쓴 시험은 아닙니다.

2026-10-15 10:36:41.447886 UTC에 다음 8개 검사가 통과했습니다. 같은 backend의 기존 5개 부하/중단 작업과 운영 source `6c5aff94`·schema V3·7개 작업은 그대로 보존했습니다.

- candidate `9926bd2f`의 JAR SHA-256 `b7fd9ceb394218a4b7b27428529e47b83763933b8663e6607c0bf2d04dae6835`로 새 API를 시작해 복원본만 V4로 migrate하고 7개 작업의 실제 HTTP DTO를 읽었습니다. 기존 업무 SQL·bytes·시각·V1~V3 이력과 기본 30초의 미사용 policy를 보존했습니다.
- 실제 이전 `5a1495be` JAR SHA-256 `ac13f7045eba661d2e90c15b7df661c6fde7039311d0a067010981914664ddc9`의 API가 V4 schema에서 시작하고 같은 7개 DTO를 읽었습니다. 이전 JAR의 main source와 build POM이 운영 source `6c5aff94`와 동일한 근거도 별도로 확인했습니다. **운영 6c OCI 이미지 자체를 실행한 호환 시험은 아닙니다.**
- 같은 이전 JAR의 worker를 전용 empty topic·실제 read-only key의 새 빈 bucket에 연결해 idle heartbeat와 정상 종료·named lock 해제를 확인했습니다. 새 작업 접수·객체 쓰기는 없었고 JVM 세 개를 정상 종료했습니다.

이 시험은 복원본의 migration과 이전 binary의 startup/read·idle worker 호환입니다. 새 cooldown 정책이 충전된 상태에서 전체 RuntimeMain을 재시작해 admission 제한이 유지되는 시험으로 확대하지 않습니다. 그 제한의 새 JVM 검증은 위 LabJobService admission 경계 시험입니다.

## 실패 이력과 한계

기본 suite의 첫 검증에서는 기존 관측 test cleanup보다 먼저 새 test gate reset을 호출해 이전 test의 slot owner 보호 검사에 걸렸습니다. cleanup 뒤 명시 reset하도록 고쳤고 최종 157개를 통과했습니다. 앞선 실패 로그는 보존했습니다. 운영 기능을 비활성화하거나 default30을 바꿔 통과시키지 않았습니다.

이 기능은 새 작업 승인 간격이며 HTTP QPS·조회 요청·모든 재시도를 제한하지 않습니다. 공개 POST·실행을 추가하지 않았고 처리 용량·SLA를 검증하지 않았습니다. 구형 stage binary는 정책을 모르므로 같은 DB에서 실행하면 우회합니다. 이전 API/idle worker의 호환 성공이 이전 stage의 정책 준수를 뜻하지 않습니다. 운영은 여전히 source `6c5aff94`·schema V3이며 V4 운영 배포·실제 새 이미지 검증은 후속입니다.
