# Platform Lab 다음 개발 계획

2026년 10월 12일 기준

Java 백엔드, 데이터 처리, 배포와 운영 경험을 방문자가 직접 확인할 수 있는 포트폴리오로 발전시킵니다. 외부 백업·격리 DB 복원·재부팅과 CI/CD의 정상 배포·실패 차단·이전 image digest 복구를 확인했습니다. **3단계의 실제 수집·실패 후 보존·Pages 게시·공개 화면과 자동 운영 기본 경로를 검증**했습니다. 게시 순서 회귀 교정, API·웹 중단 후 같은 정상 B 복원에 이어 전용 Pages 자격증명으로 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 게시를 확인했습니다. 실제 30분 간격의 반복 운영과 자격증명 만료·회전은 별도 후속입니다. 이후 합성 데이터를 Kafka와 객체 저장소로 확장하고, AI를 활용한 코드 개선과 데이터 플랫폼 사례를 추가합니다.

[공개 Lab](https://devdooly.github.io/devdooly-platform-lab/) · [전체 진행 목록](ROADMAP.md) · [현재 접속 안내](START_HERE.md)

## 출발점

| 영역 | 확인한 내용 | 다음에 채울 부분 |
| --- | --- | --- |
| Java API | 테스트 15개, MariaDB 저장, 합성 입력 12건 검증 | 메시지 수신과 재처리 |
| 포트폴리오 | 앱·플랫폼 관측 공개, 1280px·390px 확인, 로컬 웹 테스트 26개, 호스트 수집·Pages 게시 | 실제 30분 간격 반복 운영·자격증명 만료·회전 |
| Jenkins·Actions | 같은 SHA의 두 CI 성공·게시·draft GitOps PR·정상 B 배포·실제 실패 차단, main의 공개 status 수집 | credential 만료·회전과 게시 이력 보존 운영 |
| Argo CD와 Helm | 정상 A → B → A GitOps 복구, Synced·Healthy·데이터 보존과 제한된 실제 상태 수집 | 주기 관측의 반복 운영과 실패 대응 |
| 운영 | 외부 암호화 백업·격리 DB 복원·호스트 재부팅, 사용자 kubectl 복구 | 초기 비밀번호 교체, 추가 장치 사본·전체 archive 복원 |

GitHub Actions를 유일한 이미지 게시자로 유지하고, 전용 Jenkins status credential과 같은 source SHA의 두 CI 성공을 게시 조건으로 활성화했습니다. 사용자 승인으로 Actions PR 설정과 draft GitOps PR 자동 제안도 켰습니다. 공개 Lab은 기존 앱의 마지막 실제 관측본을 보여줍니다. 별도 플랫폼 collector는 최소 읽기 권한으로 실제 상태를 수집했으며 새 관측본을 수동 게시했고, 게시 순서 회귀 교정 후 실제 복구·순서 보존을 재검증했습니다. 실시간 공개 API와 조회 API 내부의 플랫폼 수집은 아직 연결하지 않았습니다. Windows 외부 암호문은 인증·해시를 확인했고, DB는 서버의 새 논리 dump로 격리 복원했습니다. 외부 암호문을 K3s에 되돌리는 통합 복구와 K3s·Jenkins archive 전체 복원은 별도로 남아 있습니다.

실행 근거는 [미니 PC 배포](evidence/mini-pc/README.md), [Jenkins 빌드](evidence/jenkins-ci/README.md), [후속 접속과 재기동 검증](evidence/operator-access/README.md), [앱 관측 계약](../apps/lab-web/OBSERVATION.md)에 있습니다. [플랫폼 관측 수집 검증](evidence/platform-observation/README.md)과 [허용 필드 계약](../apps/lab-web/PLATFORM_OBSERVATION.md)을 별도로 연결합니다. 완료 항목은 실제 검증 근거와 함께 표시합니다. [백업·복원·재부팅 검증](evidence/recovery/README.md)을 추가했습니다.

## 진행 순서

| 순서 | 주제 | 방문자에게 보여줄 결과 |
| --- | --- | --- |
| 1 | 운영 기준과 복구 | 백업·복원 검증과 장애 대응 기록 |
| 2 | CI/CD 연결 | 소스 SHA부터 실행 image digest까지 이어지는 배포 기록 |
| 3 | 관측 공개 | 빌드·배포·Pod 상태와 마지막 수집 시각 |
| 4 | Kafka와 객체 저장소 | 중복·역순·재시작에도 일관된 처리 결과 |
| 5 | AI를 활용한 Java 개선 | 실패 재현, 개선 코드, 측정 원본과 개발자의 판단 |
| 6 | Iceberg와 Trino | 적재부터 SQL 조회·재시작까지 재현되는 데이터 흐름 |

순서 1의 백업·격리 DB 복원·재부팅과 순서 2의 정상·실패·이전 digest 복구 검증을 마쳤습니다. 순서 3은 실제 수집·인증 실패 후 보존·회복·수동 공개 게시·브라우저를 확인했고, 게시 순서 회귀 교정 후 실제 재검증도 완료했고 API·웹 중단·같은 정상 B 복원도 확인했고 정기 운영 검증을 이어갑니다. 초기 비밀번호 교체·token 회전·추가 장치 사본·전체 archive 복원은 별도 운영 후속으로 남깁니다. AI 사례의 입력·테스트 설계는 작은 실험으로 병행할 수 있으며 공개 기능과 결과는 기존 5단계에 연결합니다. 각 단계의 완료 조건을 통과한 뒤 확장합니다.

## 1 운영 기준과 복구

- [x] 사용 중인 클러스터 이름·CA·접속 방식과 설치·데이터 경로를 운영 안내에 정리합니다. 삭제나 정리 전에는 연결 설정과 실제 실행 대상을 함께 확인합니다.
- [x] 관리자 초기 비밀번호 변경 여부를 확인하고, 비밀값을 공개 파일과 분리합니다.
- [x] 서버 외부의 백업 위치를 정하고 K3s datastore·token, Jenkins Home, MariaDB 데이터를 각각 보관합니다.
- [x] 운영 PVC와 분리한 테스트 볼륨에 MariaDB를 복원하고, 기존 12건 결과와 중복 방지 동작을 비교합니다.
- [x] 기존 서비스의 영향을 설명할 수 있는 복구 절차를 작성한 뒤 재부팅 복구를 별도로 검증합니다.

**완료 조건:** 백업 해시·대상·시각, 실제 복원 명령과 결과, 복구 시간, 확인한 데이터가 남아 있어야 합니다. 외부 백업은 전송 후의 무결성과 접근 권한도 확인합니다. K3s는 datastore와 함께 server token을 복원해야 하므로 둘을 같은 복구 단위로 관리합니다. [K3s 백업과 복원](https://docs.k3s.io/datastore/backup-restore)

**공개 결과:** 비밀값을 제외한 복구 기록과 kubeconfig 인증서 오류의 증상·원인·교정·재확인 과정입니다.

[운영 대상 확인](runbooks/lab-operations.md)과 [재실행 명령](runbooks/lab-recovery.md)을 함께 제공합니다. 초기 관리자 비밀번호는 아직 유효합니다. 위 체크는 변경 여부와 보관 방식을 확인했다는 뜻이며 비밀번호 교체 완료를 뜻하지 않습니다. 외부 백업과 격리 DB 복원, 호스트 재부팅 결과는 [복구 검증](evidence/recovery/README.md)에 있습니다.

## 2 CI/CD 연결

현재 흐름은 `Jenkins 테스트 + Actions 통합 검증 → Actions 이미지 게시 → digest 기록 → draft GitOps PR → 검토 후 main 반영 → Argo CD 배포`입니다. [ADR 0004](adr/0004-jenkins-gated-actions-publication.md)에 따라 Actions를 단일 게시자로 유지하고 동일 source SHA의 Jenkins 성공을 추가 조건으로 연결했습니다. 전용 status credential과 Actions PR 설정을 활성화했고 정상 B 배포·실제 실패 차단·이전 정상 A 복구를 모두 검증했습니다. [운영·검증 절차](runbooks/cicd-publication.md)와 [실행 근거](evidence/cicd-gate/README.md)를 함께 확인합니다.

- [x] Jenkins agent에 호스트 Docker socket을 공유하지 않고, 이미지 빌드는 Actions runner에서 수행합니다. agent 권한·캐시·자원 한도를 기록했습니다.
- [x] Jenkins 전용 status credential과 job별 Actions 권한을 분리하고, 실제 pending·success·failure 전달과 draft PR 제안을 확인했습니다.
- [x] 실제 JUnit 실패에서 새 이미지·게시 artifact·GitOps PR이 생기지 않고 B의 values·Deployment·Pod·SQL·PVC·기존 Docker가 유지되는지 확인했습니다.
- [x] 성공한 빌드의 source SHA, 테스트 결과, image digest, GitOps commit, 실제 실행 버전을 정상 B 배포로 연결했습니다.
- [x] GitOps values의 API/Web digest와 sourceCommit을 이전 정상 A로 되돌리고 실제 HTTP·DB·저장 시각·PVC·기존 서비스 보존을 확인했습니다.

**완료 조건:** 정상 배포 한 번, 실패 차단 한 번, 이전 버전 복구 한 번의 실제 결과를 남깁니다. 배포 상태는 Argo CD가 관리합니다. 자동 동기화가 켜진 상태의 복구는 Git의 선언 값을 되돌려 수행하며, 별도의 Argo CD rollback 명령과 혼용하지 않습니다. [Argo CD 자동 동기화와 rollback 제약](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)

**공개 결과:** 정상 배포에서는 같은 source SHA의 두 CI 성공부터 digest·GitOps·실행 이미지까지 추적했습니다. 실패 실험에서는 API 테스트 15개 중 1개가 실패했고(기대 성공 8건, 실제 7건), failure status와 Actions 검증 실패를 확인했습니다. 해당 SHA의 새 게시 결과·PR이 없었으며 기존 B의 전체 SQL·처리 시각·PVC와 기존 서비스가 유지됐습니다. 실패 변경을 원복하고 GitOps PR로 A에 복구한 뒤 Synced·Healthy, 3개 Pod Ready, 기존 SQL·Flyway·시각·PVC와 기존 Docker 보존을 확인했습니다. 과거 Jenkins의 단계 미실행·플러그인 충돌과 출처 메타데이터 교정도 설계 이유에 연결합니다.

원복 source의 두 CI 검증은 다시 성공했습니다. 실제로 수동 실행과 pollSCM이 같은 SHA의 Jenkins 빌드를 중복 생성했으며, 최신 pending을 확인한 Actions는 이전 success로 게시하지 않았습니다. GitHub metadata 조회 403으로 실패한 게시 시도도 별도로 남겼습니다. 최신 success 후 게시·draft 제안은 성공했고 이 추가 제안은 적용하지 않고 닫았습니다. 복구 PR의 변경 범위·A OCI·Helm 검증과 실제 A 실행·데이터 보존 검증은 모두 통과했습니다. token의 실제 만료·회전과 동시 요청 실험은 운영 후속이며 위 세 시나리오 완료와 구분합니다.

## 3 관측 공개

검증한 JSON을 outbound dispatch로 Pages에 반영하고 공개 브라우저를 확인했습니다. 실제 순서 역전 게시의 seed 회귀는 교정 후 공개 JSON·브라우저·이전 artifact로 보존을 재검증했습니다. 초기 자동화 비활성 설치와 정적 검증에 이어, 전용 Pages 자격증명으로 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 Pages 게시와 전체 공개 JSON 일치를 확인했습니다. timer는 enabled·active이며 실제 30분 간격 검증은 별도입니다. 이후 실시간 조회가 필요한 항목에 한해 공개 읽기 API를 연결합니다. 이번 단계에서 새 inbound 경로를 열지 않았고, Jenkins·Argo CD 관리 화면은 인증된 관리 경로를 유지합니다.

- [x] 전용 읽기 권한으로 main의 Jenkins 공개 status, 지정 Argo CD sync·health와 실제 Lab Pod 준비 수를 수집했습니다.
- [x] main·Jenkins 대상·Argo revision·API 배포 선언 소스와 고정 image digest·관측 시각·실패 코드를 strict allowlist로 정의했습니다.
- [x] 실제 인증 실패에서 마지막 성공 전체·capturedAt이 유지되고 정상 인증 후 회복되는지 확인했습니다. 출력 0600과 지정 리소스 허용·Secrets/logs/exec/nodes·변경·다른 범위 읽기 거부도 실제 확인했습니다.
- [x] 수집 실패·브라우저 조회 실패·마지막 성공 후 2시간 초과를 구분하는 UI를 로컬 테스트했습니다. 신규 13개를 포함한 전체 26개 테스트·타입 검사·Pages 경로 빌드를 통과했습니다.
- [x] 관리 토큰·원문 로그·내부 주소·임의 오류 필드를 거부하는 schema·validator와 좁은 공개 출력 계약을 구현했습니다.
- [x] 실제 HTTP 401 실패 envelope를 수동 Pages 게시하고 이전 성공 전체·시각 보존과 공개 1280px·390px 화면을 확인했습니다.
- [x] 순서 역전 게시에서 발견한 seed 회귀를 교정하고 이전 deploy artifact·공개 JSON·브라우저 기준으로 실제 보존을 재검증했습니다.
- [x] Ubuntu collector 41개·최종 자동화 35개 root·일반 사용자 검사와 초기 비활성 설치·systemd 정적 검증을 완료했습니다.
- [x] API·웹 replicas 0의 중단에서 공개 홈·마지막 기록·DB·기존 Docker를 보존하고 같은 정상 B로 복원했습니다.
- [x] 전용 Pages 자격증명을 등록하고 수동 host cycle의 실제 Pages 게시·전체 공개 JSON 일치를 확인했습니다.
- [x] 실제 systemd service 실행 성공·상태 파일 root 0600·임시 SA 토큰 정리를 확인했습니다.
- [x] timer enabled·active와 최초 자동 trigger의 Pages 게시·전체 공개 JSON·브라우저를 확인했습니다.
- [ ] 실제 30분 간격의 반복 수집·게시와 credential 만료·회전을 검증합니다.
- [ ] 필요한 경우 기존 프록시·TLS를 확인한 뒤 읽기 API를 연결하고 휴대폰 외부망에서 확인합니다.

**완료 조건:** 정상 수집, collector 실패, Lab 중단 시나리오에서 표시 내용이 실제 관측 범위와 일치합니다. 공개 화면은 현재 JVM 정보와 별도 정적 관측·CI/CD 근거를 구분합니다. 실제 API·웹 replicas 0에서 공개 홈·마지막 기록 유지와 같은 정상 B 복원을 확인했습니다. 호스트·DB 전체 중단은 이 실험 범위가 아니며 오래된 기록·브라우저 조회 실패는 오프라인 UI 검증입니다.

**현재 확인한 결과:** [실제 수집·실패 후 보존·게시·브라우저](evidence/platform-observation/README.md)를 제공합니다. 게시 순서 회귀 교정과 API·웹 중단·같은 정상 B 복원, 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 Pages 게시까지 기본 경로를 검증했습니다. 같은 마지막 intent 재전송 차단도 실제 확인했으며 전체 이력의 exactly-once 보장은 아닙니다. 실제 30분 간격의 반복 운영과 credential 권한 범위 조회·만료·회전은 별도 확인 범위로 남깁니다.

## 4 Kafka와 객체 저장소

[구현 전 조사와 작은 처리 흐름](plans/phase4-messaging-storage.md)에 제품 후보, 원본 보관·재전달·DB 멱등 처리와 장애 검증 순서를 정리했습니다. 설치와 실제 검증은 다음 단계이며, 제품 선택도 SDK 호환성 확인 후 확정합니다.

[읽기 전용 자원 사전 점검](evidence/messaging-storage/README.md)에서 잠정 메모리·디스크 관문을 통과했습니다. 한 시점의 여유이며 신규 구성의 부하 검증이나 설치 완료를 뜻하지 않습니다. 먼저 격리 환경에서 V2 작업/outbox·실행 슬롯과 실제 MariaDB의 잠금·재전달을 검증합니다.

기존 합성 센서 시나리오에 메시지 수신과 원본 보관을 추가합니다. 최대 이벤트 수, 동시 실행 수, 보존 기간부터 제한하고 하나의 worker로 시작합니다. 객체 저장소 제품은 구현 시점의 유지보수 상태·라이선스·S3 호환 기능을 확인한 뒤 선택합니다.

- [ ] 동일 이벤트 재전송, 센서별 시간 역순, 잘못된 값의 처리 규칙을 명시합니다.
- [ ] DB 반영 전후에 worker를 중단해 재시작·재전달 시 중복 적재를 방지하는지 확인합니다.
- [ ] 재시도 횟수와 실패 메시지 보관 정책을 정하고 실패 데이터의 재처리 경로를 만듭니다.
- [ ] 원본과 처리 결과를 객체 저장소에 보관하고 run ID로 연결합니다.
- [ ] 화면에 입력·성공·실패·중복 건수와 consumer lag를 표시합니다.

**완료 조건:** 메시지 전송의 멱등성과 DB의 업무 중복 방지를 나눠 검증합니다. producer 설정만으로 전체 처리의 exactly-once를 주장하지 않습니다. [Kafka producer 설정](https://kafka.apache.org/42/configuration/producer-configs/)

**공개 결과:** 장애가 발생한 지점과 재처리 후에도 유지되는 결과를 재현 가능한 작은 데이터로 설명합니다.

## 5 AI를 활용한 Java 개선

회사의 수율 로직을 옮기지 않고, 독립적인 합성 예제 하나로 시작합니다. 후보는 중첩 탐색을 Map 기반 검색으로 바꾸는 연산 개선, 또는 시간대·이벤트 순서 오류의 수정입니다.

- [ ] 버그 사례는 개선 전 실패 테스트와 경계 조건을 만들고, 성능 사례는 기능 기대 결과와 개선 전 기준 측정을 확보합니다.
- [ ] AI에 제공한 비민감 입력, 제안, 채택·수정·거절한 이유를 기록합니다.
- [ ] 독립적인 기대 결과와 비교해 유지할 동작과 교정할 동작을 구분합니다. 성능 개선에서는 동일 입력의 기능 결과가 유지되는지도 확인합니다.
- [ ] 성능 사례는 별도 JMH 프로젝트에서 입력 규모별로 측정하고 JDK·CPU·heap·warmup·fork 조건과 원본 결과를 남깁니다.
- [ ] 결과 화면에 전후 코드, 실패 테스트, 측정 조건과 개선 한계를 연결합니다.

**완료 조건:** 다른 개발자가 같은 테스트와 측정을 실행할 수 있어야 합니다. AI 사용 여부보다 오류를 어떻게 검증하고 설계를 판단했는지가 드러나야 합니다. [OpenJDK JMH 실행 안내](https://github.com/openjdk/jmh)

**공개 결과:** 실무 경험과 구분한 개인 재현 사례 한 편입니다. 측정 전에는 개선율을 기재하지 않습니다.

## 6 Iceberg와 Trino

Kafka·객체 저장소의 흐름이 안정된 뒤 데이터 플랫폼을 확장합니다. 처음에는 한 적재 작업과 한 SQL 조회로 범위를 제한합니다. 배치 작업은 필요할 때 실행하고, Spark·Trino를 모두 상시 운영하는 방식은 실제 자원 측정 후 결정합니다.

- [ ] 영속 catalog와 객체 저장소를 선택하고 table·snapshot 정보를 재시작 후에도 유지합니다.
- [ ] 합성 데이터를 Iceberg에 적재하고 Trino에서 조회해 원본 건수와 비교합니다.
- [ ] 작은 파일 증가, compaction 전후와 snapshot 보존 정책을 확인합니다.
- [ ] 반복 실행의 멱등성과 재시작 후 조회 결과를 검증합니다.

**완료 조건:** 원본·적재 작업·table snapshot·SQL 결과가 연결되고 재실행 방법이 문서화돼야 합니다. catalog와 저장소는 실제 선택한 조합의 요구사항에 맞춥니다. [Trino Iceberg connector](https://trino.io/docs/current/connector/iceberg.html)

**공개 결과:** 수집부터 저장·조회까지 한 데이터의 흐름을 따라가는 설명입니다. Airflow는 실제 스케줄링과 재시도 관리가 필요해질 때 추가합니다.

## 장비 자원과 학습

미니 PC는 단일 노드이며 기존 Docker 서비스와 함께 사용합니다. 확장 전후의 메모리 여유·디스크 증가량·기존 서비스 응답을 측정해 자원 예산을 정합니다. Jenkins agent 동시 실행 1개를 유지하고 이미지·빌드 산출물·로그의 보존 상한을 둡니다. 무거운 배치 실험과 CI 이미지 빌드는 겹치지 않게 실행합니다.

CKA 학습은 Lab과 연결합니다. context·RBAC·Service와 DNS·probe·requests/limits·PV·장애 진단을 직접 실습하고 TIL에 재현 방법을 남깁니다. 시험 합격 전에는 프로필의 표기를 준비 중으로 유지합니다.

## 바로 다음 작업

1. 외부 백업·격리 DB 복원·호스트 재부팅 검증을 완료했습니다. 초기 관리자 비밀번호 교체는 별도로 남아 있습니다.
2. CI/CD의 정상 B 배포·실제 실패 차단·이전 정상 A 복구를 완료했습니다. 전용 credential의 만료·회전은 운영 후속으로 관리합니다.
3. 게시 순서 보존과 API·웹 중단 시 공개 기록 유지·같은 정상 B 복원을 검증했습니다. 전용 자격증명의 수동 host cycle·실제 systemd service·timer 최초 자동 실행과 Pages 게시까지 기본 경로를 확인했습니다. 이후 실제 30분 간격과 credential 만료·회전을 별도로 확인합니다.
4. Kafka·객체 저장소 연결에 앞서 작업/outbox·DB 멱등 경계를 격리 환경에서 구현하고 기존 샘플 결과를 보존하는지 검증합니다. AI 개선 사례는 이후 5단계로 연결합니다.

각 결과는 소스 변경, 실행 방법, 실제 검증 결과, TIL 설명, 포트폴리오 링크로 연결합니다. 작업 완료 시 [진행 목록](ROADMAP.md)을 갱신하고 프로필에는 구현한 범위만 반영합니다.
