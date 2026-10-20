# DevDooly Platform Lab

Java 서비스 개발부터 데이터 처리, 배포와 운영까지 직접 구현하고 결과를 공개하는 개인 플랫폼 프로젝트입니다. 직접 만든 합성 센서 데이터로 처리 규칙과 오류 대응을 재현하고, [TIL](https://devdooly.github.io/TIL/)에 설계와 문제 해결 기록을 연결합니다.

[포트폴리오](https://devdooly.github.io/devdooly-platform-lab/) · [GitHub](https://github.com/DevDooly/devdooly-platform-lab) · [시작 안내](docs/START_HERE.md) · [진행 목록](docs/ROADMAP.md) · [다음 개발 계획](docs/NEXT_STEPS.md)

화면 이동: [Lab](https://devdooly.github.io/devdooly-platform-lab/#lab) · [작업·export](https://devdooly.github.io/devdooly-platform-lab/#job-observation) · [플랫폼](https://devdooly.github.io/devdooly-platform-lab/#platform) · [기술별 근거](https://devdooly.github.io/devdooly-platform-lab/#evidence) · [합성 보존 조건](https://devdooly.github.io/devdooly-platform-lab/#iceberg-policy-scenarios) · [snapshot 전후](https://devdooly.github.io/devdooly-platform-lab/#snapshot-expiration)

## 현재 상태

현재 목표는 기존 미니 PC의 서비스·자료를 보존하면서 Java·데이터 처리·배포·복구 경험과 공개 연결을 검증 기록으로 보여주는 것입니다.

| 영역 | 확인한 범위 | 근거 |
| --- | --- | --- |
| 서비스·CI/CD | Java API·worker, Kafka·Garage 배포와 같은 소스의 CI·이미지 전환·자료 보존 | [실제 배포](docs/evidence/runtime-deployment/README.md), [CI/CD](docs/evidence/cicd-gate/README.md) |
| 데이터·복구 | Cloud Spark→Trino·compaction, DB 논리 복원·Kafka/Garage PVC 격리 복원 | [Cloud](docs/evidence/cloud-lakehouse/FULL_SUCCESS.md), [DB](docs/evidence/current-db-restore/README.md), [PVC](docs/evidence/runtime-pvc-restore/README.md) |
| 보존 계획·화면 | Iceberg 실제 metadata의 KEEP 계획, 기술별 근거 탐색·합성 정책 선택 UI의 로컬 검증 | [실측 기록](docs/evidence/iceberg-capture/ATTEMPT_9.md), [합성 예제](examples/iceberg-retention-scenarios/README.md) |
| Java·AI 활용 | 합성 시간창 예제의 회귀 테스트와 Windows·Linux JMH 재현. 사람 검토는 대기 중 | [Java 예제](examples/java-window-analysis/PROVENANCE.md), [Linux 재현 결과](docs/evidence/ai-window-analysis/hosted-linux-20261018/README.md) |

지금 완료: Kafka 관측 API·collector 연결, systemd·수동 host 실행, 원래 타이머의 자연 실행 2회·회차 간격 1개와 각 회차의 공개 3파일 대조를 확인했습니다. [자연 관측 근거](docs/evidence/kafka-observation/README.md#원래-타이머의-자연-2회와-공개-게시-대조)를 따르며, 화면은 마지막 수집 기록을 보여줍니다.

내부 게이트웨이 조회와 기존 상태 보존 검증을 마쳤고, 기존 Traefik과 설정 파일 7개를 유지했습니다([검증 범위](docs/runbooks/public-read-gateway-chart.md)). DuckDNS의 표준 TLS와 외부 runner의 조회 6개·거부 3개에 이어, 공개 화면의 작업·Kafka 실시간 조회도 확인했습니다([공개 HTTPS·화면 근거](docs/evidence/public-read-https/README.md)). 작업 8개의 export 상태와 Kafka 관측을 대조했으며, 같은 Kafka 기록의 시계 경고가 해소되는 것도 확인했습니다. 격리 Kafka와 공개 근거 카드 연결을 완료했으며([검증 근거](docs/evidence/kafka-acl/README.md)), 토큰 2개도 각 목적의 GET 응답 200을 확인했습니다(회전 미실행).

새 격리 warehouse에서 snapshot 1개·data 파일 1개 만료와 tag·공유 파일·행 보존, 후속 조회·정리 검증을 마쳤습니다([실제 근거](docs/evidence/cloud-iceberg-expiration/README.md) · [TIL 해설](https://devdooly.github.io/TIL/Data/Iceberg_Snapshot_Expiration_Lab/)). DB·Garage의 선택 볼륨이 같은 파일시스템을 공유함을 읽기 전용으로 확인했습니다. 자원 예산 근거가 미확정이라 접수 gate는 보류하고, snapshot 만료 전후 [관측 화면](https://devdooly.github.io/devdooly-platform-lab/#snapshot-expiration)의 공개와 전후 전환을 확인했습니다.

2026-10-20 UTC에 선택 운영 상태·DDNS 자연 실행·표준 TLS와 외부 조회 6개·거부 3개, 공개 작업·Kafka 화면을 다시 확인했습니다([시점별 운영 근거](docs/evidence/public-read-https/ops-20261020/README.md)). 자격증명 회전과 자원 예산·접수 gate는 보류하며, 인증서 자연 갱신과 현재 공개 경로의 재부팅은 이번 검증에 포함하지 않았습니다.

새 격리 Kafka에서 consumer 정상 종료 중 backlog가 8→14로 늘고, 같은 group의 새 client가 남은 14개를 실제로 읽어 lag 0에 도달하는 검증을 마쳤습니다([실제 4단계 근거](docs/evidence/kafka-lag-recovery/README.md)). [단계별 관측 화면](https://devdooly.github.io/devdooly-platform-lab/#kafka-lag-recovery)을 공개하고 데스크톱·모바일의 단계 전환과 키보드 이동을 확인했습니다. 이 시험은 정상 consumer 종료의 범위이며, 아래 DB·export를 포함한 별도 commit 실패 시험과 구분합니다.

DB commit 후 실제 Kafka offset commit 실패와 영속 pause, 일반 run 거부, 명시적 resume 뒤 재전달 1회·export 파일 2개 검증·슬롯 해제·lag 0을 새 격리 환경에서 확인했습니다([실제 실행·앞선 실패 기록](docs/evidence/offset-commit-recovery/README.md)). 업무 행·처리 시각과 소스도 보존됐습니다. [단계별 화면](https://devdooly.github.io/devdooly-platform-lab/#offset-commit-recovery)을 공개하고 2026-10-20 13:01–13:02 UTC에 데스크톱·모바일의 단계 전환·키보드 이동·상세 근거와 가로 넘침 부재를 확인했습니다.

손상 export를 실제 런타임이 발견해 `EXPORT_FAILED`로 중지하고, 수리 없이 resume하면 재중지되는 검증도 통과했습니다([실제 수리·복구 근거](docs/evidence/export-integrity-runtime/README.md)). 시험 소유 손상 객체를 명시 삭제한 뒤 별도 resume에서 파일 2개·슬롯 해제·실제 완료 메시지 replay 1회·lag 0을 확인했습니다. 원본·업무 행과 시각·소스 보존 및 소유 자원 정리도 통과했습니다. 실제 기록을 연결한 단계 화면은 웹 160개 검사·타입·빌드와 로컬 데스크톱·모바일 확인을 마쳤으며 공개 게시를 준비 중입니다. 다음은 잘못된 Kafka 메시지가 뒤의 정상 작업을 진행시키지 않는 경계입니다. 토큰 교체·예산 정책·PR102는 계속 보류합니다.

## 로컬 실행

Java 21과 Node 24.19.0을 사용합니다. API와 화면을 별도 터미널에서 실행합니다.

```sh
cd apps/api
./mvnw -B -ntp verify
./mvnw spring-boot:run -Dspring-boot.run.profiles=local-dev
```

Windows에서는 `mvnw.cmd`를 사용합니다. 화면은 다음과 같습니다.

```sh
cd apps/lab-web
npm ci
npm run dev
```

화면은 `http://127.0.0.1:4321/`이며 `/api`를 로컬 API에 연결합니다. 전체 DB 구성은 [MariaDB·Compose 안내](docs/runbooks/local-compose.md)를 따릅니다. H2 로컬 검증, Linux MariaDB 통합 검증과 미니 PC K3s 검증은 각각 기록합니다.

## 저장소 구성

```text
apps/api/                 Spring Boot, JPA·Flyway, 데이터·HTTP 테스트
apps/lab-web/             Astro·React 포트폴리오와 Lab 조회 화면
tests/scenarios/          합성 데이터의 독립 기대 결과
infra/containers/         API·웹 이미지와 Nginx 설정
infra/charts/             API·웹·MariaDB·Kafka·Garage·worker Helm chart
infra/jenkins/            Kubernetes CI agent 정의
infra/platform/           기반 도구의 버전과 설치 값
infra/scripts/            점검·bootstrap·관리 접속 도우미
gitops/                   Argo CD Application과 환경별 image digest
docs/                     계획, ADR, 계약, 운영·검증 근거
benchmarks/               후속 공개 예제의 전후 측정
```

회사 코드·데이터·실제 수율 알고리즘을 사용하지 않습니다. 실제 접속 주소·진단 원본·비밀값은 Git에서 제외한 `.local/`에 보관합니다. 공개 화면에는 허용한 요약만 제공합니다.

