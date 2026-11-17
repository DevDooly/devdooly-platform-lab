# 새 VM 설치와 서비스별 검증 기록

## 먼저 수행한 새 Ubuntu VM

2026-11-16~17 KST의 Ubuntu 22.04 amd64 실습입니다. 당시 실행은 단계별 수동 준비와 일부 스크립트를 사용했습니다. 새 [전체 설치기](../../runbooks/fresh-lab.md)의 설치 완료 여부는 해당 설치기를 실행한 기록과 대조합니다.

| 실제 순서 | 관측 결과 |
| --- | --- |
| Windows에서 소스 검증 → Ubuntu에서 Docker Compose | Java와 Astro를 빌드하고 Ubuntu의 MariaDB·API·웹 컨테이너를 Healthy까지 확인했습니다. 첫 확인에서는 포워딩과 포트 설정이 맞지 않아 `Connection refused`를 기록했습니다 |
| K3s와 Helm → Jenkins → Argo CD | 11월 16일 19:45 KST K3s `v1.36.5+k3s1`에서 Node Ready. CoreDNS 객체 초기 생성 전에 발생한 `NotFound`를 기록했고 생성 후 확인했습니다. Jenkins `2.580.1` 로그인 HTTP 200, Argo CD `v3.5.4`와 기본 앱 `Synced`·`Healthy`를 확인했습니다 |
| Argo CD로 MariaDB·API·Astro 웹 | PVC Bound, 웹·API 응답, 저장 표본 입력 12·성공 7·실패 3·중복 2·대기 0을 확인했습니다 |
| VM 재부팅 → 네트워크 수정 후 재시험 | 첫 재부팅에서는 DHCP 주소 변경으로 K3s 바인딩이 어긋났습니다. 호스트 전용 고정 주소와 K3s 설정을 맞춘 뒤 재부팅에서 자동 기동과 저장 표본 보존을 확인했습니다 |
| Jenkins CI → Actions → Argo CD | 11월 17일 00:46 KST Actions가 격리 소스 `535c1164`의 API·웹 이미지를 게시하고 `4511909c`를 생성했습니다. 00:48 KST Argo CD가 자동 배포했습니다. 오전 확인에서 웹·API HTTP 200과 같은 MariaDB 볼륨·저장 표본을 확인했습니다. [격리 CI/CD 실행](https://github.com/DevDooly/devdooly-platform-lab-vm-cicd/actions/runs/43890556363) · [배포 커밋](https://github.com/DevDooly/devdooly-platform-lab-vm-cicd/commit/4511909cf07e64cae73273da068a6a5ca7c05997) |

Kafka·Garage·worker의 이전 실제 K3s 배포, 스토리지 복원, data export 검증은 [당시 런타임 배포 기록](../runtime-deployment/README.md)과 [Kafka·Garage 복원 기록](../runtime-pvc-restore/README.md)에 남아 있습니다. 위 VM 설치에서 확인한 MariaDB·API·웹·CI/CD와 구분합니다.

## 새 설치기로 실행할 때 남길 내용

| 항목 | 기록 |
| --- | --- |
| 대상과 입력 | VM OS·아키텍처, 실제 소스 SHA, 설치기와 이미지 버전, 관측 시각·시간대 |
| 사전 검사와 단계 | `--check` 결과, 실행한 명령, 단계별 시작·완료 시각, 성공 근거와 실패 종료 코드 |
| 서비스·앱 | Node/PVC/Pod/Argo 상태, API·웹 HTTP, Kafka topic, Garage layout·bucket과 worker 처리·export 결과 |
| Grafana | 상태 지표의 관측 시각, 서비스 하나의 로그 조회와 데이터소스 동작 범위 |
| 재실행 | 첫 실패를 보존하고 바꾼 값·명령, 다시 관측한 결과, 검증하지 않은 경로 |

공유 기록에는 필요한 결과만 남깁니다. 호스트의 주소·계정 비밀번호·키·Secret 값·원본 서비스 로그는 공유 기록에 포함하지 않습니다.

## 이번 설치기와 대시보드의 검증

2026-11-17 KST에 아래 검사를 실행했습니다.

| 검사 | 결과 |
| --- | --- |
| 고정 Helm과 설치기의 앱 values | MariaDB만 먼저 렌더링했습니다. 앱 리소스는 MariaDB·API·웹에 Kafka → Garage → worker가 차례로 추가됐습니다. Jenkins·Argo CD의 고정 chart도 렌더링했습니다 |
| Linux Python과 Bash | 설치기의 구문, 실패 시 다음 단계 중단, 완료 단계 재개, 실패한 합성 Job 진단을 확인했습니다 |
| Kubernetes·Grafana 선언 | Kustomize 결과는 리소스 21개입니다. 고정 이미지 5개, 내부 Service 4개, 상태·수집 상태·로그 패널 3개를 확인했습니다 |
| Prometheus·Loki·Alloy 설정 | 고정 버전 도구로 설정 검사를 실행했습니다. Deployment·StatefulSet의 준비 완료·부분 준비·오프라인·기대 복제본 0을 Prometheus 규칙 시험에서 확인했습니다 |
| Astro 문서 | 115개 파일의 진단은 오류·경고·힌트 0건이었습니다. Node 테스트 556건을 통과했고 28개 페이지를 빌드했습니다. 재구축 페이지의 두 설치 안내 링크도 빌드 결과에 들어갔습니다 |

런타임 values만 넣은 첫 lint에서는 API·웹 이미지와 DB Secret이 비어 있었습니다. 기본 lint values와 함께 넣은 재검사에서 schema 검증을 통과했습니다.

새 VM에서 한 번의 전체 설치와 로그인 후 Grafana 실측은 새 실행 기록이 필요합니다. 위의 기존 VM과 런타임 검증은 별도로 읽습니다.
