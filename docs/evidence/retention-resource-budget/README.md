# 보관 정책·자원 예산 실제 검증

2026-10-15 미니 PC에서 삭제 없는 보관 계획을 계산하고, 기존 limit을 유지한 채 고정 합성 입력 12개를 세 번 처리했습니다. 별도 새 시험 PVC의 정리 검증도 수행했으며 마지막 원본 보존 검사 25/25를 통과했습니다. 기존 백업·보관 PVC·작업 데이터는 삭제하지 않았습니다.

[허용 필드 결과](summary.json) · [운영 기준](../../runbooks/retention-resource-budget.md) · [순수 계획기·입력 계약](../../../infra/maintenance/README.md) · [앞선 PVC 복원](../runtime-pvc-restore/README.md)

## 실제 자료의 보관 계획

실제 `SYSTEM_UTC` 시각 2026-10-15T07:34:16.228362257Z와 5분 이내의 inventory로 CLI를 실행했습니다. 복구 호환 단위별 최신 검증본 최소 1개, 최근 7×24시간·일별 7개 날짜·주별 4개 구간, trial 완료 후 최소 7일을 적용했습니다. 키·설정·자격증명과 작업/raw/export는 항상 보호합니다.

| 실제 입력·결과 | 수량 |
| --- | --- |
| 검증한 로컬 runtime checkpoint 그룹 | 1, 보호 |
| 아직 복구 단위로 분류하지 않은 백업 root 항목 | 18, 모두 보호 |
| 보관 중인 trial 그룹 / PVC | 2 / 6, 모두 보호 |
| 백업 / trial 삭제 후보 | 0 / 0 |
| 기존 백업 / 기존 trial PVC 삭제 | 0 / 0 |

이 inventory의 검증본은 **서버의 로컬 checkpoint 묶음**입니다. 앞선 외부 AES-256-GCM 인증·복원 근거와 연결되지만, Windows에 보관한 암호화 파일 자체를 이번 서버 inventory에 넣거나 새로 백업한 결과는 아닙니다. 이후 추가한 작업 3개까지 포함한 새 checkpoint를 만들었다고 주장하지 않습니다.

계획기는 파일·Kubernetes·S3에 접근하지 않는 순수 함수이며 `apply`나 삭제 실행기가 없습니다. 31개 테스트에서 일/주 경계, 나노초 정렬, 최신 검증본, 불완전/불명/고정 자료, symlink·경로 중첩·원본 UID·mount·claimRef·키·clock 조건과 CLI를 검증했습니다. Windows 로컬과 실제 Ubuntu `python3`에서 각각 31개 모두 통과했으며 Ubuntu skip은 0개입니다. 별도로 Python 3.10 문법을 확인했습니다. 합성 입력의 오래된 완전한 백업과 정지 trial이 후보가 되는 사례는 **오프라인 정책 검사**입니다. 실제 자료의 완료 시각을 바꿔 만료시키지 않았습니다.

## 별도 disposable PVC 정리

기존 보관 자료와 분리한 새 시험 PVC에 16,384 bytes 합성 파일을 만들었습니다. 이 실험에만 TTL 60초를 적용해 최초 `KEEP_UNEXPIRED`, 실제 만료 뒤 `DELETE_ELIGIBLE_VALIDATION_ONLY`를 확인했습니다. prepare 11/11, cleanup 10/10 검사가 통과했습니다.

이때 수행한 삭제는 새 합성 검증 자원에 한정됩니다. 기존 PVC/PV 11개, 원본 Pod 6개와 Docker 38개(실행 26개)를 보존했습니다. 운영의 7일 정책을 60초로 줄이거나 보관 계획의 후보를 실행한 결과가 아닙니다. UID 조건·Retain/Released·실제 저장 파일의 정리 순서는 [운영 기준](../../runbooks/retention-resource-budget.md)을 따릅니다.

## 실제 limit과 제한된 자원 관측

6개 상시 container의 실제 cgroup v2 `cpu.max`·`memory.max`가 Kubernetes 선언과 일치했습니다. limit·image/source는 변경하지 않았습니다. summary의 `sourceCommit`은 실행 중인 API/worker 이미지의 소스이며, 새 계획기와 정책은 `plannerSha256`·`policySha256`로 별도 식별합니다. JVM 세 서비스의 RSS/PSS 읽기와 cgroup CPU·throttle·memory·OOM·swap 관측이 가능했습니다. 초기 probe는 5/5 검사를 통과했습니다.

idle 약 15초·16개 샘플, 작업 구간 약 47초·48개 샘플, 전체 약 63초·64개 샘플입니다. CPU는 `usage_usec` 증가량을 실제 시간으로 나눈 core 단위이며 관측 최대는 약 1초 구간별 평균의 최대입니다. `memory.current`는 cgroup 전체 메모리로 process RSS/PSS와 구분합니다.

| 상시 container | CPU / memory limit | idle 평균 CPU | 작업 평균 CPU | 작업 관측 CPU 최대 | 작업 memory.current 최대 |
| --- | --- | --- | --- | --- | --- |
| api | 1 / 768MiB | 0.01373 | 0.02385 | 0.17114 | 270.309MiB |
| web | 0.25 / 192MiB | 0.00019 | 0.00017 | 0.00072 | 10.309MiB |
| database | 1 / 1536MiB | 0.00850 | 0.01466 | 0.06933 | 151.871MiB |
| kafka | 2 / 2048MiB | 0.01108 | 0.01496 | 0.04605 | 451.234MiB |
| garage | 1 / 1536MiB | 0.00020 | 0.00128 | 0.01167 | 6.477MiB |
| worker | 1 / 768MiB | 0.00280 | 0.04235 | 0.66622 | 253.215MiB |

worker의 작업 구간 RSS 최대는 273.75MiB, PSS 최대는 262.80MiB였습니다. `memory.peak`는 reset하지 않은 container 수명 누적값이며 작업 구간 표의 샘플 최대와 별도로 summary에 보관합니다. worker는 237개 CPU period 중 12개·누적 431,612µs의 throttling 증가가 있었습니다. 한도보다 짧은 구간의 CPU burst와 약 1초 평균이 다를 수 있으며, throttled time을 요청 지연으로 환산하지 않습니다.

관측 중 abort와 기존 workload 재시작은 없었고 모든 상시 container의 OOM·OOM kill 증가량은 0입니다. 전체 구간 host `MemAvailable` 최소는 약 17.35GiB, 디스크 여유 최소는 약 206.76GiB였습니다. 일시 stage container의 개별 CPU·메모리는 측정하지 않았고 host 값에는 stage와 기존 다른 서비스가 함께 포함됩니다. 이는 최대 부하·OOM 유도·처리량·p95·SLA 검증이 아닙니다.

## 처리·저장 결과와 지연

새 고정 fixture 3회는 입력 12개씩의 순차 실행입니다. 각 작업은 성공 7·실패 3·업무상 중복 2·대기 0으로 EXPORTED가 됐고 Kafka committed offset 6 = log end 6, lag 0을 확인했습니다. 자동 재접수·기존 workload 재시작·limit 변경은 없었습니다. 측정 helper의 자체 검사 10/10을 통과했습니다.

| 시간 구간 | 평균 | 최대 |
| --- | --- | --- |
| DB createdAt → completedAt | 1.3344초 | 2.1931초 |
| queuedAt → completedAt | 0.6383초 | 1.4589초 |
| completedAt → export 저장 확인 기록 | 0.2599초 | 0.5520초 |
| DB createdAt → export 저장 확인 기록 | 1.5943초 | 2.7451초 |
| stage 요청 → export 저장 확인 기록 | 14.0757초 | 15.3947초 |

stage 요청 기준에는 cold JVM·설정·접수 비용이 포함되므로 DB 생성 이후의 지연과 섞지 않습니다. 세 번의 작은 표본만으로 일반적인 처리 용량이나 응답 시간 분포를 추정하지 않습니다.

DB의 저장 확인 기록과 별도로 S3를 새 GET 18회 읽었습니다. 기존 raw 3개·export 6개는 전체 bytes가 그대로였고, 새 raw 3개·export 6개도 전체 bytes를 검증했습니다. GET 검사 helper는 객체를 쓰지 않았습니다. 완료한 일시 stage Job 3개만 제거했고 DB 작업 행과 저장 객체는 보존했습니다.

## 디스크와 최종 보존 범위

디스크 snapshot은 07:15:14.015253~07:26:19.185023 UTC로 약 11분입니다. 약 63초의 자원 샘플 구간과 다릅니다. active Lab PVC의 allocated bytes는 995,328 bytes 증가했고 보관 중인 runtime trial PVC는 증가량 0입니다. 새 객체 9개의 논리 크기는 합계 14,727 bytes입니다. 백그라운드 heartbeat·WAL 등의 쓰기를 포함하므로 디스크 증가량을 작업당 순수 저장 비용으로 나누지 않습니다. PVC 요청 용량을 filesystem 강제 한도로 해석하지 않습니다.

2026-10-15T07:40:32.846315Z의 마지막 보존 검사 25/25가 통과했습니다. 기존 PVC/PV 11개·원본 Pod 6개·Docker 38개(실행 26개)를 유지했고, 기존 작업 3개의 SQL을 새 작업 행과 분리해 비교했습니다. 총 6개 EXPORTED 작업·파일 정보 12개, Kafka offset 6/log end 6/lag 0을 확인했습니다. 마지막 helper는 리소스를 삭제하거나 limit을 바꾸지 않았으며 S3 GET은 앞선 별도 18회 검증 결과입니다.

관측 timer의 기존 주기 설정과 enabled·active 상태를 유지했습니다. unit 파일 전체 bytes와 service ExecStart를 사전 값과 대조한 검증은 이번 최종 검사에 포함하지 않았습니다. 실제 접속 주소·host 저장 경로·PID·UID·자격증명·private SQL과 원본 보고서는 공개하지 않습니다. 장기 보관·키 회전, 최대 입력·동시 부하, 작업 객체 GC와 운영 자료 삭제 실행기는 후속 범위입니다.
