# Platform Lab 다음 개발 계획

초기 계획: 2026년 10월 12일 · 최근 V2 운영 배포·격리 export 경계 중단 복구 검증: 2026년 10월 15일

Java 백엔드, 데이터 처리, 배포와 운영 경험을 방문자가 직접 확인할 수 있는 포트폴리오로 발전시킵니다. 외부 백업·격리 DB 복원·재부팅과 CI/CD의 정상 배포·실패 차단·이전 image digest 복구를 확인했습니다. **기존 플랫폼 관측의 2026-10-12 수집·실패 보존·Pages 게시·공개 화면과 자동 운영·반복 게시 11회를 검증**했습니다. 게시 순서 회귀 교정, API·웹 중단 후 같은 정상 B 복원에 이어 전용 Pages 자격증명으로 수동 host cycle·실제 systemd service·timer 자동 실행을 확인했습니다. 실제 완료 간격은 약 30~31분이었고 자격증명 만료·회전과 장기간 운영은 별도 후속입니다. Kafka·Garage·상시 worker의 최초 배포와 정상 재시작 당시 총 3작업·파일 6개·슬롯 해제를 확인했습니다. 새 job timer의 자동 게시 2회·완료 간격 1개와 전용 PVC 외부 사본의 격리 복원·clone 물리 블록 복원을 검증했습니다. 이후 보존 계획·새 합성 PVC 정리·작은 자원 관측과 최대 1,000개 입력·동시 접수 경계를 격리 검증했습니다. V2 지원 API·worker를 운영에 함께 배포하고 내부 V2 작업 한 건을 추가해 현재 총 7개 EXPORTED 작업·파일 14개를 확인했습니다. 별도 격리 worker의 export 경계 강제 종료 복구도 확인했습니다. 다음은 객체 GC·다른 장애 경계/호스트 중단·과부하 정책·장기간 운영과 AI 개선·데이터 플랫폼 사례입니다.

[공개 Lab](https://devdooly.github.io/devdooly-platform-lab/) · [전체 진행 목록](ROADMAP.md) · [현재 접속 안내](START_HERE.md)

## 출발점

| 영역 | 확인한 내용 | 다음에 채울 부분 |
| --- | --- | --- |
| Java API·worker | 기본 140개, 격리 기능 IT 5개·Linux 1,000개 입력 3회·export 경계 강제 종료 복구, V2 운영 배포 후 총 7작업/14파일 확인 | 다른 장애 경계·호스트 중단·과부하 정책·장기간 관측 |
| Kafka·Garage 복구 | 외부 사본의 전용 3PVC 복원·clone 물리 블록, 보존 정책·합성 정리 검증 | 장기간 보존 운영·객체 GC·복구 절차 유지 |
| 포트폴리오 | 웹 34개, 기존 플랫폼 11회와 별도 새 job timer 자동 게시 2회·간격 1개 확인 | 장기간 반복 운영·자격증명 회전 |
| Jenkins·Actions | 같은 SHA의 두 CI 성공·게시·draft GitOps PR·정상 B 배포·실제 실패 차단, main의 공개 status 수집 | credential 만료·회전과 게시 이력 보존 운영 |
| Argo CD와 Helm | 정상 A → B → A GitOps 복구, Synced·Healthy·데이터 보존과 제한된 실제 상태 수집 | 주기 관측의 반복 운영과 실패 대응 |
| 운영 | 외부 암호화 백업·격리 DB 복원·호스트 재부팅, 사용자 kubectl 복구 | 초기 비밀번호 교체, 추가 장치 사본·전체 archive 복원 |

GitHub Actions를 유일한 이미지 게시자로 유지하고, 전용 Jenkins status credential과 같은 source SHA의 두 CI 성공을 게시 조건으로 활성화했습니다. 사용자 승인으로 Actions PR 설정과 draft GitOps PR 자동 제안도 켰습니다. 공개 Lab은 기존 앱의 마지막 실제 관측본을 보여줍니다. 별도 플랫폼 collector는 최소 읽기 권한으로 실제 상태를 수집했으며 새 관측본을 수동 게시했고, 게시 순서 회귀 교정 후 실제 복구·순서 보존을 재검증했습니다. 실시간 공개 API와 조회 API 내부의 플랫폼 수집은 아직 연결하지 않았습니다. Windows 외부 암호문은 인증·해시를 확인했고, DB는 서버의 새 논리 dump로 격리 복원했습니다. 이후 Kafka/Garage 전용 PVC 3개는 인증한 외부 사본에서 격리 복원했습니다. K3s·Jenkins archive 전체 복원은 별도로 남아 있습니다.

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

아래 11회는 2026-10-12 기존 플랫폼 수집기의 검증이며 새 job 수집 코드의 정기 실행 증거와 구분합니다.

검증한 JSON을 outbound dispatch로 Pages에 반영하고 공개 브라우저를 확인했습니다. 실제 순서 역전 게시의 seed 회귀는 교정 후 공개 JSON·브라우저·이전 artifact로 보존을 재검증했습니다. 초기 자동화 비활성 설치와 정적 검증에 이어, 전용 Pages 자격증명으로 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 Pages 게시와 전체 공개 JSON 일치를 확인했습니다. 이후 최초 자동 실행을 포함한 11회가 모두 Pages build·deploy success였고 10개 실제 서비스 완료 간격은 1825.569287~1875.101367초였습니다. timer는 enabled·active입니다. 이후 실시간 조회가 필요한 항목에 한해 공개 읽기 API를 연결합니다. 이번 단계에서 새 inbound 경로를 열지 않았고, Jenkins·Argo CD 관리 화면은 인증된 관리 경로를 유지합니다.

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
- [x] 최초 자동 실행을 포함한 11회의 Pages build·deploy success와 실제 서비스 완료 간격을 검증했습니다.
- [ ] credential 실제 만료·회전과 장기간 운영을 검증합니다.
- [ ] 필요한 경우 기존 프록시·TLS를 확인한 뒤 읽기 API를 연결하고 휴대폰 외부망에서 확인합니다.

**완료 조건:** 정상 수집, collector 실패, Lab 중단 시나리오에서 표시 내용이 실제 관측 범위와 일치합니다. 공개 화면은 현재 JVM 정보와 별도 정적 관측·CI/CD 근거를 구분합니다. 실제 API·웹 replicas 0에서 공개 홈·마지막 기록 유지와 같은 정상 B 복원을 확인했습니다. 호스트·DB 전체 중단은 이 실험 범위가 아니며 오래된 기록·브라우저 조회 실패는 오프라인 UI 검증입니다.

**현재 확인한 결과:** [실제 수집·실패 후 보존·게시·브라우저와 반복 실행 11회](evidence/platform-observation/README.md)를 제공합니다. 게시 순서 회귀 교정과 API·웹 중단·같은 정상 B 복원, 수동 host cycle·실제 systemd service·timer 자동 실행을 검증했습니다. 반복 11회의 Pages build·deploy 결과와 실제 간격을 확인했으며 각 회차의 전체 공개 JSON·UI 비교를 모두 수행했다는 뜻은 아닙니다. 같은 마지막 intent 재전송 차단도 실제 확인했으며 전체 이력의 exactly-once 보장은 아닙니다. 장기간 운영과 credential 권한 범위 조회·만료·회전은 별도 확인 범위로 남깁니다.

## 4 Kafka와 객체 저장소

[최초 계획](plans/phase4-messaging-storage.md)의 DB·원본·Kafka·export 경계를 격리 검증한 뒤, 2026-10-15 미니 PC K3s에 Kafka·Garage·상시 worker를 GitOps로 처음 배포했습니다. 최초 배포 당시 내부 고정 fixture 두 작업이 각 12/7/3/2/0으로 완료됐고 결과·실패 파일 총 4개를 전체 Get·크기·SHA-256으로 확인했습니다. 실행 슬롯은 비었으며 Kafka offset 2·log end 2·lag 0을 확인했습니다. 기존 seed·V1 처리 시각·PVC와 Docker 전체 38개·실행 26개를 보존했습니다. [최초 배포·게시 근거](evidence/runtime-deployment/README.md)를 연결합니다.

최신 운영 API·worker는 같은 source `6c5aff948770982dd44c8d44547131b3ccf6ddd9`의 V2 지원 이미지입니다. 별도 GitOps PR로 API·웹을 먼저 교체하고 worker를 뒤이어 교체한 뒤 내부 V2 fixture를 한 번 접수했습니다. 기존 여섯 작업을 보존한 채 V2의 입력 1,000 = 성공 500 + 실패 300 + 업무상 중복 200 + 대기 0, EXPORTED·슬롯 해제·Kafka offset 7/log end 7/lag 0을 확인했습니다. 현재 총 7작업·파일 14개이며, 실제 GET 21개는 기존 18개 객체와 새 원본·결과·실패 객체 3개를 합친 수입니다. [V2 운영 배포·공개 게시 근거](evidence/input-v2-deployment/README.md)를 현재 기준으로 사용합니다.

이전 단계의 [DB](evidence/db-job-foundation/README.md), [원본 S3](evidence/s3-source-storage/README.md), [실제 결합](evidence/mariadb-s3/README.md), [Kafka 중단·재전달](evidence/kafka-redelivery/README.md), [export](evidence/result-export/README.md), [상시 실행기](evidence/continuous-runtime/README.md) 검증은 각각 당시 조건과 한계를 유지합니다. 최초 운영 배포 당시 기본 API 128개·웹 34개와 별도로 확인했으며, 새 수집·게시 코드는 실제 Ubuntu 검사 135개를 통과했습니다. 후속 V2 소스의 기본 API 검증은 140개이며 아래 격리 기능·자원 검증과 구분합니다.

- [x] 고정 12개 fixture의 시간 역순·잘못된 값·업무상 중복 처리와 독립 기대 결과를 명시했습니다.
- [x] 격리 Kafka·MariaDB·Garage에서 ACK 뒤·DB commit 전후 JVM 강제 종료·재전달 멱등·offset을 검증했습니다.
- [x] 실제 K3s의 별도 worker가 연속 두 작업을 처리하고 두 파일 확인 뒤 슬롯을 해제했습니다.
- [x] 별도 작업 관측에 상태·시각·입력 회계식·예상 파일 SHA/크기를 연결하고 실제 배포 기록을 Pages에 게시했습니다.
- [x] 새 job 관측의 실제 systemd service 성공·Pages 게시·공개 JSON 전체 일치, private 0600·임시 SA token 정리를 확인했습니다.
- [x] 기존 timer의 enabled·active와 30분 주기·최대 60초 임의 지연 설정을 복구했습니다.
- [x] 원래 timer의 새 job 자동 실행·Pages 게시 2회와 완료 간격 1개(1809.371239초), unit/collector 무변경·공개 JSON 전체 일치를 검증했습니다.
- [ ] 새 job 수집의 장기간 반복 운영·실제 자격증명 만료/회전을 검증합니다.
- [x] 실제 idle worker Pod를 UID 조건으로 정상 교체하고 STOPPED→새 RUNNING·정상 TERM 종료·기존 두 작업/파일/offset·다른 서비스 보존을 확인했습니다: [근거](evidence/runtime-recovery/README.md)
- [x] 교체 worker에 새 고정 fixture를 접수해 처리·EXPORTED·파일 2개 실제 Get·슬롯 해제·Kafka offset 3/lag 0을 확인하고 원래 두 작업 전체를 보존했습니다.
- [x] Kafka/Garage 전용 3PVC의 cold copy·외부 AES-256-GCM 사본 인증·반환 해시·새 PVC 전체 manifest 복원을 검증했습니다: [근거](evidence/runtime-pvc-restore/README.md)
- [x] 격리 정책의 실제 원본 접근 차단과 Kafka 3 record/offset·Garage 9개 inline 객체의 GET 일치를 확인했습니다.
- [x] clone에만 128KiB canary를 한 번 PUT해 물리 블록을 만들고, 추가 2PVC 복원·Pod 교체 전후 각 GET10을 확인했습니다.
- [x] 복제 Kafka도 정상 TERM 교체 후 같은 PVC·3개 record의 key/value/시각·offset 3·lag 0을 보존했습니다.
- [x] 최신 검증본·미완료·키를 보호하는 순수 계획기 31개 테스트·실제 dry-run 후보 0과 새 합성 PVC만의 실제 정리 경계를 검증했습니다.
- [x] 고정 12개 입력 3회에서 기존 cgroup 설정·CPU/RSS/PSS·디스크 snapshot·처리/export 지연을 관측했습니다: [근거](evidence/retention-resource-budget/README.md)
- [x] 격리 기능 IT 5개에서 정확히 1MiB인 V2 입력 3회·기존 V1, 2/8개 동시 접수의 한 슬롯 경합, 1,001개/1MiB+1 거부·재접수/충돌 경계를 검증했습니다: [근거](evidence/input-concurrency-load/README.md)
- [x] 별도 Linux Docker에서 1CPU·768MiB의 같은 candidate worker로 1,000개 입력 3회·원본/결과/실패 전체 GET 9개와 자원을 관측했습니다. 이 세 입력은 각각 99,600B이며 정확히 1MiB 검증과 구분합니다.
- [x] V2 지원 API·worker를 모두 운영에 교체한 뒤 내부 V2 한 건·기존 여섯 작업 보존·총 7작업/14파일·공개 JSON 일치를 확인했습니다: [근거](evidence/input-v2-deployment/README.md)
- [ ] 객체 tombstone/GC·과부하와 지속 부하의 한도는 별도로 검증합니다.
- [x] 별도 Linux Docker의 V2 작업에서 결과 파일 확인 후 실패 파일 PUT을 전달하기 전 worker를 한 번 강제 종료하고, 같은 jar의 새 worker가 미완료 export를 복구하는지 검증했습니다: [근거](evidence/maximum-export-crash/README.md)
- [ ] 다른 작업 경계의 중단·진행 중 호스트 재시작 범위를 별도로 검증합니다.
- [ ] 실패 데이터 재처리와 미완료 객체를 보존하는 명시적 정리 절차를 만듭니다.
- [ ] consumer lag의 자동 공개 관측·장기간 지연/자원 지표와 과부하 대응 정책을 검증합니다. 최대 1,000개와 2/8개 동시 접수 경계의 완료를 지속 처리량·rate limit 보장으로 확대하지 않습니다.

초기 실제 worker 정상 재시작 당시 관측 절차는 17.808초였고 새 Pod의 restartCount는 0입니다. 기존 두 작업의 전체 SQL·시각과 파일 4개의 전체 Get·크기·SHA, Kafka offset 2·log end 2·lag 0이 유지됐습니다. 23개 보존 검사에서 다른 5개 Pod·Docker 전체 38개/실행 26개·전체 PVC 6개/Lab 4개·호스트 상태를 확인했습니다. 이 범위는 작업이 없는 정상 TERM 교체이며 진행 중 crash·PVC 복원·고가용성 검증으로 확대하지 않습니다.

그 정상 재시작의 후속 검증 당시 교체된 worker에 별도 고정 fixture `lab-fixture-20261015-recovery`를 접수해 입력 12 = 성공 7 + 실패 3 + 업무상 중복 2 + 대기 0, EXPORTED와 슬롯 해제를 확인했습니다. 새 결과·실패 파일 2개도 실제 Get의 전체 내용·크기·SHA-256을 대조했습니다. 전체 작업은 3개·확인 파일 6개가 됐고 Kafka offset 3·log end 3·lag 0입니다. 원래 두 작업의 전체 SQL·시각·HTTP 요약과 파일 4개는 그대로 보존했습니다.

원본 전용 PVC 3개의 외부 사본 복원과 별도 clone 물리 블록 복원을 구분했습니다. 원본의 9개 객체는 모두 inline이므로, data 블록 복원은 clone 전용 128KiB canary로 별도 입증했습니다. 원본 객체 쓰기·운영 PVC 덮어쓰기는 하지 않았고 시험 대상 5PVC의 요청량은 총 29Gi입니다. 이 요청량은 실제 사용량이나 처리 용량 측정이 아닙니다. 시험용 workload 3개를 정상 종료해 Pod 0개·Retain PVC 5개를 남겼습니다. 최종 보존 검사 28개에서 원본 SQL·작업/파일 정보·PVC 6개·Ready Pod 6개와 기존 Docker 38개/실행 26개의 상태를 확인했습니다. [실행 절차](runbooks/runtime-pvc-recovery.md)를 따릅니다.

이후 고정 12개 입력의 자원 관측 당시 세 작업을 추가해 총 6개 EXPORTED 작업·파일 12개의 전체 Get·Kafka offset 6/lag 0을 확인했습니다. 약 63초·64개 샘플의 worker 작업 구간 평균 CPU는 0.04235 core, 약 1초 관측 최대는 0.66622 core였습니다. DB 생성→export 기록 평균은 1.5943초지만 cold stage 요청부터는 14.0757초로, 시작·접수 비용을 구분했습니다. 11분 디스크 snapshot의 active PVC 증가 972KiB는 heartbeat/WAL 영향을 포함합니다. [정의·조건·한계](runbooks/retention-resource-budget.md)를 함께 읽으며 처리 용량이나 SLA로 확대하지 않습니다. 최종 25개 검사에서 기존 11PVC/PV·원본 Pod 6개·Docker 38개/실행 26개·기존 업무 SQL/객체·timer 설정과 주기 보존도 확인했습니다.

격리 Linux의 V2 export 경계 검증은 12개 검사를 통과했습니다. 첫 결과 파일의 PUT·전체 GET을 확인하고 두 번째 실패 파일 PUT을 upstream에 전달하기 전에 해당 worker만 한 번 SIGKILL했습니다. exit 137·비 OOM을 확인한 뒤 같은 source/jar의 새 worker가 PENDING export를 완료했고, 처리 SQL·시각과 첫 결과 파일 전체 바이트, 기존 네 작업/12개 객체와 이전 Kafka offset을 보존했습니다. 새 작업의 offset 1/log end 1/lag 0·슬롯 해제와 소유 컨테이너의 종료를 확인했습니다. 이 검증은 독립 Docker 환경의 한 export 경계이며 운영 K3s 중단·호스트 재시작·고가용성을 입증하지 않습니다. [전체 근거](evidence/maximum-export-crash/README.md)를 연결합니다.

최신 V2 배포 후 수동 수집·Pages 게시에서도 실제 job·플랫폼 공개 JSON 전체가 수집 원본과 일치했습니다: [최신 게시 근거](evidence/input-v2-deployment/README.md). 그보다 앞선 재시작 검증에서는 새 job의 원래 timer 자동 수집·게시 2회와 완료 간격 1개(1809.371239초)를 확인했습니다. [후속 검증 근거](evidence/runtime-recovery/README.md)는 과거 플랫폼 collector 11회와 구분합니다. 공개 화면은 약 30분 주기의 마지막 기록이며 실시간 조회가 아닙니다. 5분 heartbeat 경고는 마지막 실행 신호의 나이이고 프로세스 중단 판정이 아닙니다. 공개 POST는 없고 내부 `--lab-runtime=stage`가 고정 fixture만 접수합니다.

**완료 조건:** producer ACK·DB 멱등 처리·offset·export 확인을 각각 설명하고 실제 운영 한계를 기록합니다. 단일 노드·partition 1/RF1을 고가용성이나 전체 exactly-once로 표현하지 않습니다. [Kafka producer 설정](https://kafka.apache.org/42/configuration/producer-configs/)

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

## 내부 접수 간격 후보 검증

DB의 기본 30초 승인 간격은 구현·격리 검증을 완료했습니다. 기본 157개·실제 MariaDB/Garage 19개·외부 인증 SQL 복원본의 이전 binary 호환 8개와 같은 source CI 성공을 확인했습니다. [근거](evidence/admission-cooldown/README.md), [전환·원복 절차](runbooks/admission-cooldown.md)를 따릅니다. 운영은 아직 source `6c5aff94`·schema V3이며 다음은 새 이미지의 API V4 migration→worker 교체·기존 자료 보존입니다. 구형 stage는 정책을 우회하므로 혼용하지 않습니다. 지속 부하·HTTP QPS 제한·전체 RuntimeMain의 충전된 cooldown 재시작은 별도 미검증입니다.

## 바로 다음 작업

1. **보존 운영과 객체 GC:** 전체 운영 참조21개 KEEP·후보0과 새 Garage의 합성 객체2개 자연 GC를 확인했습니다. [객체 보호 근거](evidence/object-reference-gc/README.md)의 범위를 유지하며 운영 tombstone·삭제 intent·재전달/resume·백업 의존성을 설계합니다. 운영 삭제 실행기와 metadata DB 축소는 구현하지 않았습니다.
2. **검증 확대:** 최대 1,000개 입력·2/8개 동시 접수와 격리 Linux 3회의 관측, 한 export 경계의 worker 강제 종료 복구는 완료했습니다. 다음은 다른 장애 경계·진행 중 호스트 중단·지속 부하·과부하 거부 정책입니다. 한 슬롯 경합은 rate limiter가 아니며 작은 표본을 처리 용량·SLA로 표현하지 않습니다. 공개 실행은 열지 않습니다.
3. **장기간 수집 운영:** 원래 timer의 자동 게시 2회·실제 간격 1개는 확인했습니다. 더 긴 반복·실패 후 이전 기록 보존·자격증명 만료/회전을 이어서 검증합니다. 초기 관리자 비밀번호 교체·K3s/Jenkins archive 전체 복원도 별도 운영 후속입니다.
4. **이후 확장:** 격리 export 경계의 worker 강제 종료 복구와 기존 idle 정상 교체를 구분하고, 진행 중 호스트 재시작·고가용성은 별도 미검증으로 남깁니다. AI 개선 사례는 5단계의 독립 합성 예제로 연결합니다. 공개 실행은 내부 고정 fixture 명령으로 제한하며 새 inbound 경로는 필요성을 먼저 판단합니다.

각 결과는 소스 변경, 실행 방법, 실제 검증 결과, TIL 설명, 포트폴리오 링크로 연결합니다. 작업 완료 시 [진행 목록](ROADMAP.md)을 갱신하고 프로필에는 구현한 범위만 반영합니다.
