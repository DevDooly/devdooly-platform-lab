# 공개 TLS 인증서의 첫 저장 관측

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

## 실행과 보존 범위

[검토한 실행기](../../../infra/tls-certificate/README.ko.md)는 기존 URL secret/variable 일치와 main·수동·첫 attempt·두 확인 입력을 확인한 뒤 DNS 한 번·고정 공개 IPv4의 TLS 연결 한 번을 수행했습니다. HTTP 요청·redirect·추가 주소 재시도는 없습니다. 표준 CA·SNI를 유지하고 DNS5초·연결10초·close2초·전체25초를 실제 반환·인증서 읽기·종료 시각에서도 검사합니다.

TLS 관측은 한 번만 실행했습니다. source SHA와 workflow·run·attempt1·certificate job, 단일 ZIP entry·4KiB 이하와 원문22키를 대조해 원본 bytes와 실행 metadata를 새 폴더에 보존했습니다. SHA는 실제 받은 원문과 대조한 값이며 자기 기재 hash만으로 진위를 판단하지 않습니다. 주소·DER·subject/SAN·issuer·serial·native 오류·토큰은 원문에 포함하지 않았습니다.

서버 설정·인증서 강제 갱신·ACME·SSH·주기 실행은 변경하지 않았습니다. `naturalRenewalVerified=false`, `operatingConfigurationChanged=false`를 유지합니다. 토큰 교체·예산 정책·PR102도 계속 보류합니다.

## 저장 관측 화면의 로컬 검증

실제 첫 원문의 UTF-8 bytes를 보존한 웹 데이터와 검토한 run/source/hash 목록을 대조합니다. 서버 빌드에서 SHA·22필드·metadata6·시간 순서·동일 대상·중복/충돌을 검사한 뒤 선택한 값만 정적 화면에 표시합니다. 새 실패와 편입하지 못한 입력을 알리면서 마지막 성공을 보존합니다. 서로 다른 leaf와 기간 연장도 자연 ACME 갱신의 원인·과정·무중단을 증명한다고 해석하지 않습니다.

- 새 순수 검사19개·전체 웹207개, skip0을 통과했습니다. 실제 원문1건과 메모리 합성 반례를 구분하며, 수집 후 만료시점을 지난 시계에서도 당시87일을 유지합니다.
- 최초 타입 검사에서 Node 해시 API 타입3건이 누락됐습니다. 빌드용 `@types/node=24.19.2`와 lock의 타입 전이 의존성을 추가한 뒤46파일 오류·경고0과 루트/프로젝트 경로 빌드를 통과했습니다. 기존 실행 의존성·스크립트와 관측 실행기 원문은 유지했습니다.
- 2026-10-20 16:09–16:11 UTC에 로컬1280px·390px의 수집 시각·87일·만료·실행/소스/원문 링크, 기본 닫힘과 Enter 토글·3px 초점, 본문17px·최소48px 조작·긴 지문 줄바꿈·가로 넘침 부재를 확인했습니다.
- 원문 링크는 근거 커밋 `391c58bf9ede2a018b56d10c4c3ddbe92d27e8c0`에 고정했습니다. 공개 게시·같은 main CI·공개 화면 확인은 후속 단계입니다.
