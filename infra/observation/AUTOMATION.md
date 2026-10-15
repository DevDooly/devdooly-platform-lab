# 상태 수집과 Pages 게시 자동화

작업·export의 실제 배포 관측 자동 게시를 추가하는 선택 기능은 [JOBS_AUTOMATION.md](JOBS_AUTOMATION.md)를 따른다. `jobs_enabled`가 없으면 기존 플랫폼 전용 동작을 유지한다. Pages v2는 선택적 작업 입력과 별도 presence artifact를 사용하며, 아래 기존 플랫폼 검증 이력과 새 기능의 실제 전환 검증을 구분한다.

이 자동화는 **호스트에서 상태를 수집하고 게시를 요청하는 작업**입니다. K3s, Jenkins, Argo CD, API, 웹 서비스를 재시작하거나 배포하지 않습니다.

초기 Ubuntu 격리 환경의 자동화 검사 33개를 통과한 뒤 root 소유 실행 파일·private 설정·systemd unit을 비활성 상태로 설치했습니다. 당시 `systemd-analyze verify`와 `daemon-reload`까지만 완료했고 timer는 disabled·inactive, 전용 Pages 자격증명은 미등록이었습니다. 설치 단계에서 토큰 내용 읽기·host cycle dispatch·timer enable/start를 수행하지 않았다는 이력은 보존합니다.

2026년 10월 12일 KST에 전용 Pages 자격증명을 등록한 뒤 수동 host cycle, 실제 systemd service, timer 최초 자동 실행을 순서대로 확인했습니다. 세 실행 모두 Pages build·deploy success와 전체 공개 JSON 일치를 확인했습니다. timer는 enabled·active이고 첫 자동 수집은 `2026-10-12T01:38:38.790231Z`입니다. 실제 service sandbox에서 `Result=success`·`ExecMainStatus=0`, root 0600 상태 파일과 임시 SA 토큰 정리를 확인했습니다. [실행별 결과와 남은 범위](../../docs/evidence/platform-observation/README.md)를 참고하세요.

`host_cycle.py`는 root 전용 설정으로 10분 수명의 읽기 전용 ServiceAccount 토큰을 발급하고, 고정된 collector를 실행한 뒤 검증된 공개 JSON만 전달합니다. Collector에는 관리자 kubeconfig를 전달하지 않습니다. 임시 SA 토큰은 root 0600 파일로만 만들고 성공·실패와 관계없이 정리합니다. 기존 collector와 JSON 계약은 수정하지 않았습니다.

`pages_uploader.py`는 별도 `~/.config/devdooly-platform-lab/github-pages.token`을 읽어 `DevDooly/devdooly-platform-lab`의 `pages.yml`, `main`에 `platform_snapshot` 입력 하나를 전송합니다. URL, 저장소, workflow, ref는 설정으로 바꿀 수 없습니다. 프록시와 redirect를 사용하지 않으며 TLS 검증을 유지합니다.

공개 출력은 다음 필드 세 개로 제한합니다. `DISPATCHED`는 실행 요청을 접수하고 run ID를 확인했다는 뜻입니다. Pages 배포 성공 여부는 해당 실행 결과와 게시된 파일을 별도로 확인해야 합니다.

```json
{"attemptStatus":"DISPATCHED","runId":123,"runUrl":"https://github.com/DevDooly/devdooly-platform-lab/actions/runs/123"}
```

게시 전 journal에 마지막 snapshot의 canonical SHA-256과 전송 의도를 먼저 기록합니다. 같은 마지막 intent는 timeout이나 불확실한 응답 뒤에도 바로 재전송하지 않습니다. 설치된 uploader에 같은 snapshot·journal을 다시 입력해 `SAME_ATTEMPT_NOT_RETRIED`, 새 run ID 없음과 기존 journal bytes 보존을 실제 확인했습니다. 이 결과의 종료 코드 1은 재게시하지 않았다는 의도한 동작입니다. JSON key 순서는 fingerprint에 영향을 주지 않습니다. 새로운 수집 완료 시각이 있는 다음 주기는 새 intent로 게시할 수 있습니다. 이는 전체 이력에 대한 영구적인 exactly-once 보장이 아닙니다.

첫 timer 실행은 부팅 후 5분 조건이 이미 지나 활성화 직후 발생했습니다. 초기에는 다음 예약만 확인했으며 반복 주기 검증으로 세지 않았습니다. 이후 최초 자동 실행을 포함한 11회가 모두 Pages build·deploy success였고 10개 서비스 완료 간격은 1825.569287~1875.101367초였습니다. 기록된 서비스 완료 범위는 `2026-10-12T01:38:40.510720Z`~`2026-10-12T06:45:29.625204Z`입니다. 수집 완료·Pages 배포 완료 시각과 구분하며 각 회차의 전체 공개 JSON·UI를 모두 비교했다는 뜻은 아닙니다. credential의 실제 scope 조회·만료·회전과 장기간 운영은 별도 확인 범위입니다.

유효한 collector 실패 envelope가 생성되면 이전 `lastSuccess`를 보존한 상태로 게시할 수 있습니다. SA 발급 실패, collector 프로세스 timeout, 새 유효 파일 미생성 등 호스트 단계 오류는 게시하지 않습니다. 이 경우 공개 기록은 그대로 남아 시간이 지나면 UI의 stale 표시로 드러납니다. 이전 파일을 빈 데이터로 덮거나 임의의 성공 상태를 만들지 않습니다.

root 코드·CA·설정·상태·임시 경로는 모든 ancestor의 root 소유권, group/other 쓰기 금지, symlink 금지를 검사합니다. root 실행 코드를 사용자 쓰기 가능한 Git checkout에서 실행하지 않습니다. 게시 자격증명만 root 또는 해당 파일 소유자의 안전한 디렉터리 체인을 허용하며, POSIX에서는 열린 디렉터리 descriptor를 유지하고 `O_NOFOLLOW`로 읽습니다. 비밀값, header, 원문 HTTP 응답, 관리자 출력, 사설 주소를 journal이나 공개 출력에 남기지 않습니다.

오프라인 검증은 [공개 검증 요약](../../docs/evidence/platform-observation/summary.json)에 있습니다. 설치 조건·비활성 unit 검토·수동 검증 절차는 [INSTALL.md](INSTALL.md)를 참고하세요. 초기 Ubuntu 33개 통과 이력은 보존합니다. 정책 검사 2개를 추가한 최종 자동화 35개는 Ubuntu root·일반 사용자 환경에서 각각 35개 통과·제외 0개였고, Windows에서는 34개 통과·POSIX 권한 1개 제외였습니다. 격리된 합성 fixture 검증이며 운영 root 권한 검사는 변경하지 않았습니다. 실제 수동 host cycle·systemd service·timer 반복 게시 11회는 별도 실행 기록으로 구분합니다. credential의 실제 만료·교체와 장기간 운영은 아직 검증하지 않았습니다.

GitHub API `2026-03-10`은 dispatch 성공 시 run ID와 URL을 포함한 `200` 응답을 반환합니다. 이 버전의 요청에는 이전 버전의 `return_run_details` 필드를 넣지 않습니다. 필요 권한은 선택한 한 저장소의 Actions write입니다. [GitHub 공식 REST 문서](https://docs.github.com/en/rest/actions/workflows?apiVersion=2026-03-10#create-a-workflow-dispatch-event)
