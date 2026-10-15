# Spark 종료 지연과 OOM 서명 진단 준비본

상태는 **SOURCE_PREPARED_NOT_RUN**입니다. 이 변경을 실제 Cloud에서 실행하지 않았습니다. 기존 Cloud 6 실행(`2e3f50c446c8cf90fd0e194c92969459f7dbd09e`)은 600초 제한에서 실패했습니다. 종료 전 Spark 컨테이너는 실행 중이었고 Docker의 `OOMKilled`는 false였습니다. 제한된 로그에는 Java `OutOfMemoryError` 서명이 있었습니다. 이 세 관측만으로 Java heap 부족이나 커널 OOM, PID 한도 도달을 확정하지 않습니다.

기존 진행 기록은 두 append, Bronze 검증, Silver 호출, 결과 검증·파일 기록 단계를 지나 `STOP_SESSION`에 진입했다고 남겼습니다. 정상 종료와 최종 결과 수령은 확인되지 않았으므로 전체 Silver 호환성 검증을 통과했다고 표시하지 않습니다. 기존 실패 결과와 소스는 보존합니다.

## 이번 변경

- 이미 수집하는 제한된 private 로그에서 고정 OOM 세부 서명만 분류합니다. Java heap, native thread 생성, direct buffer, metaspace 문구가 정확히 있을 때 해당 enum을 남깁니다. 여러 종류가 보이면 복수 서명, 알려진 문구가 없으면 `OOM_SUBTYPE_UNOBSERVED`입니다. 기존 일반 Java OOM enum도 그대로 남기며, 두 필드 모두 원인 확정이 아닙니다. 오류 메시지·경로·스택·SQL·자격 증명은 공개하지 않습니다.
- 기존 종료 전 진단에서 소유 프로젝트·역할·이미지·제한·네트워크를 통과한 전체 Spark container ID를 다시 확인한 뒤, **고정된 읽기 전용 shell 한 개**로 cgroup v2의 PID·메모리 수치를 읽습니다. 사용자 인수나 경로 입력은 받지 않습니다. `/proc/self/cgroup`이 private cgroup namespace의 root 형태이고 cgroup v2 파일이 있을 때만 값을 받습니다. 수집 후에도 동일한 전체 container ID가 실행 중인지 확인합니다.
- 명령의 각 출력 pipe는 8KiB, 실행 대기는 5초로 제한합니다. 원문과 오류는 기존 private 디렉터리에만 저장합니다. 초과·실패·컨테이너 교체·PID 포화로 shell을 시작하지 못한 경우는 값 없는 `UNOBSERVED`입니다. 진단 실패가 기존 cleanup을 막거나 작업을 다시 접수하지 않습니다. 이 명령을 취소할 때는 해당 Docker CLI 하위 프로세스만 종료합니다.
- 공개 값은 `pids.current/max/events:max`, `memory.current/max/events`의 고정 숫자·boolean·관측 상태뿐입니다. `max`는 무제한 여부와 null로 표현하며, 없는 선택 counter를 0으로 만들지 않습니다. 현재 계획의 PID 제한은 **256**, Spark driver heap은 **1536MiB**, 컨테이너 메모리는 **3GiB**입니다. 실제 읽은 제한과 계획의 일치 여부도 별도 boolean으로 남깁니다.

이 값은 순서대로 읽은 **한 시점 표본**이며 원자적인 전체 snapshot이 아닙니다. events는 해당 cgroup의 누적 counter이며 하위 cgroup 포함 여부는 커널·mount 옵션에 따릅니다. 이전 값과의 차이나 이번 오류에서 증가한 수치를 측정하지 않습니다. 관측에 성공한 표본에는 진단 shell 자체의 PID·메모리 영향이 포함됩니다. 따라서 native-thread 서명과 `pids.events:max > 0`이 함께 있어도 단독 원인으로 결론 내리지 않습니다. Java OOM과 Docker `OOMKilled`, cgroup `oom/oom_kill`은 서로 다른 관측입니다.

## 그대로 유지하는 범위

Spark/Silver 계산·SQL·MERGE·같은 작업의 순차 replay·GZIP table property·`versionAsOf`·JAR/이미지 pins·fixture·CPU·메모리·PID 제한·사용자·네트워크·권한·600초 작업 제한은 바꾸지 않습니다. Bootstrap 전체 bytes, Compose, workflow, 기존 `wait_spark_once`, 성공 결과 검증 및 cleanup 흐름도 유지합니다. 새 partial result 공개나 메모리 증설, 자동 재시도는 없습니다.

공개 artifact는 기존 `.local/spark-ci-public/summary.json` 하나입니다. 로그, inspect, 환경, connection, private 진행 파일, cgroup 원문은 업로드하지 않습니다. 진단과 cleanup은 기존 작업 제한 뒤에 별도의 짧은 시간이 필요합니다. 이는 600초 실행 시간을 늘린다는 의미가 아닙니다.

## 확인 방법과 범위

```sh
python3 -B -m unittest discover -s infra/spark-ci -p 'test_*.py' -v
python3 -B -m unittest discover -s infra/spark-silver -p 'test_*.py' -v
```

오프라인 검증은 정확한 서명·미분류·복수 서명, 안전한 숫자 파싱, 전체 container ID 변경, 종료한 컨테이너, exec 실패·출력 초과, private 출력 분리, 종료 전 수집 순서를 확인합니다. 작은 로컬 Python 하위 프로세스로 pipe 상한을 검증하며 Docker·Spark·JAR·SQL·네트워크는 실행하지 않습니다. 새 Cloud 실행은 별도 명시한 작업으로만 진행하며, 이전 실패를 자동 재실행하지 않습니다.

Linux 문서의 [cgroup v2 PID·메모리 인터페이스](https://docs.kernel.org/admin-guide/cgroup-v2.html)는 한도와 누적 events의 의미를 설명합니다. Java의 [메모리 오류 설명](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html)과 OpenJDK 21의 [direct buffer 할당 코드](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/nio/Bits.java)는 Java OOM이 여러 종류의 할당 실패를 포함함을 뒷받침합니다. 이 준비본은 서명과 자원 관측을 추가할 뿐 실제 오류의 원인이나 해결을 증명하지 않습니다.
