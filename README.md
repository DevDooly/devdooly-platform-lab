# DevDooly Platform Lab

Java 서비스 개발부터 데이터 처리, 배포와 운영까지 직접 구현하고 결과를 공개하는 개인 플랫폼 프로젝트입니다. 직접 만든 합성 센서 데이터로 처리 규칙과 오류 대응을 재현하고, [TIL](https://devdooly.github.io/TIL/)에 설계와 문제 해결 기록을 연결합니다.

[포트폴리오](https://devdooly.github.io/devdooly-platform-lab/) · [GitHub](https://github.com/DevDooly/devdooly-platform-lab) · [시작 안내](docs/START_HERE.md) · [진행 목록](docs/ROADMAP.md) · [다음 개발 계획](docs/NEXT_STEPS.md)

## 현재 상태

현재 목표는 기존 미니 PC의 서비스·자료를 보존하면서 Java·데이터 처리·배포·복구 경험과 공개 연결을 검증 기록으로 보여주는 것입니다.

| 영역 | 확인한 범위 | 근거 |
| --- | --- | --- |
| 서비스·CI/CD | Java API·worker, Kafka·Garage 배포와 같은 소스의 CI·이미지 전환·자료 보존 | [실제 배포](docs/evidence/runtime-deployment/README.md), [CI/CD](docs/evidence/cicd-gate/README.md) |
| 데이터·복구 | Cloud Spark→Trino·compaction, DB 논리 복원·Kafka/Garage PVC 격리 복원 | [Cloud](docs/evidence/cloud-lakehouse/FULL_SUCCESS.md), [DB](docs/evidence/current-db-restore/README.md), [PVC](docs/evidence/runtime-pvc-restore/README.md) |
| 보존 계획·화면 | Iceberg 실제 metadata의 KEEP 계획, 기술별 근거 탐색·합성 정책 선택 UI의 로컬 검증 | [실측 기록](docs/evidence/iceberg-capture/ATTEMPT_9.md), [합성 예제](examples/iceberg-retention-scenarios/README.md) |
| Java·AI 활용 | 합성 시간창 예제의 회귀 테스트와 Windows·Linux JMH 재현. 사람 검토는 대기 중 | [Java 예제](examples/java-window-analysis/PROVENANCE.md), [Linux 재현 결과](docs/evidence/ai-window-analysis/hosted-linux-20261018/README.md) |

최근 완료한 범위는 다음과 같습니다. 실행별 소스·수치·실패 이력과 한계는 연결한 실제 근거를 따릅니다.

- **키보드 탐색:** [실행 결과 탭](docs/evidence/lab-keyboard/README.md)의 양끝 방향키 순환과 Home·End 이동을 수정했습니다. 로컬 브라우저8가지·웹207검사·타입·빌드와 같은 main의 Pages·CI, 공개 데스크톱·모바일 반영을 확인했습니다.

- **실행기 오류 처리:** [합성 Error 회귀 검증](docs/evidence/runtime-error-cleanup/README.md)으로 정상 종료 오기록과 자원 정리 누락을 재현·수정했습니다. 관련26개와 전체 API 검증(233개 중222개 통과·Linux 전용11개 생략)을 로컬에서 확인했으며 운영 배포는 별도입니다.

- **런타임 장애:** [offset commit 실패 복구](docs/evidence/offset-commit-recovery/README.md)와 [손상 export 수리](docs/evidence/export-integrity-runtime/README.md)를 검증했습니다. [잘못된 입력](docs/evidence/invalid-message-runtime/README.md)과 [잠금 연결 손실](docs/evidence/runtime-lease-loss/README.md)은 정상 작업 보존과 실행기 종료를 확인한 결과로, 복구 완료와 구분합니다.
- **데이터 보존:** [격리 PostgreSQL 정상 재시작](docs/evidence/cloud-catalog-restart/README.md) 뒤 catalog·조회·전체 객체 보존과 [새 합성 warehouse의 snapshot 만료](docs/evidence/cloud-iceberg-expiration/README.md)를 확인했습니다. 운영 자료의 만료·삭제 결과가 아닙니다.
- **공개 조회:** [첫 TLS 인증서 관측](docs/evidence/tls-certificate/README.md)의 수집 당시87일·만료시각과 출처를 [공개 화면](https://devdooly.github.io/devdooly-platform-lab/#tls-certificate)에 연결했습니다. 웹207검사·타입·두 경로 빌드, 같은 main의 Pages·컨테이너CI와 공개 데스크톱·모바일 확인을 마쳤습니다. 자연 갱신·현재 가용성은 별도입니다.
- **공개 화면:** [근거 검색·필터·6개씩 더 보기](https://devdooly.github.io/devdooly-platform-lab/#evidence)와 [실행 잠금 사례](https://devdooly.github.io/devdooly-platform-lab/cases/runtime-ownership/)를 공개했습니다. [heartbeat 시각 표시 수정](docs/evidence/job-heartbeat-order/README.md)은 웹188개 검사·타입·프로젝트 경로 빌드와 같은 main의 Pages·CI·Jenkins, 공개 데스크톱·모바일 확인을 마쳤습니다.

[장애별 판단표](docs/runbooks/continuous-runtime.md#실제-네-가지-장애의-판단-기준--2026-10-20-utc)는 저장 상태·실제 종료·재개 전제를 구분합니다. [AI 예제 소유자 검토자료](docs/reviews/ai-window-owner-review.md)의 사람 판단은 **PENDING**입니다.

## 다음 단계와 보류

인증서 자연 갱신·현재 공개 경로의 재부팅·K3s/Jenkins 전체 archive 복원은 아직 검증하지 않았습니다. 별도 격리 환경이 없어 **K3s·Jenkins 실제 기동 복원은 보류**합니다. [복원 사전준비](docs/plans/historical-runtime-restore.md)에 파일 검증과 실제 기동, 재개 시 필요한 자료·실행 대상을 정리했습니다. 후속 순서는 [다음 개발 계획](docs/NEXT_STEPS.md)을 따릅니다. 토큰 교체·자원 예산 정책·PR102 접수 gate의 보류도 유지합니다.

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

