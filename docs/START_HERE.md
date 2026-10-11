# 현재 상태에서 이어서 구축하기

Java API·포트폴리오를 구현하고 Ubuntu 미니 PC에 K3s·Jenkins·Argo CD를 설치했습니다. 현재 상태와 관측 시각은 [미니 PC 근거](evidence/mini-pc/README.md), 실제 빌드는 [Jenkins 근거](evidence/jenkins-ci/README.md)에서 확인합니다. 전체 단계는 [진행 목록](ROADMAP.md)을 따릅니다.

## 확인한 결과

- 서버 지문 대조와 전용 키 SSH 인증, Ubuntu·포트·기존 서비스 읽기 전용 점검
- 기존 Docker 컨테이너 23개와 방화벽 설정 보존, 새 Lab 전용 설치·저장 경로
- K3s Node Ready와 클러스터 API·DNS·외부 HTTPS 통신 확인
- Java 21·Spring Boot API 테스트 15개, Astro·React 테스트 13개
- Linux runner의 이미지 빌드·MariaDB·API 교체·데이터 보존 검증
- GHCR 이미지 게시와 미니 PC에서 익명 다운로드
- Jenkins Kubernetes agent의 테스트·패키징·필수 산출물과 같은 SHA의 commit status 전달 확인
- 현재 main의 Jenkins·Actions 성공을 함께 요구하는 단일 이미지 게시 경로와 draft GitOps PR 자동 제안
- 정상 B 배포의 source·digest·GitOps·실행 이미지 추적과 실제 JUnit 실패의 게시·PR·배포 차단
- GitOps 값을 이전 정상 A로 되돌려 API/Web pin·source·전체 SQL·처리 시각·PVC와 기존 Docker 보존 검증
- 기존 저장소 `gitops/`의 digest 고정값으로 Argo CD 앱 배포
- API·웹·DB Ready, PVC Bound, 웹을 통한 12건 처리 결과 검증
- 공개 Pages용 실제 관측 기록 수집과 계약 검증
- 외부 암호화 백업·격리 DB 복원·호스트 재부팅: [근거와 한계](evidence/recovery/README.md)

Jenkins의 첫 빌드는 플러그인 충돌로 단계가 실행되지 않아 성공으로 인정하지 않았습니다. 교정 후 실제 단계·JUnit·산출물을 확인했고, 전용 status credential을 등록해 Actions 게시 gate에 연결했습니다. Actions가 유일한 이미지 게시자이며 사용자 승인으로 Actions의 PR 생성·승인 허용 설정과 draft GitOps PR 제안을 활성화했습니다. 워크플로는 PR을 자동 승인하거나 병합하지 않습니다. [정상 배포와 실패 차단](evidence/cicd-gate/README.md)을 확인합니다.

## 지금 접속하기

공개 결과는 [포트폴리오](https://devdooly.github.io/devdooly-platform-lab/)에서 볼 수 있습니다. **미니 PC에서 확인한 마지막 기록**은 정적 관측본이며, 실시간 상태는 아닙니다. API의 플랫폼 `NOT_CONFIGURED`는 상태 수집이 연결되지 않았음을 뜻합니다.

관리 화면은 [SSH 접속 도우미](runbooks/admin-access.md)를 사용합니다. 본인 PC에 준비한 `.local/open-admin.ps1`을 실행한 동안 Jenkins는 `http://127.0.0.1:18081`, Argo CD는 `https://127.0.0.1:18443`에서 접속합니다. 초기 로그인 정보는 미니 PC 프로젝트의 `.local/admin/`에 0600 파일로 보관합니다. 비밀번호를 채팅이나 Git으로 옮기지 않습니다.

Argo CD 자체 서명 인증서는 접속 안내에 따라 서버 인증서 지문을 대조합니다. 오래된 CA가 남아 있던 사용자 kubeconfig는 원본을 백업하고, 사용자 승인 후 현재 K3s 전용 0600 설정으로 교정했습니다. 현재 context는 `devdooly-platform-lab`이며 시스템 Helm·Docker·프록시는 유지합니다.

## 다음 작업

[다음 개발 계획](NEXT_STEPS.md)에 우선순위와 단계별 결과물·완료 조건을 정리했습니다.

1. 초기 관리자 비밀번호 변경과 본인 관리 화면 로그인 확인
2. 확보한 외부 백업의 추가 물리 장치 사본과 K3s·Jenkins archive 전체 복원 검토
3. 전용 status credential의 만료·회전과 게시 산출물 보존 운영 정리
4. 허용 필드만 수집하는 Jenkins·Argo CD collector 연결
5. 기존 프록시·DDNS·TLS 조건을 확인한 뒤 공개 읽기 API와 외부망 검증
6. Kafka·S3 및 AI 개선 재현을 진행 목록 순서대로 추가

CI/CD의 정상 배포·실패 차단·이전 digest 복구를 확인했으며, 다음 개발은 3단계 관측 공개입니다. 기존 서비스가 있으므로 재부팅·방화벽 변경·프록시 교체를 일괄 실행하지 않습니다. Windows 외부 사본의 무결성, 격리 DB 복원과 호스트 재부팅을 검증했습니다. K3s·Jenkins archive 전체 복원은 아직 별도 작업입니다. PV의 Delete 정책 때문에 PVC·namespace를 수동 삭제하면 데이터가 지워질 수 있습니다.

## 관련 자료

- [전체 계획](PROJECT_PLAN.md), [배포 결정](adr/0003-gitops-in-existing-repository.md)
- [API 계약](contracts/demo-api.md), [API 검증](evidence/api-mvp/README.md)
- [화면 검증](../apps/lab-web/VALIDATION.md), [관측 기록 계약](../apps/lab-web/OBSERVATION.md)
- [K3s bootstrap](runbooks/k3s-bootstrap.md), [플랫폼 설치](runbooks/platform-install.md)
- [이미지 게시](runbooks/image-publication.md), [앱 Helm](runbooks/app-helm.md)
