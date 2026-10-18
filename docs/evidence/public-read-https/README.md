# 공개 HTTPS 후보 검사 기록

## DuckDNS 후속 hosted 검증 통과

2026-10-18 [GitHub hosted 검사 39134935997](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39134935997)에서 별도 DDNS 도메인의 표준 CA·SNI TLS와 허용 조회 6개, 지정 거부 3개를 확인했다. [실제 성공 결과 JSON](hosted-duckdns-success-20261018.result.json)은 같은 run의 artifact 1,882바이트를 변경 없이 보존한다.

| 항목 | 당시 확인한 결과 |
| --- | --- |
| 검사기 소스 | `772d14973ac2ecf647efb496863d6f0f10cb700c` |
| 조회 API 소스 | `245d61a5749760a20918ab091d9410ce6735b1c0` — 6개 응답에서 같음 |
| 검사 시각(UTC) | 2026-10-18 14:12:45.329 ~ 14:13:00.391 |
| 공개 IPv4·표준 TLS | 선택한 공개 IPv4, 기본 CA·SNI 검증 통과 |
| 허용 GET | summary·releases·run list·run detail 예시·jobs·Kafka 6개 모두 200 |
| 거부 요청 | 잘못된 경로 404 · 허용되지 않은 Origin 403 · 허용되지 않은 method 405 |
| 결과 | `PASS / NONE` |

검사는 소유한 전용 경로의 고정 조회 목록과 지정 거부 요청만 다룬다. 각 응답의 DTO·소스·수집 시각을 검사했으며 시각에는 최대 5초의 미래 clock skew 허용 정책을 적용했다. 서버 시계 정확도, 모든 경로·쓰기 요청 차단, 관리 기능, 장기간 가용성이나 성능을 증명하지 않는다. JSON에는 endpoint 주소·응답 본문·인증서·자격증명이 없다.

이번 검사는 기존 후보 URL secret만 사용했다. 후속 Pages 실시간 조회 설정은 반영했으며 실제 공개 화면은 자연 배포 뒤 대조한다. 이 JSON 자체가 후속 설정과 공개 화면을 검증한 근거는 아니다. 이전 실패와 당시 CAA 결과는 아래와 원 JSON에 그대로 보존하며 이번 성공의 구체적인 발급 원인을 그 과거 결과만으로 소급 확정하지 않는다.

## 이전 도메인의 최초 검사·CAA 기록

아래 원문은 이전 도메인과 각 검사 시점의 상태를 보존한 기록이다. 새 DDNS의 현재 CAA 정책이나 최신 연결 상태를 뜻하지 않는다.

2026-10-18 [GitHub hosted 검사 39125726243](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39125726243)는 공개 IPv4를 선택했지만 표준 TLS를 확인하지 못해 `TLS_OR_NETWORK_UNVERIFIED`로 종료됐다. 첫 summary 요청에서 HTTP 응답을 확인하지 못했으며, 이후 GET과 거부 경로 검사는 진행하지 않았다.

| 항목 | 실제 결과 |
| --- | --- |
| 검증 소스 | `08a239c5e111f7a6fd0bb59c0e040478f72e7c53` |
| 검사 시각(UTC) | 2026-10-18 12:04:03.348 ~ 12:04:04.134 |
| 공개 IPv4 선택 | 확인 |
| 표준 TLS | 미확인 |
| 허용 GET 6개·거부 3개 | 9개 모두 HTTP status 없음 |
| Pages live 설정 | 전환하지 않음 |

[실제 유한 결과 JSON](hosted-candidate-20261018.result.json)은 해당 run artifact의 내용을 그대로 보존한다. 주소·응답 본문·인증서·자격증명은 포함하지 않는다. 이 결과만으로 포트포워딩, 도달한 서버의 identity 또는 구체적인 TLS 실패 원인을 확정할 수 없다. 로컬에서 관측한 self-signed 인증서와 외부 실패의 원인이 같다고 단정하지 않는다.

후보 검사는 별도 URL secret을 사용했으며 운영 URL secret·Pages live 변수를 변경하지 않았다. 다음 검사는 외부 접속 설정을 확인하고 상태가 바뀐 뒤 진행한다. 표준 TLS와 hosted GET 6개·거부 3개가 통과해야 실시간 공개 연결을 완료한 것으로 기록한다. [연결 절차와 검증 범위](../../runbooks/public-read-gateway-chart.md)를 따른다.

## 현재 CAA 관측

2026-10-18 12:43:02.973359 UTC에 Google Public DNS의 공개 [DNS JSON API](https://developers.google.com/speed/public-dns/docs/doh/json)로 CAA를 조회했다. 대상 호스트에는 CAA가 없었고, 바로 위 도메인에서 처음 발견한 CAA 2개는 발급자 값이 빈 `issue`·`issuewild` 각 1개였다. 발급자를 허용하는 레코드는 관측하지 않았다.

| 조회 단계 | DNS 결과 | CAA 개수 | 선택 결과 |
| --- | --- | --- | --- |
| 대상 호스트 | NOERROR | 0 | 상위 조회 진행 |
| 바로 위 도메인 | NOERROR | 2 | 빈 발급자의 `issue` 1개·`issuewild` 1개 |

[RFC 8659 §3](https://www.rfc-editor.org/rfc/rfc8659.html#section-3)의 상위 조회 규칙과 [§4.2](https://www.rfc-editor.org/rfc/rfc8659.html#section-4.2)·[§4.3](https://www.rfc-editor.org/rfc/rfc8659.html#section-4.3)의 빈 발급자 의미에 따라, 현재 관측한 정책은 일반·와일드카드 인증서에 어떤 발급자도 허용하지 않는다. 이는 공개 재귀 resolver의 조회 시점 정책 해석이며, authoritative DNS·DNSSEC·실제 ACME 계정 일치는 독립 검증하지 않았다. 과거 ACME 오류 시점의 DNS 정책이나 로컬·hosted TLS 실패의 정확한 원인, 기존 발급 인증서의 유효성을 확정한 결과가 아니다. 기존 Traefik과 서비스는 유지한다.

[익명화한 유한 DNS 요약](caa-dns-20261018.summary.json)은 `schemaVersion: 1`로 조회 단계·DNS 상태(`0`은 NOERROR)·레코드와 제약의 개수·현재 정책 해석을 저장한다. 도메인·주소·원 CAA 값·연락처·계정 URI·로컬 증거 해시는 포함하지 않는다. 이전 hosted 결과 JSON은 변경하지 않는다.

별도 방화벽 읽기에서는 IPv4 전체 출발지·인터페이스 제한 없는 TCP 80·443의 UFW 수신 허용 선언을 확인했다. 방화벽을 변경하지 않았으며 이 선언만으로 외부 패킷 경로 전체를 증명하지 않는다. 현재 단계에서는 DNS·서버 설정 변경이나 TLS·ACME 재시도를 수행하지 않았다.

다음은 보유 도메인과 DNS/CAA 관리 가능 여부를 확인해 사용할 도메인을 선택하는 것이다. 현재 DDNS 제공자의 CAA 수정 지원 여부는 미확인이다. 도메인과 발급 허용 정책을 준비한 뒤 표준 CA·SNI TLS → hosted GET 6개·거부 3개 → Pages 실시간 조회 → 자격증명 회전 순서로 진행한다. 인증서 발급이나 공개 live 연결은 아직 완료하지 않았다.
