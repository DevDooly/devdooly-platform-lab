# 백업·시험 자료 보존과 자원 예산

보존 정책은 검증한 복구 자료를 지키면서 오래된 시험 자료의 정리 후보를 계산하기 위한 것이다. 현재 [순수 계획기](../../infra/maintenance/README.md)는 **dry-run만 지원**하며 삭제 실행기·자동 GC·S3 연결은 없다. 실제 정리 절차는 새로 만든 합성 PVC 하나에서 별도로 검증했다. [실행 근거와 측정 조건](../evidence/retention-resource-budget/README.md), [앞선 PVC 복원](../evidence/runtime-pvc-restore/README.md)을 함께 읽는다.

## 보존 단위와 기간

| 대상 | 유지 기준 |
| --- | --- |
| 검증한 백업 | `kind + compatibilityFamily`별 최신 완전한 검증본 최소 1개를 나이와 무관하게 유지 |
| 일·주별 백업 | 최근 7×24시간의 검증본 전부, UTC 최근 7개 날짜의 일별 최신본, 현재 ISO 주를 포함한 최근 4개 주의 주별 최신본 유지 |
| 완료한 runtime trial | 고정된 시험 완료 시각부터 최소 7일. 이후에도 소유·UID·백업·정상 중지·mount 없음·Retain을 모두 확인한 경우에만 후보 |
| 실패·불명·불완전·고정 자료 | 자동 후보에서 제외. 완료 시각·무결성·복구 의존성을 별도로 확인 |
| 별도 키·설정·자격증명 파일 | 항상 보호. 암호화 archive와 복호화 키를 같은 만료 단위로 삭제하지 않음 |
| 작업·raw·export 객체 | 상태·나이와 관계없이 전부 보호. 객체 GC는 아직 구현하지 않음 |

최신 runtime checkpoint는 Kafka/Garage PVC와 SQL·관련 설정의 복구 단위다. 이를 최신 K3s controller·Jenkins Home/키·이전 호환 DB의 백업 대신 사용하지 않는다. archive·manifest·검증 기록 등 필수 member를 완전한 그룹으로 관리하고 그룹 일부만 후보로 분리하지 않는다. trial이 참조하는 백업도 보호한다.

별도 평문 키/설정 파일과 암호화 archive 안에 포함된 복구용 사본은 collector가 구분한다. archive 안의 사본은 해당 복구 그룹의 완전성과 의존성 기준을 적용한다.

파일 이름이나 filesystem mtime으로 완료 시각을 추정하지 않는다. 일·주 대표본이 겹치면 하나의 백업에 여러 보존 이유가 붙으며, 위 규칙이 백업 수를 정확히 7개 또는 4개로 줄인다는 뜻은 아니다. inventory가 5분 초과 오래되면 후보를 억제한다. 상세 schema·선택 순서·명시적 가상 시각의 표시는 [계획기 계약](../../infra/maintenance/README.md)을 따른다.

2026-10-15 만든 runtime trial PVC 5개와 2026-10-11의 DB trial PVC 1개는 모두 7일 미만이므로 보호한다. 이전 DB trial은 다른 ownership label 체계를 사용하므로 현재 runtime trial 계약으로 자동 채택하지 않는다. 7일 경과만으로 삭제 가능해지는 자료도 아니다. 실제 보관 자료·백업을 이번 검증 때문에 삭제하거나 시각을 바꾸지 않았다.

07:34:16 UTC의 새 실제 inventory로 계획기를 실행해 검증한 local runtime checkpoint 1그룹과 아직 분류하지 않은 backup-root 항목 18개, trial 2그룹/6PVC를 보호했다. 백업·trial 삭제 후보는 각각 0개였고 기존 자료 삭제도 0개였다. 외부 AES-GCM 사본의 read-back과 키 사용 가능 여부를 확인해 local checkpoint 검증에 연결했지만 Windows 암호문 파일 자체가 서버 inventory에 포함됐다는 뜻은 아니다. 순수 계획기 테스트 31개와 실제 dry-run은 별도 결과로 기록한다.

## 작업과 객체의 보호 경계

`STAGING`, `QUEUED`, `COMPLETED + PENDING`은 원본·결과 또는 재시도에 필요한 자료가 남아 있는 상태다. `PAUSED_OPERATOR`, 불명 소유권·상태, 실행 슬롯 점유나 미확인 outbox도 정리 사유가 될 수 없다. `EXPORTED`는 저장 확인을 DB에 기록한 상태이며 삭제 허가가 아니다.

DB 참조·outbox와 Kafka 재전달·명시적 resume·객체 identity를 함께 다루는 tombstone/GC 프로토콜이 없다. 따라서 S3 객체·DB 작업 행을 나이만으로 지우거나 prefix 전체를 삭제하지 않는다. 공개 작업 관측 API의 파일 hash·크기는 DB의 예상값과 저장 확인 기록이며 현재 객체의 존재나 GC 가능성을 조회한 결과도 아니다.

## 실제 정리 검증의 좁은 범위

기존 trial을 만료시켜 시험하지 않고 **새 disposable namespace·64Mi 요청 PVC 하나·16KiB 합성 파일**을 만들었다. `purpose=cleanup-validation`, 고정 operation과 namespace/PVC/PV UID·실제 저장 경로를 기록했다. 원본 및 기존 trial 11개 볼륨과 경로가 겹치지 않음을 먼저 확인했다.

1. 고정 image의 비특권 bare Pod로 합성 파일을 쓰고 전체 bytes·SHA-256과 private 백업의 read-back을 대조했다. 외부 통신은 default deny로 막았다.
2. PVC 생성 직후 실제 시각의 `KEEP_UNEXPIRED`를 기록했다. 이 fixture에만 적용한 validation TTL은 60초이며 운영 trial의 7일 보존 기한과 분리했다. UTC·monotonic clock과 boot identity도 대조했다.
3. bare Pod를 UID 조건·30초 grace로 정상 종료하고 Pod 0·모든 namespace의 해당 mount 부재를 확인했다. PV는 claim 삭제 전에 Retain으로 지정했다.
4. 실제 만료 후 잘못된 UID의 DELETE가 HTTP 409로 거부되고 PVC가 그대로임을 확인했다. 올바른 UID로 fixture PVC만 삭제한 뒤 Released PV와 합성 파일이 남아 있음을 확인했다.
5. 해당 PV만 UID 조건으로 삭제했다. 검증된 파일 하나를 `O_NOFOLLOW`·directory fd 조건으로 unlink하고 빈 fixture 디렉터리만 rmdir했다. 재귀 삭제·강제 삭제·기존 자료 삭제는 하지 않았다. 마지막으로 소유한 namespace만 UID 조건으로 삭제했다.

실제 prepare 11개·cleanup 10개 검사를 통과했고 기존 PVC/PV 11개·원본 Pod 6개·Docker 38개를 보존했다. 이 결과는 정리 절차의 별도 실험이며 운영 dry-run 계획을 자동 실행한 결과가 아니다. Retain PVC 또는 namespace를 삭제해도 디스크가 자동 회수된다고 해석하지 않는다. [Kubernetes PV 회수 정책](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#reclaiming)

## 자원 예산과 측정 방법

기존 CPU·memory limit 설정을 바꾸지 않고 먼저 실제 cgroup v2의 `cpu.max`·`memory.max`와 선언을 비교한다. 자원 측정은 무거운 CI와 겹치지 않는 조건에서 idle 구간과 고정 12개 입력의 순차 작업 3회로 제한한다. 최대 1,000개 입력·동시 부하·디스크 채우기·OOM 유도·과부하 시험은 이 범위에 포함하지 않는다. 공개 실행도 열지 않는다.

| 값 | 기록할 의미 |
| --- | --- |
| CPU 평균 | 구간의 `cpu.stat usage_usec` 증가량 / 실제 경과 시간. CPU 1개 사용을 100%로 표현 |
| 관측 CPU 최대 | 약 1초 간격의 샘플 구간별 평균 중 최대. 순간 peak나 처리 용량의 상한이 아님 |
| `memory.current` | cgroup의 현재 전체 메모리. process RSS/PSS와 같은 값이 아님 |
| process RSS/PSS | 주 프로세스의 resident/proportional set. shared memory 계산 방식을 구분 |
| `memory.peak` | 이번 절차에서 reset하지 않은 cgroup 생성 이후의 누적 최고치. 측정 구간의 최고치와 구분 |
| OOM | `memory.events`의 전후 증가량과 종료 상태. OOM이 없었다는 사실이 한도 스트레스 검증은 아님 |
| 디스크 | PVC 실제 allocated/apparent bytes와 host 여유를 기록. 요청량·백업 크기·실제 증가량을 구분 |

CPU limit은 throttling으로 적용되고 memory limit은 OOM 처리와 연결된다. 낮은 부하에서 선언과 cgroup 설정이 같음을 확인하는 것과 한도에 도달한 동작을 시험하는 것은 다르다. [Kubernetes CPU·memory 제한](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/#requests-and-limits), [Linux cgroup v2 CPU·memory](https://docs.kernel.org/admin-guide/cgroup-v2.html)

`requests.storage` quota는 PVC 요청량 합계를 제한한다. local-path PVC의 요청 64Mi나 trial 요청합 29Gi를 filesystem의 강제 사용량 제한으로 표현하지 않는다. 현재 자료는 실제 디스크 점유량과 여유를 함께 확인해야 한다. [Kubernetes 저장소 quota](https://kubernetes.io/docs/concepts/policy/resource-quotas/#storage-resource-quota)

## 2026-10-15 제한된 실제 관측

기존 6개 상시 container의 실제 cgroup v2 CPU·memory 설정이 선언과 일치했다. 설정이나 image/source를 바꾸지 않고 idle 약 15초와 순차 작업 구간 약 47초, 총 약 63초·64개 샘플을 관측했다. 고정 입력 12개를 세 번 추가해 총 6개 EXPORTED 작업·파일 정보 12개·Kafka offset 6/log end 6/lag 0이 됐다. 기존 작업 3개의 기록은 유지했으며 raw 6개·export 12개 전체 GET도 별도로 확인했다. transient stage container 자체의 CPU·메모리는 측정하지 않았고 host 값에는 다른 서비스와 stage의 영향이 포함된다.

| 관측값 | 실제 결과 |
| --- | --- |
| worker 작업 구간 평균 CPU / 약 1초 관측 최대 | 0.04235 core / 0.66622 core, 기존 limit 1 core |
| worker 작업 구간 `memory.current` 최대 | 253.215MiB, 기존 limit 768MiB |
| worker process RSS / PSS 관측 최대 | 273.75MiB / 262.80MiB |
| Kafka / API `memory.current` 관측 최대 | 451.23MiB / 270.31MiB, 기존 limit 2GiB / 768MiB |
| host `MemAvailable` / 디스크 여유 관측 최소 | 약 17.35GiB / 206.76GiB |
| DB `createdAt → exportCompletedAt` 평균 / 최대 | 1.5943초 / 2.7451초 |
| stage 요청 → export 기록 평균 / 최대 | 14.0757초 / 15.3947초, cold stage 시작 비용 포함 |

관측 중 abort·OOM counter 증가·host swap I/O 증가·container swap 증가·기존 workload 재시작은 없었다. 기존 host의 swap 사용량 전체가 0이라는 뜻은 아니다. worker의 CPU throttling은 237개 period 중 12개·누적 431,612µs 증가했다. 이를 요청 지연 0.431612초로 환산하지 않는다. 약 1초 샘플의 최대가 1 core보다 낮아도 더 짧은 quota 구간의 throttling을 놓칠 수 있다.

실제 디스크 전후 snapshot은 07:15:14~07:26:19 UTC의 약 11분으로 자원 샘플 구간보다 넓다. active Lab PVC 4개의 allocated bytes는 995,328 bytes(972KiB) 증가했고 보관 중인 runtime trial PVC 5개는 증가량 0이었다. 백그라운드 heartbeat·WAL 등의 영향을 포함하므로 이를 작업당 순수 디스크 증가량으로 나누지 않는다. 상세 원문·개별 지연·회계식은 [근거](../evidence/retention-resource-budget/README.md)에 보존한다.

07:40:32 UTC의 최종 보존 검사 25개도 통과했다. 기존 PVC/PV 11개·원본 Pod 6개·Docker 38개/실행 26개, 기존 작업의 SQL·시각과 원본 객체 9개의 전체 bytes를 유지했다. 새 세 작업에 해당하는 허용 행을 제외한 기존 6개 업무 테이블을 대조했고 실행 중 journal은 비교에서 구분했다. timer의 정적 설정·주기와 enabled/active, host boot·방화벽도 보존했다. timer unit bytes 또는 service 실행 파일 전체를 대조한 결과로 확대하지 않는다.

## 지연을 읽는 기준과 후속 범위

`createdAt → exportCompletedAt`은 원본 준비와 대기를 포함한 DB 기록 구간이다. `queuedAt → completedAt`의 처리 구간과 `completedAt → exportCompletedAt`의 export 구간을 별도로 제시한다. 내부 stage 명령의 총 wall time에는 JVM 시작·설정·접수 비용도 들어가므로 이 값들을 같은 지연으로 섞지 않는다.

고정 fixture 3회는 작은 실제 관측 표본이다. 처리량·p95·SLA나 최대 입력의 성능 보장으로 확대하지 않는다. 상세 수치는 [측정 원본과 한계](../evidence/retention-resource-budget/README.md)에 실제 통과 결과만 기록한다. 후속은 진행 중 장애·최대 입력/동시성 검증, 검증된 객체 GC 프로토콜과 장기간 운영이다.
