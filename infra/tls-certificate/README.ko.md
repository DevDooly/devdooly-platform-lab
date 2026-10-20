# 공개 TLS 인증서의 첫 저장 관측

실제 첫 실행: [39452152238 통과](../../docs/evidence/tls-certificate/README.md). 수집 당시87일·만료시각과 원문을 보존했고, 순수 이력 검사와 로컬·공개 데스크톱/모바일 표시를 확인했다. 인증서 자연 갱신·실제 두 관측의 비교·정기 실행은 아직 검증하지 않았다. 이 소스는 기존 승인된 공개 API 호스트의 TLS 연결 한 번에서 유효기간을 읽는 단발 관측이다. HTTP 요청은 0회이며 기존 GET6·거부3 [HTTPS 검사](../public-https-smoke/README.ko.md)와 구분한다.

기존 [10월20일 운영 근거](../../docs/evidence/public-read-https/ops-20261020/README.md)의 만료시각·당시88일은 그대로 보존한다. 과거 파일을 새 관측으로 덮어쓰거나 인증서 변경·자연 갱신 완료로 소급 해석하지 않는다.

## 실행 전제와 연결 경계

기존 저장소 URL secret `LAB_PUBLIC_API_URL`과 동명 variable의 일치, `TLS_CERTIFICATE_CONFIRM=true`, `TLS_CERTIFICATE_TARGET_OWNERSHIP=true`, `TLS_CERTIFICATE_VARIABLE_MATCH=true`가 필요하다. 이 저장소의 `main`·`workflow_dispatch`·첫 attempt·40자리 source SHA가 아니면 DNS 전에 실패한다. 새 PAT나 URL 입력·설정 등록은 하지 않는다.

기존 URL validator와 공개 IPv4 분류기를 재사용한다. DNS는 IPv4 전체1~16개를 확인하고 private·예약 주소가 섞여도 거부한다. 첫 공개 IP 한 곳에만 고정해 TLS 연결1회를 수행한다. 기본 CA·hostname·SNI·최소 TLS1.2를 유지하고 실제 authorized=true·session 재사용false·remote IP/443·TLS1.2/1.3을 대조한다. 사용자 CA·TLS 우회·proxy·debug·keylog 환경은 빈 값이어도 DNS 전에 거부한다.

소켓의 `getPeerX509Certificate()`에서 실제 Date 두 개와 leaf DER Buffer1~65,536bytes를 RAM에서 검사한다. subject·SAN·issuer·serial·DER·주소·예외 원문은 게시하지 않는다. session·cookie·인증·HTTP·redirect·재시도·ACME 조작·SSH·서버 변경은 없다.

DNS5초·접속10초·close2초, 전체25초를 제한한다. 각 단계의 실제 반환·secureConnect와 인증서 읽기 직후·close 관측에서도 monotonic 기한 미만인지 확인한다. 전체 기한은 마지막 판정에도 적용한다. 소켓의 실제 close 이벤트 뒤에만 성공할 수 있으며 기한 초과에는 소유 소켓 폐기를 시도한다. 늦은 close를 관측했으면 `connectionClosed=true`여도 인증서 성공은 거부한다. close를 보지 못하면 false다. 남은 OS DNS 작업은 CLI 종료를 늦추지 않는다.

## 공개 결과22필드

`schemaVersion=1`, `kind=tls-certificate-snapshot`, `scope=PUBLIC_TLS_HANDSHAKE_ONLY`와 다음 필드만 기록한다.

| 묶음 | 필드와 의미 |
| --- | --- |
| 출처·판정 | `status`, `errorCode`, `validatorSourceCommit`, `captureStartedAt`, `capturedAt` |
| 연결 | `publicIpv4Verified`, `standardTlsVerified`, `connectionClosed`, `protocol` |
| 지문 | `targetBindingSha256`는 정확한 UTF-8 `https://hostname:443`의 SHA-256(경로·끝 slash 없음), `certificateSha256`는 leaf DER의 SHA-256. raw hostname·DER는 출력하지 않는다. |
| 기간 | `notBefore`, `notAfter`는 UTC millisecond ISO, `remainingValiditySeconds`, `remainingFullDays`, `warningThresholdDays=30`, `expiryAssessment` |
| 범위 | `naturalRenewalVerified=false`, `operatingConfigurationChanged=false` |

시작보다 완료 wallclock이 앞서면 실패한다. 인증서 기간은 완료시각에서 `notBefore <= capturedAt < notAfter`여야 한다. 잔여초는 완료시각 기준 floor, 남은 일수는 그 초를86,400으로 나눈 floor다. **공개 정수 잔여초가30일 이하**이면 `EXPIRING_WITHIN_30_DAYS`, 초과면 `VALID_OVER_30_DAYS`다. 예를 들어30일+999ms는 floor초 정책상 경보 범위이며 실제 Traefik 갱신 예정일이 아니다.

실패하면 protocol·인증서 지문·유효기간·잔여값은 null, `expiryAssessment=UNKNOWN`이다. TLS 실패를 만료·CA·DNS 변경의 특정 원인으로 단정하지 않는다. 실패 enum은 설정/환경·DNS·접속/전체/close 기한·TLS 속성/인증서/기간·시계·출력·미확인으로 한정하며 원문 오류를 직렬화하지 않는다.

CLI는 새 결과 파일 경로 하나만 받는다. DNS 전에 `wx`·0600으로 열어 기존 결과를 거부하고 공개 JSON은4KiB 이하로 제한한다. console에는 고정된 status/errorCode만 출력한다. 원문이나 비밀값을 추가하는 artifact는 없다.

## 검증의 범위

단위 검사는 probe를 import하기 전에 DNS·TLS·HTTPS native entrypoint를 대체한다. 조건 불충족 IO0, 주소 혼합·미인증·재사용·다른 remote, Date/DER 거부, 초 단위30일 경계, close·시간 제한과 비공개 오류를 확인한다. 이는 실제 CA·외부 접속 성공의 증거가 아니다. 실제 수동 관측은 검토된 소스·workflow에서 별도로 수행하고 결과·source·run에 묶어 보존한다. 실행기에 자동 주기나 이력 누적은 없다. 웹의 별도 순수 이력 검사는 검토한 원문·출처만 비교하며 새 TLS 연결을 수행하지 않는다.

## 다음 수동 관측을 보존하는 순서

새 관측이 필요할 때 검토된 main 소스와 기존 대상 설정을 확인하고 다음을 한 번 실행한다. 별도 토큰 발급이나 URL을 명령행에 넣는 과정은 없다.

```sh
gh workflow run tls-certificate.yml --repo DevDooly/devdooly-platform-lab --ref main \
  -f confirm_certificate_probe=true -f confirm_target_ownership=true
```

1. 반환된 run URL·head SHA·첫 attempt와 두 job의 결과를 확인한다. 응답이 불명확하면 기존 실행을 먼저 찾으며 새 실행을 반복하지 않는다. `Re-run jobs`의 attempt2는 허용되지 않는다.
2. 7일 보존 artifact의 단일 요약을 받고 원문 bytes·실행 source·run·완료시각·conclusion·SHA를 별도 폴더에 보존한다. 실패 원문도 성공으로 바꾸거나 이전 파일에 덮어쓰지 않는다.
3. 공개 이력에는 검토한 실제 원문과 명시적인 run/source/hash 결합을 추가한다. 같은 대상·시간 순서·마지막 성공 보존과 로컬/공개 화면을 다시 확인한다. Actions 성공만으로 화면 반영이 완료된 것은 아니다.

인증서가 바뀌거나 만료시점이 연장돼도 그것만으로 자연 갱신의 원인·과정·무중단을 입증하지 않는다. 이 명령은 자동 주기 등록이나 인증서 발급·강제 갱신 명령이 아니다.
