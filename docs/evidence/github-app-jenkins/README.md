# Jenkins의 GitHub App 인증 전환

2026-10-23 UTC에 개인 PAT 대신 저장소 하나에 설치한 GitHub App으로 Jenkins의 커밋 상태 기록을 연결했습니다. [연결 변경 PR #192](https://github.com/DevDooly/devdooly-platform-lab/pull/192)의 main 커밋은 `420cf2ce9d6b35111d12602e71cc1d79cfa8ef67`입니다.

이후 같은 날 19:19:30(KST)에 [실제 만료 후 갱신 한 주기](NATURAL_EXPIRY.md)를 별도로 검증했습니다. 만료한 토큰 401 → native 접근 1회 → 새 토큰 200·저장소 일치·유효기간 1시간을 확인했습니다. 공개 화면은 [제한된 요약 JSON](natural-expiry-summary.json)을 사용합니다.

## 실제 검증

| 항목 | 확인한 결과 |
| --- | --- |
| App 설치 | 개인 Lab 저장소 1개, Commit statuses 읽기·쓰기와 Metadata 읽기 |
| 플러그인 | 기존 77개 집합에서 6개 추가·2개 상향, 최종 83개 활성 |
| 호환성 | Jenkins 2.580.1에서 core 요구와 의존성 323개 비교 통과: 필수 308·존재 optional 15 |
| 보존·재시작 | 정지 상태의 Home 백업, 별도 플러그인 디렉터리 검증·전환, Ready 복귀. 기존 job·PVC·build 150·PAT 보존 |
| 자격증명 | 별도 App credential 등록 후 입력 키와 RAM 비교 일치, 지정 저장소 접근 성공 |
| Jenkinsfile | 실제 Declarative linter 통과. pending·success·unsuccessful에 native `usernamePassword` 바인딩 |
| 새 Jenkins 실행 | 자동 감지된 build **151**, queue **300**, 위 main SHA와 실제 checkout·`ci-build-info.txt` 일치 |
| 단계·산출물 | 7개 필수 단계 성공, API jar·Java 예제 jar·웹 dist·소스 정보·pending 기록 보관 확인 |
| 커밋 상태 | `ci/jenkins-test`: pending **57070838925** → success **57070972173**, 작성자 `devdooly-platform-lab-ops[bot]` |
| 같은 소스의 Actions | [Validate Lab containers 39920196385](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39920196385) 성공 |

기존 job의 공개 저장소 clone·main 제한·상태 context·검사와 산출물 보관 순서는 유지했습니다. 개인키는 Jenkins credential에 암호화 저장합니다. 평문 키·토큰·관리 응답·접속 정보는 공개 근거에 포함하지 않습니다. LLM에 비밀을 전달해 작업시키는 방식이 아닙니다.

## 발견한 문제와 대응

- 최초 준비된 플러그인 집합은 기존 Git 플러그인의 optional `token-macro` 최소 버전 조건을 충족하지 못했습니다. 실제 Jenkins `VersionNumber` 비교로 발견했고 `token-macro:477.vd4f0dc3cb_cf1`와 연관 의존성을 보완한 뒤 전체 검사를 다시 통과했습니다.
- 설치 전 고정 job XML 응답에는 `X-Jenkins` 헤더가 없어 첫 실행이 서버 변경 없이 중단됐습니다. 해당 응답만 기존 설정 전체 SHA로 확인하고 나머지 API의 버전 검사를 유지한 뒤 재실행했습니다.
- 첫 App 성공 이후 게시 gate는 이전 개인 계정을 기대해 차단됐고 publish·GitOps 제안은 생략됐습니다. 실제 build 151과 App 상태 쌍을 확인한 뒤 `JENKINS_STATUS_ISSUER`를 확인된 App 작성자로 전환했습니다. 작성자 검사를 제거하거나 오래된 성공으로 우회하지 않았습니다.

## 한계와 보류

native App 토큰으로 저장소 읽기와 새 CI의 상태 쓰기, 별도 후속에서 기본 저장소 credential 접근 시 실제 만료 후 lazy refresh 한 주기를 확인했습니다. 접근 없는 선제·주기 갱신, 개인키 교체·권한 철회 복구, 갱신 뒤 새 전체 CI 실행, 새 이미지의 운영 배포나 K3s·Jenkins 전체 기동 복원을 완료했다는 뜻은 아닙니다. 기존 PAT는 보존했으며 실제 fallback은 시험하지 않았습니다. 앞선 첫 만료 검증의 UNVERIFIED 기록도 후속 성공과 분리해 유지합니다.

Pages 토큰 교체·별도 환경의 기동 복원·예산 정책·PR #102는 보류합니다. [운영 안내](../../runbooks/jenkins-ci.md)를 함께 확인합니다.

## 관측 계약 연결

새 수집기는 실측한 App 작성자만 허용합니다. 저장된 과거 `DevDooly` 기록을 보존하기 위해 Python DTO·JSON Schema·브라우저는 과거 작성자와 App 작성자 두 값만 읽도록 했습니다. 임의 작성자·누락·비슷한 이름은 거부하며, 최신 잘못된 상태 뒤의 과거 성공으로 대체하지 않습니다.

로컬 Python 관측 검사는 42개 중 41개 통과·기존 POSIX 권한 검사 1개 생략, 브라우저 관측 검사는 13개 통과했습니다. 과거 lastSuccess의 시각·내용 보존도 검증했습니다. 이 로컬 결과만으로 운영 수집기 반영을 주장하지 않습니다.
