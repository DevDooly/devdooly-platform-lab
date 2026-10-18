# 선택적 조회 gateway의 Helm 선언

현재 연결 근거(2026-10-19 정리): [내부 조회·접근 진단과 보존 검증](../evidence/public-read-gateway-internal/README.md)에 이어 DuckDNS 도메인의 표준 CA·SNI TLS, GitHub 외부 runner의 허용 GET 6개·지정 거부 3개와 Pages 실시간 조회를 확인했습니다. [실제 HTTPS·공개 화면·자연 DDNS timer 기록](../evidence/public-read-https/README.md)은 각각의 확인 시점과 범위를 구분합니다. 아래 초기 활성화 조건과 이전 도메인의 실패는 당시 기록으로 보존하며 현재 연결 상태를 뜻하지 않습니다.

공개 live GET은 기존 Traefik에 추가한 전용 `/platform-lab/api` 경로를 사용합니다. Pages의 `LAB_PUBLIC_API_URL` 설정과 실제 Job·Kafka 화면은 위 브라우저 근거에서 확인했습니다. 프런트엔드 설정은 HTTPS base의 `/api` 또는 `/platform-lab/api`를 허용하며, 조회 실패 시 마지막 게시본으로 전환하는 동작은 유지합니다. 설정값만으로 연결 성공을 판정하지 않습니다.

## DDNS부터 조회 gateway까지

| 계층 | 담당하는 일 | 다른 계층과의 경계 |
| --- | --- | --- |
| DuckDNS | 도메인의 IPv4 A 갱신 요청 | 포트를 열거나 방화벽·TLS를 설정하지 않음. `UPDATE_ACCEPTED`는 요청 수락이며 DNS 값 일치·전파의 별도 확인이 필요 |
| 공유기 포트포워딩·DMZ | 외부에서 들어온 패킷을 지정 장비로 전달 | DDNS는 목적지 이름을 제공할 뿐 이 전달 설정을 대신하지 않음 |
| 호스트 방화벽 | 장비에 도착한 트래픽에 수신 규칙 적용 | 기존 IPv4 TCP 80·443 허용 선언은 확인했지만 선언만으로 외부 경로 전체를 증명하지 않음 |
| 기존 Traefik | HTTPS와 Host·전용 경로를 처리해 Lab gateway로 전달 | 기존 서비스·provider 파일 7개 유지. 외부 웹 연결은 기존 TCP 80·443을 사용하며 관리 포트 공개 추가는 필요하지 않음 |
| Lab 조회 gateway | 고정 조회 경로·method·Origin 정책 적용 | 외부 runner에서 GET 6개와 지정 거부 3개 확인. 공개 POST·관리 API·작업 실행 기능을 제공하지 않음 |

DDNS updater의 파일·단일 요청·timer 계약은 [구현 안내](../../infra/duckdns-updater/README.ko.md), 실제 자연 실행 한 회는 [공개 근거](../evidence/public-read-https/README.md#duckdns-timer의-자연-실행-확인)로 구분합니다. updater 안내의 미배포·검증 대기 문구는 구현 준비 시점의 기록입니다. 접수 성공만으로 모든 주기의 DNS 일치나 인증서 갱신을 완료 처리하지 않습니다.

표준 TLS 검증은 연결 대상의 인증서를 확인합니다. Origin 정책은 사용자별 인증이나 요청 서명을 제공하지 않으며, 선택한 거부 3개가 임의의 모든 경로·공격·관리 접근을 검증한 것은 아닙니다. 허용 필드의 읽기 전용 공개 범위와 기존 관리 경로를 유지합니다.

## 재부팅·주소 변경·인증서 갱신 점검

기존 [호스트 재부팅 검증](lab-operations.md#호스트-재부팅)은 새 공개 HTTPS 경로를 추가하기 전의 별도 기록입니다. 재부팅은 다른 Docker 서비스에도 영향을 주므로 기존 운영 절차를 따르며, 이 문서는 새 재부팅·재시작을 실행한 결과가 아닙니다.

1. 재부팅 이후 DDNS timer의 enabled·active·다음 예정 시각과 최근 요청 수락 기록을 확인합니다. DNS A와 현재 WAN IPv4의 일치는 별도로 대조하며, updater는 기존 AAAA를 검증하지 않습니다. 불명확한 timeout을 즉시 중복 요청으로 바꾸지 않습니다.
2. 기존 Traefik의 identity·주소와 gateway의 private `/32` parameter가 여전히 일치하는지 확인합니다. 주소가 바뀌면 과거 값을 성공 근거로 쓰지 않으며 허용 subnet을 자동 확대하지 않습니다. `/32`는 NAT·node 예외와 주소 재사용까지 배제하는 영구 identity 증명이 아닙니다.
3. 표준 CA·SNI TLS와 고정 조회·거부 경로를 같은 시점에 다시 확인한 기록으로 연결 상태를 판정합니다. Pages의 성공 표시나 지난 hosted 결과만으로 재부팅 후 경로를 통과 처리하지 않습니다.
4. 인증서의 자연 갱신은 기존 Traefik resolver가 담당하며, DDNS timer와 별도입니다. 갱신 시점의 표준 TLS·인증서 유효기간과 필요한 웹 경로를 확인하는 후속 관측이 필요합니다. 새 공개 경로를 포함한 재부팅 후 복구와 인증서 자연 갱신 완료는 아직 실증하지 않았습니다.

## 초기 chart 준비 기록

이 선언은 검증한 조회 정책을 K3s에 올리기 위한 준비입니다. chart 기본값은 `publicReadGateway.enabled: false`이며, 내부 활성화 후보는 `home-lab/runtime.yaml`에 true를 선언합니다. 실제 AppProject 권한 적용과 runtime 활성화는 아래 순서로 별도 진행해야 합니다. Windows 오프라인 검사와 소스 `501e127`의 실제 Linux CI에서 기본값·명시적 false의 기존 렌더 보존과 true의 4개 resource 추가를 확인했습니다. [실제 결과와 첫 실패](../evidence/public-read-gateway-chart/README.md)를 구분해 남깁니다. 내부 활성화 후보의 Windows 오프라인 K fixture 검사 1회(Helm 15호출)와 현재 N 값의 별도 렌더 1회는 통과했습니다. [K fixture 결과](../evidence/public-read-gateway-internal/activation-render.k-fixture.json)와 [현재 값 결과](../evidence/public-read-gateway-internal/activation-render.current-values.json)를 구분합니다. 새 활성화 소스의 Linux CI·클러스터 배포·외부 HTTPS는 아직 실행하지 않았습니다.

## 구현과 기존 검증의 경계

[격리 Nginx 검증](../evidence/public-read-gateway/README.md)은 실제 Nginx 1.30.5에서 HTTP 620개 검사와 자기 컨테이너·네트워크 정리를 확인했습니다. 그 결과는 fake upstream을 둔 Linux CI의 기록입니다. 새 Deployment, Kubernetes DNS·NetworkPolicy, 실제 API 또는 외부 사이트에서 같은 결과가 나온다는 뜻이 아닙니다.

chart의 `files/public-gateway/nginx.conf`와 `proxy.inc`는 해당 정책 파일을 그대로 복사합니다. 이미지도 기존 `infra/image-lock.json`의 digest를 사용합니다. 고정 upstream `api.platform-lab.svc.cluster.local:8080`을 보존하므로 다른 namespace에서 활성화하면 Helm이 실패합니다. 활성화 외 upstream·이미지·replica·자원·노출 방식은 values로 바꿀 수 없습니다.

활성화 시 새로 추가되는 것은 ConfigMap·Deployment·ClusterIP Service·NetworkPolicy 각 1개입니다. 기존 API·web·DB·Kafka·Garage·worker, 이미지와 Secret 참조를 변경하지 않습니다. 이 파일은 ingress·NodePort·hostPort·hostNetwork·LoadBalancer·TLS·공개 주소를 만들지 않습니다.

## 고정된 실행 범위

| 항목 | 선언 |
| --- | --- |
| Pod | replica 1, UID/GID·fsGroup 101, RuntimeDefault, 토큰 자동 mount 없음 |
| 컨테이너 | 루트 파일시스템 읽기 전용, privilege escalation 금지, capabilities 전부 제거 |
| 자원 | requests 25m / 32Mi / 임시저장 32Mi, limits 250m / 128Mi / 임시저장 64Mi |
| 쓰기 공간 | `/tmp`만 Memory emptyDir 16Mi, 정책 ConfigMap은 읽기 전용 |
| probe | 8080 TCP listener만 확인하며 API 정상 응답을 판정하지 않음 |
| inbound | 같은 namespace·같은 chart/release의 `public-read-client` label Pod에서 TCP 8080만 |
| outbound | 같은 namespace·같은 chart/release의 API Pod TCP 8080, kube-system의 kube-dns Pod UDP/TCP 53만 |

이 표는 NetworkPolicy에 선언한 Pod peer 범위입니다. [Kubernetes 공식 문서](https://kubernetes.io/docs/concepts/services-networking/network-policies/)에 따르면 해당 Pod가 있는 node의 접근을 차단할 수 없고, source/destination NAT와 정책 적용 순서가 구현마다 다를 수 있으므로 node·host·NAT 경로와 외부 Traefik→K3s 연결은 별도 통합 검증이 필요합니다.

## 선택적인 proxy 주소 한 개

`publicReadGateway.trustedProxyCidr`의 기본값은 빈 문자열입니다. 비어 있으면 기존 NetworkPolicy 선언을 유지합니다. 선택할 때는 canonical RFC1918 IPv4 주소 한 개의 `/32`만 허용하며, 기존 client Pod 규칙 뒤에 해당 source의 TCP 8080 ingress 규칙 하나만 추가합니다. 기존 selector·API/DNS egress·다른 resource는 유지합니다. 예시 `10.23.45.67/32`는 합성 값이며 실제 운영 주소가 아닙니다. 넓은 subnet·IPv6·public/loopback 주소·잘못된 octet·선행 0·문자열 이외의 값은 거부합니다. 이 값만 설정해 gateway를 활성화하지는 않습니다.

실제 주소는 Git values나 공개 문서에 넣지 않습니다. 필요한 경우 현재 Application의 소유권·source·기존 Helm parameter를 확인한 뒤 비공개 운영 변경으로 parameter 한 개만 전달합니다. [Argo CD의 Helm parameter](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/#helm-value-precedence)는 valueFiles보다 우선하므로 기존 parameter와 관리 주체를 먼저 확인해야 합니다. 이 override의 실제 적용·주소와 정책 유지·namespace에서의 GET·원복 검증은 별도 운영 단계이며, 현재 후보 작성만으로 완료하지 않습니다.

Docker 주소가 바뀌면 예전 `/32`는 새 주소를 허용하지 않습니다. 다만 주소 재사용, node 접근 예외와 NAT 때문에 이를 proxy의 영구 identity나 완전한 격리 보장으로 해석할 수 없습니다. 주소 변경 시 기존 값을 제거하고 새 identity·주소·경로를 다시 확인합니다. 과거 namespace GET의 연결 거부도 NetworkPolicy 단독 원인으로 확정하지 않았습니다. 실제 소스 주소와 정책의 적용 관계는 새 통합 검증이 필요하며, 실패하면 subnet이나 node 범위를 자동으로 넓히지 않습니다. Traefik 재시작·Docker 네트워크 변경·NodePort·추가 Ingress controller·직접 API 공개는 이 변경에 포함하지 않습니다.

오프라인 검사는 기존 검사기에 빈 문자열의 enabled bytes 보존, 세 RFC1918 범위의 단일 `/32`가 NetworkPolicy 한 규칙만 추가하는지, disabled bytes 보존과 잘못된 입력 12개 거부를 추가합니다. Windows Helm 4.3.0에서 기존 경로와 새 조건을 합친 오프라인 32회 검사를 통과했고 원본 소스·도구 bytes가 유지됨을 확인했습니다.

실제 운영에서는 Application의 private Helm parameter 한 항목을 추가하고, 다른 매개변수와 나머지 spec을 유지한 채 NetworkPolicy에 단일 `/32 → TCP 8080` 규칙이 반영됐음을 확인했습니다. 기존 API·worker Pod와 PVC, jobs/export/Kafka의 선택 상태 여섯 구성 요소도 기준과 같았습니다. 이어 기존 Traefik의 네트워크 공간에서 고정 summary GET 한 번이 HTTP 200과 현재 API 계약을 통과했습니다. 실제 주소와 비공개 운영 증거는 Git에 게시하지 않습니다.

이 결과는 NAT 경로나 NetworkPolicy의 독점 원인을 증명하지 않습니다. 이후 기존 Traefik에 전용 공개 route를 게시하고, 원 YAML 파일 7개와 provider root의 소유·identity 정보가 유지됐음을 확인했습니다. 이전 도메인의 당시 표준 CA·SNI TLS 검증은 self-signed 인증서에서 실패했습니다. 아래 실패를 TLS 우회나 live 변수 등록으로 통과 처리하지 않았으며, 후속 DuckDNS 성공 기록과 구분합니다.

별도의 [GitHub hosted candidate 검사](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39125726243)는 전용 candidate secret만 사용해 당시 live 설정을 바꾸지 않고 실행했습니다. 공개 IPv4 선택은 확인됐지만 표준 TLS는 통과하지 못했고 `TLS_OR_NETWORK_UNVERIFIED`로 종료됐습니다. 9개 검사 모두 HTTP status가 없어 정상 HTTP 조회·허용/거부 검증 완료의 근거가 아닙니다. 이 외부 실패를 로컬의 self-signed 인증서 관측과 같은 원인으로 단정하지 않습니다. 당시 Pages live 변수와 production URL secret은 미설정이었으며, 후속 표준 TLS·hosted GET6·거부3 통과 뒤에 실시간 화면을 연결했습니다. 검사 시점의 [실제 유한 결과와 해석](../evidence/public-read-https/README.md)을 저장소에도 보존했습니다.

이전 도메인의 2026-10-18 12:43:02.973359 UTC [공개 CAA 조회](../evidence/public-read-https/README.md#현재-caa-관측)에서는 대상 호스트에 CAA가 없고 바로 위 도메인에 빈 발급자의 `issue`·`issuewild`가 각각 1개 있었습니다. 당시 상위 정책은 인증서 발급자를 허용하지 않았지만, 이 관측을 과거 TLS·ACME 실패의 정확한 원인이나 새 DDNS 정책으로 소급하지 않습니다. UFW의 IPv4 전체 출발지 TCP 80·443 허용 선언도 확인했고 추가 방화벽 변경 없이 사용할 도메인을 별도로 선택했습니다. 이 CAA 읽기 자체는 DNS·서버 설정을 바꾸지 않았으며, 이후 DuckDNS 표준 TLS·hosted 9개·Pages 연결과 자격증명 회전은 서로 다른 단계로 구분합니다.

클라이언트 Pod는 만들지 않습니다. 배포 후 별도 검증을 하려면 지정한 client selector를 쓰는 격리 Job 등이 필요합니다. Docker 검증의 tmpfs `noexec/nosuid/nodev`나 PID 64 제한을 Kubernetes emptyDir·Deployment가 똑같이 제공한다고 주장하지 않습니다. Memory emptyDir는 Pod 메모리를 사용합니다.

## 초기 활성화 전에 확인했던 조건

2026-10-18 08:34:31 UTC의 실제 AppProject 관측에는 NetworkPolicy 권한이 없었습니다. 내부 활성화 후보의 소스 선언은 기존 6종에 `networking.k8s.io/NetworkPolicy` 1종만 추가합니다. 오프라인 검사기는 정확한 7종·전용 namespace 목적지·빈 cluster whitelist를 확인하며 실제 권한을 적용하지 않습니다. 실제 AppProject에 이 권한을 먼저 추가하고 기존 조건 보존을 확인한 뒤 runtime의 활성화 값을 반영해야 합니다. 권한 적용 전 runtime enabled true를 main에 병합하면 Argo CD의 자동 sync가 먼저 시도될 수 있으므로 두 실행 순서를 분리합니다. [내부 활성화 계획](../plans/public-gateway-internal-enable.md)을 따릅니다.

2026-10-18 08:07:23 UTC의 읽기 전용 preflight는 대상 namespace에서 ResourceQuota·LimitRange·NetworkPolicy가 각각 0개이고 API label이 예상과 일치하며, 나열한 정책에 의한 API ingress 격리는 없음을 확인했습니다. DNS Pod 1개와 고정 kube-dns label은 관측했지만 namespace identity는 확인하지 않았습니다. 따라서 후보 DNS egress의 적합성은 UNKNOWN이며 DNS·네트워크 연결·scheduler admission·배포 통과를 확인한 결과가 아닙니다. 후속 08:34:31 UTC 관측에서는 kube-system namespace identity·해당 label과 API instance label의 일치를 확인했습니다. 실제 DNS/API 연결·NetworkPolicy 강제·scheduler admission은 아직 확인하지 않았습니다.

외부 연결은 기존 HTTPS proxy의 identity·provider·route·인증서·도달 경로와 클라이언트 식별을 확인한 뒤 별도 결정합니다. 현재 chart의 제한은 기본 Nginx peer 기준이며 여러 외부 peer가 있는 전역 제한의 독립 검증은 기존 CI에서 수행하지 않았습니다.

## 오프라인 검사와 CI 연결

`ci/validate-public-gateway-render.mjs`는 지정한 Helm 실행 파일, 공개 chart·값·정책·image-lock·AppProject와 기존 YAML 모듈만 사용하도록 준비합니다. 새 dependency 설치·클러스터 접근·apply를 수행하지 않습니다. 출력 폴더는 새 경로여야 하며 원본 chart 안에 결과를 쓰지 않습니다.

검사 조건은 기본값/명시적 false의 렌더가 고정한 기존 main K의 12개 resource·전체 bytes와 같고, true는 기존 12개를 보존하며 4개만 추가하는 것입니다. 정책 ConfigMap의 두 파일 bytes, 이미지 pin, security/resource/volume/probe/NetworkPolicy의 고정 범위, 다른 namespace 활성화 거부와 enabled 타입·추가 속성 거부도 확인합니다. 실패한 Helm 입력은 실패로 남기며 자동 재시도하지 않습니다.

별도 `public-gateway-chart.yml`은 읽기 전용 권한으로 기존 Linux Helm 4.3.0 archive pin을 사용하고, 정확한 main K 공개 Git blob에서 기준 chart와 값을 만듭니다. 원 chart의 새 기준 렌더와 후보 chart를 같은 main K 값으로 비교합니다. Windows도 immutable baseline workspace의 K 값을 사용하며, 실제 현재 home-lab 값의 렌더 검사는 별도 단계로 구분합니다. Linux archive의 전체 SHA와 그 안의 단일 `linux-amd64/helm` bytes도 실제 CI에서 확인했습니다. 다운로드·고정 npm 의존성 준비 단계와 클러스터에 접근하지 않는 Helm 렌더 단계를 구분합니다. API·web 전체 테스트와 HTTP 컨테이너 검증은 이 workflow에서 반복하지 않습니다. 기존 image-only `validate-gitops.yml`은 유지합니다.

실제 검토 후 실행할 때는 Node 24.19.0과 승인된 Helm 4.3.0을 명시합니다. 아래 인수는 공개 fixture·검증 도구·새 출력 폴더의 로컬 경로이며 비밀값이 아닙니다.

```text
node infra/charts/platform-lab/ci/validate-public-gateway-render.mjs
  --helm <approved-helm-executable>
  --baseline <immutable-rendered-baseline.yaml>
  --baseline-receipt <immutable-render-receipt.json>
  --yaml-require-from <existing-lab-web-package.json>
  --output <fresh-local-validation-directory>
```

Linux에서는 `--helm-archive <verified-linux-archive>` 인수가 추가로 필요합니다. Windows 원 로컬 검사와 소스 `501e127`의 Linux CI 결과는 각각 보존합니다. 문서 갱신 후 정확한 새 head의 CI 결과와 실제 적용 결과는 별도로 확인합니다.
