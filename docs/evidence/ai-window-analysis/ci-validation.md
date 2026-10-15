# Java 예제의 CI 연결 검증

독립 [Java 시간창 예제](../../../examples/java-window-analysis/README.md)의 기능 검증을 기존 게시 gate에 연결했습니다. [수동 JMH 측정 근거](README.md)의 소스 16개·측정 원본 hash·미커밋 출처와 사람 검토 대기는 그대로 유지합니다.

GitHub Actions와 Jenkins는 예제의 `verify`, JUnit 결과와 `target/benchmarks.jar`를 요구합니다. Actions는 runner 결과 처리의 Python 검사 3개도 실행합니다. Jenkins는 예제 JAR·기존 API JAR·웹 entry·같은 source metadata가 모두 있어야 성공 commit status 단계로 넘어갑니다. CI에서 JMH 성능 측정을 반복하지 않습니다.

로컬 통합 검사에서는 예제 Java 테스트 20개, runner Python 검사 3개, 웹 테스트 41개와 Astro check·Pages 경로 build를 확인했습니다. CI 회귀 검사 2개는 실제 Jenkins archive guard shell을 실행하여 예제 JAR이 없거나 비어 있으면 거부하고, 필수 합성 산출물이 모두 있을 때만 통과하는 경계를 확인합니다. 이는 실제 원격 CI 빌드의 실패 주입 결과와 구분합니다.

2026-10-15T11:59:16.130027Z에 실제 Jenkins Declarative linter가 후보 Jenkinsfile SHA-256 `e547ddd6919c348e65e77a8b408982ec65bde1ac1e9f882921a9c2dfd8b9729f`를 통과했습니다. 이 호출은 빌드를 시작하거나 Jenkins job을 변경하지 않았습니다. 향후 같은 통합 commit의 실제 Actions/Jenkins 결과와 이미지 게시 근거는 별도로 연결해야 합니다.

포트폴리오의 데스크톱·390px 화면에서 실제 관측 JSON 연결, 기본 접힌 코드, fixture 선택과 가로 넘침 없음을 확인했습니다. 선택은 기존 정적 기록만 바꾸며 Java·미니 PC 작업을 실행하지 않습니다. 이 예제를 운영 ETL의 개선율이나 회사 알고리즘의 공개 자료로 사용하지 않습니다.

## 후속 실제 main 검증과 공개 게시

PR #37을 main `f7bdffeeb0e8806d6d17503a2bc8867e8656af64`로 병합한 뒤 [Actions 38734388503](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38734388503)와 Jenkins build 35가 모두 성공했습니다. Jenkins의 실제 JUnit 177개(API 157·예제 20)는 실패·skip 0이며 예제 JAR·API JAR·웹·동일 source metadata archive를 확인했습니다. 브랜치 CI의 실제 XML도 177개·실패/오류/skip 0이고 필수 예제 JAR을 보존했습니다. 첫 Jenkins 읽기는 빌드가 pending인 동안 실패했고 성공 status 확인 뒤 새 읽기 기록으로 검증했습니다.

[Pages 38734388547](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38734388547)의 build·deploy 성공 후 공개 AI JSON 전체가 main의 파일과 같은 SHA-256임을 확인했습니다. 공개 화면에서도 nested 4,096세션 선택·UTC 코드 펼치기와 기존 7개 EXPORTED 작업 관측을 확인했습니다. [TIL 글](https://devdooly.github.io/TIL/LLM_Development/UTC_Window_Analysis_Case/)은 문서 검사 42개·strict build·별도 저장소 배포를 통과했고 공개 HTTP 응답을 확인했습니다.

[전체 게시 근거](publication.json)는 실제 source와 실행 번호를 구분합니다. Linux CI의 예제 JAR SHA-256 `97c0b6bfed0575209593cf0f74b3ba08389ec36765a022c7e097d39c6b7918a9`는 기존 Windows 측정 JAR의 `983019bb…`와 다릅니다. 측정 소스 16개는 [Git 게시 바이트 일치](published-source-equivalence.json)로 연결하며, 서로 다른 빌드 JAR이 같다고 추정하거나 JMH를 다시 실행하지 않았습니다. 사람 검토는 여전히 PENDING입니다.
