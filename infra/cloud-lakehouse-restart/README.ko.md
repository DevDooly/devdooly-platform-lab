# fresh Cloud warehouse의 Trino 정상 재기동 검증 구성

새 GitHub hosted Linux 실행 안에서 같은 PostgreSQL JDBC catalog·Garage warehouse를 두 Trino lifecycle이 순서대로 읽도록 구성했습니다. 과거 Cloud 시험의 ephemeral 저장소를 되살리거나 미니 PC native 시험을 재실행하지 않습니다. Cloud·Docker runtime·workflow dispatch는 아직 실행하지 않았습니다.

2026-10-18 Windows의 표준라이브러리 합성 검사7개는 실제 child exit0으로 끝났습니다. 원 supervisor는 Windows CRLF 줄바꿈을 해석하지 못해 실패 결과를 남겼고, 고정된 기존 로그의 정확한7명·`Ran 7 tests`·`OK`를 별도 후처리해 통과를 확인했습니다. 원 실패 결과와 로그를 보존했으며 검사를 다시 실행하지 않았습니다. 당시 source5개와 frozen16개의 전후 bytes가 같았습니다. 이 결과는 adapter 경계만 검증하며 실제 factory·컨테이너·Cloud warehouse의 재기동 성공을 뜻하지 않습니다.

원 `infra/cloud-lakehouse-ci` runtime 7개·manifest와 Spark base pin을 변경하지 않습니다. 기존 Spark 적재·작은 compaction의 fresh 준비 block을 재사용하고, 원 factory·SELECT 10개·JDBC pointer·정상 TERM·전체 warehouse GET/LIST 계약을 호출합니다. 최초 Trino가 비 OOM·실제 exit 0 또는 143으로 종료된 뒤 그 새 시험이 만든 CID 하나만 force/volume 삭제 없이 제거합니다. survivor의 전체 identity를 이어받은 새 context에서 다른 Trino CID를 한 번 시작합니다. 각 lifecycle의 start는 한 번이며 자동 restart/retry는 없습니다.

첫째·둘째의 Bronze 시점 행 6/12/12와 현재 12, Silver 12(성공7/실패3/중복2), snapshot3·현재 file1·두 JDBC pointer를 비교합니다. 둘째도 정상 종료한 뒤 Python reader로 compaction 뒤 전체20개 object bytes와 과거14개 보존을 확인합니다. PostgreSQL·Garage 프로세스와 중지된 Spark의 state도 유지해야 합니다. 실제 종료 코드를 0으로 정규화하지 않습니다.

합성 검사7개는 handoff 역할·state·initializer 불일치, 기존 volume 재채택, proof 경로 거부와 정상 stop 미확인·CID 불일치·제거 실패·잔류 시 새 context 생성 거부를 다룹니다. Cloud 서비스·환경 준비를 포함하지 않는 회귀 검사 명령은 다음과 같습니다.

```sh
python3 -B -m unittest discover -s infra/cloud-lakehouse-restart -p 'test_lifecycle.py' -v
```

실제 runtime 명령은 main의 수동 opt-in 전용입니다. `SOURCE_ONLY_NOT_RUN`은 아직 실행하지 않은 Cloud runtime의 manifest 상태이며 위 합성 검사 결과와 구분합니다. 코드 검토 후 정확한 manifest SHA를 사용해 실행 여부를 결정합니다.

```sh
python3 -B infra/cloud-lakehouse-restart/run_restart.py \
  --source-manifest-sha256 <reviewed-runtime-manifest-sha256> \
  --ack-fresh-cloud-trino-restart
```

runtime은 저장소의 정확한 checkout·GitHub hosted Linux·main의 수동 dispatch·첫 run attempt만 허용합니다. source/manifest 검증 뒤에만 fresh private/public 경로를 만들며 기존 출력 폴더는 재사용하지 않습니다. workload는 최초 PostgreSQL/Garage start 전부터 하나의600초 clock을 사용하고, PASS에는 cleanup을 포함한 실제 elapsed≤600초가 필요합니다. 실패 시에는 명령별 timeout과 best-effort cleanup을 유지하므로 모든 실패가600초 안에 강제 종료된다는 보장은 없습니다. 재기동 전에는 stage180초+cleanup90초의 여유를 모두 요구합니다. image pull·JAR 검증·build 준비는 workload clock 밖이지만 향후 workflow의 별도 job bound 안에 둡니다. 최소 MemAvailable7GiB·준비 disk8GiB gate와 순차 peak5GiB 설정은 성능·실제 RSS·runner 용량 보장이 아닙니다.

공개 출력은 `.local/cloud-trino-restart-public/summary.json` 한 개입니다. sourceCommit·phase·유한 failure code·검사 flags·실제 exit·행/파일/객체 결과·elapsed·cleanup 상태를 담습니다. CID/PID·cgroup·initializer·volume 이름·secret·raw command/log·전체 object copy는 private 경로에만 남고 artifact로 올리지 않습니다. 실패·불명확 결과는 보존하며 새 start/재시험을 수행하지 않습니다. cleanup은 검증된 자기 CID만 중지하고 volume 삭제·전역 prune·snapshot 만료·object GC는 하지 않습니다. ephemeral runner의 보관 수명, 동시 writer·호스트 장애·HA·지속 부하·운영 가용성을 검증하는 시험이 아닙니다.
