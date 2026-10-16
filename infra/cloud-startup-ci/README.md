# PG/Garage 시작 명령만 분리하는 Cloud 진단 후보

**SOURCE_ONLY_NOT_RUN**. 이 새 후보는 아직 게시·dispatch·Docker 실행하지 않았습니다. 기존 Cloud9 runtime과 첫 두 실패 artifact를 바꾸거나 재실행하지 않습니다. 미니 PC·운영 namespace·운영 DB·원본 객체에 접근하지 않습니다.

실제 두 번째 실패는 source `d4bd48aaa5bb68154970600a5c50ac0e3fc5ee54`, Actions run `38833863253`, 요약 SHA `570805bc765ac6437f07f546b3b77a153c9cb91ea097c265ba91ec22d3323aac`입니다. sequence 28의 `COMPOSE_START_POSTGRES`가 timeout 없이 exit 1이었고, cleanup의 마지막 sequence 35 container inspect는 exit 0 뒤 validation이 실패했습니다. 당시 원문 stderr/State.Error와 정확한 cleanup guard는 공개되지 않아 **원인은 미확정**입니다. 첫 요약 SHA `a42f34aba82140189f08f530574b10c6911a5ae229ff13ebca63b2b82b3ffe21`도 그대로 유지합니다.

## 달라지는 범위

새 driver는 검토된 `run_trial9.py` SHA `5f601685a72ccd75f9e45c425ed8310b2c1d33931d3fd19c9a468a720feecd03`의 `make_attempt`와 원래 command·전체 configuration guard를 import합니다. Docker client/server·Compose의 실제 version, 고정 stderr/`State.Error` signature, literal validation code, `id/imageId/config/host/mounts/created` 변경 boolean만 덧붙입니다. secret·argv·URL·path·오류 message·Env 원문을 공개하지 않습니다. 알 수 없는 오류는 `UNOBSERVED_VALIDATION_FAILURE`로 남깁니다.

`ValueError`와 `RuntimeError`도 **정확한 type이고 pinned source의 literal require code와 문자열 전체가 같을 때만** 공개합니다. 대문자 형식이라는 이유만으로 exception message를 공개하지 않습니다. stderr signature는 원인 확정이 아니라 제한된 텍스트가 관측됐다는 뜻입니다. Docker state 원문은 RAM에서 검사하고 공개 값은 고정 enum·boolean·exit code로 제한합니다.

optional 진단 projection의 오류가 원래 command 반환이나 guard를 덮지 않도록 따로 기록합니다. projection 오류가 있으면 새 진단 PASS는 불가하지만, 원래 cleanup guard를 완화하거나 우회하지 않습니다. 첫 primary failure와 cleanup failure는 별도 배열로 남깁니다. `check=False` readiness의 비정상 종료를 그 자체만으로 fatal command로 승격하지 않습니다.

## 그대로 유지하는 모델과 실제 실행 요청

- 원래 `compose_trial9.plan`의 **5-service 전체 모델**을 그대로 생성합니다. PG·Garage service의 image·limits·mount·network·capability·초기화 SQL/설정이 원래와 같습니다.
- Trino의 `env_file: ./trino.env` 선언을 유지하고 파일은 원래 PG/Garage 시작 이전 시점과 같이 **만들지 않습니다**. placeholder로 parse failure를 숨기지 않습니다. Trino config/reader/Silver secret 파일도 만들지 않습니다.
- 새 UUID project의 postgres·garage **두 service만** `create --no-build`하고 각 `start`를 한 번 요청합니다. Spark local image tag는 모델에 남지만 빌드하거나 pull하지 않습니다. Trino/Spark base image도 pull하지 않습니다. Compose create/start의 heavy role 요청은 subprocess 전에 거부합니다. 전체 모델에 dependencies가 없다는 순수 검사도 수행합니다.
- 같은 PostgreSQL image의 `/bin/chown` initializer를 network none, CPU 0.1·memory 64Mi·PID 16으로 한 번 실행해 새 Garage metadata/data volume만 1000:1000으로 준비합니다. volume identity와 initializer guard는 원래 구현을 그대로 사용합니다.
- PG와 Garage는 각각 CPU 0.5·memory 512Mi·PID 256, read-only rootfs·restart no·internal network·host port 없음입니다. readiness는 `pg_isready`와 Garage `node id --quiet`뿐입니다. node ID는 공개하지 않습니다.
- application/JAR/vendor/업무 fixture·Spark·Trino·reader·bucket/key 생성·layout 변경·S3 operation·Iceberg mutation은 호출하지 않습니다. 초기 PostgreSQL의 빈 JDBC catalog table 생성은 기존 `pg_init` fixture와 같으며 새 DB에만 수행됩니다.

## 시간·정리와 성공 범위

image pull 두 번과 fixture/create/initializer 준비는 원래처럼 시작 clock 전입니다. 준비 command는 기본 60초, image pull은 각 120초입니다. 같은 MemAvailable 7GiB 확인과 initializer exit 0 후 **새 진단 전용 clock 180초를 한 번** 시작합니다. 기존 600초 workload clock을 연장·재사용하거나 reset하지 않습니다. 시작된 clock의 결과 시각에는 정리 시간도 포함해 PASS가 180초 이내인지 확인합니다.

cleanup은 clock 부족과 관계없이 원래 safety-stop 경계의 read 5초/자기 container TERM 10초 요청·CLI 15초 상한을 사용합니다. 알려진 두 role와 initializer만 존재하는 경로에서 cleanup command 상한 합은 100초입니다. workflow 전체 상한은 준비를 포함해 30분입니다. runner/daemon 단절이나 job 강제 종료 뒤 정리가 됐다고 추정하지 않습니다.

정리 전에 원래 full signature/owner/image/network/mount/limits를 다시 확인합니다. 변화가 있으면 fixed code와 변경 boolean을 남기고 **자동 force/kill/guard 완화 없이** cleanup FAILED_OR_UNOBSERVED로 남깁니다. 모든 stop은 자기 full CID에만 요청하고 정상 비활성 readback을 확인합니다. container·volume·network는 삭제하지 않으며 GitHub runner storage의 휘발성을 명시합니다. 원래 실패의 정리 미확인 상태도 이 새 시도의 결과로 덮어쓰지 않습니다.

`passed`는 같은 두 base 서비스의 readiness와 정확한 자기 정리·진단 완료를 뜻합니다. 모델과 env-file 부재 확인 flag는 해당 guard를 실제로 통과한 뒤에만 true입니다. 조기 version/pull 실패 시 false로 유지합니다. `sparkTrinoReaderStartRequested:false` 등은 코드상 비요청 범위이며 운영 프로세스 전체 부재나 사용하지 않은 이미지의 물리 cache 부재를 주장하지 않습니다. compaction·Spark/Silver·Trino SQL·실시간 가용성·SLA·기존 실패의 단일 원인을 검증하지 않습니다.

## 수동 workflow 제안

동봉 `lab-ci.yml`은 현재 feature의 전체 workflow bytes를 기반으로 한 **미적용 제안**입니다. `run_cloud_startup_probe`만 true로 선택합니다. 기존 `run_s3_trial`, `run_spark_trial`, `run_cloud_lakehouse_trial`은 모두 false여야 합니다.

startup=true이면 일반 verify와 기존 세 heavy trial을 제외합니다. 새 job의 첫 step에서 조합을 검증하며 다른 true가 있으면 checkout·서비스 생성 전에 고정 코드로 실패합니다. startup=false 또는 입력이 없는 push/default dispatch/기존 trial 경로는 기존 job 본문과 조건을 그대로 유지합니다. 새 job은 8개 순수 검사 후 hash 고정된 driver 한 번만 호출하고, **새 공개 summary.json 한 파일만** upload합니다. private 폴더·dump·config·raw log는 upload하지 않습니다.

실행 후보 명령은 workflow 안에 실제 self SHA와 함께 고정됩니다. source commit은 실제 `GITHUB_SHA`와 checkout HEAD를 대조하며, 기존 runtime/helper 6개 파일의 전체 SHA를 검사합니다. 원본 helper의 `main`, vendor, heavy workload는 호출하지 않습니다.

## 소스 검증

순수 검사는 pinned 함수 import·합성 inspect metadata·mock subprocess만 사용합니다. Docker·registry·DB·SSH·MiniPC에 연결하지 않습니다.

```sh
python3 -B -m unittest discover -s infra/cloud-startup-ci -p 'test_*.py' -v
```

8개 검사는 실제 frozen full signature/foreign owner/PID limits 거부, whole 5-service 모델·early flags, `ValueError`/secret exception 구분, private args·stderr·TimeoutExpired.cmd 차단, expected nonzero와 checked failure 구분, heavy 요청의 사전 거부, optional 진단 실패의 guard 비변경, 고정 clock 만료를 포함합니다. 현재 C-only 후보에서 Windows의 실제 순수 8개가 실패·오류·skip 0으로 통과했습니다. 이것은 Linux Docker 시작 결과가 아닙니다.
