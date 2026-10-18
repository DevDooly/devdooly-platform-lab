# 내부 조회 gateway 활성화 계획

이 후보는 main N `6b405ab5`의 공개 소스를 기준으로 준비합니다. 실제 gateway를 띄우거나 외부에 공개한 결과가 아닙니다. 기존 main K fixture의 CI 통과와 현재 환경 값의 렌더·실제 배포를 구분합니다.

## 후보 변경

- `home-lab/runtime.yaml`에 `publicReadGateway.enabled: true`만 추가합니다. 기존 API·web·worker source와 image digest·환경 설정을 보존합니다.
- 전용 AppProject의 기존 6개 namespace resource kind에 `networking.k8s.io/NetworkPolicy` 1개만 추가합니다. destination·source repository·빈 cluster whitelist를 유지합니다.
- checker는 이 정확한 7종과 전용 destination·빈 cluster whitelist를 확인합니다. Windows와 Linux 모두 원/새 chart를 고정한 K fixture로 비교하며 이 검사를 실제 환경 값의 렌더로 표시하지 않습니다.

gateway는 내부 ClusterIP·replica 1·고정 Nginx 정책·UID 101·읽기 전용 루트·Memory tmp 16Mi를 그대로 사용합니다. 새 chart 값·Ingress·NodePort·외부 TLS·API/worker 이미지·기존 서비스 정책은 추가하거나 바꾸지 않습니다.

## 확인한 사실과 아직 모르는 것

2026-10-18 08:34:31 UTC의 읽기 점검에서는 kube-system namespace identity·DNS label과 API Deployment/Pod instance label의 일치, Running API Pod 1개를 확인했습니다. Node 1개는 Ready이고 선택한 pressure 신호가 없었습니다. MemAvailable 16,240MiB·루트 파일시스템 가용 204,245MiB는 해당 시점의 관측이며 스케줄링·지속 용량을 보장하지 않습니다.

실제 전용 AppProject는 destination과 빈 cluster whitelist가 예상대로였고 NetworkPolicy 권한은 허용되지 않았습니다. DNS/API 연결·정책의 실제 강제·scheduler admission·Pod 기동·외부 HTTPS는 아직 확인하지 않았습니다. NetworkPolicy의 node·host·NAT 경로 한계는 [runbook](../runbooks/public-read-gateway-chart.md)을 따릅니다.

## 검증·실행 순서

1. 완료 — Windows C 후보에서 K fixture checker를 한 번 실행했습니다. version 포함 15회 호출·예상 거부 9개, 기존 12개 전체 bytes 보존·true 4개 추가와 정확한 7종 AppProject 선언을 확인했습니다. [K fixture 결과](../evidence/public-read-gateway-internal/activation-render.k-fixture.json)를 보존합니다.
2. 완료 — 별도의 C 실행기로 실제 현재 N의 `home-lab/values.yaml`과 활성화 후보 `runtime.yaml`을 사용해 한 번 렌더했습니다. 16개 resource·기존 12개 전체 객체/image/source/environment 보존과 전체 렌더 SHA `05f59ba6…`를 확인했습니다. [현재 값 결과](../evidence/public-read-gateway-internal/activation-render.current-values.json)를 K fixture와 구분합니다. source 51개·도구·원 기준 파일은 전후 동일했고 클러스터에 적용하지 않았습니다.
3. Root 검토 후 활성화 PR을 준비합니다. 실제 전용 AppProject에 기존 6종·destination·빈 cluster whitelist를 조건으로 하는 원자적 NPK 1종 추가와 복원 방법을 먼저 준비합니다.
4. 권한 추가·보존을 실제로 확인한 뒤 runtime 활성화 PR을 병합하고 Argo CD sync를 관측합니다. API·worker를 수동 Helm으로 중복 배포하지 않습니다.
5. 지정 client selector를 쓰는 격리 검증으로 DNS·API·허용/거부 경로를 확인하고, 전후 jobs/export의 안정 필드·Pod/PVC metadata·Kafka 관측을 비교합니다. 이는 전체 DB 행·BLOB의 동등성 대조가 아닙니다. TCP probe Ready만으로 API·정책 성공을 판정하지 않습니다.

실제 적용 전에는 현재 source/image·namespace 자원·권한·기존 상태를 다시 확인합니다. 실패하면 단계를 멈추고 원본 결과를 보존하며, 기존 서비스에 영향을 주는 복원은 준비한 정확한 범위에서 수행합니다. 공개 사이트의 실시간 endpoint 연결과 외부 Traefik→K3s/TLS는 별도 후속입니다.
