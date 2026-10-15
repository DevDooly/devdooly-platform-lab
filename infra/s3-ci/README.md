# Apache5와 실제 Garage의 격리 검증 후보

이 실행기는 준비된 소스이며 아직 GitHub Linux에서 실행하지 않았습니다. AWS SDK 2.55.16의 Apache5 전환 후, 기존 실제 IO 테스트를 새 GitHub-hosted runner의 MariaDB 11.8.9·Garage 2.4.1에서 선택합니다. 미니 PC·운영 endpoint·SSH·운영 credentials를 사용하지 않습니다.

기본 `verify`가 통과한 뒤 별도 수동 `run_s3_trial` job으로 실행합니다. 기존 `lab-ci.yml`에 boolean input과 선택 job을 추가하며, 별도 workflow를 만들지 않아 아직 default branch에 없는 새 workflow의 dispatch 문제를 피합니다. Heavy job은 일반 push/PR에서 자동으로 실행하지 않습니다.

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
