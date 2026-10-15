# 작업 관측 자동 수집과 Pages v2 게시

기존 플랫폼 수집·게시 주기에 `GET /api/jobs/observation`의 실제 배포 기록을 추가한다. 수집기는 작업 실행·파일 export·운영자 재개를 수행하지 않는다. 이 문서는 구현과 운영 전환 절차이며, 실제 서비스 실행·Pages 배포·공개 JSON 비교 결과는 별도 근거에 기록한다.

## 읽기 범위

1. 기존 root host cycle이 수명 10분의 `platform-public-observer` SA token을 0600 임시 파일로 발급한다.
2. 기존 플랫폼 collector가 원래의 관측 envelope를 만든다. 실패 envelope와 `lastSuccess` 보존은 그대로 유지한다.
3. private 설정에 `"jobs_enabled": "true"`가 있으면 같은 SA로 `platform-lab`의 `api` Service 하나를 읽는다. 기존 `services/api get` 권한을 사용하며 새 RBAC, exec, port-forward 권한을 추가하지 않는다.
4. Service의 name·namespace·selector·ClusterIP type·http 8080 port를 확인한다. 이 설치의 K3s Service CIDR인 `10.43.0.0/16`에 속하는 IPv4 ClusterIP만 허용한다. API Service CIDR을 바꾸는 환경은 먼저 이 제한을 별도 검토해야 한다.
5. 그 ClusterIP의 **고정 GET 경로** `/api/jobs/observation`을 조회한다. 애플리케이션 요청에는 SA token·cookie를 보내지 않으며 proxy·redirect를 사용하지 않는다. 외부 공개 포트·프록시·방화벽 변경은 없다.

`job_contract.py`는 최대 32KiB, 환경 `MINI_PC`, 범위 `DEPLOYED_RUNTIME`, 실제 40자리 source commit만 허용한다. 모든 중첩 필드·상태·오류 코드·파일 hash/크기·건수·시각·최근 작업 20개 제한을 검증한다. 격리 시험이나 로컬 응답은 이 자동 게시 입력으로 사용하지 않는다. DB 결과로 계산한 예상 파일 정보와 `exportCompletedAt`의 저장 확인 기록을 그대로 전달하며, 저장소를 다시 조회하거나 현재 프로세스 생존을 확정하지 않는다.

## 보존과 게시 순서

- root 0700 state 디렉터리의 `jobs-observation.json`은 검증된 실제 HTTP 응답만 0600 atomic write한다. 오류 때 이전 파일 bytes·확인 시각을 바꾸지 않는다.
- `jobs-capture.json`은 root 0600의 별도 수집 시도 기록이다. 실패는 고정 `JOB_CAPTURE_FAILED` 코드로만 남기고 raw 응답·주소·예외를 기록하지 않는다.
- 작업 수집 실패·timeout·새 파일 미생성은 유효한 플랫폼 envelope의 게시를 막지 않는다. 그 주기의 `jobs_snapshot` 입력을 생략하면 Pages가 이전 유효 작업 기록을 유지한다. 실패 상태를 새 작업 성공이나 빈 작업 목록으로 대체하지 않는다.
- 공개 작업 v1은 DB snapshot 형식이다. 별도의 작업 collector 실패 envelope는 추가하지 않았다. 공개 화면에는 원래 DB 확인 시각과 오래된 기록·heartbeat 경고가 남으며, 즉시 수집 오류는 private `jobs-capture.json`에서 확인한다.
- uploader는 고정 `pages.yml`의 `main`에 `platform_snapshot`과 선택적 `jobs_snapshot`을 한 번 전송한다. 두 입력 전체의 canonical fingerprint를 게시 intent에 먼저 기록한다. 응답이 불확실해도 같은 마지막 intent를 무조건 재전송하지 않는다. 전체 요청은 65,536 bytes 이하로 제한한다.
- Pages v2는 각각의 마지막 **성공한 실제 deploy attempt**에서 검증한 artifact를 복구한다. 플랫폼은 기존 v1·v2 이력을 모두 지원한다. 작업은 v2 이력의 `job-observation-<run>-a<attempt>` artifact만 사용한다.
- 작업 artifact에는 `publication.json`의 `recordPresent`와, 기록이 있으면 정확한 `jobs.latest.json`을 저장한다. 최초 seed·입력이 없으면 `recordPresent:false`만 저장하고 사이트의 작업 파일은 만들지 않는다. 이 상태는 공개 UI의 미관측 표시로 이어진다.
- 실제 배포 작업 기록이 생긴 후 입력 없는 push·지연된 이전 수집은 마지막 작업 기록을 지우거나 시각을 되돌리지 않는다. 같은 시각의 서로 다른 payload, 누락·만료된 필수 artifact, 신뢰할 수 없는 workflow metadata는 게시를 중단한다. CDN 응답은 복구 기준으로 사용하지 않는다.
- 기록은 게시 시각으로 다시 찍지 않는다. `capturedAt`과 API·실행기 각각의 소스 SHA를 보존한다. Node의 기존 strict job validator를 Pages에서 다시 실행한다. 입력은 event 파일에서 읽으므로 원문 JSON·실패 payload를 workflow console의 env나 shell에 삽입하지 않는다.

## 기존 서버의 전환 순서

1. 이 코드와 `jobs_snapshot` 입력을 지원하는 Pages v2 workflow를 먼저 main에 반영한다. 초기 격리 seed를 운영 배포 관측으로 게시하지 않는다. 실제 배포 관측이 없으면 작업 파일이 없는 Pages 게시도 정상이다.
2. API의 실제 image/source·DB migration·GET 응답을 확인한다. 응답의 환경은 `MINI_PC`, 범위는 `DEPLOYED_RUNTIME`이어야 한다. API·실행기 source SHA와 DB 보존을 따로 검증한다.
3. observer timer의 기존 상태를 기록한다. timer만 잠시 멈추고 실행 중인 oneshot service가 끝났는지 확인한다. K3s·API·worker를 이 전환 때문에 재시작하지 않는다.
4. 기존 root 코드·private 설정을 root 전용 위치에 백업한다. 검토한 동일 commit의 아래 파일을 root 소유·0644로 안전한 `/opt/devdooly-platform-lab/observation` 경로에 함께 교체한다. 상위 디렉터리의 root 소유·group/other 쓰기 금지·symlink 금지를 유지한다.

```text
platform_collector.py    platform_contract.py
host_cycle.py            pages_uploader.py
job_collector.py         job_contract.py
```

5. 기존 root 0600 observer JSON의 다른 값은 유지하고 `"jobs_enabled": "true"` 한 항목만 추가한다. 값은 JSON boolean이 아니라 문자열이다. 설정이 없거나 `"false"`이면 기존 플랫폼 전용 동작을 유지한다. 별도 API URL·token·인증 정보는 추가하지 않는다.
6. 아래 기존 수동 cycle을 한 번 실행한다. 출력은 기존 `attemptStatus`, `runId`, `runUrl` 세 필드다. 이 실행의 `DISPATCHED`는 Pages 배포 성공과 별도로 확인한다.

```sh
sudo /usr/bin/python3 -B /opt/devdooly-platform-lab/observation/host_cycle.py --config /etc/devdooly-platform-lab/observer.json
```

7. root 상태 파일의 소유권·0600과 임시 SA token 정리를 내용 노출 없이 확인한다. 반환한 Pages 실행의 build·deploy 성공, 두 공개 JSON의 실제 수집 시각·전체 허용 필드·source SHA와 private 원본의 일치를 확인한다. 작업 파일에는 저장소 주소·object key·원본·비밀값이 없어야 한다.
8. 기존 `platform-observation.service`를 실제 systemd sandbox에서 한 번 실행해 같은 확인을 반복한다. 원래 활성 상태였던 timer를 복구하고 다음 자동 회차의 실제 게시를 확인한다. 주기는 기존 약 30분이며 이 변경으로 빈도를 늘리지 않는다. 작업 heartbeat의 5분 경고는 게시 간격 사이에도 나타날 수 있는 **기록 나이** 표시다.

service의 기존 150초 제한 안에서 SA 발급 15초, 플랫폼 collector 프로세스 80초, 작업 collector 프로세스 20초, GitHub socket 15초 제한을 사용한다. unit·PAT·RBAC 변경은 필요하지 않다. 새 job collector 코드는 기존 uploader의 import 의존성이므로 `jobs_enabled:false`로 사용하더라도 함께 설치한다. 문제가 생기면 private 설정만 `false`로 되돌려 플랫폼 전용 게시를 유지할 수 있다. 마지막 공개 작업 기록을 임의로 삭제하거나 journal을 지워 재게시하지 않는다.

## 오프라인 검증

```sh
python3 -B -m unittest discover -s tests/observation -p 'test_*.py' -v
```

추가 시험은 strict 계약·고정 Service/GET 경로·인증 분리·실패 때 파일 보존·공동 dispatch와 intent·job timeout 때 플랫폼 게시·v1→v2 artifact 전환·초기 미관측 manifest·지연 기록·충돌·artifact 누락을 검증한다. 실제 mini PC 읽기·Pages 게시와 Linux 권한 검증은 이 합성 시험과 구분한다.
