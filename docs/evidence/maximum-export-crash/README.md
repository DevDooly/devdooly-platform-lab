# 1,000건 작업의 부분 export 중단과 복구

2026-10-15 UTC, 별도 Linux Docker worker의 **계산이 DB에 commit된 후 결과 파일 저장·확인을 마치고 실패 파일 PUT을 Garage에 전달하기 직전**에 SIGKILL 1회를 수행했습니다. 동일 JAR의 새 worker가 이미 완료된 계산을 반복하지 않고 남은 export를 완료했으며, 첫 결과 파일의 전체 bytes와 기존 4개 작업·12개 객체를 보존했습니다. 실제 검사 12/12와 후속 운영 보존 18/18을 통과했습니다. [기계 판독 요약](summary.json)을 제공합니다.

이 기록은 [격리 최대 입력·동시성·부하 검사](../input-concurrency-load/README.md)의 후속입니다. 실제 운영 API·worker의 V2 배포·공개 7개 작업은 [별도 배포 근거](../input-v2-deployment/README.md)입니다. 이번 강제 종료는 운영 worker·K3s·호스트에 수행하지 않았습니다.

## 고정한 경계

시험 소스는 `5a1495be4973d43b34dc5c169dbf66bec7459968`, JAR SHA-256은 `ac13f7045eba661d2e90c15b7df661c6fde7039311d0a067010981914664ddc9`입니다. 앞선 3회 부하 검사와 같은 JAR을 사용했습니다. worker는 1 CPU·768MiB, 보조 프록시는 0.5 CPU·192MiB이며 Docker 내부 네트워크에서만 동작합니다. 프록시는 정확한 worker IP와 고정 run의 raw/export 경로만 허용하고 host port를 게시하지 않았습니다.

| 중단 직전 조건 | 실제 확인 |
| --- | --- |
| 계산 결과 | 입력 1,000 = 성공 500 + 실패 300 + 중복 200 + 대기 0, DB commit 완료 |
| 작업 상태 | COMPLETED / PENDING, 실행 슬롯 점유 |
| 실행기 | RUNNING / EXPORT, 실패 코드 없음 |
| 첫 결과 파일 | 실제 PUT·GET 후 direct GET 전체 bytes 일치, 157,919 bytes |
| 실패 파일 | 원래 signed wire를 받은 뒤 hold, Garage에는 미전달 |
| Kafka | partition 0, committed offset 1 / end 1 / lag 0 |

실패 파일 전송을 hold한 뒤 checkpoint 저장까지 약 2.764초였습니다. 이는 강제 종료 시간이나 복구 지연이 아닙니다. 실제 종료 요청 직전에도 RUNNING/EXPORT·COMPLETED/PENDING·점유 슬롯·정확한 container ID·non-OOM을 다시 확인하고, SDK의 기존 8초 read timeout보다 짧은 **6초 이내** 경계에서만 KILL을 허용했습니다. 실제 종료는 exit 137, OOMKilled false였습니다. timeout 변경이나 앱 내부 테스트 hook은 추가하지 않았습니다.

## 재시작 후 검증

hold한 실패 PUT은 종료·timeout·정리 경로에서도 Garage로 전달하지 않았습니다. 같은 source/JAR의 새 worker가 Garage에 직접 연결해 pending export를 우선 완료했습니다.

- 새 작업의 원본 bytes, 계산 결과 1,000행과 작업 생성·queue·계산 완료 시각, DISPATCH 행은 그대로였습니다.
- 첫 결과 파일의 전체 bytes가 동일했고 실패 파일도 전체 GET·크기·SHA-256·독립 기대 내용과 대조했습니다. 신규 원본·두 export의 전체 GET은 3개입니다.
- 신규 Kafka offset/end는 1/1, lag 0이며 두 파일 확인 후 슬롯이 비었습니다.
- 기존 4개 작업의 전체 SQL·시각과 객체 12개를 전후 전체 GET으로 비교했습니다. 앞선 부하 topic의 offset 3과 별도 회복 작업의 offset 1도 그대로였습니다.
- 최종 격리 DB는 5개 작업·5,000개 outcome·ACKNOWLEDGED outbox 10개·pending 0입니다. 의도된 KILL 대상 외 나머지 시험 컨테이너는 정확한 자체 ID에 TERM만 사용해 정리했고 backend 3개와 모든 시험 데이터·실패 기록은 보존했습니다.

## 준비 실패를 교정한 과정

첫 프록시는 Docker worker에서 host gateway로 연결하지 못해 작업 접수·KILL 전에 중단됐습니다. 방화벽 변경 없이 프록시를 같은 전용 Docker 네트워크 안으로 옮겼습니다.

두 번째 프록시는 첫 결과 파일을 실제 저장·GET했지만 실패 파일의 wire SHA를 문서 SHA와 비교해 잘못 거부했습니다. 이때 KILL은 실행하지 않았고 이미 접수된 작업은 COMPLETED/PENDING·PAUSED_OPERATOR/EXPORT_FAILED로 보존됐습니다. 원인을 확인한 뒤 명시적 resume 1회와 새 direct worker로 **동일 작업의 export만** 회복했습니다. 회복 검사 11/11·전체 GET 23회를 통과했으며 재접수·재계산·객체 수선은 없었습니다. 이 회복은 crash 성공으로 세지 않았습니다.

실제 candidate S3 SDK·Java 21과 loopback listener, dummy credentials로 같은 전송 형식을 재현했습니다. 합성 payload 크기 157,919와 88,195 bytes에서 wire 크기는 각각 158,184와 88,371 bytes였습니다. 서명용 `aws-chunked` 프레임 때문에 wire SHA는 문서 SHA와 다르지만 프레임을 검증해 해석한 payload SHA는 같았습니다. 이는 실제 문서 내용을 로컬 시험에 재사용했다는 뜻은 아닙니다.

마지막 프록시는 허용된 signed framing·길이·decoded SHA를 검증하고 **원래 signed wire를 수정 없이** 전달합니다. chunk signature 형식을 검사하지만 서명 자체를 인증하는 주체는 전달받은 Garage입니다. hold한 실패 PUT은 인증을 대신하는 방식으로 저장하지 않았습니다. 알 수 없는 encoding·trailer·길이 초과·손상은 거부합니다. decoder 12개·driver guard 5개와 실제 SDK 두 크기 회귀 검사를 통과한 후 새 run/topic/container로 마지막 시험을 수행했습니다. 이전 실패 run을 자동 재접수하거나 보고서를 덮어쓰지 않았습니다.

## 운영 보존과 한계

격리 시험 뒤 읽기 전용 검사 18/18에서 실제 운영 7개 작업의 전체 업무 SQL·시각·작업 DTO, Kafka offset 7/lag 0, 같은 source `6c5aff94`와 실제 OCI·CRI 이미지, 기존 Pod 6개·PVC/PV 11개·Docker 38개, host boot·방화벽·timer unit/주기를 보존했습니다. 이 후속 검사는 운영 객체를 새 GET한 결과가 아니며, 운영 객체의 전체 검증은 앞선 배포 기록의 21개 GET입니다.

계산 중간의 CPU 작업 중단, Kafka/DB crash, 실제 운영 worker 강제 종료, 진행 중 호스트 재부팅·고가용성·장기간 장애는 이번 범위가 아닙니다. 보조 프록시의 wire 상한 4MiB는 이번 약 158KB·88KB 문서 검증의 한도이며, framing을 포함한 모든 4MiB 문서의 전송을 시험했다는 뜻이 아닙니다. checkpoint·private 실행 영수증은 비공개 보관하고 접속 주소·credentials·object key·HTTP header·SQL 원문은 공개하지 않습니다.
