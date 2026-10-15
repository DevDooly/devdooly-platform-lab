# 최대 입력·동시 접수와 격리 Linux 자원 관측

2026-10-15. V1 12건을 유지하면서 V2 고정 합성 입력 1,000건을 추가했습니다. 기본 검증 140개, 실제 기능 IT 5개와 별도 Linux 실행 검사 10/10을 통과했습니다. 기능 IT의 Windows JVM과 Linux의 제한 자원 실행을 나누어 기록합니다. **이번 결과는 후보 코드의 격리 검증이며 기존 K3s 운영에 V2를 배포한 결과가 아닙니다.**

[허용 필드 요약](summary.json) · [ADR 0010](../../adr/0010-versioned-bounded-input.md) · [재현 절차](../../runbooks/maximum-input-concurrency.md) · [기존 운영의 작은 입력 관측](../retention-resource-budget/README.md)

## 소스와 실행 범위

후보 소스는 [`5a1495be4973d43b34dc5c169dbf66bec7459968`](https://github.com/DevDooly/devdooly-platform-lab/commit/5a1495be4973d43b34dc5c169dbf66bec7459968)이고, 실제 Linux에서 실행한 JAR의 SHA-256은 `ac13f7045eba661d2e90c15b7df661c6fde7039311d0a067010981914664ddc9`입니다. Git SHA와 JAR bytes 지문을 구분하며 이 지문을 OCI image digest로 표시하지 않습니다. 해당 소스의 [branch CI 38704327628](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38704327628)이 성공했고 [초안 PR 27](https://github.com/DevDooly/devdooly-platform-lab/pull/27)로 검토합니다. CI 성공은 운영 배포 성공을 의미하지 않습니다.

실제 연결은 기존 운영과 분리한 Docker project·internal network·전용 DB/bucket/topic/volume입니다. host published port는 만들지 않았습니다. 기능 IT는 Windows Java 21·Asia/Seoul에서 numeric loopback/SSH tunnel로 Linux의 MariaDB 11.8.9·Kafka 4.3.1·Garage 2.4.1에 연결했습니다. 별도 Linux 실행은 같은 후보 JAR의 명시적 `run` worker와 세 번의 `stage` CLI를 사용했습니다. 고정된 시험 backend 주소를 명시적 hosts mapping으로 연결한 Docker 시험이며 K3s 서비스 DNS나 후보 image의 운영 배포를 검증한 것은 아닙니다.

기본 seed와 stage 기본값은 V1 12건입니다. V2도 임의 입력이 아닌 공개 합성 내용·순서가 고정된 1,000건입니다. 원본 전체 1 MiB, 결과/실패 문서 각각 4 MiB, Kafka 포인터 1,024 bytes 상한과 export 저장 확인까지의 단일 슬롯을 유지했습니다. 공개 실행 POST·HTTP 관리자 명령·요청률 제한기는 추가하지 않았습니다.

## Windows 드라이버의 실제 기능 IT

`MaximumInputConcurrencyIT`의 5개 사례 모두 실패·오류·skip 없이 통과했습니다. 실제 상시 runner/actions를 별도 JVM 프로세스로 실행했고 DB·Kafka·S3와 HTTP를 대조했습니다.

| 사례 | 실제 결과 |
| --- | --- |
| 정확히 1 MiB인 V2 원본 3회 + V1 1회 | 동일 daemon에서 각각 별도 접수·EXPORTED·슬롯 해제. V1 SQL·시각 보존, outcome 3,012개·export 파일 8개, committed 4/log end 4/lag 0 |
| 서로 다른 run 2개 동시 접수 | 승인 1·슬롯 충돌 1. 패자의 DB 작업·outbox·S3 원본 0. 승인 작업 1,000건·export 2개 |
| 서로 다른 run 8개 동시 접수 | 승인 1·슬롯 충돌 7. 같은 패자 무부작용 확인. 승인 작업 1,000건·export 2개 |
| 경계 초과·버전 불일치 | 1,001건·1,048,577 bytes·V1 선언/V2 내용의 세 호출을 접수 전에 거부. 작업·outbox·원본·결과 0, 빈 슬롯·log end 0 |
| 재요청·충돌·다음 슬롯 | 같은 원본의 행·시각 보존, 다른 hash와 이미 관측된 손상 원본의 자동 덮어쓰기 거부. 이전 완료 작업의 재요청/export가 다음 슬롯을 해제하지 않음. 두 작업 완료·export 4개·committed/log end 2/2 |

최대 입력 사례는 원본과 두 export 파일의 전체 GET bytes·크기·SHA-256을 검증하고 실제 HTTP의 완료 건수·파일 근거·빈 슬롯을 확인했습니다. group 없는 직접 할당 consumer와 auto commit 비활성으로 Kafka 포인터를 읽고 기존 offset 보존도 대조했습니다. 관측 HTTP 자체가 현재 S3 객체를 다시 검증한다는 뜻은 아닙니다.

동시 접수에서는 worker를 먼저 소비시키지 않고, 승자가 DB 접수를 commit한 뒤 외부 저장 경계에서 대기해 슬롯 점유를 유지했습니다. barrier는 DB connection 획득 전에 두었고 기존 pool 5개를 늘리지 않았습니다. 이는 슬롯의 burst 접수 경계입니다. 초당 요청 제한·공개 HTTP 부하·다중 작업 동시 처리 용량을 검증한 것이 아닙니다. 손상 객체의 복구는 소유 시험 fixture의 명시적 조치였으며 애플리케이션 자동 복구로 기록하지 않습니다.

V1 원본과 고정 시각의 export bytes/hash/key는 변경 전 지문으로 확인했습니다. 이전 코드가 V2까지 읽거나 처리할 수 있다는 전방 호환성은 없습니다. 운영에서 첫 V2 작업을 접수하려면 API와 worker를 모두 지원 image로 갱신해야 합니다.

## Linux에서 같은 자원 제한으로 세 번 실행

전용 Linux worker에 **CPU 1 core·memory 768 MiB**, memory와 같은 swap limit을 적용했습니다. 같은 worker를 유지하며 cold JVM의 별도 내부 stage CLI로 V2 작업을 세 번 순차 접수했습니다. 각 작업은 1,000/500/300/200/0으로 EXPORTED가 됐고, 전체 결과 3,000개·outbox 6개·pending 0·빈 슬롯·Kafka committed 3/log end 3/lag 0을 확인했습니다. 자동 재접수나 worker 교체는 없었습니다. 자체 검사 10/10과 2026-10-15T08:29:29.040531Z의 성공 보고를 확인했습니다.

Linux에서 사용한 원본은 각 **99,600 bytes**입니다. 1,000건 최대 개수와 자원 제한을 검증한 것이며, 정확히 1 MiB인 원본 세 번은 앞선 Windows 기능 IT의 별도 결과입니다. 두 조건을 하나의 Linux 최대 bytes 부하 시험으로 합치지 않습니다.

S3를 새 GET 9회 읽어 raw 3개와 결과/실패 6개의 전체 bytes·크기·SHA를 확인했습니다. 각 raw는 99,600 bytes, 결과는 157,909 bytes, 실패 파일은 88,185 bytes였습니다. 결과의 1,000개 판정과 실패 300개의 입력/rawLine을 독립 기대값 및 DB와 대조했습니다. 결과에는 작업 ID·시각이 들어가므로 크기가 같아도 서로 다른 작업의 결과 SHA가 같다고 가정하지 않습니다.

## CPU·메모리와 지연

관측은 worker 한 container와 그 Java process를 대상으로 했습니다. 시작 전/후 idle을 각각 약 15초 계획했고, 실제 샘플의 첫 시각부터 마지막 시각까지를 계산했습니다. 전체 72개 샘플·74.38567705초, workload 43개 샘플·44.055114877초입니다. 단계별 첫/마지막 샘플 사이 간격은 경계 구간을 제외하므로 단계 시간을 단순 합산해 전체 시간으로 사용하지 않습니다.

| 샘플 구간 | 개수 / 실제 기간 | 평균 CPU cores | 약 1초 구간 평균의 관측 최대 | memory.current 관측 최대 |
| --- | --- | --- | --- | --- |
| idle 전 | 15 / 14.6315초 | 0.01994 | 0.07823 | 249,430,016 bytes |
| workload | 43 / 44.0551초 | 0.10111 | 0.95030 | 274,259,968 bytes |
| idle 후 | 14 / 13.5981초 | 0.00786 | 0.01136 | 274,460,672 bytes |
| 전체 | 72 / 74.3857초 | 0.06554 | 0.95030 | 274,460,672 bytes(261.746MiB) |

CPU는 cgroup `usage_usec` 증가량을 실제 경과 시간으로 나눈 core 단위입니다. workload에서 CPU period 295개 중 throttled period 38개·throttled time 2,902,705µs 증가가 있었습니다. 전체는 485개 중 39개·2,903,281µs입니다. throttled time을 작업 지연으로 환산하지 않으며 관측 최대는 순간 peak가 아닙니다.

전체 구간 Java RSS/PSS 관측 최대는 각각 279,965,696 / 279,961,600 bytes였습니다. `memory.current`는 cgroup 메모리이고 RSS/PSS는 process 지표이므로 서로 같은 값이나 같은 범위로 해석하지 않습니다. reset하지 않은 수명 누적 `memory.peak`는 시작 250,155,008 → 끝 275,161,088 bytes였으며 샘플 최대와 별도로 기록합니다. OOM·OOM kill 증가량은 0이고 host 여유·swap abort 조건은 발생하지 않았습니다. 일시 stage container의 개별 자원은 측정하지 않았으며 host 여유에는 기존 서비스와 stage가 함께 포함됩니다.

| 지연 구간 / 표본 3개 | 평균 | 최대 |
| --- | --- | --- |
| DB 작업 생성 → export 저장 확인 기록 | 2.193894초 | 3.584745초 |
| cold stage 요청 → DB 작업 생성 | 11.915178초 | 12.127927초 |
| cold stage 요청 → export 저장 확인 기록 | 14.109072초 | 15.224021초 |
| cold stage 요청 → 완료·파일 검증 관측 | 14.896443초 | 16.094075초 |

DB 작업 생성 이후 지연에는 원본 확인·대기·처리·export가 포함됩니다. cold stage 요청 기준에는 JVM 시작·설정·접수 비용도 포함되며 마지막 관측 기준에는 조회와 파일 검증 비용이 더해집니다. 세 번의 순차 실행으로 처리량·최대 수용량·p95·SLA를 추정하지 않습니다. 장기 운전·진행 중 crash·최대 입력의 동시 처리·공개 과부하 시험도 이번 범위가 아닙니다.

## 디스크와 원래 운영 보존

시험 Docker 볼륨의 allocated bytes snapshot은 **08:27:19.399706 → 08:29:48.158030 UTC, 148.758324초**입니다. 74.3857초의 CPU/메모리 샘플 구간과 다릅니다.

| 시험 볼륨 | 전 → 후 allocated bytes | 증가량 |
| --- | --- | --- |
| DB | 181,809,152 → 181,809,152 | 0 |
| Kafka | 937,984 → 983,040 | 45,056 |
| Garage metadata | 4,825,088 → 4,853,760 | 28,672 |
| Garage data | 147,456 → 225,280 | 77,824 |
| 합계 증가 | — | 151,552 |

DB 사전 할당 안에서 데이터가 늘 수 있으므로 allocated 증가량 0을 데이터 증가 없음으로 표시하지 않습니다. 이 구간은 metadata·background writes·이전 기능 IT 정리의 tombstone 영향 등을 포함하며 작업당 순수 저장 비용이 아닙니다. 새 객체 9개의 논리 크기는 합계 1,037,082 bytes로 allocated bytes와 구분합니다.

원래 운영의 source는 계속 `ed5815e7d72c6ea4f52456d902b7407c7a4a67b0`입니다. 08:18:30.569875 UTC의 baseline 16/16과 08:29:48.470378 UTC의 final 21/21을 통과했습니다. 원래 Docker 38개(실행 26개)의 상태·시작 시각·정규화한 mount, Ready Pod 6개·PVC/PV 11개의 동일성, 업무 SQL 6개 테이블의 전체 행·시각, EXPORTED 작업 6개·파일 정보 12개를 보존했습니다. 이 최종 보존 helper는 원래 객체를 새 GET하지 않았으며, 이번 GET 9회는 시험 환경의 새 객체에만 해당합니다.

시험 worker와 stage container 3개는 정상 종료해 정지 상태로 보관했습니다. 시험 backend 3개는 실행 상태로 남겼고 모든 시험 데이터·볼륨을 보존했습니다. container/volume 삭제나 객체 GC는 수행하지 않았습니다. `remainingOwnedRunningCount: 0`은 실행 드라이버가 관리한 worker/stage 범위이며 backend까지 모두 정지했다는 뜻이 아닙니다.

## 준비 실패와 공개 범위

첫 기능 시험 준비에서는 실제 `SOURCE_COMMIT` 미주입으로 S3/Kafka 시험 client 생성 전에 설정 검사가 실패했습니다. Linux 준비에서는 image RepoDigest의 tag 문자열 비교가 맞지 않아 읽기 검사에서 한 번 중단됐습니다. 실제 source 주입과 고정 digest 대조로 각각 준비를 바로잡았으며 이 두 실패에서 workload 작업을 접수하지 않았습니다. 이를 실패한 작업을 숨기거나 자동 재접수해 성공시킨 결과로 표시하지 않습니다.

공개 요약은 source·artifact 지문, 시간·수량·제한·메트릭·판정만 선택했습니다. 접속 주소·host 경로·IP·PID·cgroup 경로·credentials·환경 변수 값·실행 명령 원문·SQL 원문·private 보고서는 공개하지 않습니다. 현재 운영의 V2 반영, 공개 관측 게시와 source/image 일치는 별도 배포 근거에서 검증해야 합니다.
