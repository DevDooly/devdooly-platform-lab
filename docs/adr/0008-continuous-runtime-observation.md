# 0008 명시적 상시 실행기·영속 정지와 별도 작업 관측

상태: 구현·격리 실행·HTTP 관측·화면 및 기존 운영 보존 검증 완료 · 2026-10-15 KST. 기본 120개·실제 IT 4개·웹 34개를 통과했다. 운영 및 공개 Pages 배포는 후속이다.

## 실행과 소유권

기본 HTTP 앱과 상시 실행기를 같은 코드에서 명시적인 실행 명령으로 구분한다. 기본 API 시작이나 profile 선택만으로 Kafka·S3 client·worker loop가 생성되지 않는다. `--lab-runtime=run`만 web server 없는 worker context를 시작하며, worker는 Flyway를 실행하지 않고 API/관리 절차로 적용된 V3 schema를 요구한다.

하나의 소유 thread가 pending export → pending dispatch 발행 → 한 record 수신을 반복한다. idle 대기는 유한하며 각 단계 사이에서 stop 요청을 확인한다. 기존 ACK·DB·offset·두 파일 확인 뒤 슬롯 해제 경계를 그대로 사용한다. 종료 요청은 같은 소유 thread가 client를 닫도록 전달하며 오류를 기록한 상태를 정상 STOPPED로 덮어쓰지 않는다.

MariaDB 전용 비트랜잭션 connection의 schema별 named lock을 프로세스 실행 기간 보유한다. 다른 실행기는 즉시 거부하고 journal을 바꾸지 않는다. 단계·journal 변경 전에 현재 connection의 lock 소유를 다시 확인한다. 이는 정상 동시 시작을 제한하는 한정 Lab 정책이다. 소유권 확인과 외부 IO 사이의 원자적인 fencing이나 다중 노드 HA를 제공하지 않는다. connection 유실과 이미 진행 중인 외부 IO는 기존 DB 멱등·확인 뒤 ACK 경계로 다루며 완전한 분산 lock이라고 표현하지 않는다.

## 영속 상태와 재시작

V3의 `lab_runtime` singleton은 status·stage·고정 failure code·실행/heartbeat/종료 시각·source commit만 기록한다. 원문 예외·호스트·credentials는 기록하지 않는다. 소유권과 DB 기록이 가능한 경우 오류를 `PAUSED_OPERATOR`로 보존하고 client를 닫는다. 새 프로세스의 run은 이 상태를 자동 해제하지 않는다. 원인을 확인한 뒤 별도 `--lab-runtime=resume` 명령이 같은 named lock을 확보해 정지를 해제하며, 처리를 다시 시작하려면 run을 실행한다. public HTTP의 재개·중지·실행 명령은 제공하지 않는다.

강제 종료 때 남은 RUNNING 상태는 현재 named lock을 새로 확보한 프로세스가 다시 시작할 수 있다. 이는 미완료 export/outbox·offset을 기존 검증 경계로 회복하기 위한 것으로 PAUSED_OPERATOR의 재시작 정책과 다르다. DB에 남은 heartbeat는 마지막 실행 신호이며 현재 프로세스가 살아 있음을 직접 증명하지 않는다.

## 작업·export 관측

`GET /api/jobs/observation`의 별도 `job-observation v1` 계약을 추가한다. 기존 `lab-observation v1`·`platform-observation v1`과 고정 seed 결과는 유지한다. 읽기 전용 repeatable-read snapshot에서 runtime journal·슬롯·최신 작업 최대 20개를 읽고 상태·시각·건수·파일별 예상 SHA/크기만 허용한다. S3·Kafka를 호출하거나 작업 잠금을 잡아 상태를 수집하지 않는다.

파일 SHA/크기는 불변 DB snapshot에서 재생성한 예상 내용이다. `exportCompletedAt`은 exporter가 두 파일을 확인한 뒤 DB에 기록한 저장 확인 시각이다. 관측 API가 현재 S3 객체를 다시 읽었다는 뜻은 아니다. 작업 원본·object key·bucket·접속 주소·원문 오류는 내보내지 않는다. 오류 응답도 고정 code만 반환한다.

화면은 same-origin 조회와 별도 정적 관측 파일을 지원한다. 정적 파일은 실제 격리 HTTP 응답을 strict validator로 확인한 뒤 저장하며, 관측 전에는 성공 데이터를 만들지 않는다. 검증 환경·수집 시각·소스·실행 heartbeat와 기록의 오래됨을 표시한다. API/파일 조회 실패 때는 마지막 성공 기록을 보존하고 실패를 별도로 표시한다. 격리 시험 기록을 미니 PC 운영 상태로 표시하지 않는다.

## 범위

현재 Kafka factory의 숫자 loopback/SSH 시험 접속 범위를 유지한다. 상시용 consumer의 max poll interval은 10분이며 기본 consumer의 2분과 구분한다. 이는 긴 export 단계 동안의 rebalance 여유이며 전체 처리 시간이나 가용성 SLA가 아니다. SDK timeout·finite retry는 각 호출에 적용한다.

이번 구현·격리 실행으로 Kubernetes worker 배포·실제 운영 서비스 상주·공개 Pages 배포·공개 실행·보존 자동화·최대 1,000개·다중 partition·HA까지 완료하지 않는다. 운영 image·GitOps pin·기존 서비스와 데이터는 유지하며 다음 배포 단계에서 별도로 검증한다.

[재실행 절차](../runbooks/continuous-runtime.md) · [작업 관측 계약](../contracts/job-observation.md) · [실제 검증 근거](../evidence/continuous-runtime/README.md)
