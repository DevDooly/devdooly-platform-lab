# 신규 내부 접수의 저장소 예산 계약 — 미연결 후보

이 문서는 서비스에 연결하지 않은 설계 초안이며 현재 API·worker의 접수 조건을 바꾸지 않는다. 운영 reader·정책 기본값·Bean/controller·migration·배포가 없고 과부하 방지가 구현됐다는 근거가 아니다. 순수 함수만 먼저 병합해 완료로 표시하지 않는다. 공개 실행·POST도 추가하지 않는다.

## 적용 위치와 기존 재시도

현재 `LabJobService.prepareSource`는 run ID·CanonicalSource를 검증한 뒤 transaction에서 slot을 lock하고 existing run을 조회한다. existing의 hash/scenario/전체 source가 일치하면 먼저 반환한다. 다른 source를 같은 ID로 보내는 경우는 현재 충돌이다. 미래의 새 저장소 gate도 이 순서를 보존하고 **기존 run 반환 뒤에는 평가하지 않는다**. `SourceStagingService`는 그 뒤 `storeAndVerify`를 수행할 수 있으므로 기존 재시도의 외부 I/O까지 생략하는 계약은 아니다.

새 run 경로에서만 기존 occupied slot·legacy run 충돌 검사 후, `reserveAdmissionCooldown()`·STAGING insert·slot update 직전에 판단한다. Pure API에는 run ID나 `isRetry` 인자가 없어 caller가 임의 same-ID 주장으로 FIT을 받을 경로가 없다. existing 여부와 source 일치는 서버의 DB 검사이며 이 순수 함수가 검증하지 않는다.

## 관측과 clock

운영 reader와 정책 관리 범위에서 만든 immutable snapshot/계수만 신뢰한다. HTTP/CLI 작업 payload가 available bytes·observedAt·scope·estimate·reserve를 지정할 수 없어야 한다. 아직 운영 reader는 구현하거나 특정하지 않았다. 실제 경로·mount·Garage replica/layout을 확인하지 않은 host disk/컨테이너 filesystem 값은 아래 scope를 충족하지 않는다.

| domain | KNOWN snapshot이 다뤄야 할 선택 범위 | 미완료 조건 |
| --- | --- | --- |
| DATABASE | 현재 DB의 data/index/redo/binlog/temp 등 해당 신규 작업의 쓰기 경로와 그 backing의 가용 예산 | 경로 누락·단순 DB 논리 행수·다른 mount 관측이면 UNKNOWN |
| GARAGE | 고정 bucket의 저장 layout·replica/allocation/metadata overhead를 고려한 선택 write budget | 한 로컬 disk 여유만 알거나 cluster/write budget으로 변환 못하면 UNKNOWN |

domain들이 같은 backing을 공유할 수 있다. 독립 quota/배정 또는 이중계상 없는 검증된 집계가 없으면 둘을 독립 KNOWN으로 만들지 않는다. `INDEPENDENT_SELECTED_WRITE_BUDGET` enum은 reader가 충족해야 할 계약일 뿐 함수가 실제 독립성이나 강제 quota를 입증하는 기능이 아니다.

### 공유 filesystem은 단일 pool로 계산한다 — 미래 연결 계약

읽기 전용 관측 한 번에서 선택 DB·Garage metadata/data 경로가 같은 filesystem을 공유함을 확인했다. 이는 독립 저장소 둘의 용량이 아니며 전체 물리 장치·다른 서비스·쓰기 예산의 검증도 아니다. Garage byte/object quota는 미선언이었고, DB hard quota·운영 계수·미반영 charge 회계는 아직 UNKNOWN이다. 실제 주소·경로·여유 수치는 이 계약에 넣지 않는다.

공유 pool의 접수 판단을 향후 구현한다면 다음 입력을 한 관측·회계 범위에 묶어야 한다. `F`는 선택 pool의 신뢰된 가용 bytes 관측 **한 번**, `R`은 공통 reserve **한 번**, `U`는 승인했으나 아직 `F`에 반영되지 않은 잔여 charge, `W`는 다른 writer의 선택 범위에 배정한 allowance다. 동일 bytes·charge·reserve를 둘 이상의 항목에 중복 계상하지 않는다.

```text
H = F - R - U - W
Bdb + Bgarage <= H
```

모든 항은 검증된 범위의 음이 아닌 정수여야 하며, 산술 overflow·누락·회계 중첩·writer 범위 불명은 UNKNOWN 또는 invalid로 거부한다. 입력과 회계가 모두 KNOWN이고 산술 검증을 통과했을 때 `F < R + U + W`이거나 `Bdb + Bgarage > H`이면 알려진 예산 부족으로 거부하며, 관측 불명의 UNKNOWN과 구분한다. `Bdb`와 `Bgarage`는 **이번 신규 작업**의 선택 물리 쓰기 상한으로, DB 쓰기 증폭과 Garage replica·metadata 비용을 포함해야 한다. 같은 `F`를 DB/Garage의 available에 각각 복사하거나 두 번 합산하지 않으며, 공통 reserve를 domain별 reserve처럼 반복 차감하지 않는다.

이미 쓰여 `F`에서 제외된 bytes를 `U`로 다시 빼지 않는다. `U`는 아직 반영되지 않은 잔여분만 다루며, 반영 여부·잔여 charge를 신뢰 있게 구분하지 못하면 0으로 가정하지 않고 UNKNOWN이다. 이번 신규 요청의 `Bdb/Bgarage`를 기존 `U`에도 넣어 중복 차감하지 않는다. 승인 후 charge의 원자적 계상·usage 반영에 따른 해제·다른 writer 참여는 별도 회계/예약 설계가 필요하며, 위 부등식이나 단일 slot만으로 공간 예약을 보장하지 않는다.

Garage는 bytes와 별개로 신규 raw 1개·export 2개의 **객체 3자리**를 확인해야 한다. object quota·usage·미반영 object charge가 불명확하면 bytes가 맞아도 UNKNOWN이다. 이 계약은 실제 quota나 운영 계수를 새로 설정하는 제안이 아니다.

**현재 `Coverage` enum과 `evaluateNewAdmission`에는 공유 pool 입력·합산 판정이 없다.** 위 계약은 향후 지원 조건이며 현재 함수로 공유 pool을 지원한다고 표시하지 않는다. 실제 공유 관측을 `INDEPENDENT_SELECTED_WRITE_BUDGET`으로 바꿔 넣거나 임의 분할 숫자로 FIT을 만들지 않는다. 독립 배정 또는 새 pool 계약의 신뢰 reader·회계·clock을 확보하기 전에는 UNKNOWN으로 두고 운영 연결을 보류한다.

### 접수 잠금과 관측 시각

reader는 transaction 밖에서 갱신하고 접수 transaction은 immutable view만 평가한다. source가 일치하는 existing run은 먼저 반환하며 그 뒤 resource gate를 평가하지 않는다. 신규 분기는 `slot/job/policy 및 필요한 모든 admission lock → 별도 DB now → immutable view의 scope/시각/회계/fence 검증 → 정책 판단 → cooldown charge·STAGING insert·slot update → commit` 순서를 지켜야 한다. policy row를 잠그는 읽기/검증과 cooldown 갱신을 분리해 판단 전에는 charge하지 않는다. 추가 reservation row가 필요하면 그 lock도 DB now보다 먼저 얻어야 한다.

row lock을 기다리는 SQL 안에서 잡은 시각이나 transaction 시작 전 app Clock을 **모든 lock 뒤의 DB now**로 대신하지 않는다. future/stale과 view 재사용 fence를 그 시각으로 확인하고 UNKNOWN/부족/오류이면 cooldown·job·slot·outbox 변경과 작업 저장 I/O 전에 거부한다. admission marker fence는 동일 view의 재사용을 막는 경계이며 물리 예약이나 다른 writer 전체의 배제를 증명하지 않는다. authoritative DB clock과 관측 clock 사이 변환·오차 범위를 별도 검증해야 한다. 현재 app Clock과 DB clock이 동등하다는 가정은 두지 않으며 미래 시각은 거부한다. Clock 결합/reader가 없으면 운영 연결하지 않는다. transaction 종료 뒤 기존 `storeAndVerify` 흐름은 유지하므로 existing 반환을 재시도 전체 I/O 0으로 표현하지 않는다.

## estimate와 결정

현재 CanonicalSource는 실제 validated bytes 1..1,048,576·events 1..1,000, ExportBundle은 문서 각각 최대 4,194,304 bytes다. 이 값은 논리 payload hard cap이며 physical disk 성장률이나 quota가 아니다.

- DATABASE: `dbFixed + sourceBytes × dbSourceFactor + eventCount × dbOutcomeBound`.
- GARAGE: `(sourceBytes + 2 × 4,194,304) × garagePayloadFactor + 3 × garageObjectOverheadBound`.

DB fixed에는 job/run/outbox/export metadata와 해당 쓰기 증폭의 보수적 상한을 포함해야 한다. source/outcome 계수는 버전별 schema·페이지·redo/binlog·temp 등 선택 footprint를 반영해야 한다. Garage는 raw1+export2의 세 객체와 전체 두 문서 cap을 예산에 넣고, payloadFactor/overhead는 실제 선택 replica/layout의 보수적 상한이어야 한다. 별도 검토된 근거 없이 운영 값을 정하지 않는다. 산술 검사는 계수의 보수성을 증명하지 않는다. shared writer와 동시 공간 변화도 남는다.

| 입력/관측 | 결정 |
| --- | --- |
| snapshot 없음 또는 scope UNKNOWN | 해당 domain UNKNOWN 거부 |
| domain 불일치·음수·잘못된 정책·범위 밖 source/events | INVALID 거부 |
| observedAt > now / age > maxAge | FUTURE / STALE 거부 |
| estimate 또는 reserve+estimate long overflow | OVERFLOW 거부 |
| DB 또는 Garage available < reserve+estimate | 해당 저장소 예산 부족 거부 |
| 두 저장소 모두 exact boundary 이상 | STORAGE_ESTIMATE_FITS; 기존 접수 조건은 계속 적용 |

maxAge·reserve·계수에 운영 기본값은 없다. synthetic test 값으로 운영 임계치를 권고하지 않는다. FIT은 공간 예약·transaction 성공·저장 성공·처리량·SLA·전체 cluster capacity의 증거가 아니다. 저장 실패 때 자동 새 ID 제출·쿨다운 초기화·retry를 추가하지 않고 기존 same-ID 확인/복구와 실패 기록을 유지한다.

## 검증 범위

2026-10-18 Windows JDK 21.0.9의 별도 standalone 모듈에서 순수 함수 검사 3개를 실행해 실패·오류·skip 0으로 통과했다. 전체 API 소스 컴파일·DB/S3 통합·실제 접수 reader/clock 연결은 검증하지 않았다. 이 결과는 RAM 산술 prototype의 검증이며 현재 서비스의 과부하 차단을 입증하지 않는다.

순수 Java21 함수의 세 검사는 다음 경계를 다룬다. 두 budget 독립성/정확한 reserve equality/1byte 부족, 미관측·불완전·future 1ns·stale 1ns, 음수·범위 초과·estimate/reserve overflow를 확인한다. same-ID 우회 flag가 API에 없음을 유지한다. 기존 DB/S3/동시성 통합 검사를 복제하지 않는다. 실제 reader·clock·접수 연결을 별도 검증하기 전 운영 안전·과부하 차단 완료로 표시하지 않는다.
