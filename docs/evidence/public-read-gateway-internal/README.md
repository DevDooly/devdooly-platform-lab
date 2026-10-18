# 내부 게이트웨이 조회·접근 진단

미니 PC의 Kubernetes 내부에서 조회용 게이트웨이를 배포하고, 허용된 클라이언트가 사용할 수 있는 조회와 제한되는 요청을 확인했습니다. 다른 클라이언트의 TCP 연결은 즉시 거절됐으며 그 전후 허용된 클라이언트의 조회는 정상 응답했습니다. 시험 자원을 정리한 뒤 기존 API·worker·저장소·작업의 선택 상태가 유지되는지도 비교했습니다.

2026-10-18의 개인 Lab 기록입니다. 외부 HTTPS와 공개 사이트의 실시간 API 연결은 아직 대기 중입니다.

| 확인한 항목 | 실제 관측 |
| --- | --- |
| 내부 배포 | Argo CD의 고정 소스 반영과 gateway 선언 4개, Ready 1개 확인 |
| 허용 조회 | summary·release·run 목록·job·Kafka·고정 상세 조회 6개 통과 |
| 요청 제한 | 잘못된 메서드·쿼리·비공개 경로 요청 3개가 정한 응답으로 제한됨 |
| 별도 클라이언트 진단 | DNS 성공, 직접 API 조회 200, gateway TCP 시도 1회의 ECONNREFUSED(111), 측정 0ms |
| 전후 대조 | TCP 시도 전후 허용된 별도 클라이언트의 gateway summary가 모두 200, 같은 DNS 대상 확인 |
| 임시 자원 정리 | 첫 시험 3개와 후속 진단 4개를 각각 생성 시 확인한 UID로 정리하고 부재 확인 |
| 기존 상태 보존 | API·worker·Pod·PVC 및 공개 job/Kafka 안정 필드 6개 범주 비교 일치. PVC 4개, EXPORTED 작업 8개, export 파일 metadata 16개, commit/end/lag 8/8/0 |

## 첫 실패와 후속 진단을 구분합니다

첫 접근 시험은 허용 조회와 요청 제한을 통과했지만, 거부할 클라이언트의 TCP 연결이 4초 동안 응답하지 않을 것으로 기대했습니다. 실제로는 즉시 OTHER_ERROR가 관측돼 전체 시험은 **실패**로 남겼습니다. 이때 정확한 errno는 수집하지 않았습니다.

후속 진단에서는 응답 없는 경우만 성공으로 정하지 않고 TCP 결과와 errno를 수집했습니다. 허용 클라이언트의 전후 조회와 직접 API 조회가 200인 상태에서, 다른 클라이언트의 gateway 연결은 ECONNREFUSED(111)로 즉시 거절됐습니다. **이는 후속 실행의 관측이며 첫 실패의 errno나 정확한 원인을 소급해 확정하지 않습니다.**

K3s는 [kube-router 기반 Network Policy controller](https://docs.k3s.io/networking/networking-services#network-policy-controller)를 사용한다고 설명하며, [공식 kube-router 구현](https://github.com/cloudnativelabs/kube-router/blob/master/pkg/controllers/netpol/pod.go)에는 REJECT 규칙 생성 경로가 있습니다. 이 기록에서는 설치된 controller 버전과 실제 커널 규칙을 조사하지 않았으므로, 연결 거절이 NetworkPolicy만의 결과라는 독립 인과성은 증명하지 않습니다.

## 확인 범위와 다음 단계

같은 합성 개인 Lab에서 짧게 관측한 결과입니다. Node·host·NAT 경로, 부하 포화, 장기간 가용성, 자격증명 회전과 전체 DB/BLOB 내용 동등성은 확인하지 않았습니다. 마지막 보존 비교는 시간·heartbeat·정상 poll 단계처럼 변하는 항목을 제외한 선택 상태를 비교했습니다.

다음은 기존 외부 프록시와 인증서 상태를 정리하고 외부 HTTPS를 연결하는 작업입니다. 공개 화면은 현재까지 게시한 관측 기록을 보여주며 내부 API를 실시간으로 호출하지 않습니다.

## 소스와 요약

- [내부 배포 소스](https://github.com/DevDooly/devdooly-platform-lab/tree/1a9365fbad66fcc8e0cf5ab3cf957c1f70dc15fe/infra/charts/platform-lab)
- [활성화 PR #77](https://github.com/DevDooly/devdooly-platform-lab/pull/77)
- [공개 요약 JSON](summary.json)

요약에는 실행 날짜·소스·관측 결과·정리·보존 범위만 담습니다. 실제 주소, UID, nonce, DNS 지문과 private baseline hash는 공개하지 않습니다.
