# 단계별 작업과 완료 조건

체크된 항목은 확인된 결과가 있는 작업입니다. 계획 단계의 기능에는 체크하지 않습니다. 현재 로컬·Linux runner 검증과 미니 PC의 K3s·Jenkins·Argo CD 실행을 확인했으며, 실제 근거와 남은 작업을 구분합니다. 각 항목은 실제 검증과 함께 갱신합니다. 우선순위와 구체적인 다음 결과물은 [다음 개발 계획](NEXT_STEPS.md)을 따릅니다.

## 저장소 준비 완료

- [x] 프로젝트 이름과 로컬 저장소 위치 결정
- [x] 전체 계획과 첫 기술 결정 정리
- [x] 시작 안내, 환경 점검 절차와 검증 양식 작성
- [x] Git 초기화와 문서·디렉터리 안내의 초기 커밋
- [x] GitHub origin 연결과 main 최초 push

## 0 기존 환경 확인

- [x] Ubuntu 버전·지원 상태, CPU·메모리·디스크 확인
- [x] 기존 서비스·컨테이너·포트와 데이터 경로 조사
- [x] SSH 접속 방법과 서버 지문 확인
- [x] 백업 현황과 별도 백업 위치 결정: [외부 암호화 백업](evidence/recovery/README.md)
- [ ] 기존 DDNS·공인 IP·CGNAT 여부와 HTTPS 선택지 확인
- [x] 설치 경로·PV 경로·자원 예산·원상 복구 범위 기록

완료 조건: 기존 서비스에 미칠 영향을 설명하고, 보존할 데이터와 새로운 설치 범위를 정할 수 있습니다.

## 1 최소 서비스와 포트폴리오

- [x] Java·Spring Boot·빌드 도구·Node·Astro 버전 선택과 고정
- [x] 합성 데이터 schema, seed와 독립적인 기대 결과 정의
- [x] Spring Boot 샘플 결과 조회 API, JPA·Flyway 구현과 H2 검증
- [x] Linux runner의 MariaDB 실제 연결·컨테이너·API 교체와 멱등 검증: [근거](evidence/compose-ci/README.md)
- [x] 입력 검증·중복·시간·실패 시나리오 확인: API 테스트 15개 통과
- [x] Astro·React Lab 조회 화면과 로컬 API 연결: 테스트 13개·타입 검사·HTTP smoke 통과
- [x] 공개 포트폴리오 저장소와 Pages 주소 확인
- [x] GitHub Actions 최초 게시 성공과 외부 화면 검증: [공개 기록](evidence/web-mvp/README.md)
- [x] 소개·기술 경험·프로젝트 설명과 기존 TIL 연결
- [x] 테스트 결과와 공개 가능한 샘플 결과 기록

완료 조건: 동일 샘플의 기대 결과를 반복 검증할 수 있고, 화면에서 현재 구현 범위와 설계를 이해할 수 있습니다.

근거: [API 검증](evidence/api-mvp/README.md), [화면 검증](../apps/lab-web/VALIDATION.md), [Pages 게시](runbooks/pages.md). 1단계의 로컬·임시 Linux 컨테이너와 Pages 검증을 마쳤습니다. 미니 PC 운영 결과는 [실제 서버 근거](evidence/mini-pc/README.md)에 별도 기록합니다.

## 2 K3s와 CI 및 CD

- [x] 점검 결과에 맞춰 K3s와 namespace·자원 설정 구성
- [x] Jenkins controller executor 0, 별도 agent·테스트 pipeline 정의 작성
- [x] Jenkins 실제 Kubernetes agent·테스트·패키징 성공 확인: [근거](evidence/jenkins-ci/README.md)
- [x] 실제 JUnit 실패·failure status·Actions 검증 실패에서 이미지·PR·배포 차단과 기존 B 보존 확인: [근거](evidence/cicd-gate/README.md)
- [x] Actions 이미지 빌드·GHCR 게시·digest 기록과 서버 익명 다운로드
- [x] API·화면·MariaDB 앱 Helm chart 작성과 lint·render 검증: [근거](../infra/charts/platform-lab/ci/render-validation.json)
- [x] 기존 저장소 gitops/에 실제 image digest·환경 values·Application 연결: [결정](adr/0003-gitops-in-existing-repository.md)
- [x] 같은 source SHA의 Jenkins·Actions 검증 → Actions 단일 게시 → draft GitOps PR 연결: [절차](runbooks/cicd-publication.md)
- [x] Argo CD 동기화와 실제 서비스 버전 확인
- [x] 고정 image digest의 정상 배포와 Argo CD Synced·Healthy 확인
- [x] 정상 B 배포에서 source·OCI digest·GitOps commit·실행 이미지와 데이터 보존 연결: [근거](evidence/cicd-gate/README.md)
- [x] GitOps 값을 이전 정상 A digest·source로 복구하고 Argo Synced·Healthy, HTTP·전체 SQL·처리 시각·DB/PVC·기존 서비스 보존 검증: [근거](evidence/cicd-gate/README.md)
- [x] 재부팅 복구와 필요한 설정·데이터의 외부 백업 확보: [실제 검증](evidence/recovery/README.md)

완료 조건: 소스 commit부터 image digest, GitOps commit, 실행 버전까지 추적되고 실패·복구 결과가 남습니다.

정상 A → B 배포, 실제 main의 실패 차단, GitOps A 복구를 확인했습니다. 2단계의 세 운영 시나리오를 완료했고 3단계 관측 공개를 진행합니다. token의 실제 만료·회전, 동시 요청 실험과 K3s·Jenkins archive 전체 복원은 별도 운영 후속으로 남깁니다.

## 3 외부 공개

- [x] 관리 도구의 SSH 인증 접속과 localhost 화면 응답 검증 ([접속 안내](runbooks/admin-access.md))
- [ ] 미니 PC 공개 Lab의 HTTPS 경로와 실시간 API 연결
- [x] 공개 플랫폼 관측의 strict allowlist 계약·validator와 읽기 전용 collector 구현: [계약](../apps/lab-web/PLATFORM_OBSERVATION.md)
- [x] 전용 ServiceAccount로 지정 Deployment·DB StatefulSet·Pod 준비 상태·Argo와 main의 Jenkins status 실제 수집: [근거](evidence/platform-observation/README.md)
- [x] 실제 읽기 권한 허용·거부, 출력 0600, 인증 실패 때 마지막 성공 전체·시각 유지 및 회복 확인: [근거](evidence/platform-observation/summary.json)
- [x] collector 실패·브라우저 조회 실패·2시간 초과·출처 차이를 구분하는 UI 로컬 검증: 전체 26개 테스트·타입 검사·Pages 경로 빌드
- [x] 허용 JSON의 수동 outbound Pages 게시·HTTP 401 실패 보존과 새 플랫폼 카드 공개 1280px·390px 확인: [근거](evidence/platform-observation/README.md)
- [x] 실제 순서 역전 게시에서 발견한 seed 회귀 교정과 이전 성공 artifact·공개 JSON·브라우저 기준 재검증: [실패 발견과 교정](evidence/platform-observation/README.md)
- [x] Ubuntu collector 41개·최종 자동화 35개 root·일반 사용자 각각 통과와 비활성 설치·systemd 정적 검증: [상태](../infra/observation/AUTOMATION.md)
- [x] 전용 Pages 자격증명으로 수동 host cycle·Pages 게시와 전체 공개 JSON 일치 확인
- [x] 실제 systemd service 실행 성공·root 0600 상태 파일·임시 SA 토큰 정리 확인
- [x] timer enabled·active와 최초 자동 trigger의 Pages 게시·전체 공개 JSON·브라우저 확인
- [x] 최초 자동 실행을 포함한 11회의 Pages build·deploy success와 실제 서비스 완료 간격 검증: [실행 목록](evidence/platform-observation/README.md)
- [ ] credential 실제 만료·회전과 장기간 운영 검증
- [x] API·웹 replicas 0 중단에서 공개 홈·마지막 기록·DB·기존 서비스 보존과 같은 정상 B 복원 검증: [근거](evidence/platform-observation/README.md)
- [ ] 공개 읽기 API 구현과 실시간 연결
- [ ] 휴대폰 외부망에서 TLS·화면·API와 관리 접근 제한 확인
- [x] 검토한 실제 앱 관측 snapshot을 Pages 소스에 등록: [근거](evidence/mini-pc/README.md)
- [x] Lab 연결 실패와 합성 샘플을 표시하고 미관측 시각을 구분
- [x] 실제 관측 snapshot·수집 시각·source SHA 표시 구현과 관측 계약 검증
- [ ] 필요한 항목에 한해 Jenkins·Argo CD 실시간 요약과 배포 이력 연결

완료 조건: 방문자가 합성 데이터 결과와 배포 요약을 볼 수 있고, Lab 중단 때도 공개 홈의 프로젝트와 이전 결과를 읽을 수 있습니다. 첫 공개 목표는 여기까지입니다. 실제 수집·인증 실패·회복·공개 게시·브라우저·게시 순서 보존과 API·웹 중단 후 같은 정상 B 복원을 확인했습니다. 수동 host cycle·실제 systemd service·timer 자동 실행과 반복 게시 11회의 Pages build·deploy success까지 검증했습니다. 첫 실행의 즉시 trigger와 후속 10개 실제 간격을 구분했고, 완료 간격은 1825.569287~1875.101367초였습니다. 만료·회전의 장기 운영과 선택적인 실시간 공개 API·inbound 연결은 별도 후속입니다.

## 4 Kafka와 객체 저장소

검토용 DB foundation을 구현했으며 운영에는 배포하지 않았다. [격리 검증 결과](evidence/db-job-foundation/README.md)와 [내부 서비스 절차](runbooks/db-job-foundation.md)를 연결한다.

- [x] V2 작업·outbox·단일 슬롯, raw 원본 hash·DB 멱등 경계 구현
- [x] 실제 MariaDB의 V1 업그레이드·빈 DB 초기화·반복 시작, 동시 제출·rollback·재전달·Asia/Seoul 시각 일치 검증
- [x] 이전 image의 V2 DB 호환성과 기존 운영 SQL·PVC·Docker 보존, 임시 자원 정리 확인

- [x] 명시적 Kafka publisher·worker, ACK 뒤 outbox 확인·Get-only 원본 검증·DB commit 뒤 수동 offset 구현: [ADR 0006](adr/0006-explicit-kafka-dispatch.md)
- [x] 실제 Kafka·MariaDB·Garage에서 JVM 중단 세 경계·재전달 멱등·손상 원본 fail-stop/명시적 fixture 복구, 결과 건수·offset·lag 0·기존 운영 보존: [근거](evidence/kafka-redelivery/README.md)
- [x] 결정적 결과·실패 파일 export, 전체 bytes/크기/SHA 확인 뒤 outbox·EXPORTED·슬롯 해제: [ADR 0007](adr/0007-verified-result-export.md)
- [x] 실제 MariaDB/Garage 정상·반복/다음 슬롯 보존·부분 저장·손상 거부·최종 DB rollback·JVM 중단 2개 경계와 재시도, 기존 운영 보존: [근거](evidence/result-export/README.md)
- [ ] 상시 worker/export 실행기·운영자 영속 정지/재개·job/export 관측과 운영 배포 검증
- [ ] 다중 partition·이벤트별 전달 순서 검증이 필요할 때 별도 확장
- [x] Garage·Java SDK의 필요한 API·기본 checksum 실패와 호환성 교정 검증 후 한정 선정: [ADR 0005](adr/0005-verified-raw-source-storage.md)
- [x] 원본 전체 bytes·크기·SHA-256, 상태 전환 전 실패·재시도와 컨테이너 재생성 후 Get-only 보존: [근거](evidence/s3-source-storage/README.md)
- [x] 실제 MariaDB·Garage 결합의 정상·손상·DB statement 오류 rollback과 원본 보존·재시도, 같은 DB 반복 및 운영 보존: [근거](evidence/mariadb-s3/README.md)
- [ ] 자동 보존 정책·지연·자원 지표 연결
- [ ] 최대 1,000개 이벤트·전체 동시 작업 1개·요청 빈도 제한 검증
- [ ] 제한을 검증한 뒤 공개 샘플 실행 기능 추가

완료 조건: 입력 건수가 성공·실패·중복·대기로 설명되고, 데이터 유실이나 무제한 실행 없이 결과를 확인할 수 있습니다.

## 5 LLM 개선 사례와 복구

- [ ] 개인 공개 예제로 연산 비효율과 시간 처리 오류 정의
- [ ] AI 제안·사람의 판단·변경 이유·전후 테스트 기록
- [ ] seed·입력 크기·환경·반복 조건을 고정해 측정
- [x] 별도 테스트 볼륨으로 DB 복원 검증: [실제 검증](evidence/recovery/README.md)
- [ ] 파일·K3s·Jenkins archive 전체 복원 검증
- [ ] 결과와 한계를 TIL 및 포트폴리오에 연결

완료 조건: 개선 전 실패·개선 후 성공과 측정 원본을 재현할 수 있고, 백업한 데이터의 복원 결과가 있습니다.

## 6 데이터 플랫폼 확장

- [ ] Iceberg의 영속 catalog와 backing store 결정
- [ ] Spark 적재·compaction과 Trino 조회 연결
- [ ] 재시작 후 메타데이터와 데이터 조회 검증
- [ ] 필요한 경우 Airflow DAG 추가
- [ ] CI 빌드와 겹치지 않는 실행 예산·종료·복구 절차 기록

완료 조건: 동일 warehouse에서 쓰기·조회·재시작·compaction이 검증되고 실행 시 자원 사용량이 남습니다.

단계는 의존 순서이며 기간 약속이 아닙니다. 각 단계 완료 후 다음 확장의 필요성과 자원을 다시 판단합니다.
