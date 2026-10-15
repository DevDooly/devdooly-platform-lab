# 결과·실패 파일 export와 슬롯 해제 검증

2026-10-15 KST에 실제 MariaDB 11.8.9·Garage 2.4.1을 격리 실행했다. Java 21·Asia/Seoul에서 기본 verify **97개**, 별도 실제 서비스 IT **6개**가 모두 통과했다. 기존 Kafka 시험과 별개이며 이 실행에서 Kafka broker·상시 worker·공개 API를 배포한 것은 아니다.

[실제 수치·파일 hash·보존 결과](summary.json) · [시험 소스 지문](source-fingerprint.json) · [재실행 절차](../../runbooks/result-export.md) · [ADR 0007](../../adr/0007-verified-result-export.md)

## 실제로 확인한 결과

DB 완료 작업의 결과 JSON 12개 outcome과 실패 JSON의 실패 입력 3개·원본 line·독립 기대 이유를 실제 Get으로 확인했다. 입력 회계식은 12 = 성공 7 + 실패 3 + 업무상 중복 2 + 대기 0이다. 두 파일의 전체 bytes·크기·SHA-256이 일치한 뒤에만 export outbox 확인·EXPORTED 시각·슬롯 해제를 DB 트랜잭션으로 확정했다.

| 실제 시험 | 실패/중단 경계와 회복 결과 |
| --- | --- |
| 정상·반복·다음 작업 | 두 파일 확인 뒤 슬롯 해제·새 작업 접수. 이전 작업 반복은 기존 export/처리 시각·객체·새 작업 슬롯 보존 |
| 두 번째 파일 경계 오류 | 첫 파일 실제 Get 확인 후 의도적 adapter 경계 예외. PENDING·슬롯 유지·후속 접수 거부. 재시도에서 첫 객체 재검증 후 두 번째 저장·확인 |
| 같은 크기의 손상 객체 | 덮어쓰기 없이 실패, PENDING·슬롯 유지. 시험 코드의 소유 fixture 제거 후 재시도로 완료 |
| 실제 DB 완료 오류 | export 상태·outbox ACK SQL 실행 뒤 슬롯 해제 SQL에서 trigger/SQLSTATE 45000 발생. DB 전체 rollback·객체 보존. trigger 제거 뒤 동일 파일 확인·완료 |
| 첫 객체 확인 후 JVM 종료 | atomic checkpoint·DB PENDING·점유 슬롯을 확인한 뒤 강제 종료. 새 exporter로 두 파일 확인·완료 |
| 두 객체 확인 후 DB ACK 전 JVM 종료 | atomic checkpoint·DB PENDING·점유 슬롯을 확인한 뒤 강제 종료. 두 객체 재검증·완료 |

각 최종 정상 상태는 run 1·outcome 12·서로 다른 문서 2개 확인·EXPORTED·빈 슬롯이다. 정상 시험은 이후 새 작업을 실제 접수하고 이전 작업을 다시 export해 새 슬롯 점유를 보존한 추가 관측도 남겼다. JSON의 추가 관측 1개를 일곱 번째 테스트로 세지 않는다. `objectsVerified=2`는 최종 문서 두 개이며 모든 시도에서의 Get 호출 총합이 아니다. `exportPuts`를 해석할 때도 SDK 메서드 호출과 wire-level retry를 구분한다.

강제 종료는 Windows child JVM을 두 경계에서 각각 한 번, 총 2회 수행했다. 실제 atomic checkpoint를 대조한 뒤 `destroyForcibly()`와 종료를 확인했으며, 고정 sleep·예외만 주입한 시험이 아니다. Garage·네트워크 중단이나 Linux Pod SIGKILL을 검증한 것은 아니다. 원문 log·checkpoint는 비공개 진단 자료에 남겼다.

## 정리와 기존 운영 보존

시험 teardown 뒤 소유 raw/export 객체와 DB 작업·outbox·run·outcome·trigger를 정리했고 빈 singleton slot 1개와 V1/V2 각각 성공 1회를 확인했다. 전용 container 2개·DB named volume 1개·internal network 1개를 제거했다. 비공개 Garage 진단 데이터는 보존했다.

고정 전후 관측에서 기존 Docker 전체 38개 ID·실행 중 26개의 시작 시각/mount, 운영 Pod 3개·PVC 2개, 전체 SQL·Flyway·처리 시각·API 저장 필드·image pin/source·Argo revision·host boot·node·방화벽을 보존했다. 이번 작업에는 운영 배포·롤백이 없으며, 과거 observer의 restored 명칭을 그런 동작으로 해석하지 않도록 공개 요약에는 unchanged로 기록했다.

## 한계와 다음 작업

명시적 내부 adapter 호출이며 기본 HTTP 앱의 자동 bean·listener·scheduler·public POST·UI/관측 계약·GitOps pin은 바꾸지 않았다. 문서별 최대 4 MiB, 원본은 기존 1 MiB/12개 fixture만 허용한다. 실패 rawLine은 원래 line text를 보존하고 CR/LF separator는 제외한다.

한 문서의 Get·Put·Get 각각이 기존 SDK의 유한 대기/재시도 설정을 사용하며 전체 export를 30초로 보장하지 않는다. DB에 새 pair manifest·파일 영수증을 추가하지 않았고, 반복 시 불변 DB snapshot에서 같은 버전/key/bytes를 재생성해 재검증한다. 단일 신뢰 writer 정책이며 조건부 생성·WORM·객체의 이후 삭제 방지·호스트/디스크 장애·시스템 전체 exactly-once를 보장하지 않는다.

다음은 상시 worker/export 실행기·운영자 정지/재개 정책과 job/export 관측 계약을 설계하고, 제한된 운영 배포를 별도로 검증하는 일이다. 자동 보존/삭제·최대 1,000개 입력·다중 worker·공개 실행은 미구현이다.
