# worker의 process 진행 상태와 Kubernetes 준비 상태

현재 소스는 **별도 후보 구현**이다. 로컬 Windows에서 기존 157개와 새 19개를 포함한 API verify 176개를 실행했으며 실패·오류 0, POSIX 전용 7개는 skip이었다. 실행한 검사는 169개다. Linux 파일 검증·probe 자원 측정·실제 image 배포는 아직 **NOT_RUN**이다. 이 문서만으로 현재 미니 PC의 readiness 문제가 수정됐다고 표시하지 않는다.

## 목적과 제한

V4의 첫 worker 교체 관측에서는 새 Pod가 Ready였지만 runtime은 아직 이전 STOPPED를 표시했다. 이후 새 실행기의 전체 관측은 정상으로 확인했다. 이 후보는 컨테이너 시작과 실제 owning runner의 준비를 구분한다. [당시 배포 기록](../evidence/admission-v4-deployment/README.md)은 실패한 첫 관측과 CRI 종료 미관측을 그대로 보존한다.

새 progress record는 **해당 process가 마지막 stage 경계에서 journal commit과 소유권 확인을 마쳤다**는 뜻이다. 현재 S3/Kafka의 건강·순간적인 lease 보유·완료 SLA·분산 fencing을 보장하지 않는다. 외부 I/O가 진행 중일 때 독립적인 건강 thread가 기록을 갱신하지 않는다.

## 동작

기존 API·stage·resume와 progress 설정이 없는 run 명령은 파일을 만들지 않는다. worker의 `runtime.worker.progressProbeEnabled`는 기본 false다. true로 설정한 경우에만 고정 `LAB_RUNTIME_PROGRESS_FILE=/tmp/lab-runtime/ready`와 Downward API의 `LAB_RUNTIME_POD_UID`를 전달하고 exec readinessProbe를 붙인다. 임의 파일 경로나 public endpoint를 받지 않는다.

run process는 Linux PID 1이어야 한다. 0700 디렉터리·0600 일반 파일에 다음 고정 필드만 atomic rename으로 쓴다: 버전, instance UUID, PID/start ticks, boot UUID, Pod UID, source SHA, health/stage, boot-clock 기록·만료 시점. 파일은 ephemeral `/tmp` 안에 있고 PVC·다른 컨테이너와 공유하지 않는다. 비밀값·주소·업무 객체 키는 포함하지 않는다.

- 초기화 중에는 STARTING이다. 첫 READY는 클라이언트 준비와 `states.start`를 거쳐 실제 owning thread의 stage/journal commit이 끝난 뒤에만 기록한다.
- probe는 현재 `/proc/1/stat`의 start ticks·boot UUID와 Pod UID·source를 대조한다. 같은 Pod가 다시 실행돼 이전 파일이 남아도 새로운 process의 준비로 사용하지 않는다.
- 서로 다른 JVM의 `System.nanoTime` 원점을 비교하지 않고 Linux `/proc/uptime`을 사용한다. 잘못된 형식·크기·권한·소유자·symlink·미래/만료 기록·다른 process/source는 거부한다.
- stop 요청·pause·lease loss·close에서는 NOT_READY를 단방향으로 고정한다. 후속 stage가 READY를 되살리지 않는다. progress 게시 실패는 처리기를 중단해 고정 RUNTIME_FAILED로 pause하며 자동 resume·재접수를 하지 않는다. 저장 경로 자체를 갱신하거나 지울 수 없는 실패에는 이전 기록의 만료가 최종 방어다.

만료는 마지막 stage 진행 이후 **240초**다. 기존 S3의 API call 30초·attempt 10초·read 8초, 두 export 파일에서 이어지는 유한한 여러 호출을 고려한 후보값이다. 정상 긴 export에서도 거짓 경고가 없는지는 실제 Linux에서 추가로 확인해야 한다. 240초는 작업 처리 시간 보장이 아니다.

## probe와 종료 정책

exec probe는 별도 작은 Java class 경로를 실행한다. Spring Boot JAR·DB·Kafka/S3 client·HTTP listener를 시작하지 않는다. `jdeps`로 의존성이 `java.base`뿐임을 확인했다. API image에는 이 class와 nested class만 별도로 복사한다.

readiness만 10초 주기·5초 timeout·실패 3회/성공 1회로 제안한다. **startupProbe와 livenessProbe는 추가하지 않는다.** readiness 실패로 Kubernetes가 이 process를 강제로 재시작하지 않으며 기존 종료 유예 300초·JVM hook 240초를 유지한다. process가 실제로 종료된 경우 Deployment의 기존 restart 정책은 별개다. operator pause는 재시작으로 해제하지 않는다.

작은 probe JVM의 heap 16MiB·metaspace 24MiB·code cache 16MiB 후보값은 RSS 상한이 아니다. probe도 worker의 같은 768MiB cgroup에 들어간다. 실제 CPU/RSS/PSS·OOM·기동 지연·timeout과 긴 export 중 동작은 아직 측정하지 않았다. 이 비용을 0이라고 표시하지 않는다.

## 검증과 적용 순서

새 테스트는 고정 형식 golden·foreign PID/Pod/source·restart ticks/boot·정확한 만료 경계·startup/pause·잘못된 record를 거부한다. runner 검사는 commit 이후 callback, progress 오류의 pause, lease loss 뒤 READY 금지와 close 전 NOT_READY를 대조한다. POSIX 전용 검사는 실제 owner/mode/symlink·부분 파일과 writer의 terminal latch·갱신 실패를 확인하며 Windows에서는 skip했다.

1. Linux CI에서 기존 API와 새 19개를 모두 skip 없이 확인한다.
2. 새 API image의 OCI digest·source와 probe class를 대조한다. 구형 image에 progress flag를 켜지 않는다.
3. 격리 Linux에서 real PID 1·같은 cgroup·private 파일·정상/오류/재시작·긴 stage와 probe 비용을 측정한다.
4. 실제 적용은 GitOps 값으로만 수행하고 새 Pod의 Ready 시점에 **그 새 process**의 source·startedAt·fresh heartbeat·OCI/CRI를 함께 확인한다. 가능한 경우 교체 전에 종료 watch를 시작하고 미관측을 정상 종료로 추정하지 않는다.
5. 기존 SQL·작업/객체·Kafka·Pod/PVC/Docker·호스트·timer를 전후 대조한다. 이전 실패와 unknown write outcome을 보존하며 자동 접수/repair로 성공을 만들지 않는다.

후보 코드·로컬 테스트와 실제 Linux/운영 증거를 구분하고, 실제 적용 뒤에만 별도 근거로 완료를 기록한다.
