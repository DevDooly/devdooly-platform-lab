# 공개 HTTPS 후보 검사 기록

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
