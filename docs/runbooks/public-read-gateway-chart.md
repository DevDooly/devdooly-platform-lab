# 선택적 조회 gateway의 Helm 선언

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

클라이언트 Pod는 만들지 않습니다. 배포 후 별도 검증을 하려면 지정한 client selector를 쓰는 격리 Job 등이 필요합니다. Docker 검증의 tmpfs `noexec/nosuid/nodev`나 PID 64 제한을 Kubernetes emptyDir·Deployment가 똑같이 제공한다고 주장하지 않습니다. Memory emptyDir는 Pod 메모리를 사용합니다.

## 활성화 전에 남은 조건

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
