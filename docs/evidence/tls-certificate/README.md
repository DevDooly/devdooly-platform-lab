# 공개 TLS 인증서의 저장 관측

## 두 번째 실제 관측 — 2026-10-20 18:42 UTC

기존 수동 workflow를 main `6f551a16a8ed536bb126403234c41b9e9b266d43`에서 한 번 실행했습니다. [run39477022262](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39477022262)의 오프라인20검사·certificate 단계가 성공했습니다. 기존 공개 URL 변수의 HTTPS·443·사용자 호스트 일치를 확인했고, workflow가 기존 secret과 변수의 일치도 검사했습니다. 새 토큰·SSH·라우트 확인용 POST·운영 설정 변경은 사용하지 않았습니다.

| 항목 | 두 번째 실제 결과 |
| --- | --- |
| 수집 시작 / 완료 | `2026-10-20T18:42:25.437Z` / `2026-10-20T18:42:26.245Z` |
| 연결 | DNS1회·TLS 연결 최대1회·HTTP0회, 공개 IPv4·기본 CA·SNI·TLS1.3·실제 close 확인 |
| 인증서 기간 | `2026-10-18T13:10:03.000Z` ~ `2027-01-16T13:10:02.000Z` |
| 수집 당시 잔여 | 7,583,255초 / floor87일 · `VALID_OVER_30_DAYS` |
| 실제 원문 | [22필드 summary.json](hosted-39477022262/summary.json), 911bytes |
| 원문 SHA-256 | `8c80681035f3e8f87d18eed2d84577f999e71cada2f6a361d2a727559c75e39f` |
| 실행 metadata | [run-metadata.json](hosted-39477022262/run-metadata.json), 346bytes |
| metadata SHA-256 | `ef721347b32dcb1d1d2528205c591b631912e14a95f98e66a4c1e614fef84088` |

첫 수집15:51:13.433Z와 두 번째18:42:26.245Z의 대상 binding·leaf 지문·notBefore·notAfter는 모두 같습니다. **두 실제 시점의 동일 인증서 관측**이며, 자연 갱신·강제 갱신·HTTP API 정상 여부·장기간 가용성을 증명하지 않습니다. `naturalRenewalVerified=false`, `operatingConfigurationChanged=false`를 유지합니다.

고정 run/source/repository/main·수동·attempt1, certificate job과 결론, 단일 artifact의 결합을 확인했습니다. ZIP을 추출하지 않고 정확한 JSON entry1개·4KiB 이하·22필드·수집/완료 시각·기간 산술을 검증한 뒤 원 bytes와6필드 metadata를 새 파일로 보존했습니다. 기존 원문·마지막 성공을 수정하거나 관측을 재실행하지 않았습니다. 원문에 주소·DER·토큰은 포함하지 않습니다.

공개 화면은 아직 첫 기록을 표시합니다. 로컬 후보에는 첫 entry의 UTF-8 원문과 metadata를 그대로 보존한 채 두 번째 실제 기록을 추가했습니다. 두 번째 원문 링크는 [근거 커밋73f068c](https://github.com/DevDooly/devdooly-platform-lab/blob/73f068c129cb65d65f198b094a482c421e0ffc9b/docs/evidence/tls-certificate/hosted-39477022262/summary.json)에 고정했습니다. 검토한 run/source/hash로 이력을 검사하고 마지막 성공과 같은 run의 원문 링크만 선택하므로, 새 입력이 실패하거나 격리되면 이전 마지막 성공과 해당 원문 링크를 유지합니다.

기존 첫 관측 검증을 유지하고 같은 actual-case에 두 번째 원문 bytes/hash와 두 기록의 `UNCHANGED_CERTIFICATE` 기대를 반영했습니다. 전체 웹207개·skip0, 타입47파일 오류·경고·힌트0와 두 페이지 빌드를 통과했습니다. 관측을 다시 실행한 결과가 아닙니다.

로컬1280px·390px에서 동일 인증서 표시, 마지막 수집18:42:26.245Z·87일·만료 시각, 실행39477022262·소스6f551a1·고정 원문 링크를 확인했습니다. native details는 기본 닫힘이며 Enter로 열면 두 실제 수집 시각과 원문 SHA가 보이고 다시 Enter로 닫혔습니다. 본문17px, 문서 폭1265px·375px에서 가로 넘침이 없었고 모바일의 긴 SHA도 details335px·카드375px 안에서 줄바꿈했습니다. 공개 배포와 반영 확인은 아직 예정입니다.

## 첫 실제 관측 — 2026-10-20 15:51 UTC

2026-10-21(KST), 기존 공개 Lab 호스트의 인증서 유효기간을 수동으로 관측했습니다. [첫 실제 실행39452152238](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39452152238)은 오프라인20검사와 TLS 관측 단계를 모두 통과했습니다.

| 항목 | 실제 결과 |
| --- | --- |
| 실행 소스 | [`8c17642ad4c38a6f0edd3fb47dafa4ec5a431723`](https://github.com/DevDooly/devdooly-platform-lab/commit/8c17642ad4c38a6f0edd3fb47dafa4ec5a431723) |
| 수집 시작 / 완료 | `2026-10-20T15:51:12.647Z` / `2026-10-20T15:51:13.433Z` |
| 연결 | 공개 IPv4 검증·표준 CA·TLS1.3·실제 close 관측 통과 |
| 인증서 기간 | `2026-10-18T13:10:03.000Z` ~ `2027-01-16T13:10:02.000Z` |
| 수집 당시 잔여 | 7,593,528초 / floor87일 |
| 당시30일 경보 | `VALID_OVER_30_DAYS` |
| 실제 원문 | [22필드 summary.json](hosted-39452152238/summary.json), 911bytes |
| 원문 SHA-256 | `72c806703547c2fb30a1e9a7e15b1baf41cddc88cc6318ef5589f7c24c69a157` |
| 실행 metadata | [run-metadata.json](hosted-39452152238/run-metadata.json) |

이 값은 **수집 당시의 저장 관측**입니다. 현재 접속 성공·현재 남은 일수·Traefik 갱신 예정일·장기 가용성을 표시하지 않습니다. 첫 leaf 지문 기록이므로 인증서 자연 갱신이나 교체 이력도 아직 검증하지 않았습니다. 기존10월20일 운영 요약의88일과 만료시각은 당시 원문 그대로 보존하며, leaf 지문이 없는 과거 요약을 이22키 이력으로 재작성하지 않습니다.

## 첫 실행과 보존 범위

[검토한 실행기](../../../infra/tls-certificate/README.ko.md)는 기존 URL secret/variable 일치와 main·수동·첫 attempt·두 확인 입력을 확인한 뒤 DNS 한 번·고정 공개 IPv4의 TLS 연결 한 번을 수행했습니다. HTTP 요청·redirect·추가 주소 재시도는 없습니다. 표준 CA·SNI를 유지하고 DNS5초·연결10초·close2초·전체25초를 실제 반환·인증서 읽기·종료 시각에서도 검사합니다.

첫 TLS 관측은 해당 실행에서 한 번만 수행했습니다. source SHA와 workflow·run·attempt1·certificate job, 단일 ZIP entry·4KiB 이하와 원문22키를 대조해 원본 bytes와 실행 metadata를 새 폴더에 보존했습니다. SHA는 실제 받은 원문과 대조한 값이며 자기 기재 hash만으로 진위를 판단하지 않습니다. 주소·DER·subject/SAN·issuer·serial·native 오류·토큰은 원문에 포함하지 않았습니다.

서버 설정·인증서 강제 갱신·ACME·SSH·주기 실행은 변경하지 않았습니다. `naturalRenewalVerified=false`, `operatingConfigurationChanged=false`를 유지합니다. 토큰 교체·예산 정책·PR102도 계속 보류합니다.

## 첫 화면의 로컬 검증

실제 첫 원문의 UTF-8 bytes를 보존한 웹 데이터와 검토한 run/source/hash 목록을 대조합니다. 서버 빌드에서 SHA·22필드·metadata6·시간 순서·동일 대상·중복/충돌을 검사한 뒤 선택한 값만 정적 화면에 표시합니다. 새 실패와 편입하지 못한 입력을 알리면서 마지막 성공을 보존합니다. 서로 다른 leaf와 기간 연장도 자연 ACME 갱신의 원인·과정·무중단을 증명한다고 해석하지 않습니다.

- 새 순수 검사19개·전체 웹207개, skip0을 통과했습니다. 실제 원문1건과 메모리 합성 반례를 구분하며, 수집 후 만료시점을 지난 시계에서도 당시87일을 유지합니다.
- 최초 타입 검사에서 Node 해시 API 타입3건이 누락됐습니다. 빌드용 `@types/node=24.19.2`와 lock의 타입 전이 의존성을 추가한 뒤46파일 오류·경고0과 루트/프로젝트 경로 빌드를 통과했습니다. 기존 실행 의존성·스크립트와 관측 실행기 원문은 유지했습니다.
- 2026-10-20 16:09–16:11 UTC에 로컬1280px·390px의 수집 시각·87일·만료·실행/소스/원문 링크, 기본 닫힘과 Enter 토글·3px 초점, 본문17px·최소48px 조작·긴 지문 줄바꿈·가로 넘침 부재를 확인했습니다.
- 원문 링크는 근거 커밋 `391c58bf9ede2a018b56d10c4c3ddbe92d27e8c0`에 고정했습니다.

## 첫 화면의 공개 게시와 확인

[PR155](https://github.com/DevDooly/devdooly-platform-lab/pull/155)를 main `4362975cb9c6f324f65f423bd42e81ddbd6a1f71`에 병합했습니다. 같은 소스의 [Pages39455602690](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39455602690)·[컨테이너CI39455602586](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39455602586)·TLS/HTTPS 오프라인 검사를 통과했습니다. [공개 저장 관측 화면](https://devdooly.github.io/devdooly-platform-lab/#tls-certificate)에서 확인할 수 있습니다.

2026-10-20 16:16–16:19 UTC에 공개1280px·390px의 수집 시각·87일·만료와 고정 원문 링크, 기본 닫힘·Enter 토글·새로고침 후 닫힘, 본문17px·summary54px·초점3px·긴 지문 줄바꿈·가로 넘침 부재를 확인했습니다. 실제 읽기 API의 카드가 로드된 뒤 모바일 증거 구도를 다시 확인했습니다. TLS 관측을 다시 실행한 결과나 실제 두 인증서의 비교가 아닙니다.

이 화면 소스의 Jenkins commit status는 당시 미관측입니다. 후속 이미지 workflow는 gate 종료 뒤 publish·GitOps 제안을 생략했으며, Pages 게시와 실제 이미지 게시·운영 배포를 구분합니다.
