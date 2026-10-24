# Kafka 웹 조회 화면 — Kafbat UI

작성 기준: 2026-10-24 KST. 이 문서는 **추가 UI의 배포 준비와 운영 확인 절차**입니다. 아래 정적 검증만으로 설치·외부 로그인·Kafka 조회 성공을 표시하지 않습니다. 실제 설치와 공통 인증 프록시는 운영 담당자가 별도로 반영하고 그 결과를 남깁니다.

## 화면에서 볼 것

로그인 후 Kafka 화면에서 `platform-lab`을 선택합니다. Topics에서 토픽·파티션·offset을, Consumers에서 consumer group·committed offset·lag를 확인할 수 있습니다. Messages는 개인 Lab의 합성 데이터만 소량 조회합니다. 보존 기간 때문에 이미 사라진 메시지는 조회되지 않을 수 있고, 화면의 조회 자체가 새 작업 실행이나 복구 시험을 뜻하지 않습니다.

토픽 생성·삭제, 메시지 발행, consumer offset 재설정, broker 설정 변경은 이 화면의 허용 범위에 포함하지 않습니다.

## 추가되는 구성

[manifest](../../infra/service-console/kafbat/manifests.yaml)는 기존 `platform-lab` namespace에 `platform-lab-kafbat` 이름의 ConfigMap·Deployment·ClusterIP Service만 추가합니다. Kafka broker·listener·advertised address·기존 workload 이미지와 source pin을 수정하지 않습니다. Ingress·NodePort·hostPort·PVC·ServiceAccount 권한도 만들지 않습니다.

| 항목 | 설정 |
| --- | --- |
| 애플리케이션 | Kafbat UI v1.5.0, 공식 GHCR OCI index digest 고정 |
| 내부 HTTP | `platform-lab-kafbat.platform-lab.svc.cluster.local:8080` |
| Kafka 연결 | 기존 `kafka.platform-lab.svc.cluster.local:9092`, PLAINTEXT |
| 외부 접속 | 별도 HTTPS 호스트의 `/`에서 공통 인증 프록시를 통과한 뒤 접근 |
| 서버 쓰기 제한 | cluster `read-only: true`, 동적 설정·MCP·Swagger 비활성화 |
| 데이터 읽기 | String 내장 SerDe, 최대 페이지 100건, auto-create·auto-commit 비활성화 |
| 컨테이너 | non-root UID/GID 1000, service-account 토큰 미마운트, 읽기 전용 root FS, 모든 capability 제거 |
| 자원 | request 100m·256Mi / limit 500m·768Mi, heap 최대 384Mi |
| 임시 저장 | PVC 없이 `/tmp` emptyDir 64Mi, ephemeral request 16Mi / limit 128Mi |
| probe | `/actuator/health/liveness`, `/actuator/health/readiness`; 시작 대기 최대 약 5분 |

요청·한도는 새 UI 한 개의 설정입니다. 보류 중인 전체 디스크·DB·Garage 예산 정책이나 강제 quota를 결정한 것이 아닙니다. probe는 UI 프로세스 상태만 확인합니다. 별도의 Kafka cluster 연결·토픽 조회 결과를 함께 확인해야 합니다.

## 인증과 읽기 전용의 경계

외부 로그인은 운영 담당자가 구성하는 HTTPS 공통 인증 프록시에서 수행합니다. Kafbat 내부 `auth.type`은 `DISABLED`이므로 **프록시를 우회해 도달하면 별도 로그인이 없습니다**. 인증이 적용되지 않은 외부 라우트, 별도 포트 공개, 공용 port-forward를 만들지 않습니다. ClusterIP는 그 자체로 다른 Pod의 접근까지 막는 NetworkPolicy가 아닙니다. 프록시 연결 전 내부 노출 경로와 기존 네트워크 정책을 확인합니다.

`read-only: true`는 Kafbat 서버가 cluster API의 변경 요청을 거절하는 제한입니다. 일부 메시지 분석·smart-filter POST는 공식 코드의 읽기 예외입니다. Kafka ACL이나 별도 broker의 읽기 전용 자격증명을 발급한 것은 아니므로, broker 차원의 무수정 권한 보장으로 설명하지 않습니다. broker의 PLAINTEXT·기존 접근 정책은 이번 배포에서 바꾸지 않습니다.

사용자 JAR·외부 SerDe·Kafka Connect·ksqlDB·Schema Registry·MCP를 추가하지 않습니다. 기본 배포에 포함된 CEL 필터 기능까지 제거했다고 주장하지 않습니다. 메시지 원문·내부 그룹 이름·토큰·자격증명을 공개 캡처나 Git 기록에 넣지 않습니다.

## 고정 이미지의 확인 근거

2026-10-23 23:57:43 UTC에 [공식 최신 release](https://github.com/kafbat/kafka-ui/releases/tag/v1.5.0)와 GHCR의 익명 manifest 응답을 조회했습니다. v1.5.0은 2026-04-20 게시됐고, source commit은 `afc9c918e13c4422268a3a5b7933c7b448746c82`입니다.

```text
ghcr.io/kafbat/kafka-ui:v1.5.0@sha256:7cda86a33344160309fdb65146332e4da65db81a945614f2fe32e210803f6fd1
linux/amd64 manifest: sha256:2fc9a60b223de6d8cb45a64175afcbb79207ae19306a0b99c558aeaa1b22b6e9
```

OCI index 응답의 `Docker-Content-Digest`와 실제 응답 bytes SHA256이 일치했습니다. [image-lock.json](../../infra/service-console/kafbat/image-lock.json)에 범위를 기록했습니다. image layer 다운로드·서명 검증·취약점 검사·컨테이너 기동을 수행한 결과는 아닙니다. 공식 [Dockerfile](https://github.com/kafbat/kafka-ui/blob/afc9c918e13c4422268a3a5b7933c7b448746c82/api/Dockerfile)의 비root 사용자와 실제 image config의 `kafkaui`를 확인했으며, 숫자 UID 1000·읽기 전용 FS의 실제 기동은 운영 반영 때 확인합니다.

## 배포 담당자 순서

아래는 저장소 루트에서 실행하는 절차입니다. 현재 문서 작성 작업에서는 클러스터에 실행하지 않았습니다.

1. 기존 서비스·Kafka 상태, 같은 이름의 리소스 유무, 인증 프록시의 로그인·익명 차단을 확인합니다. 새 UI를 외부 라우트와 연결하기 전에 우회 포트가 없는지 확인합니다.
2. 로컬 렌더링 후 운영 대상에서 server dry-run을 수행합니다.

   ```sh
   kubectl kustomize infra/service-console/kafbat
   kubectl apply --dry-run=server -k infra/service-console/kafbat
   ```

3. 준비 결과가 맞으면 새 세 리소스만 반영하고 Ready를 확인합니다.

   ```sh
   kubectl apply -k infra/service-console/kafbat
   kubectl -n platform-lab rollout status deployment/platform-lab-kafbat --timeout=300s
   kubectl -n platform-lab get deployment/platform-lab-kafbat service/platform-lab-kafbat
   ```

4. 운영 담당자가 공통 HTTPS 인증 프록시의 **새 UI 전용 호스트**와 내부 ClusterIP를 연결합니다. 별도 호스트의 루트로 제공하므로 context/base path를 변경하지 않습니다. 기존 API·Jenkins·Argo CD 라우트와 인증 설정은 별도 검토합니다.
5. 실제 외부 클라이언트에서 익명 요청은 로그인 요구 또는 401/403인지, 로그인 후 HTML·정적 자원·Kafka cluster/topic/group 조회가 정상인지 확인합니다. UI의 읽기 전용 표시와 변경 버튼 부재도 확인합니다. 세션·Authorization·cookie 원문은 로그에 남기지 않습니다.
6. 배포 전후 기존 workload 이미지/source pin·Pod·Kafka topic/group 상태를 비교합니다. 변경 API를 실제로 호출하거나 토픽·데이터를 만들지 않고 확인한 범위만 기록합니다. broker 장애·복구·장기 가용성 시험은 별도입니다.

ConfigMap만 바꾸면 실행 중인 Spring 설정이 자동 재로딩되지 않습니다. UI 설정 갱신은 새 설정 검토 후 **UI Deployment만** 다시 생성하거나 rollout restart해 적용합니다. 기존 broker나 worker를 재시작하지 않습니다.

문제가 생기면 새 외부 라우트를 먼저 해제하고, 새 UI의 리소스만 제거할 수 있습니다. 아래 삭제 대상에 Kafka broker·PVC·namespace·기존 서비스는 포함하지 않습니다.

```sh
kubectl delete -k infra/service-console/kafbat
```

## 실제 운영 반영 — 2026-10-24

서버 dry-run 후 새 리소스3개를 적용했고 UI Deployment Ready를 확인했습니다. HTTPS 인증 프록시를 연결해 익명 HTML/API401, 인증 후 UI HTML200, cluster1개 ONLINE·readOnly=true, 토픽1개·consumer group1개 조회200을 확인했습니다. 기존 workload 사양·UID와 기존 Traefik 파일은 전후 같았습니다. /consumer-groups의 첫404를 보존하고 공식 /consumer-groups/paged로 정정한 별도 GET200을 기록했습니다. 신규 데이터·Kafka 변경 요청은 하지 않았으며 브라우저 로그인 후 메시지 탐색·쓰기 거부 요청·장애 복구는 시험하지 않았습니다. [서비스 접속 안내](service-console.md)의 계정/인증 범위와 한계를 함께 읽습니다.

아래 항목은 manifest 작성 단계의 원래 검증 이력입니다. 이후 운영 확인을 과거 시점에 소급하지 않습니다.

## 작성 단계의 검증과 남았던 확인

- 로컬 `kubectl kustomize`가 ConfigMap·Service·Deployment 3개를 정상 렌더링했습니다. Helm은 로컬에 없으며 새 chart dependency를 추가하지 않았습니다.
- bundled Python에 PyYAML이 없어 별도 YAML parser 검사는 수행하지 못했습니다. 첫 제한된 shell에서 경로 접근 실패가 있었고, 허용된 로컬 렌더링으로 다시 확인했습니다.
- server dry-run·이미지 pull·Pod 기동·probe HTTP·Kafka 연결·쓰기 차단·외부 인증·브라우저 화면 확인은 **이 문서 작성 범위에서 미실행**입니다. 운영 담당자가 실제 결과로 갱신합니다.
- 공통 인증 프록시가 비밀번호나 IdP 최초 로그인을 요구하면 사용자가 정한 안전한 입력 경로를 이용합니다. Kafka UI 자체에는 새 GitHub 토큰이 필요 없습니다.
- Pages 토큰 교체·별도 환경의 K3s/Jenkins 기동 복원·전체 자원 예산 정책·PR #102 보류는 그대로입니다.

## 공식 설정 근거

- [YAML 설정과 `read-only`](https://ui.docs.kafbat.io/configuration/configuration-file)
- [동적 설정·base path·release check](https://ui.docs.kafbat.io/configuration/misc-configuration-properties)
- [고정 버전의 서버 읽기 전용 필터](https://github.com/kafbat/kafka-ui/blob/afc9c918e13c4422268a3a5b7933c7b448746c82/api/src/main/java/io/kafbat/ui/config/ReadOnlyModeFilter.java)
- [고정 버전의 dynamic-config 검증](https://github.com/kafbat/kafka-ui/blob/afc9c918e13c4422268a3a5b7933c7b448746c82/api/src/main/java/io/kafbat/ui/util/DynamicConfigOperations.java)
- [고정 버전의 MCP 조건](https://github.com/kafbat/kafka-ui/blob/afc9c918e13c4422268a3a5b7933c7b448746c82/api/src/main/java/io/kafbat/ui/config/McpConfig.java)
- [Spring Boot 3.5 probe 설정](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
