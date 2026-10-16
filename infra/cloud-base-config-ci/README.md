# PG·Garage 시작 후 설정 읽기 진단 후보

상태: `SOURCE_ONLY_CANDIDATE_NOT_RUN`. 이 새 후보는 아직 컨테이너·CI에서 실행하지 않았습니다. 기존 전체 시험과 좁은 진단의 실패 기록, 소스, runtime manifest는 그대로 보존합니다. 설정이나 guard를 고쳐 통과시키는 실행이 아닙니다.

최신 전체 시험 [38839670201](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38839670201)의 source `8e55f467faee38cee124690af1e80e65f69fc18c`, runtime manifest `eb15f2681632198a29fc76c5b12f3383e56e7caeb8cbeaa8958e25e8ae703d6e`, 공개 summary SHA `eebb19a8bed2a663d8216f3583d95e7d1a9956f6e5d4d279701a615bc441357b`를 별도 이력으로 연결합니다. 263ms에 `SAME_OWN_CONTAINER_FULL_CONFIGURATION`으로 실패했고 command failure는 없었습니다. initializer 종료는 확인했으나 모든 컨테이너의 종료는 미확인입니다. Spark·Trino 시작/성공은 확인하지 못했습니다. 어떤 Config 필드가 바뀌었는지는 이 기록만으로 확인하지 못했습니다.

그 전 좁은 진단 [38837630164](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38837630164)의 summary `c41ce401a46e061bb829902de97b7399cbf20288ad274612d6f8703a4ae8b07d`는 Garage Mounts의 **순서만** 바뀐 관측과 PG Compose start의 `ENV_FILE_MISSING_SIGNATURE`를 남겼습니다. 이번 후보는 그 뒤에 작성한 frozen full runner `bc5d6afb086b6ba32c1fd98586f197c3c41d1533a02bebb9b43d84a286b3c852`의 `make_attempt`를 사용합니다. 이전 두 전체 실패의 유일한 원인을 소급해 입증하지 않습니다.

## 실행 범위와 입력

검토 후 root가 새 feature source에서 **한 번의 새 수동 실행**을 선택할 수 있도록 만든 제안입니다. 이전 Actions 실행을 재시도하지 않습니다. 새 입력은 `run_base_config_readback=true`이며 기존 `run_s3_trial`, `run_spark_trial`, `run_cloud_lakehouse_trial`은 모두 `false`여야 합니다. 다른 flag가 참이면 checkout·이미지 pull·서비스 생성 전 고정 오류로 거부하며 기존 세 trial job도 선택되지 않습니다. 새 입력이 false인 push·수동 실행의 기존 동작은 유지합니다.

```sh
python3 -B -m unittest discover -s infra/cloud-base-config-ci -p 'test_*.py' -v
python3 -B infra/cloud-base-config-ci/run_config_readback.py \
  --self-sha256 <검토된 runner 전체 SHA256> \
  --ack-fresh-base-config-readback
```

실행은 GitHub-hosted Linux만 허용하고 `SOURCE_COMMIT`, `GITHUB_SHA`, checkout HEAD의 일치를 frozen reader로 확인합니다. runner 자체 whole SHA와 고정된 6개 의존 소스의 whole SHA를 먼저 검사합니다. 입력은 저장소의 고정 image·Compose·Garage 설정뿐이며 사용자 endpoint·bucket·key·business fixture를 받지 않습니다.

원래 **5개 서비스 전체 Compose model**을 유지합니다. PG·Garage 서비스는 frozen Cloud8 plan과 같고, 시작하지 않는 Trino의 `env_file: [./trino.env]` 선언을 남기면서 실제 파일은 원래 pre-Garage 시점처럼 생성하지 않습니다. Spark의 새 local tag는 선언만 하며 빌드·pull하지 않습니다. 실제 create/start는 PG와 Garage 두 개, 기존의 동일한 `/bin/chown` initializer 하나뿐입니다. JAR 다운로드·API 빌드·Spark·Trino·reader·fixture 적재·SQL·bucket/key 생성·미니 PC 접속은 없습니다. PG 자체 초기화 SQL과 새 임시 비밀번호 생성은 기존 frozen 절차 그대로입니다.

PG와 Garage pinned image 두 개만 pull합니다. 새 UUID project의 기존 컨테이너·네트워크·volume 부재, 신규 local volume과 자체 internal network를 확인합니다. initializer는 64MiB·0.1 CPU·PID 16·network none이며 full owner/CID/spec 검사 뒤 한 번 실행합니다. PG와 Garage는 각각 0.5 CPU·512MiB·PID 256, read-only rootfs·기존 mount/user/security/network 설정을 유지합니다. 실제 MemAvailable 7GiB gate도 그대로입니다.

## 공개 readback 계약

`.local/cloud-base-config-public/summary.json` 하나만 upload합니다. 새 scope는 `ISOLATED_CLOUD_PG_GARAGE_CONFIG_READBACK_DIAGNOSTIC`, schemaVersion은 1입니다. 이전 좁은 schema와 다른 신규 계약입니다.

- 실제 Docker client/server·Compose 버전, 고정 stage/guard code, command sequence/category/checkRequested/returnCode/timeout/outcome만 공개합니다. `ValueError`·`RuntimeError`의 메시지도 고정 소스에 존재하는 literal code일 때만 허용합니다.
- 동일 role에 대한 전체 signature 6개(`id`, `imageId`, `config`, `host`, `mounts`, `created`)의 변경 boolean을 남깁니다. Mounts signature는 frozen full guard와 동일하게 **각 member의 전체 JSON**을 canonical-sort합니다. 모든 필드·JSON 타입·중복 member를 유지하고 순서만 제거합니다.
- 원본 Mounts 초기 배열은 메모리에만 두고 `mountOrderOnlyChanged`, `mountContentChanged`를 따로 계산합니다. guard 입력·bound signature를 수정하거나 실제 mount 내용을 정규화하지 않습니다.
- `configKnownKeyChanged`와 `hostConfigKnownKeyChanged`는 소스의 고정 allowlist에 있는 필드마다 변경 여부만 공개합니다. `MacAddress`도 변경 여부뿐이며 실제 MAC은 내보내지 않습니다. 알려지지 않은 필드는 이름·값을 내보내지 않고 `configUnknownKeysChanged`·`hostConfigUnknownKeysChanged` boolean으로만 묶습니다. key 부재와 null, JSON 타입 차이, 중첩 내용도 비교합니다.
- 최초 bound signature가 없으면 비교 값은 null입니다. model·Trino 파일 부재 등 검증 flag도 실제 해당 검사가 완료되기 전에는 false입니다. 관측 실패는 고정 code로 남기고 PASS를 막으며 원본 실행 guard는 계속 적용합니다.

Env·자격증명·오류 원문·MAC·command argv·unknown key 이름·경로·개별 설정값·그 hash·컨테이너 ID는 공개하지 않습니다. Docker inspect는 메모리에서만 처리하고, 민감하지 않은 command stdout/stderr도 새 private root에만 저장합니다. 공개 요약은 명시된 필드만 조립하며 raw Mounts baseline이나 bound Config를 직렬화하지 않습니다.

## 시계·실패·정리

이미지 pull과 초기 준비 뒤, 최초 PG/Garage start 전 단일 180초 시계를 한 번 기록합니다. readiness 검사 구간은 최대 30초이고 종료 여유를 유지합니다. 상위 Actions job은 준비를 포함해 15분으로 제한합니다. clock reset·자동 retry·재start·실패 후 guard 완화는 없습니다.

실제 시작은 frozen full runner의 fresh full CID·owner·전체 config·semantic mount·network·image·CPU/memory/PID 검증 뒤 `docker start <정확한 bound CID>` 한 번입니다. PG 시작 뒤 Config가 달라지면 다음 full guard가 실패하고, 진단 boolean만 남깁니다. fixture를 통과시키려고 Config/HostConfig/Mounts 필드를 삭제하거나 MAC을 제외하지 않습니다.

finally의 initializer와 PG/Garage 종료 역시 **현재 frozen guard 그대로**입니다. cleanup inspect에는 별도 최대 5초, TERM에는 `--time=10`/command 최대 15초를 적용합니다. 현재 whole signature가 바뀌면 cleanup 권한을 넓히지 않으며 `ownedContainersStopped=false`와 고정 실패를 보존합니다. 알려지지 않은 컨테이너를 이름만으로 stop하거나 강제 kill/delete하지 않습니다. 모든 자기 자원 정상 종료·readiness·전체 검사·진단 관측과 180초 이내 조건을 모두 만족할 때만 passed입니다. volume은 삭제하지 않고 runner의 ephemeral storage에 남깁니다.

## 로컬 검증

새 synthetic pure test 15개가 actual frozen 의존 소스를 읽어 통과했습니다. 실제 Docker·네트워크·CI는 호출하지 않았습니다. 시작 후 synthetic MAC 변경을 full guard가 계속 거부하는 사례, Config/HostConfig의 알려진·알려지지 않은 중첩/타입/부재 변화, 원문 비밀값 미출력, 전체 Mounts 순서만 변경된 경우와 내용 변경 구분, foreign owner/PID limit 거부, heavy/unknown CID start 차단, 첫 실패와 cleanup 실패 분리, 고정 단일 시계와 원래 full 5-service model을 확인합니다. Windows 최초 test의 intent-file writer 모의 누락으로 생긴 `O_NOFOLLOW` 오류는 test 경계만 고쳤으며 runtime guard를 바꾸지 않았습니다.

이 결과는 실제 Config 변화·원인·새 시작 성공·Spark→Trino 연결·compaction·운영 자료 보존을 입증하지 않습니다. actual readback과 후속 수정은 root의 전체 소스 검토와 별도 새 실행 선택이 필요합니다.
