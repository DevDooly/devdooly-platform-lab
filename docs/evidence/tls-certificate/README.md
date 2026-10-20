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

## 공개 표시 후속

실제 첫 기록을 작은 정적 블록에 연결하고, 같은 대상·순서·출처를 지키는 이력 검사와 마지막 성공 보존을 구현할 예정입니다. 타입·build·로컬/공개 데스크톱·모바일 확인은 아직 PENDING입니다. 이후 서로 다른 leaf와 기간 연장을 관측하더라도 자연 ACME 갱신의 원인·과정·무중단을 증명했다고 해석하지 않습니다.
