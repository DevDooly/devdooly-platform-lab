# 개인 Lab 앱 Helm chart

Spring Boot API, Nginx 정적 화면, MariaDB를 전용 namespace에 하나씩 배치하는 최소 chart입니다. Kubernetes 1.32 이상을 대상으로 하며 K3s 1.36.5 기준으로 로컬 렌더링했습니다.

API/web 이미지 빌드와 MariaDB 통합 실행은 [Linux Compose CI](../../../docs/evidence/compose-ci/README.md)에서 검증했습니다. 이후 실제 게시 digest로 미니 PC에 배포해 DB PVC Bound, 앱 Pod Ready와 Argo CD Synced/Healthy를 확인했습니다. **웹에서 API를 호출하는 HTTP 경로의 성공은 별도 검증 항목**입니다. 최신 결과와 한계는 [미니 PC 검증 기록](../../../docs/evidence/mini-pc/README.md)을 따릅니다. 기본 values의 이미지 repository·digest와 database.existingSecret는 의도적으로 비어 있습니다.

## 구성과 제약

| 구성 | 설정 |
| --- | --- |
| API | Deployment 1개, replica 1, Recreate, UID/GID 10001 |
| 화면 | Deployment 1개, replica 1, Recreate, Nginx UID/GID 101 |
| DB | MariaDB 11.8.9, StatefulSet replica 1, 저장소 이미지 digest 고정 |
| 저장소 | DB 전용 ReadWriteOnce 10Gi local-path PVC |
| 통신 | api:8080, web:8080, db:3306, 모두 ClusterIP |
| 관리자 권한 | ServiceAccount 토큰 자동 마운트 안 함, RBAC 생성 안 함 |
| 공개 경로 | Ingress 지원 안 함, NodePort·LoadBalancer·hostPort 없음 |
| 비밀번호 | 기존 Secret의 app-password·root-password key 참조만 함 |

Service 이름은 api·web·db로 고정했습니다. chart는 Nginx의 `API_UPSTREAM_HOST`에 `api.<Release.Namespace>.svc.cluster.local`을 전달합니다. Nginx의 동적 resolver가 search 도메인을 확장하지 않으므로 Kubernetes에서는 전체 Service 이름을 사용하며, Compose의 기본 호스트 `api`와 구분합니다. **전용 namespace에 chart release 하나만** 설치해야 합니다. 기본 문서의 release는 lab, namespace는 platform-lab입니다. 기존 서비스·DB 경로를 재사용하지 않습니다.

API/web은 읽기 전용 루트 파일 시스템, 제한된 /tmp emptyDir, RuntimeDefault, 권한 상승 금지와 capability 제거를 적용합니다. MariaDB는 공식 entrypoint가 자체 데이터 경로의 권한을 준비한 뒤 mysql 사용자로 전환하는 방식을 유지합니다. DB 초기 프로세스까지 nonroot라고 주장하지 않으며 이 설정 그대로는 Pod Security restricted 정책을 충족하지 않습니다.

## 자원 예산

| 컨테이너 | CPU 요청 / 제한 | 메모리 요청 / 제한 |
| --- | --- | --- |
| API | 100m / 1 | 256Mi / 768Mi |
| 화면 | 25m / 250m | 64Mi / 192Mi |
| MariaDB | 100m / 1 | 512Mi / 1536Mi |
| 합계 | 225m / 2.25 | 832Mi / 2496Mi |

Jenkins·Argo CD·K3s·빌드 agent·OS 자원은 별도입니다. DB PVC는 10Gi이며 local-path 용량 요청이 디스크 사용량의 강제 상한을 보장하지는 않습니다.

## 로컬 렌더링 검증

설치된 Helm 4.3.0으로 저장소 루트에서 실행합니다.

    helm lint infra/charts/platform-lab --strict --kube-version 1.36.5 --values infra/charts/platform-lab/ci/lint-values.yaml
    helm template lab infra/charts/platform-lab --namespace platform-lab --kube-version 1.36.5 --values infra/charts/platform-lab/ci/lint-values.yaml

ci/lint-values.yaml은 존재하지 않는 example.invalid 이미지와 가짜 Secret 이름으로 **문법·정책만** 검사하는 fixture입니다. 설치, kubectl apply, Argo CD Application의 valueFiles에 사용하지 않습니다. 실행 가능한 배포 예시가 아닙니다.

화면 의존성이 설치된 Node 환경에서는 다음 명령으로 같은 검증과 15개 정책 검사, 잘못된 입력 6개의 거부를 재현합니다.

    node infra/charts/platform-lab/ci/validate-render.mjs

Helm 경로가 다르면 HELM_BINARY에 실행 파일 경로를 지정합니다. 기본 도구는 저장소 .local/tools/helm-4.3.0/windows-amd64/helm.exe이며 Helm 4.3.0 빌드를 확인합니다. 원본 manifest는 Git 제외 경로 .local/app-helm-render에만 저장하고, 공개 검증 결과는 [ci/render-validation.json](ci/render-validation.json)에 기록합니다.

2026-10-11 검증: Helm v4.3.0+gbec5b06, strict lint/render 통과, manifest 7개, 정책 15개 통과, 필수값 누락·잘못된 digest·API 복제 확대·Ingress·다른 storageClass 입력 6개 거부 확인. Kubernetes API server 검증 및 실제 실행 결과로 해석하지 않습니다.

## 실제 배포 전에 필요한 값

- api.image.repository·digest, web.image.repository·digest: 이 저장소 Dockerfile로 빌드하고 registry에 게시한 **앱 이미지**의 주소와 실제 sha256 digest입니다. infra/image-lock.json에 있는 Temurin·Nginx 기반 이미지 digest를 앱 digest로 대신 넣지 않습니다.
- api.sourceCommit: 해당 앱 이미지에 대응하는 Git commit입니다. 기본값 unknown은 해당 실행에 실제 소스 commit을 주입하지 않았다는 뜻입니다.
- database.existingSecret: 같은 namespace에 미리 준비한 Secret 이름입니다. appPasswordKey·rootPasswordKey로 지정한 두 key가 있어야 합니다. Secret의 값은 Git이나 Helm values에 넣지 않습니다.
- imagePullSecrets: registry가 비공개이면 같은 namespace의 기존 image pull Secret 이름을 지정합니다.

실제 구성은 [ADR 0003](../../../docs/adr/0003-gitops-in-existing-repository.md)에 따라 같은 저장소의 [gitops/environments/home-lab/values.yaml](../../../gitops/environments/home-lab/values.yaml)에서 관리하고 Argo CD가 배포를 소유합니다. Jenkins에서 같은 앱에 helm upgrade를 추가하지 않습니다. 후속 절차는 [앱 배포 안내](../../../docs/runbooks/app-helm.md)를 따릅니다.

## 초기화·보존 범위

Flyway와 합성 데이터 seed는 API 시작 시 실행됩니다. API replica 1과 Recreate는 이 Lab의 단일 초기화 프로세스 전제이며, 동시 최초 초기화를 해결하는 분산 잠금 구현이 아닙니다. 복제 확장 전에 migration/seed 실행을 별도로 설계해야 합니다. API 기동이 DB 초기화보다 빠르면 프로세스가 실패·재시도할 수 있습니다. probe가 DB 준비를 기다리는 init 단계나 의존성 순서를 대신하지 않습니다.

DB PVC는 StatefulSet 삭제·축소 시 유지됩니다. **namespace 삭제나 PVC 직접 삭제까지 막아주지는 않습니다.** release/namespace 이름을 바꾸면 기존 claim을 자동으로 재사용하지 않습니다. 보존된 PVC에 재설치할 때는 기존 계정 비밀번호를 유지해야 하며 Secret 값만 바꾸어도 DB 계정 비밀번호가 갱신되지는 않습니다. 실제 Jenkins·DB PV의 reclaimPolicy는 Delete이므로 claim을 삭제하면 provisioner가 저장 데이터를 제거할 수 있습니다. PV는 전용 /var/lib/devdooly-platform-lab/storage 아래에 생성합니다. 단일 노드 local-path는 복제·백업이 아니므로 별도 백업과 복구 검증이 필요합니다.

bootstrap이 보관한 감사 자료는 같은 호스트의 설정·네트워크 상태 기록이며 DB·PVC 데이터 백업이 아닙니다. 외부 백업·복원과 호스트 재부팅 복구는 아직 검증하지 않았습니다. 로컬 렌더링 기록, Argo 동기화·Pod readiness, 실제 HTTP 조회와 데이터 복원 결과를 각각 구분합니다.

## 공식 참고

- [Kubernetes StatefulSet PVC 보존](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#persistentvolumeclaim-retention)
- [Spring Boot Kubernetes probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [MariaDB healthcheck.sh](https://mariadb.com/docs/server/server-management/automated-mariadb-deployment-and-administration/docker-and-mariadb/using-healthcheck-sh)
- [MariaDB 공식 Dockerfile과 entrypoint](https://github.com/MariaDB/mariadb-docker)
- [Nginx 공식 Alpine Dockerfile](https://github.com/nginx/docker-nginx/blob/master/stable/alpine-slim/Dockerfile)

## 선택적인 Kafka·Garage·상시 worker

`runtime.kafka.enabled`, `runtime.garage.enabled`, `runtime.worker.enabled`의 기본값은 모두 `false`입니다. 이 경우 기존 7개 리소스만 렌더링합니다. 세 항목을 켜면 Kafka·Garage StatefulSet 각 1개, ClusterIP Service 각 1개와 worker Deployment 1개를 추가해 총 12개가 됩니다. worker에는 HTTP 포트와 Service가 없습니다.

기존 API/Web 이미지 게시 gate의 `gitops/environments/home-lab/values.yaml`은 이미지 전용 형식을 유지합니다. runtime 설정은 별도 `gitops/environments/home-lab/runtime.yaml`에서 관리하며, Argo CD Application의 `helm.valueFiles`에 이 파일을 추가해야 반영됩니다. 자동 이미지 게시가 이 파일이나 worker 핀을 덮어쓰지 않습니다. worker는 검증한 API 이미지의 repository·digest와 대응하는 40자리 source commit을 **별도로 명시**해야 합니다. 비활성 기본값에서는 이미지가 비어 있어도 되지만, 활성화하면 schema가 누락·`unknown`·복제 확대·250초 미만 종료 유예를 거부합니다.

| 추가 구성 | 고정 조건 | 영속 저장소 |
| --- | --- | --- |
| Kafka | 4.3.1 JVM, combined KRaft 1대·static voter 1개, 기본 partition 1·RF 1, topic 자동 생성 비활성 | 전용 5Gi claim, metadata와 log 경로 함께 보존 |
| Garage | 2.4.1 linux-amd64, SQLite·replication factor 1, S3 포트만 ClusterIP | metadata 2Gi·data 10Gi, 별도 claim |
| worker | API 이미지의 명시적 CLI `--lab-runtime=run`, replica 1·Recreate, 종료 유예 300초 | DB outbox·journal과 외부 객체 저장소 사용 |

Kafka/Garage claim은 StatefulSet 삭제·축소 시 `Retain`입니다. 직접 PVC·namespace를 지우는 작업과 local-path PV의 Delete 정책까지 방지하지는 않습니다. 단일 노드·단일 복제 구성은 합성 데이터 Lab 용도이며 복제나 백업을 제공하지 않습니다. Garage layout의 capacity와 local-path PVC 요청도 실제 디스크 사용량의 강제 상한은 아닙니다.

추가 요청량은 CPU 450m·메모리 1280Mi, 제한 합계는 CPU 4·메모리 4352Mi입니다. 추가 PVC 요청은 총 17Gi이며 기존 DB 10Gi는 유지합니다. 실제 가용량·백업과 기존 서비스 자원은 rollout 전에 별도로 확인합니다.

모든 추가 Pod는 명시적 nonroot UID/GID, RuntimeDefault, capability 제거와 권한 상승 금지를 사용하고 Kubernetes API 토큰을 마운트하지 않습니다. Garage와 worker는 읽기 전용 루트와 제한된 `/tmp`를 사용합니다. Kafka는 공식 entrypoint가 `/opt/kafka/config`에 설정을 생성하므로 이미지의 쓰기 가능한 레이어를 유지합니다. Kafka의 appuser UID/GID는 고정 이미지에서 1000/1000으로 확인한 값입니다.

Kafka 주소는 `kafka.<namespace>.svc.cluster.local:9092`, Garage는 `http://garage.<namespace>.svc.cluster.local:3900`입니다. Kafka controller는 9093의 내부 static voter만 사용하며 외부 주소를 advertise하지 않습니다. headless Kafka Service는 처음의 voter DNS 순환 대기를 막도록 `publishNotReadyAddresses: true`입니다. Garage RPC는 Pod 내부 loopback만 사용하며 RPC·관리·웹 포트를 Service로 열지 않습니다. 이 구성은 신뢰하는 개인 클러스터 내부의 PLAINTEXT/HTTP 경로이며 외부용 TLS·인증 경로를 제공하는 구성이 아닙니다.

### 외부에서 먼저 준비하는 Secret

chart는 Secret을 만들지 않습니다. 값·설정 원본·키 출력은 Git 제외 private 경로에 제한된 파일 권한으로 보관합니다.

| 이름 | key | 용도 |
| --- | --- | --- |
| `platform-lab-kafka` | `cluster-id` | 최초 생성한 KRaft cluster ID. 같은 PVC에서는 유지 |
| `platform-lab-garage-config` | `garage.toml` | RPC secret이 포함된 전체 설정, 파일 모드 0440으로 마운트 |
| `platform-lab-runtime-s3` | `access-key-id`, `secret-access-key` | 해당 합성 bucket의 read/write key, owner 권한 없음 |
| 기존 `platform-lab-db` | `app-password` | 기존 DB 계정 사용. DB 계정이나 비밀번호를 초기화하지 않음 |

Garage private 설정의 필수 경로는 `metadata_dir = "/var/lib/garage/meta"`, `data_dir = "/var/lib/garage/data"`입니다. `db_engine = "sqlite"`, `replication_factor = 1`, RPC bind/public은 `127.0.0.1:3901`, `[s3_api]`의 bind는 `0.0.0.0:3900`, region은 `garage`로 맞춥니다. RPC secret은 새로 생성한 32-byte hex 값이며 공개 TOML·Helm values에 넣지 않습니다. namespace의 Secret을 변경한 뒤에는 사용 중인 프로세스·RPC 연결에 미치는 영향을 검토하고 해당 Pod를 계획대로 교체해야 합니다.

### 단계별 bootstrap과 실제 검증

1. 기존 DB·서비스 상태와 새 외부 백업을 확인하고, Kafka/Garage private Secret을 준비합니다.
2. `runtime.yaml`에서 Kafka·Garage만 켜고 worker는 끈 상태로 GitOps에 반영합니다. Pod/PVC·권한·기존 서비스 보존을 확인합니다.
3. 아래의 내부 Kafka topic과 신규 Garage layout·bucket·read/write key를 준비합니다. Secret 값을 Git·채팅·공개 근거로 출력하지 않습니다.
4. 같은 source SHA에서 Jenkins·Actions를 통과한 API 이미지 게시·GitOps 반영 후 API가 V2·V3 migration을 적용했는지 확인합니다. 상시 CLI는 migration을 적용하지 않습니다.
5. 검증한 worker 이미지·source commit·S3 Secret을 지정하고 worker를 켭니다. API `api.environment`도 `mini-pc`로 설정해 관측 scope를 구분합니다.
6. 관리자 전용 1회 Job에 `--lab-runtime=stage`와 고유한 `LAB_RUNTIME_STAGE_RUN_ID=lab-fixture-...`를 전달해 고정 합성 입력 12개만 등록합니다. 이후 실제 dispatch·수신·두 파일 전체 GET 검증·EXPORTED·슬롯 해제와 consumer lag을 확인합니다. stage Job은 상시 chart 리소스가 아닙니다.

Kafka topic은 이미지를 실행 중인 Kafka Pod 안에서 생성합니다. 아래는 기본 release `lab`, namespace `platform-lab`의 명령이며, 실행 전에 현재 context·실제 Pod·topic 이름을 확인합니다.

```sh
kubectl -n platform-lab exec lab-platform-lab-kafka-0 -- \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka.platform-lab.svc.cluster.local:9092 \
  --create --if-not-exists --topic platform-lab-dispatch-v1 \
  --partitions 1 --replication-factor 1 \
  --config min.insync.replicas=1 \
  --config retention.ms=604800000 \
  --config retention.bytes=134217728 \
  --config max.message.bytes=1024
```

`--if-not-exists`는 기존 topic의 설정을 고쳐 주지 않습니다. 생성 후 `--describe --topic platform-lab-dispatch-v1`로 실제 partition·RF·설정을 대조합니다. 초기 metadata와 consumer group ID는 기존 PVC와 함께 유지합니다.

Garage CLI는 `/garage -c /etc/garage/garage.toml`입니다. `status`, `node id --quiet`, `layout show`로 **신규 PVC의 레이아웃이 아직 비어 있는지** 확인한 뒤 해당 node ID에 `layout assign -z home-lab -c 8G <node-id>`를 실행하고 최초 버전일 때만 `layout apply --version 1`을 적용합니다. 재시작한 기존 layout에 최초 명령을 무조건 반복하지 않습니다.

bucket/key 준비에는 실제 격리 시험과 같은 JSON CLI를 사용할 수 있습니다.

```sh
# 아래 출력은 node ID·bucket ID·key secret을 포함하므로 private 파일로만 캡처합니다.
# Garage Pod: lab-platform-lab-garage-0
/garage -c /etc/garage/garage.toml json-api CreateBucket '{"globalAlias":"platform-lab-synthetic"}'
/garage -c /etc/garage/garage.toml json-api CreateKey '{"name":"platform-lab-worker"}'
# 위에서 실제로 반환한 ID를 private 도우미에서 구성해 전달합니다.
/garage -c /etc/garage/garage.toml json-api AllowBucketKey \
  '{"bucketId":"<returned-bucket-id>","accessKeyId":"<returned-access-key-id>","permissions":{"read":true,"write":true,"owner":false}}'
```

CreateKey의 `accessKeyId`와 `secretAccessKey`를 각각 private 0600 파일에 저장하고 `kubectl create secret generic platform-lab-runtime-s3 --from-file=access-key-id=<private-file> --from-file=secret-access-key=<private-file>`로 준비합니다. 실제 key 값이 shell history·명령 인수·일반 로그에 들어가는 `--from-literal` 방식은 사용하지 않습니다. 이미 생성된 bucket/key를 발견하면 임의로 다시 생성하거나 지우지 말고 기존 소유·권한과 private 보관본을 대조합니다.

Kafka/Garage의 TCP probe는 리스너 연결만 확인합니다. topic·bucket·권한·DB migration·job 성공을 증명하지 않습니다. worker에는 거짓 성공을 만들 수 있는 파일 probe를 추가하지 않았습니다. Kubernetes의 프로세스 상태와 `/api/jobs/observation`의 실제 journal·heartbeat·job/export 상태를 함께 확인합니다. `PAUSED_OPERATOR`는 재시작으로 지워지지 않으며 원인을 확인·교정한 뒤 소유권으로 직렬화된 별도 `--lab-runtime=resume`을 실행해야 합니다.

로컬 검증은 기존 `ci/validate-render.mjs`에 더해 아래를 실행합니다. fixture 이미지는 배포하지 않습니다.

```sh
node infra/charts/platform-lab/ci/validate-runtime-render.mjs
```

2026-10-15에 strict lint/render, runtime 정책 20개와 잘못된 값 13개의 schema 거부를 확인했습니다. 비활성 7개·storage만 활성 11개·worker까지 활성 12개 리소스와 기존 API/Web/DB manifest 보존을 검사했습니다. 이 로컬 결과는 서버 배포·PVC Bound·broker/S3·실제 job 실행 결과를 대신하지 않으며 [ci/runtime-render-validation.json](ci/runtime-render-validation.json)에 범위를 구분합니다.

- [Kafka 공식 Docker 예제](https://github.com/apache/kafka/blob/4.3.1/docker/examples/docker-compose-files/single-node/plaintext/docker-compose.yml), [공식 configure](https://github.com/apache/kafka/blob/4.3.1/docker/resources/common-scripts/configure), [Dockerfile의 appuser](https://github.com/apache/kafka/blob/4.3.1/docker/jvm/Dockerfile)
- [Garage 공식 설정](https://garagehq.deuxfleurs.fr/documentation/reference-manual/configuration/), [단일 노드와 수동 bootstrap](https://garagehq.deuxfleurs.fr/documentation/quick-start/)

## 선택적 조회 gateway

`publicReadGateway.enabled`의 기본값은 `false`입니다. 고정 정책·ClusterIP·NetworkPolicy 선언과 활성화 전 조건은 [별도 운영 안내](../../../docs/runbooks/public-read-gateway-chart.md)를 따릅니다. Windows 오프라인 검사와 소스 `501e127`의 실제 Linux CI에서 확인한 기존 12개 보존·4개 추가는 [실제 결과](../../../docs/evidence/public-read-gateway-chart/README.md)에 기록했습니다. 실제 home-lab 활성화·AppProject 변경·외부 노출은 후속입니다.
