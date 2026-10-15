# Kafka·Garage 격리 PVC 복원 검증

2026-10-15 미니 PC의 Kafka PVC 1개와 Garage metadata/data PVC 2개를 cold backup하고, 외부 PC의 암호화 백업을 인증·복호화하여 새 격리 저장소로 복원했습니다. 합성 데이터의 개인 Lab 검증입니다. [허용 필드 결과](summary.json), [복원 절차](../../runbooks/runtime-pvc-recovery.md), [공개 관측](https://devdooly.github.io/devdooly-platform-lab/#job-observation)에 연결합니다.

## 원본 checkpoint와 외부 백업

실행 슬롯이 비고 작업 3개가 EXPORTED, Kafka committed offset 3 = log end 3인 상태를 기준으로 삼았습니다. 원본 worker·Kafka·Garage만 정상 종료하고 세 Pod가 없는 상태에서 파일을 복사했습니다. API·web·DB와 기존 Docker 서비스는 계속 유지했습니다.

| 항목 | 실제 결과 |
| --- | --- |
| cold copy 시작 ~ 원본·Argo 복귀 UTC | 2026-10-15 06:13:29.948900 ~ 06:14:08.695312, 약 38.746초; 전체 유지보수 시간과 구분 |
| 원본 cold PVC | Kafka 1 + Garage metadata 1 + Garage data 1 |
| 전체 파일 비교 | 파일 SHA·크기·소유자·권한·nanosecond mtime·디렉터리 manifest 일치 |
| checkpoint 묶음 | 260,493 bytes, SHA-256 a33d97b75057a2f4bf798cdd553d910f52019bf0a94597c040d7317aca9e2491 |
| 외부 보관 | 별도 기존 키의 AES-256-GCM, 파일을 다시 읽어 인증·복호화 후 전체 SHA 일치 |
| 실제 복원 입력 | 외부 암호화 파일에서 인증·복호화한 bytes를 서버의 새 입력 파일로 전달 |
| 재개 | 원본 3개 정상 복귀, Argo CD 자동 동기화 정책 원문 복구, business SQL 전체 보존 |

checkpoint에는 세 PVC와 관련 Secret, 실제 Kafka 설정, DB checkpoint 정보가 포함됩니다. Secret·개인키·SQL 원문·내부 주소·Pod UID·로그는 공개하지 않습니다. DB는 복원하지 않았으며, 세 저장소를 함께 특정 시점으로 복원하는 전체 플랫폼 PITR을 검증한 결과가 아닙니다.

## 격리부터 확인한 첫 복원

새 namespace를 만든 뒤 Secret과 복원 데이터를 넣기 전에 자격증명 없는 probe로 원본 Kafka broker/controller·Garage·DB의 Pod IP와 Service IP 접속을 확인했습니다. default deny와 같은 namespace·DNS 허용 정책을 적용한 뒤 같은 probe의 원본 접속이 두 회차 모두 차단됐고 DNS는 동작했습니다. 원본 서버가 동시에 Ready이고 별도 경로의 접속도 되는지 확인해 장애에 따른 접속 실패와 구분했습니다. NetworkPolicy가 호스트 자체를 차단한다고 주장하지 않습니다.

새 PVC 3개의 UID·PV·저장 경로가 원본과 다른 것을 확인하고 PV를 Retain으로 지정했습니다. 복원 후 프로세스 시작 전에 전체 파일 manifest를 비교했습니다. Kafka는 복원된 저장소를 재포맷하지 않고 직접 실행했으며, advertised listener와 controller 주소를 격리 환경으로 바꿨습니다. Garage RPC는 loopback을 유지하고 외부 peer discovery가 없는 설정을 확인했습니다. API·DB·worker는 복제 실행하지 않았습니다.

## Kafka 데이터·offset·재시작

실제 Kafka 4.3.1 image digest와 동일한 broker/controller 설정으로 복원했습니다. 원본과 복원본의 cluster·node·directory·topic identity, 메시지 3건의 key/value 전체 bytes·timestamp·partition·offset, consumer committed offset 3 = log end 3·lag 0이 일치했습니다. 수신은 수동 partition 지정과 auto commit 비활성으로 수행하여 consumer group과 offset을 변경하지 않았습니다.

이후 격리 Kafka Pod만 UID 조건·종료 유예 120초로 교체했습니다. 기존 프로세스는 TERM exit 143으로 종료하고 12.71초 뒤 같은 PVC·image·설정을 쓰는 새 Pod가 Ready가 됐습니다. 재시작 후 같은 메시지와 offset 검사가 12/12 통과했습니다. 강제 삭제·format·offset reset·새 발행은 실행하지 않았습니다.

## Garage: 기존 작은 객체와 실제 블록을 나눠 검증

원본 입력 3개와 결과·실패 파일 6개, 총 9개를 첫 복원본에서 새 GET으로 읽어 전체 bytes·크기·SHA·JSON identity를 대조했습니다. 모두 일치했습니다. 이 9개는 전부 3,072 bytes 미만의 inline 객체이고 원본 data PVC에는 큰 객체의 물리 블록이 없었습니다.

따라서 격리 복원본에만 결정적인 131,072 bytes canary를 한 번 PUT했습니다. 원본 bucket에는 쓰지 않았습니다. metadata/data PVC를 정상 종료 상태에서 cold copy하고 실제 비-inline 블록 파일 1개를 확인했습니다. 다시 만든 별도 PVC 2개에 복원한 뒤 원본 9개 + canary 1개를 모두 GET했습니다. 그 Garage Pod를 정상 교체한 뒤에도 같은 10개를 다시 읽었습니다.

canary의 SHA-256은 a06113fe4c4b6f0e7e6b6d37d754379b82287d3a71f8160e9154608e9e18a627입니다. 이는 원본에 존재하던 큰 객체를 복구했다는 의미가 아니라, 별도 격리 입력의 실제 data block과 metadata를 함께 복원한 검증입니다.

## 원본 보존과 종료 상태

검증 후 격리 StatefulSet 3개는 replica 0, 시험 Pod는 0개입니다. 시험 PVC 5개(요청 합계 29GiB)는 PV Retain 상태로 남겼습니다. 요청 용량은 실제 디스크 점유량과 다르며, 보존 기한·삭제 계획을 정한 뒤 시험 저장소만 정리해야 합니다.

원본 PVC 6개와 binding·저장 경로, workload 6개의 선언, API·web·DB Pod, cold maintenance 뒤 복귀한 worker·Kafka·Garage Pod, Docker 38개(실행 26개)의 ID·시작·mount를 대조했습니다. 전체 business SQL, EXPORTED 작업 3개와 파일 정보 6개, 빈 슬롯, Kafka offset 3/3·lag 0을 보존했습니다. 원본 객체 9개도 마지막 새 GET에서 전체 bytes가 같았습니다. Argo CD Synced/Healthy와 기존 30분 관측 timer·service를 유지했습니다. 상세 통과 항목은 [summary.json](summary.json)을 따릅니다.

이번 검증은 정상 종료한 단일 노드 Lab의 cold restore입니다. 운영 중 무정지 백업, 처리 중 강제 장애, 다중 노드 HA, 전체 DB·Kafka·Garage 시점 복구, 장기 보관·키 회전은 후속 범위입니다. 공개 화면은 마지막 자동 수집 기록이며 시험 namespace의 관리자 기능을 외부에 열지 않았습니다.
