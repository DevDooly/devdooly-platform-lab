# Apache5와 실제 Garage의 격리 검증 후보

이번 포트 진단 파생 실행기는 준비 상태이며 아직 GitHub Linux에서 실행하지 않았습니다. AWS SDK 2.55.16의 Apache5 전환 후, 기존 실제 IO 테스트를 새 GitHub-hosted runner의 MariaDB 11.8.9·Garage 2.4.1에서 선택합니다. 미니 PC·운영 endpoint·SSH·운영 credentials를 사용하지 않습니다.

기본 `verify`가 통과한 뒤 별도 수동 `run_s3_trial` job으로 실행합니다. 기존 `lab-ci.yml`에 boolean input과 선택 job을 추가하며, 별도 workflow를 만들지 않아 아직 default branch에 없는 새 workflow의 dispatch 문제를 피합니다. Heavy job은 일반 push/PR에서 자동으로 실행하지 않습니다.

## 첫 Garage 시도의 포트 경계 실패와 새 진단 범위

첫 실제 격리 시도는 GitHub run `38797343522`, source `ccb0e1b6f91f5fdaa8bd15ec465908841e209335`에서 `NUMERIC_LOOPBACK_ONLY_EPHEMERAL_PORT`로 실패했습니다. API 빌드와 다섯 IT 실행 전이므로 테스트와 API artifact는 `null`입니다. 생성한 자기 소유 컨테이너 세 개는 모두 정상 중지로 기록됐습니다. 당시 실제 Docker inspect는 공개 artifact에 없으므로, port map의 부재·형태·주소·숫자 중 어느 조건이 실패했는지와 그 원인은 **미관측**입니다. `--internal`이 원인이라고 확정하지 않습니다.

새 파생본은 full ID와 기존 소유권·이미지·네트워크·bind·자원 검사를 통과한 DB/Garage의 **시작 후** inspect에서 다음 두 층을 각각 고정 enum과 boolean으로 투영합니다. 두 서비스의 투영을 먼저 저장한 뒤 기존 actual-port gate를 평가합니다.

- `HostConfig.PortBindings`: 요청 map의 관측 여부, 대상 bind가 하나인지, loopback 요청인지, host port가 비어 있거나 0인지, 추가 요청이 없는지.
- `NetworkSettings.Ports`: 실제 map/대상 항목의 관측 상태, 단일 loopback 주소, 유효한 숫자 포트, 추가 publish의 유무.

`UNOBSERVED`, `MALFORMED`, `TARGET_MISSING`, `TARGET_UNPUBLISHED`, `TARGET_INVALID_COUNT`, `TARGET_MALFORMED`, `SINGLE_BINDING`만 내보냅니다. 미관측/비정상 필드의 검증 boolean은 `false`입니다. raw inspect, 실제 주소·포트·container ID/name·환경·credentials는 공개하지 않습니다. 새 `portBindingDiagnostics`는 연결 성공이나 실제 listener의 건강 상태를 증명하지 않습니다. 이전 실패의 원인을 확인했다는 표시도 하지 않습니다.

**연결 경계는 유지합니다.** 요청한 HostConfig만으로 실제 포트를 추측하거나 fallback하지 않습니다. 활성 numeric loopback mapping이 없으면 기존 코드로 실패하며, `--internal`, `127.0.0.1` publish, 자원 한도, 원본 Apache5 소스 세 파일과 다섯 IT 선택, 종료/unknown-outcome 규칙은 그대로입니다. 이 파생본은 관측 공백을 줄이는 진단 변경이며 실제 Garage 호환성 수정·검증 완료가 아닙니다. 새 실행은 운영자가 별도 fresh GitHub 시도로 수행해야 하며 이전 시도를 자동 재실행하지 않습니다.

Docker의 [port publishing 설명](https://docs.docker.com/engine/network/port-publishing/)은 loopback publish와 gateway mode에 따른 host-port 차이를 설명하고, [internal network 설명](https://docs.docker.com/reference/cli/docker/network/create/#network-internal-mode---internal)은 외부 통신 제한과 host의 직접 접근을 구분합니다. 이것은 설계 참고이며 첫 runner의 Docker 버전/설정을 관측한 증거가 아닙니다.

## 실제 실행 전 확인할 범위

- 새 internal Docker network와 DB/meta/data named volume 세 개, 새 bucket·read/write/nonowner key를 만듭니다. MariaDB·Garage는 각각 1 CPU/1GiB, 0.5 CPU/512MiB입니다. Garage는 UID1000, 읽기 전용 root와 `/tmp` 32MiB를 사용합니다. 짧은 root chown initializer는 network none·0.1 CPU·64MiB이며 새 Garage 두 volume만 바꿉니다. MariaDB는 공식 bootstrap entrypoint를 사용합니다.
- 기존 테스트가 numeric loopback을 요구하므로 두 서비스 포트는 **127.0.0.1에만** 임시 publish합니다. 공개 bind와 추가 published port는 거절합니다. 운영 endpoint guard를 확대하지 않습니다.
- 세 Apache5 변경 파일 SHA와 checkout SHA를 확인하고 API JAR를 빌드합니다. JAR의 실제 Apache5 2.55.16 의존성과 factory/raw/export class bytes가 IT classpath의 compiled bytes와 같은지 전후 비교합니다. 이 검사는 별도 컨테이너 production loop를 실행했다는 뜻이 아닙니다.
- 기존 `GarageRawSourceIT`의 일반 네 메서드를 명시적으로 선택합니다. persistence marker 시험은 선택하지 않아 skip을 성공으로 셈하지 않습니다. 실제 SDK PUT/전체 GET·HEAD·LIST·자신의 key DELETE, staging/repeat, 손상 원본 보존, DB mark 진입 전 오류 후 재검증을 확인합니다. 이 클래스의 DB는 H2이며 MariaDB 증거로 표시하지 않습니다.
- 기존 `VerifiedResultExportIT`의 `actualResultAndFailuresAreVerifiedBeforeReleaseAndRepeatsCannotReleaseNextJobsSlot` 하나를 선택합니다. 이 클래스만 새 MariaDB schema `platform_lab_export_it`를 사용합니다. 원본 업로드·전체 검증, 고정12 처리, 결과·실패 파일 두 개의 실제 PUT·전체 bytes/크기/SHA·실패 이유, EXPORTED/슬롯 해제, 반복 요청의 추가 export PUT 0, 다음 작업 슬롯 보존을 확인합니다.
- 실제 Surefire XML의 정확한 다섯 메서드·5 pass/0 failure/0 error/0 skip·Asia/Seoul을 확인합니다. DB의 테스트 job/outbox/run/outcome과 점유 슬롯도 모두 0이어야 합니다. Kafka·동시성·성능·운영 배포 검증으로 확대하지 않습니다.

## 실패·종료·공개 자료

각 intent/log는 새 private 디렉터리에 O_EXCL로 남깁니다. DB/S3 credentials와 원본 Maven/Docker 로그는 `0600`, 상위 디렉터리는 `0700`입니다. Garage RPC config만 nonroot container가 읽도록 private 디렉터리 안에서 `0444`로 둡니다. S3 key·DB 비밀번호는 config에 넣지 않습니다.

기존 IT의 teardown은 실패 시에도 등록한 UUID 객체와 DB 행만 정리할 수 있습니다. 이 실행기는 그 동작을 바꾸지 않으므로 실패한 객체/행을 반드시 보존한다고 주장하지 않습니다. Docker volume과 private 진단 로그는 남기고, 기록된 full ID/name/label/image/network/bind/limit을 확인한 자기 컨테이너에만 TERM을 보냅니다. 종료되지 않으면 실패로 남기며 강제 kill·재시도·컨테이너/volume 삭제는 하지 않습니다. GitHub가 실행 후 disposable runner 전체를 폐기하는 것과 별개입니다.

공개 artifact는 `.local/s3-ci-public/summary.json` 하나뿐입니다. 실제 source/JAR SHA, 선택 테스트 집계, 제한된 종료·실패 코드만 포함하며 XML·원본 로그·환경·endpoint·bucket/key·credentials·Docker ID는 업로드하지 않습니다. Windows의 이전 느린 read 성공이나 이번 후보 준비만으로 Linux 실패의 원인·해결 완료를 주장하지 않습니다.

```sh
python3 -B -m unittest discover -s infra/s3-ci -p 'test_*.py' -v
# 실행은 SOURCE_COMMIT=${GITHUB_SHA}를 지정한 전용 GitHub Linux job에서만 허용
python3 -B infra/s3-ci/run_s3_ci.py
```
