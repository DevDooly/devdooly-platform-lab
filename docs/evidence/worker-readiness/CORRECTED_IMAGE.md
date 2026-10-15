# 수정 이미지의 canary와 배포 진행

2026-10-15 14:54:11 UTC까지의 후속 기록입니다. [첫 실패와 SGID 진단](README.md)은 당시 결과 그대로 보존합니다. 이번에는 **수정 이미지의 격리 canary 10개 사례, 실제 Ready 전환·owning process 준비 상태와 배포 후 보존을 확인했습니다. 고정 12개 입력을 접수한 뒤 grace 300초를 지정해 유휴 worker를 교체하고, 같은 ID의 읽기 전용 재시도와 임시 credential 회수까지 통과했습니다.** 이전 worker의 exit는 관측하지 못했으며 정상 종료를 추정하지 않습니다.

## 수정 소스를 실제 이미지에 연결했습니다

[PR #43](https://github.com/DevDooly/devdooly-platform-lab/pull/43)의 Linux CI는 API 180개·독립 예제 20개, 총 200개를 실패·오류·skip 없이 실행했습니다. 같은 변경을 포함한 main 소스 `3e0d85be`의 Jenkins build 39도 JUnit 합계 200개와 필수 산출물·소스 정보를 확인해 성공했습니다. [실제 Linux CI](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38746521878)와 운영 이미지 소스는 공개 요약에서 구분합니다.

새 이미지의 익명 registry 조회·K3s cache·실제 OCI class 검사는 5/5를 통과했습니다. 별도 probe class와 같은 이미지의 app.jar 내부 class 바이트가 같고 Java classfile major가 65임을 확인했습니다. CI JAR의 class와 동일하다고 추정하지 않았습니다. API·웹 모두 같은 소스의 digest로 고정했으며, 이 prefetch 단계는 Pod나 운영 데이터를 변경하지 않았습니다.

## 열 개 사례는 파일 프로토콜을 검증했습니다

14:22:40 UTC에 수정 이미지의 별도 canary가 10개 사례를 모두 통과했습니다. 첫 실패와 이후 진단 근거를 보존한 같은 격리 namespace에서 새 Job만 만들었습니다. 테스트는 PID 1·UID 10001과 fsGroup/emptyDir 조건을 사용하고, 이미지에 실제 포함된 probe class를 별도 JVM으로 실행했습니다.

| 사례 | 기대한 결과 |
| --- | --- |
| writer STARTING | probe가 거부 |
| writer READY/EXPORT | probe가 허용 |
| 다른 source·시작 ticks·PID | 각각 거부 |
| 만료 시각·잘못된 mode·손상 record | 각각 거부 |
| terminal 뒤 committed·starting | 각각 Ready 재게시 없이 거부 |

READY/EXPORT는 DB commit 없이 합성 callback을 호출한 파일 검증입니다. 만료 사례는 과거 boot timestamp를 쓴 합성 record이며 240초를 실제로 기다린 결과가 아닙니다. 시작 ticks 불일치도 실제 worker 재시작이 아닙니다. DB·lease·Kafka·S3에 연결하지 않았고 운영 health 파일을 바꾸지 않았습니다. 종료한 자체 Pod와 Job은 UID로 정리했으며 남은 수는 각각 0개입니다. 첫 실패 결과는 변경하지 않았습니다.

각 probe 실행 중 관측한 자원은 다음과 같습니다. Java 21 child는 heap 8~16MiB·Serial GC·ActiveProcessorCount 1로 실행했습니다. 모두 한 번씩 실행한 10개 사례의 범위이며, 정상 장기 worker에 주기적으로 probe를 넣었을 때의 비용이나 처리 용량을 측정한 값은 아닙니다.

| 관측값 | 실제 범위 또는 최대 |
| --- | ---: |
| probe 한 번의 wall time | 83.525~205.318ms |
| 마지막 생존 표본의 CPU 시간 | 30~130ms, 최종 CPU 시간의 하한 |
| RSS 표본 최대 | 42,770,432B, 약 40.789MiB |
| PSS 표본 최대 | 26,326,016B, 약 25.106MiB |

RSS/PSS는 실행 중 표본의 최대이며 lifetime peak가 아닙니다. 샘플 수는 사례마다 4~9개였고 OOM 증가가 없었습니다. JVM heap 상한을 RSS 상한으로 읽거나 이 짧은 관측을 p95·SLA로 환산하지 않습니다.

## API·웹부터 전환하고 worker를 관측하기 시작했습니다

배포 전 검사는 기존 운영 자료 보존 21/21과 기존 객체 21개의 전체 GET을 통과했습니다. 이어 [PR #44](https://github.com/DevDooly/devdooly-platform-lab/pull/44)의 API·웹 전환을 반영했습니다. 14:35:15 UTC의 검사에서 실제 이미지·소스를 확인했고 보존 검사 25/25와 같은 21개 객체의 전체 바이트 비교를 통과했습니다. 이 중간 단계의 worker는 이전 소스로 계속 실행됐습니다. 기존 7개 작업·파일 정보 14개·업무 SQL과 원본 서비스도 유지됐습니다.

worker를 바꾸기 전에는 읽기 전용 watch를 먼저 시작했습니다. 14:42:26 UTC의 확인 도구는 watch가 실제로 읽은 이전 worker의 식별자·전체 상태 hash, 실제로 살아 있는 관측 PID와 시작 정보·명령, source·APIweb 근거 연결을 대조했습니다. 시작 표식은 신선했고 당시 이전 worker는 같았으며 watch 결과 파일도 아직 없었습니다. 이후 14:42:42 UTC에 [PR #45](https://github.com/DevDooly/devdooly-platform-lab/pull/45)의 worker-only 설정을 반영했습니다.

14:46:33 UTC에 실제 watch도 2/2를 통과했고 NotReady→Ready를 관측했습니다. 이 watch는 전체 객체 GET이나 전체 자료 보존 검사를 하지 않았습니다. 같은 process의 owning-stage commit·RUNNING·fresh heartbeat와 기존 SQL·객체·리소스 보존은 이어지는 after 검사로 확인합니다.

14:48:08 UTC의 after 검사는 단계 검사 2/2·보존 검사 23/23과 기존 객체 21개의 전체 GET·바이트 비교를 통과했습니다. source·실제 OCI/CRI·process 식별자·owning journal의 RUNNING과 신선한 heartbeat를 함께 확인했고, 기존 7개 작업·업무 SQL·원본 리소스를 보존했습니다. after 결과의 `readyTransitionObserved:false`는 그 단계에서 새 전환을 다시 관측하지 않았다는 뜻입니다. 앞선 watch에서 관측한 전환과 구분하며, Ready 실패로 해석하지 않습니다.

## 유휴 worker 교체와 같은 ID의 읽기 전용 재시도

후속 검사는 14:52:10 UTC에 10/10을 통과했습니다. 내부 명령으로 새 V1 합성 입력 12개를 한 번 접수했고 성공 7·실패 3·중복 2·대기 0으로 export를 마쳤습니다. 실제 DB 정책의 승인 시각과 다음 허용 시각에 30초가 부과됐으며 전체 작업은 8개·export 파일은 16개가 됐습니다.

작업이 끝나 슬롯이 빈 상태에서 이전 worker의 UID를 지정하고 grace 300초를 요청해 한 번 교체했습니다. 새 Pod의 NotReady→Ready와 같은 이미지의 준비 상태 복구를 관측했습니다. 이전 컨테이너 exit는 `UNOBSERVED`이며 exit 0/143이나 SIGTERM 정상 종료의 근거가 없습니다. 작업이 진행 중인 worker나 호스트를 중단한 실험도 아닙니다.

이어서 실제 Garage ACL을 읽어 확인한 단일 버킷 RO credential로 같은 ID를 다시 제출했습니다. read만 허용하고 write·owner·createBucket은 허용하지 않은 조건에서 재시도가 성공했고, 받아들여진 새 S3 write나 승인 정책의 재부과는 없었습니다. 이 검증은 HTTP PUT 시도 횟수를 직접 계측하지 않았습니다. 다른 새 ID를 실제 운영 승인 간격 안에 제출해 거부시키는 실험도 수행하지 않았습니다.

후속 파일 검증은 접수 전 기존 21개, 접수 후 24개, RO 재시도 후 같은 24개를 각각 전체 GET했습니다. 서로 다른 객체는 최종 24개이며 각 단계의 조회 수를 더해 객체 수로 표시하지 않습니다. 기존 업무 자료와 첫 결과를 보존했고 두 개의 완료한 자체 stage Job만 정리했습니다. 최종 Kafka는 committed offset 8·log end 8·lag 0이며 실행 슬롯은 비었습니다. 전체 8개 작업이 COMPLETED·EXPORTED였고 부과된 30초 정책 값도 유지됐습니다.

14:54:11 UTC에는 임시 RO credential 회수 3/3도 통과했습니다. 지정한 자체 키 한 개와 해당 Secret만 회수했으며 새 키를 만들거나 객체에 접근하지 않았습니다. 다른 키·버킷 설정은 유지했고 credential 값은 공개하지 않았습니다.

| 후속 단계 | 이 기록의 상태 |
| --- | --- |
| 수정 OCI·실제 class 대조 | PASS |
| 수정 이미지 격리 canary 10개·표본 자원 관측 | PASS |
| 배포 전 보존·API/웹 전환 | PASS |
| 실제 watch 시작 표식·살아 있는 관측 process 확인 | PASS |
| worker GitOps 설정 반영·실제 NotReady→Ready watch | PASS |
| after의 owning journal·전체 보존 검사 | PASS |
| grace 300초 지정 유휴 worker 교체·새 Pod 준비 복구 | PASS, 이전 exit UNOBSERVED |
| 고정 V1 접수·30초 부과·같은 ID RO 재시도 | PASS |
| 임시 RO credential 회수 | PASS |

전체 SHA·사례별 수치·단계별 근거 연결은 [후속 공개 요약](corrected-image.json)에 담습니다. 처음 실패한 이미지와 별도 진단의 기록을 보존하면서 이후 검증을 연결합니다. 운영 worker의 진행 중 작업/호스트 중단, 장기간 probe 비용과 공개 실행은 별도 후속입니다.
