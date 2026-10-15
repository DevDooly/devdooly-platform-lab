# Worker readiness: Linux 회귀와 격리 디렉터리 진단

이 문서는 첫 진단 당시 기록입니다. 이후 수정 이미지의 적용·교체·재시도는 [후속 검증](CORRECTED_IMAGE.md)에서 확인합니다.

2026-10-15 14:10:59 UTC까지 확인한 기록입니다. **Linux CI는 API 180개·독립 Java 예제 20개, 총 200개를 skip 없이 통과했습니다. 첫 격리 canary는 0개 사례에서 실패했고, 같은 이전 이미지의 별도 진단에서 SGID 상속과 생성자 거부 경로를 직접 재현했습니다.** 수정 이미지의 canary·실제 GitOps Ready 전환·worker 재시작 검증은 아직 대기입니다. 운영 worker에 readiness를 적용한 결과로 표시하지 않습니다.

## 첫 canary와 이후 진단을 구분합니다

첫 canary의 소스는 `8521d755be223f1f3114859d5f32578983bec98a`입니다. 익명 registry 조회와 K3s cache의 index→amd64 manifest→config→CRI 연결을 확인했고, 실제 OCI의 별도 probe class와 같은 OCI app.jar 내부 class가 바이트 단위로 일치했습니다. Java classfile major는 65, probe class SHA-256은 `868d5321ee3a451ecdc3bb9613d68e8803b0cfd82eeabb75a1834b271088cbe4`입니다. 이 단계의 검사 5/5와 전후 운영 보존 검사 각 21/21을 통과했습니다. CI JAR의 class와 같다고 가정하지 않았습니다.

2026-10-15T13:41:00.748064Z에 저장된 첫 canary 결과는 **FAILED**입니다. 프로세스는 exit 1로 끝났고, 실제 사례 목록은 비어 있었습니다. 로그는 `CANARY_EXECUTION_FAILED`라는 일반 오류만 남겼으며 생성자 예외 class나 stack을 기록하지 않았습니다. probe class 해시는 실제 이미지와 로그에서 확인했지만, 실패한 canary 결과의 완료 필드는 null이었습니다. 이 실패 결과를 통과로 바꾸거나 10개 사례를 실행했다고 표시하지 않습니다.

종료 후 kubelet이 해당 임시 볼륨을 제거해 첫 컨테이너의 디렉터리 권한을 사후 확인할 수 없었습니다. 따라서 그 로그만으로 SGID를 원인으로 확정하지 않았습니다. 실패 결과·Pod/Job/ConfigMap 선언·로그를 먼저 보관한 뒤, 종료한 자체 Pod와 비활성 Job·더 이상 참조하지 않는 자체 class ConfigMap만 UID와 resourceVersion을 대조해 정리했습니다. namespace·quota·default-deny 정책은 유지했습니다. 이 단계에서 기존 객체 21개를 전체 GET했습니다.

## 같은 이전 이미지로 직접 재현한 경로

2026-10-15T14:06:58.485014Z의 별도 격리 진단은 UID 10001·동일 fsGroup/emptyDir 설정·동일 이전 이미지 안에서 같은 Java 소스로 별도 컴파일한 writer 진단 payload를 사용했습니다. 이 writer payload와 OCI app.jar writer class의 바이트 일치는 확인하지 않았습니다. DB·lease·Kafka·S3 client를 시작하지 않았고 운영 health 파일을 건드리지 않았습니다.

- 부모 임시 디렉터리의 SGID 비트를 관측했습니다.
- `0700`을 요청한 새 디렉터리의 실제 mode가 `02700`인 것을 관측했습니다. 부모 권한은 전후 같았습니다.
- 실제 `LocalRuntimeProgress` 생성자가 `RuntimeReadyProbe.privateDirectory`에서 `IllegalArgumentException`으로 거부되는 자체 stack frame을 관측했습니다.
- health record는 만들지 않았으며, 진단 자체가 권한을 고치지도 않았습니다.

이 재현은 Linux에서 부모 SGID 비트가 새 디렉터리에도 상속된다는 [Linux man-pages의 mkdir(2) 설명](https://man7.org/linux/man-pages/man2/mkdir.2.html)과 일치합니다. 새 디렉터리의 SGID 상속과 엄격한 `0700` 검사의 충돌을 직접 확인한 결과입니다. 첫 실패 컨테이너에서 누락된 예외 stack을 복원한 기록은 아닙니다.

진단 검사 3/3을 통과했고 기존 7개 작업·업무 SQL·객체 참조 21개와 전역 리소스 식별자를 보존했습니다. 14:08:37.134114Z의 후속 정리도 3/3을 통과했습니다. 종료한 자체 진단 Pod/Job/ConfigMap의 근거를 보관하고 UID로 정리했으며, 같은 namespace·quota·정책을 유지했습니다. 남은 Pod/Job/Secret/PVC/Service는 각각 0개입니다. 기존 **동일한 객체 21개**를 다시 전체 GET해 앞선 사본과 바이트 단위로 비교했습니다. 두 번의 조회를 42개 서로 다른 객체로 세지 않습니다.

## 수정 범위와 Linux CI

수정 소스는 [PR #43](https://github.com/DevDooly/devdooly-platform-lab/pull/43)의 `6a5305b670dd53f9b56a9638b64917575a232737`입니다. 디렉터리가 없어서 **이번 생성자가 새 inode를 만드는 데 성공한 경우에만** 소유자·파일 식별자·mode를 확인하고 상속된 SGID를 제거합니다. 기존 `02700`·group-writable 디렉터리나 symlink의 권한을 수리하지 않으며, 기존 엄격한 검사를 유지합니다.

[실제 Linux Actions 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38746521878)의 JUnit XML을 대조했습니다. API 180개·독립 예제 20개는 실패·오류·skip 모두 0입니다. writer suite 9개 중 다음 Linux 회귀 4개가 실제 실행됐습니다.

| 회귀 사례 | 확인 범위 |
| --- | --- |
| `newlyCreatedPrivateDirectoryClearsInheritedSetgid` | SGID 부모에서 새 디렉터리 생성·0700 정리, 부모 불변 |
| `existingSetgidDirectoryIsRejectedWithoutRepair` | 기존 02700을 거부하고 그대로 보존 |
| `existingGroupWritableDirectoryIsRejectedWithoutRepair` | 기존 group-writable 권한을 거부하고 그대로 보존 |
| `existingSymlinkCannotRepairTargetPermissions` | symlink를 거부하고 대상 권한 보존 |

최초 Windows 후보의 API 176개 중 실행 169개·POSIX skip 7개는 과거 조건입니다. 위 200개는 수정 후보 소스의 **Linux CI 합계**이며, 운영 배포나 canary 성공 횟수가 아닙니다.

실제 격리 진단과 정리를 마친 뒤 14:10:59 UTC에 PR #43을 main `3e0d85be2f529026cb44812602e31c0e18797b45`로 반영했습니다. 위 JUnit 200개는 branch 소스 `6a5305b6`의 검증입니다. 새 main의 CI·Jenkins·이미지 게시는 이 기록에서 대기이며 branch 성공으로 대신하지 않습니다.

## 남은 검증

| 단계 | 이 기록의 상태 |
| --- | --- |
| 수정 후보 Linux CI와 SGID 회귀 | PASS |
| 첫 이미지의 별도 격리 진단·종료 리소스 정리 | PASS |
| 첫 synthetic canary | FAILED, 0개 사례 |
| 수정 이미지 게시·actual OCI class 대조 | PENDING |
| 수정 이미지의 격리 canary·probe CPU/RSS/PSS·지연 | PENDING |
| API·웹→worker 실제 GitOps 전환과 관측한 NotReady→Ready | PENDING |
| 새 worker의 owning stage commit·RUNNING·fresh heartbeat·동일 process 확인 | PENDING |
| 실제 worker 재시작과 같은 ID의 읽기 전용 재시도 | PENDING |

기존 운영 소스 `202ab6806130cfb37e8829ce7d52c89990d8a54a`·schema V4와 7개 EXPORTED 작업은 이 진단 동안 유지됐습니다. 기존 [V4 전환 기록](../admission-v4-deployment/README.md), [readiness 설계·적용 조건](../../runbooks/worker-readiness.md), [공개 요약](summary.json)을 함께 확인합니다. readiness는 마지막 owning-stage 진행 기록의 신선도를 검사하며 DB/S3/Kafka의 지속적인 건강·분산 fencing·처리 용량·SLA를 보장하지 않습니다. startup/liveness나 강제 재시작을 추가한 결과도 아닙니다.
