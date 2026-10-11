# 구현 결과와 검증 기록

실제 검증을 수행한 뒤 `docs/evidence/<scenario>/README.md`와 필요한 원본을 추가합니다. 현재 기록은 다음과 같습니다.

| 기록 | 확인한 범위 |
| --- | --- |
| [Linux 컨테이너 통합](compose-ci/README.md) | 실제 MariaDB·Flyway·컨테이너·API 주소 변경·Nginx와 결과 보존 |
| [API MVP](api-mvp/README.md) | Windows·Java 21, 테스트 15개, H2 실제 HTTP·DB 검증 |
| [화면 테스트](../../apps/lab-web/VALIDATION.md) | 타입 검사·테스트 4개·정적 빌드, 로컬 API HTTP smoke |
| [Pages 최초 공개](web-mvp/README.md) | Actions 게시 성공, 공개 문서·asset 200, PC·모바일 UI 확인 |
| [플랫폼 관측 수집·게시](platform-observation/README.md) | 제한된 실제 수집·인증 실패 보존·수동 Pages·공개 화면; 게시 순서 회귀 교정·보존과 API·웹 중단·동일 정상 B 복원 검증 |
| [앱 Helm 렌더링](../../infra/charts/platform-lab/ci/render-validation.json) | strict lint·7개 리소스·정책 15개·잘못된 입력 거부 6개. 실제 배포 미검증 |
| [플랫폼 Helm 렌더링](../../infra/platform/render-validation.json) | Jenkins·Argo CD strict lint와 33개 정책 검사. 서버 실행 미검증 |

미니 PC 운영·Argo CD는 [실제 서버 근거](mini-pc/README.md), Jenkins pipeline은 [실제 빌드](jenkins-ci/README.md), 게시 차단·GitOps 복구는 [CI/CD gate](cicd-gate/README.md)에 별도 기록했습니다. Helm 렌더링 결과는 그 정적 검사 범위이며 실제 배포 근거와 구분합니다.

## 기록 양식

```markdown
# 확인한 동작

- 상태: 진행 중 / 검증 완료
- 검증 일시와 시간대:
- 소스 commit:
- 관련 ADR 또는 변경:
- 개인 재현 / 실무 사례 설명의 구분:

## 목적과 기대 결과

입력과 독립적으로 정한 기대 결과, 실패 시 판단 기준을 적습니다.

## 재현 환경과 실행

OS, CPU, 메모리, JVM·라이브러리 버전, seed와 입력 크기,
사전 조건과 실제 실행 명령을 기록합니다.

## 확인한 결과

성공·실패, 결과 건수, 테스트 출력과 측정 원본을 연결합니다.
CI/CD라면 source commit, image digest, GitOps commit과 실행 버전을 연결합니다.

## 한계와 다음 작업

확인하지 못한 조건과 다시 검증할 조건을 적습니다.
```

공개할 이미지·영상·로그는 민감정보를 확인한 뒤 필요한 부분만 포함합니다. 큰 실행 산출물과 전체 로그는 로컬에 두고, 저장소에는 재현에 필요한 소규모 자료와 승인한 결과를 남깁니다.

성능 비교는 seed, 데이터량, warm-up, 반복 횟수와 환경을 고정합니다. 측정 전 예상치와 실제 결과를 구분하고 개인 예제의 개선율을 회사 프로젝트의 성과로 사용하지 않습니다.
