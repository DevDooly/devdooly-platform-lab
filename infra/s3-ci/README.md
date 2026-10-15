# Apache5 격리 Garage 검증 — 명시적 loopback TCP relay 실험

상태: **SOURCE_PREPARED_NOT_RUN**. 이 파생본으로 Docker·GitHub Cloud·미니 PC를 실행하지 않았습니다. Windows 로컬의 순수 검사와 loopback TCP fixture 검사는 실제 MariaDB/Garage 호환성 증거가 아닙니다. 원본 Apache5 소스 세 파일과 기존 다섯 IT의 코드·선택은 바꾸지 않습니다.

## 이전 실패와 새 연결 조건

첫 GitHub run `38797343522` / source `ccb0e1b6f91f5fdaa8bd15ec465908841e209335`는 `NUMERIC_LOOPBACK_ONLY_EPHEMERAL_PORT`로 실패했지만 실제 port map은 미관측이었습니다. 두 번째 run `38799502058` / source `27cb082a198b99117b37f8da44f253491b2a2fd9`의 공개 진단은 **DB와 Garage 모두** 요청한 `HostConfig`의 단일 loopback·빈/0 host port와 실행 중 상태를 확인했으나, 실제 `NetworkSettings.Ports`는 `TARGET_MISSING`이라고 기록했습니다. 두 시도 모두 API 빌드/IT 전에 실패했고 tests/JAR는 null, 자기 소유 컨테이너 세 개는 중지됐습니다. 두 번째 관측은 활성 mapping 부재의 증거이며 Docker `--internal`이 유일한 원인이라는 증거는 아닙니다.

새 profile은 처음부터 `OWNED_INTERNAL_BRIDGE_HOST_LOOPBACK_TCP_RELAYS`입니다. 실제 Docker `--publish`를 제거하고 다음 경로만 사용합니다.

```text
host Java IT → 127.0.0.1:임시포트 → 표준 라이브러리 TCP relay
            → 실제 소유 internal bridge의 DB:3306 / Garage:3900
```

요청한 Docker 포트나 임의 DNS/IP로 fallback하지 않습니다. 외부 연결 가능한 네트워크·전체 인터페이스 bind·운영 endpoint·SSH·production credential을 추가하지 않습니다. Docker 공식 문서는 internal bridge에서 host가 container IP에 직접 접근할 수 있다고 설명합니다. 이 기능을 **새 시도의 실제 TCP positive control**로 확인해야 하며 실패하면 더 넓은 경로를 만들지 않습니다. [Docker internal network](https://docs.docker.com/reference/cli/docker/network/create/#network-internal-mode---internal)

## 소유권과 전송 한도

fresh GitHub run/attempt 이름으로 만든 internal network, 새 DB/meta/data volume 세 개와 컨테이너 세 개만 사용합니다. DB는 1 CPU/1GiB, Garage는 0.5 CPU/512MiB입니다. 기존 짧은 initializer의 network none·0.1 CPU/64MiB, Garage UID1000·read-only root·tmpfs32MiB, 원본 IT의 연결 guard를 유지합니다.

각 relay는 시작 전에, 그리고 **매 연결을 대상에 전달하기 전에** 실제 full CID/name/label/image·전체 Config/HostConfig/mount object·PID/StartedAt·restart0을 대조합니다. container endpoint와 실제 network의 ID/endpoint ID/name/IP/subnet이 일치하고, 소유 local bridge가 Internal=true이며 Docker host publish가 없음을 확인합니다. 대상은 그때 고정한 numeric private IPv4와 DB3306/Garage3900뿐입니다. 후속 read-only inspect는 shared `Attempt.command`의 sequence나 파일을 쓰지 않고, 각 CLI는 최대 2초·응답 8MiB로 제한합니다. 검사 결과 원문은 RAM에만 두며 출력/기록하지 않습니다.

Listener는 `127.0.0.1:0`에만 bind합니다. 서비스별로 최대 active 연결16·전체 연결512·연결당 16MiB·전체 양방향 64MiB·idle60초·연결180초·relay360초입니다. 각 방향의 pending buffer는 64KiB입니다. byte 한도 초과 시도는 최대 1바이트까지 읽어 관측한 뒤 더 전달하지 않고 실패합니다. target connect는 3초 이내입니다. HTTP/SQL payload를 해석하거나 저장/출력하지 않습니다. EOF의 half-close와 양방향 bytes를 그대로 전달합니다. 단순 TCP positive control은 SQL/S3 명령의 성공을 뜻하지 않습니다.

Maven package와 실제 JAR/class 일치 검사를 마친 뒤 relay를 시작하고, 두 경로의 실제 TCP 연결을 확인한 다음 기존 IT를 실행합니다. 전체 시도900초·Maven IT300초·API의 기존 connect/read/attempt/call timeout은 바꾸지 않습니다. 검사/연결이 늦거나 연결·byte·시간 한도를 넘으면 시도를 실패로 남깁니다. 자동 재접수는 없습니다.

## 그대로 검증하는 다섯 IT

- `GarageRawSourceIT`의 일반 메서드 네 개: 실제 SDK PUT·whole GET·HEAD·LIST·등록한 자기 key DELETE, staging/repeat, 손상 원본 유지, DB mark 전 오류 후 재검증입니다. 이 클래스의 DB는 **H2**, 객체 저장소는 실제 Garage입니다.
- `VerifiedResultExportIT.actualResultAndFailuresAreVerifiedBeforeReleaseAndRepeatsCannotReleaseNextJobsSlot`: 새 MariaDB schema `platform_lab_export_it`와 실제 Garage를 사용합니다. 고정12 입력의 결과/실패 whole bytes·크기·SHA·사유·EXPORTED/슬롯 해제·반복 export PUT0·다음 슬롯 보존을 확인합니다.

Java 21 / AWS SDK Apache5 2.55.16과 원본 POM·factory·deadline test 세 파일의 hash, 실제 API JAR의 factory/raw/export class bytes 일치, 정확한 Surefire 다섯 사례/0 failure/error/skip/Asia-Seoul, 자기 DB 행/슬롯0을 요구합니다. 원본 IT teardown은 등록한 UUID 객체와 행을 실패 때도 지울 수 있으므로 이 실행기가 모든 실패 데이터를 보존한다고 주장하지 않습니다. Kafka·지속성·중단 복구 검증은 이번 범위가 아닙니다.

## 종료와 공개 자료

모든 경로에서 등록한 자기 relay listener/socket을 shutdown하고 최대 12초 내 threads join을 확인합니다. 각 relay의 종료 실패는 다음 relay와 기존 exact-ID 컨테이너 TERM 시도를 막지 않습니다. relay 정리 뒤 Docker 정리를 수행하며, 강제 컨테이너 kill·volume 삭제·재생성·자동 재시도는 없습니다. unknown create/command outcome, relay 실패/미종료, 컨테이너 미종료는 성공이 아닙니다. 새 연결 조건에서 통과하려면 두 positive control·정확한5 IT·JAR binding·모든 relay/container 종료가 함께 확인돼야 합니다.

공개 artifact는 기존 `.local/s3-ci-public/summary.json` 하나뿐입니다. source/JAR 해시·고정 scope/profile·테스트 집계·종료 bool·safe failure code·relay 연결/byte 집계와 고정 한도만 추가합니다. 실제 target/listener IP·포트·Docker ID/name·환경·credential·HTTP/SQL bytes·원문 로그는 게시하지 않습니다. DB/S3 credentials와 기존 Docker/Maven 원문 로그는 private `0700`/`0600`에 둡니다. 새 read-only callback의 stdout/stderr는 별도 로그로 남기지 않습니다.

```sh
# 순수 fixture + 실제 로컬 loopback TCP 검사, Docker/서버 접속 없음
python3 -B -m unittest discover -s infra/s3-ci -p 'test_*.py' -v
# 실제 서비스 실행은 별도 fresh GitHub Linux run에만, 기존 optional job 사용
python3 -B infra/s3-ci/run_s3_ci.py
```

로컬 TCP fixture는 test-only로 in-memory target을 자기 loopback server로 대체해 전송·half-close·byte/idle/동시접속 한도·thread 종료를 검증합니다. production에는 그 대체를 켜는 env/CLI 옵션이 없습니다. Docker 소유권·network/IP·동일 process/spec 검사는 별도의 순수 거부 사례로 검증합니다. 이 준비본의 실제 Cloud/Garage 결과는 아직 없습니다.
