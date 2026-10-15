# 객체 참조 보호·격리 Garage GC 검증

운영 전체 참조 수집 **19/19**, 별도 disposable Garage의 자연 GC **11/11** 검사를 실제로 통과했다. 운영 객체는 삭제하지 않았다. [공개 요약](summary.json), [검증 절차와 한계](../../runbooks/object-reference-gc.md), [설계 결정](../../adr/0012-reference-protection-and-isolated-gc.md)을 함께 읽는다.

## 구분한 검증 범위

| 범위 | 현재 상태 | 확인한 범위 |
| --- | --- | --- |
| 순수 객체 참조 계획기 | 오프라인 검증 완료 | 실제 DB를 주장하는 production 계약과 DB 없는 합성 fixture 계약 분리, unknown·pending 보호, production 후보 0개 |
| 2차 운영 전체 DB·S3 참조 수집 | 실제 19/19 통과 | 전체 DB 작업 7개·outbox 14개·slot 1개, LIST 21개 모두 KEEP·후보 0개 |
| 새 disposable Garage의 2차 GC | 실제 11/11 통과 | 정확한 A/C 두 key만 삭제, B/D 전체 bytes 불변, 고유 C 블록 2개 회수·보호 블록 3개 유지 |

계획기에는 삭제 실행기·`apply`·Kubernetes/S3 연결이 없다. production은 `canaries:[]`를 강제하며 DB에 남은 모든 run의 raw/result prefix와 unknown 객체를 보호한다. `EXPORTED` 또는 오래된 객체라는 사실은 삭제 허가가 아니다. 기존 [백업·trial 보존 정책](../../runbooks/retention-resource-budget.md)의 JOB/RAW/EXPORT 보호도 바꾸지 않는다.

오프라인 검사 52개가 통과했다. 계획기 20개, GC guard 12개, 전체 참조 수집기 12개, 2차 GC의 version·격리 회귀 4개, 2차 수집기의 SQL 표현·strict parser 회귀 4개이며 원격 통합 실행 결과와 구분한다. 주요 Python 소스는 3.10 문법 검사를 통과했다.

순수 [계획기 코드](../../../infra/maintenance/object_reference_plan.py)와 [20개 검사](../../../tests/maintenance/test_object_reference_plan.py)는 공개해 재현할 수 있다. 기존 보존 계획기 31개와 합친 공개 maintenance suite 51개도 통과했다. 이 51개에는 앞의 객체 계획기 20개가 포함되므로 오프라인 52개에 다시 더하지 않는다. [CLI와 합성 예시](../../../infra/maintenance/OBJECT_REFERENCE_PLAN.md)를 제공하며 private collector·GC 실행 도구와 실제 host 경로/자격증명은 게시하지 않는다.

## 첫 시도의 실제 실패

첫 disposable Garage는 정확한 고정 이미지에서 `garage v2.4.1 [features: ...]`를 출력했다. 준비 도구가 `2.4.1` 앞의 단어 경계를 잘못 검사해 object PUT·DELETE 전에 중단됐다. **PUT 0회·DELETE 0회**, 새 Garage는 TERM으로 종료됐고 exit 0이었다. 새 named volume 2개와 실패 영수증은 보존했다. 원본·기존 시험 객체를 변경하지 않았다.

첫 소스와 결과를 덮어쓰지 않고 2차 도구·리소스·bucket·key prefix를 모두 분리했다. 정확한 `garage v2.4.1`과 뒤 공백/문자열 끝을 허용하고 `2.4.10`을 거부하는 회귀 검사를 추가했다. 이 준비 실패를 GC 성공 또는 삭제 복구 결과로 세지 않는다.

첫 운영 참조 수집도 S3 LIST 전에 중단됐다. MariaDB가 session read-only 변수의 값을 JSON 내부에 숫자 대신 bare `ON`으로 출력해 strict JSON parser가 거부했다. DB·객체를 변경하지 않았고 첫 소스·실패 결과를 보존했다. 2차 수집기는 SQL에서 해당 값만 `CAST(... AS UNSIGNED)`로 표현하며 parser에서 `ON`을 치환해 복구하지 않는다. 출력 디렉터리도 새로 분리했다.

## 운영 전체 참조 수집의 실제 결과

공개 observation의 최근 작업 목록을 전체 참조 certificate로 사용하지 않는다. 내부 DB의 전체 job/outbox/slot/runtime을 한 `READ ONLY`·`REPEATABLE READ`·consistent snapshot에서 row별 JSON으로 읽고 실제 COUNT와 비교한다. 10,001번째 row와 출력 상한으로 누락·초과를 거부한다. 이 수집기는 V1~V3 schema를 명시적으로 지원한다.

DB transaction을 닫은 뒤 원본 Garage의 Service·Pod UID·selector를 고정해 GET LIST의 모든 페이지를 읽는다. LIST size는 내용 hash가 아니므로 `sha256:null`, `contentVerified:false`로 기록한다. 두 번째 DB snapshot에서 참조·상태·source·runtime 시작이 같아야 하며 상시 loop의 heartbeat/stage 변화만 허용한다. 전후 안정성이 이후의 TOCTOU 위험을 없애지는 않는다.

2026-10-15 10:53:56 UTC에 source `6c5aff948770982dd44c8d44547131b3ccf6ddd9`·V3 schema에서 실제 19/19 검사를 통과했다. 전체 DB 작업 7개·outbox 14개·slot 1개와 LIST 1페이지의 객체 21개(원본 7개·export 14개)를 확인했다. 모두 DB run 참조로 보호했고 unknown 0개·삭제 후보 0개였다. 객체 GET·PUT·DELETE는 각각 0회이며 원본 자원도 변경하지 않았다.

이 결과는 LIST와 참조 보호의 검증이다. [앞선 V2 배포의 21개 전체 GET](../input-v2-deployment/README.md)을 이번 수집의 내용 hash 검사로 다시 세지 않는다. 공개 inventory·plan fingerprint는 [summary](summary.json)에 기록하고 private DB/객체 key 원문은 공개하지 않는다.

## 2차 disposable GC의 실제 결과

운영·기존 부하 시험의 Garage를 재사용하지 않는다. 새 internal network·fresh node/key/bucket·metadata/data volume 2개, RPC loopback과 published port 0개로 격리한다. 고정 Garage 2.4.1, SQLite metadata, RF1, 정수 `block_size=1048576`, compression 1을 사용한다.

| 합성 key 역할 | payload | 정확한 동작 |
| --- | --- | --- |
| A | 2MiB stream S | 등록한 A key만 1회 DELETE |
| B | A와 전체 bytes 동일 | 합성 EXPORTED 참조로 KEEP·whole GET 확인 |
| C | 별도 2MiB stream T | 등록한 C key만 1회 DELETE |
| D | 별도 128KiB stream U | 합성 PENDING 참조로 KEEP·whole GET 확인 |

이 시험에는 애플리케이션 DB가 없다. B/D 보호는 명시적인 `ISOLATED_CANARY_REFERENCE_FIXTURE`이며 실제 DB tombstone/삭제 연동 검증이 아니다. 실제 초기 파일은 S 2개·T 2개·U 1개, 총 5개였다.

DELETE 전 전체 GET·크기·hash, 이후 GET 404와 B/D 불변을 함께 확인했다. 실제 PUT 4회·DELETE 2회·GET 21회를 수행했으며 GET 횟수에는 전체 GET·404 확인·bucket LIST가 포함된다. 원본·기존 시험 Garage의 DELETE는 0회였다.

고유 C DELETE **요청 시작** 이후 마지막 존재 관측은 602.916467초, 두 블록 모두 사라진 첫 관측은 612.963607초였다. 공유 S/U 세 블록과 B/D의 전체 bytes는 유지됐다. 소실한 C 두 파일의 allocated bytes 합계는 **2,105,344 bytes**였다. 이 관측 구간을 정확한 내부 삭제 시각·완료 SLA로 표현하지 않으며 A의 논리 2MiB까지 회수량에 더하지 않는다.

10:59:06 UTC에 11/11 검사를 통과하고 새 Garage를 TERM으로 정상 종료했다. 새 volume 2개와 결과를 보존했으며 첫 준비 실패의 volume 2개도 별도로 남겼다. clock 변경·repair·vacuum·purge·강제 kill fallback은 사용하지 않았다. 회수량은 metadata DB 축소·host 디스크 여유 변화가 아니다.

## 미검증 경계

- 운영 객체 삭제·job tombstone·자동 GC·삭제 중 unknown outcome 복구·동시 writer와의 TOCTOU 해결
- metadata tombstone의 24시간 GC·SQLite/LMDB 파일 축소·RF>1 분산 정합성·고가용성
- 새 Garage의 재시작 후 삭제 상태 보존·장기간 반복 GC·용량/SLA

운영 수집기의 전후 보존과 GC 도구의 기존 Docker identity·start·mount·limit 보존을 각각 확인했다. GC 도구가 운영 객체를 전체 GET하거나 K3s·DB·호스트 전체의 별도 후속 검사를 대신 수행한 것은 아니다. IP·node ID·credential·host 경로·전체 DB/inspect 원문은 공개하지 않는다.

## 격리 GC 종료 후 운영 보존

2026-10-15 11:06:53.155835 UTC에 운영 source `6c5aff94`·schema V3·7개 작업을 다시 확인했습니다. 기존 38개 Docker identity와 별도 시험에서 정상 종료한 정확한 추가 5개만 구분했고 전후 보존 검사 각 19개가 통과했습니다. 원본 7개·export 14개를 **새로 전체 GET 21회** 수행해 크기·SHA·전체 bytes와 checkpoint 및 독립 시나리오 내용까지 대조했습니다. 상위 검사 3/3이 통과했으며 운영 SQL migration·객체 쓰기·원본 리소스 변경은 없었습니다. 이 GET은 앞선 LIST 수집 및 disposable GC의 GET/404/LIST 합계와 별도입니다.
