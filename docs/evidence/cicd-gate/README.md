# CI 게시 gate 준비 검증

현재 결과는 **별도 초안 브랜치의 준비 검증**입니다. 전용 Jenkins status credential 등록 전이며 운영 main의 새 게시 gate 활성화, 정상·실패·이전 digest 복구 완료를 뜻하지 않습니다.

## 확인한 내용

- Python 67개: 같은 SHA·최신 상태·issuer·실행 중 재시도·오래된 성공 선택 방지·중복 게시·values 변경 범위·기존 PR의 초안과 자동병합 조건
- Node 6개: 상태 입력 검증·잘못된 응답·자격 증명 누락·redirect 차단·원문 오류 노출 방지
- 기존 웹 의존성의 YAML 파서로 workflow 3개 구문과 중복 key 검사
- 실제 Jenkins Declarative linter 통과: 빌드 실행과 job 설정 변경 없이 검사
- 실제 GitHub의 현재 main과 성공한 Actions 기록을 읽어, Jenkins 성공 기록이 없을 때 `JENKINS_STATUS_MISSING`으로 게시 차단

[관측 요약](summary.json)과 [활성화·실제 검증 절차](../../runbooks/cicd-publication.md)를 함께 확인합니다. 원문 토큰·관리자 비밀번호·서버 주소·내부 로그는 포함하지 않습니다.

Jenkins status issuer variable은 DevDooly로 설정했습니다. 선택적 GitOps PR 자동 제안은 활성화하지 않았습니다. 현재 Actions 기본 권한은 read이며 PR 승인 설정은 false입니다. 이 기록은 전용 token의 실제 권한이나 만료일 확인을 대신하지 않습니다.

## 남은 실제 검증

전용 credential을 등록한 뒤 같은 main SHA의 Jenkins pending·success, Actions 통합 검증, GHCR 게시와 두 digest, GitOps PR과 Argo 배포를 연결합니다. 의도적인 JUnit 실패에서 이미지·PR·배포가 차단되는지 확인하고, GitOps digest를 이전 정상 버전으로 되돌려 HTTP·DB·PVC를 비교합니다. 이 결과가 확보되기 전에는 계획의 2단계를 완료로 표시하지 않습니다.
