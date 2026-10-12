# 설치와 운영 전환 검증

초기 설치에서는 root 소유 실행 파일·private 설정·unit의 비활성 배치와 `systemd-analyze verify`, `daemon-reload`까지만 완료했습니다. 당시 timer는 disabled·inactive이고 전용 Pages 자격증명은 없었으며 토큰 내용 읽기·host cycle dispatch·timer enable/start를 수행하지 않았습니다. 초기 Ubuntu 격리 환경의 자동화 검사 33개 통과 이후, 정책 검사 2개를 추가한 35개가 root·일반 사용자 환경에서 각각 모두 통과했고 제외 항목은 0개였습니다.

2026년 10월 12일 KST에 전용 Pages 자격증명을 등록해 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 Pages 게시와 전체 공개 JSON 일치를 확인했습니다. 이후 최초 자동 실행을 포함한 11회가 모두 Pages build·deploy success였고 실제 서비스 완료 간격 1825.569287~1875.101367초를 확인했습니다. timer는 enabled·active입니다. 초기 설치·최초 실행·후속 반복 검증을 [공개 검증 기록](../../docs/evidence/platform-observation/README.md)에 구분합니다. 자격증명 scope 조회·만료·회전과 장기간 운영은 별도 검증으로 남아 있습니다.

아래는 새 환경의 설치·수동 검증 절차입니다. 기존 파일이 있다면 동일 bytes·소유권·권한을 확인해 재사용하고, 다르면 덮어쓰지 않고 중단합니다. 전용 자격증명 등록과 실제 host cycle 검증이 끝날 때까지 timer를 활성화하지 않습니다. 별도 Pages 수동 게시 결과는 [공개 검증 기록](../../docs/evidence/platform-observation/README.md)에 구분합니다.

## 선행 조건

- `main`의 `.github/workflows/pages.yml`에 `workflow_dispatch.inputs.platform_snapshot` 문자열 입력과 frozen JSON 계약 검증이 있어야 합니다. 공개 JSON을 그대로 shell 명령에 삽입하지 않고 파일로 안전하게 처리해야 합니다.
- Pages workflow가 입력을 검증해 공개 관측 파일을 생성하고 Pages 배포까지 완료하는 수동 경로를 먼저 검증합니다. Dispatch 접수만으로 배포 성공을 판단하지 않습니다.
- `platform-public-observer` SA와 최소 RBAC를 먼저 적용·검증합니다. 관리자 자격증명은 root의 SA 발급 단계에서만 사용합니다. Collector는 Secrets, logs, exec, nodes 또는 쓰기 권한을 받지 않습니다.
- Ubuntu의 Python 3 표준 라이브러리, systemd, root 소유 K3s 실행 파일, root 0600 kubeconfig, CA 파일이 필요합니다. 서버 주소는 loopback HTTPS를 사용하고 CA 검증을 유지합니다.
- 게시용 fine-grained PAT를 새로 발급합니다. Resource owner는 DevDooly, repository 선택은 `devdooly-platform-lab` 하나, repository permission은 **Actions read/write**만 부여합니다. 만료일을 정하고 기존 commit-status PAT를 재사용하지 않습니다. 파일 형식 검사는 토큰의 실제 scope를 증명하지 않으므로 발급 화면에서 직접 확인합니다.

## 파일 배치

아래는 root가 검토한 저장소 파일을 새 환경에 배치하는 예시입니다. 이번 서버의 비활성 설치는 완료했으며, 기존 파일이 있는 환경에서는 이 복사 명령을 바로 실행하지 않습니다. collector와 contract는 앞 단계에서 검증한 동일 파일을 사용합니다. 코드·설정·CA·K3s·상태·임시 경로의 모든 ancestor가 root 소유이며 group/other 쓰기 불가여야 하고 symlink가 없어야 합니다. `/home/<operator>` 또는 `/tmp` 아래에서 root 코드를 실행하거나 상태를 저장하지 않습니다. K3s 경로가 symlink라면 root 소유 실제 파일의 절대 경로를 설정합니다.

```sh
sudo install -d -o root -g root -m 0755 /opt/devdooly-platform-lab/observation
sudo install -o root -g root -m 0644 /path/to/reviewed/repository/infra/observation/platform_collector.py /opt/devdooly-platform-lab/observation/
sudo install -o root -g root -m 0644 /path/to/reviewed/repository/infra/observation/platform_contract.py /opt/devdooly-platform-lab/observation/
sudo install -o root -g root -m 0644 /path/to/reviewed/repository/infra/observation/pages_uploader.py /opt/devdooly-platform-lab/observation/
sudo install -o root -g root -m 0644 /path/to/reviewed/repository/infra/observation/host_cycle.py /opt/devdooly-platform-lab/observation/
sudo install -d -o root -g root -m 0700 /etc/devdooly-platform-lab
sudo install -d -o root -g root -m 0700 /var/lib/devdooly-platform-observer
sudo install -d -o root -g root -m 0700 /run/devdooly-platform-observer
```

관리자 설정은 `/etc/devdooly-platform-lab/observer.json` root 0600 파일로 만듭니다. 공개 저장소에 실제 사용자·관리자 경로나 주소가 들어간 완성 설정을 저장하지 않습니다. [observer.example.json](observer.example.json)의 placeholder를 개인 서버에 맞춰 작성합니다. `k3s_path`의 파일 이름은 `k3s`여야 합니다. CA를 새로 내려받거나 TLS 검증을 끄지 않습니다.

`/etc/devdooly-platform-lab/observer.env`도 root 0600으로 만들고 다음 경로 변수 한 개만 저장합니다. 토큰, kubeconfig 내용, 서버 주소를 환경변수에 넣지 않습니다.

```text
OBSERVER_CONFIG_FILE=/etc/devdooly-platform-lab/observer.json
```

게시용 PAT는 운영 사용자가 안전한 편집기로 `~/.config/devdooly-platform-lab/github-pages.token`에 저장합니다. `.config`부터 파일까지 symlink를 사용하지 않고, ancestor는 root 또는 해당 사용자 소유이며 group/other 쓰기가 불가해야 합니다. 해당 lab 디렉터리는 0700, token 파일은 0600, hard link는 없어야 합니다. 토큰을 터미널 명령 인수·환경변수·채팅·Git에 넣거나 화면에 출력하지 않습니다. 실제 절대 파일 경로를 root 전용 JSON에만 등록합니다.

## 비활성 unit 검토

```sh
sudo install -o root -g root -m 0644 /path/to/reviewed/repository/infra/observation/platform-observation.service /etc/systemd/system/
sudo install -o root -g root -m 0644 /path/to/reviewed/repository/infra/observation/platform-observation.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/platform-observation.service /etc/systemd/system/platform-observation.timer
sudo systemctl daemon-reload
sudo systemctl is-enabled platform-observation.timer
sudo systemctl is-active platform-observation.timer
```

이 단계는 unit을 등록·검토할 뿐 timer를 enable/start하지 않습니다. 기존 timer가 이미 활성화되어 있다면 중복 설치를 진행하지 말고 운영 상태를 먼저 확인합니다. Template은 부팅 5분 후 첫 실행, 완료 후 30분 간격과 최대 60초 지연을 제안합니다. `Persistent=false`이므로 중단 중 누락된 모든 실행을 한 번에 따라잡지 않습니다.

## 수동 1회 검증 후 운영 전환

설정·전용 자격증명·workflow 입력 검증이 준비된 후 root가 다음 명령으로 한 주기를 실행합니다. 이 명령은 상태 수집과 GitHub Actions 게시 요청만 수행합니다. 앱이나 K3s를 재시작하지 않습니다.

```sh
sudo /usr/bin/python3 -B /opt/devdooly-platform-lab/observation/host_cycle.py --config /etc/devdooly-platform-lab/observer.json
```

확인 항목:

1. 출력 필드가 `attemptStatus`, `runId`, `runUrl` 세 개뿐인지 확인합니다. 비밀값이나 private 응답을 전체 출력해 조사하지 않습니다.
2. `DISPATCHED`와 해당 GitHub run의 Pages 배포 성공을 별도로 확인합니다. 공개 사이트의 JSON 완료 시각, 최근 실패/이전 성공 보존, private 정보 부재를 확인합니다.
3. 상태·journal·lock 파일은 root 0600, 상태·임시 디렉터리는 root 0700인지 확인하고 임시 `sa-*.token` 파일이 남지 않았는지 **내용 출력 없이** 확인합니다.
4. 같은 마지막 intent의 불확실한 응답을 즉시 재전송하지 않는지 확인합니다. 응답을 못 받았다는 이유로 journal을 지워 재전송하지 않습니다. 마지막 intent guard는 전체 이력 deduplication이 아닙니다.
5. `systemd-run`/unit 실행의 sandbox와 실제 Linux 권한을 검증합니다. `CAP_DAC_READ_SEARCH`는 root가 별도 사용자 소유 0600 PAT를 읽기 위해 유지한 권한입니다. root 서비스 자체는 kubeconfig로 SA를 발급할 수 있는 신뢰 경계이며 collector에 그 권한을 전달하지 않습니다.
6. 수동 host cycle에 이어 실제 `platform-observation.service`를 한 번 실행해 sandbox 안에서의 자격증명 읽기·SA 발급·수집·게시 요청·정리를 검증합니다. 서비스의 `Result=success`·`ExecMainStatus=0`과 해당 Pages build·deploy 성공, 전체 공개 JSON 일치를 각각 확인한 뒤 timer를 활성화합니다. oneshot 서비스가 성공 후 inactive 상태인 것은 정상입니다. 초기 설치와 실제 운영 전환 결과는 실행 근거에 구분합니다.

수동 실행 결과를 확인한 뒤 실제 unit과 timer를 다음 순서로 실행합니다. 이미 활성화한 환경에 설치 명령을 반복하지 않습니다.

```sh
sudo systemctl start platform-observation.service
sudo systemctl show platform-observation.service -p Result -p ExecMainStatus
# service가 요청한 Pages build/deploy와 전체 공개 JSON·임시 토큰 정리를 확인한 뒤 진행합니다.
sudo systemctl enable --now platform-observation.timer
sudo systemctl is-enabled platform-observation.timer
sudo systemctl is-active platform-observation.timer
sudo systemctl list-timers platform-observation.timer
```

timer의 첫 자동 trigger도 service 결과와 별도로 Pages 배포·공개 JSON을 확인합니다. 부팅 후 5분이 지난 환경에서는 활성화 직후 실행될 수 있습니다. 다음 실행 예약만으로 실제 간격 검증을 대신하지 않습니다. 이번 환경에서는 최초 자동 실행을 포함한 11회의 Pages build·deploy 결과와 10개 실제 서비스 완료 간격을 별도로 확인했습니다. 이 수치는 장기간 가용성이나 모든 회차의 전체 JSON·UI 비교를 보장하지 않으며 만료·회전은 후속으로 남깁니다.

SA 발급이나 프로세스 실행이 실패하면 새 공개 envelope가 없어 이전 공개 기록이 stale로 남습니다. Collector가 유효한 실패 envelope를 생성한 경우에는 이전 `lastSuccess`를 유지한 최근 실패를 게시합니다. 15초 SA 발급 제한, collector 총 80초 프로세스 제한, GitHub socket timeout 15초를 사용하고 systemd 주기 전체는 150초로 제한합니다. HTTP redirect·자동 retry·관리자 fallback은 사용하지 않습니다.

동결한 collector는 별도의 `.platform-observation.json.lock` 파일을 사용합니다. Collector가 강제 종료되어 이 파일이 남으면 다음 수집이 차단될 수 있습니다. 자동으로 잠금을 지우지 않습니다. 관리자가 collector 프로세스가 없음을 확인한 뒤 그 잠금 파일만 정리하고 수동 검증합니다. snapshot과 dispatch journal을 삭제해 복구하지 않습니다. 일반 timeout 경로에서는 SA 임시 파일을 정리하지만 호스트 전원 종료·SIGKILL 이후에는 수명 10분 토큰의 만료와 runtime 디렉터리 정리 상태도 확인합니다.

## 오프라인 검사

통합 시 Python 파일과 unit을 `infra/observation`, 테스트를 `tests/observation/test_phase3_automation.py`에 배치합니다. 임시 디렉터리의 순수 테스트는 root ancestor 정책을 mock하며, 소유권·symlink 정책은 별도 합성 메타데이터 테스트로 검증합니다. 초기 Ubuntu 33개 통과 이력과 별도로, 최종 35개는 root·일반 사용자에서 각각 POSIX 0600 검사를 포함해 모두 통과·제외 0개였습니다. Windows에서는 35개 중 34개 통과·POSIX 권한 1개 제외였습니다. 일반 사용자 실행을 위한 합성 fixture만 교정했으며 운영 root 권한 검사는 그대로 유지했습니다. 실제 host cycle·systemd service·timer 반복 게시 11회는 합성 검사와 구분해 기록했습니다. 자격증명 만료·회전과 장기간 운영은 별도 검증으로 남아 있습니다.

```sh
python3 -B -m unittest discover -s tests/observation -p 'test_phase3_automation.py' -v
```

이 테스트는 실제 token이나 GitHub dispatch를 사용하지 않습니다. Python 표준 라이브러리 이외 패키지가 필요하지 않습니다.
