# 객체 참조 보호와 격리 Garage GC

운영의 DB 행·raw·export 객체는 삭제하지 않는다. [실행 근거](../evidence/object-reference-gc/README.md)와 [설계 결정](../adr/0012-reference-protection-and-isolated-gc.md)을 먼저 확인한다. 전체 운영 참조 수집 19/19·별도 disposable Garage 자연 GC 11/11 검사를 실제로 통과했다. 순수 [계획기·공개 합성 예시](../../infra/maintenance/OBJECT_REFERENCE_PLAN.md)는 실행기 없이 재현할 수 있다.

## 운영 참조를 수집하는 경계

순수 계획기의 production 계약은 실제 전체 DB snapshot과 전체 S3 LIST를 입력으로 받지만, 입력의 사실 여부를 자체적으로 조회하지는 않는다. 따라서 별도 root 전용 수집기가 다음 경계를 확인한다. 삭제 실행기와 public POST는 추가하지 않는다.

1. 고정된 원본 namespace·DB schema, Garage Service IP·Pod UID·selector와 현재 source를 확인한다. frozen preservation 도구·계획기의 SHA-256과 root 전용 private 파일 권한도 확인한다.
2. 전체 job/outbox/slot/runtime을 단일 [READ ONLY consistent transaction](https://mariadb.com/docs/server/reference/sql-statements/transactions/start-transaction)에서 읽는다. InnoDB·REPEATABLE READ, 실제 COUNT와 row별 JSON 수, singleton slot/runtime 및 V1~V3 migration을 확인한다. aggregate 문자열의 잘림을 완전한 snapshot으로 취급하지 않는다.
3. transaction을 끝낸 뒤 원본 고정 bucket에 **GET LIST만** 수행한다. 최대 10,000개·100페이지에서 continuation 종료·순환·중복을 검사하며 180초 orchestration guard를 둔다. LIST에서 얻은 size를 whole GET·SHA 검증으로 바꾸어 표시하지 않는다.
4. 두 번째 전체 DB snapshot에서 모든 참조·상태·source·runtime 시작이 같음을 확인한다. heartbeat/stage는 상시 loop 때문에 달라질 수 있지만 heartbeat 퇴행은 거부한다. frozen 원본 보존 capture의 전체 SQL·Pod/PVC/PV/Service/workload, Kafka·Docker·timer/unit·boot/firewall도 비교한다.
5. `PRODUCTION_REFERENCES`, `noApplicationDatabase:false`, `canaries:[]`로 계획한다. 모든 raw/result run prefix와 unknown 객체를 KEEP하고 후보 0개/실행기 없음만 성공으로 기록한다.

운영 수집기는 기존 runtime의 자격증명을 메모리에서 사용하되 HTTP 기능을 GET LIST로 제한한다. 기존 key 자체의 write 권한을 제거하거나 새 read-only key로 교체한 검증은 아니다. Secret 원문은 보고서·stdout에 넣지 않고 identity hash만 private 기록한다.

LIST size의 내용 검증은 `sha256:null`, `contentVerified:false`다. 앞뒤 DB·리소스 안정성 검사만으로 이후 동시 writer와 삭제 사이의 race가 없어지지 않는다. 수집을 통과해도 이후 같은 plan을 실행하는 기능은 없다.

첫 수집은 MariaDB의 session read-only 변수가 JSON 안에서 bare `ON`으로 직렬화돼 LIST 전에 실패했다. 실패 소스·결과를 유지하고 2차 SQL에서만 `CAST(@@session.tx_read_only AS UNSIGNED)`를 사용한다. parser는 잘못된 JSON을 계속 거부하며 출력·영수증도 새 경로로 분리한다.

실제 2차 수집에서는 V3·source `6c5aff948770982dd44c8d44547131b3ccf6ddd9`의 전체 작업 7개·outbox 14개·slot 1개와 LIST 1페이지·객체 21개를 확인했다. 원본 7개·export 14개 모두 보호, unknown 0개·후보 0개였고 객체 GET·PUT·DELETE는 하지 않았다. 10:53:56 UTC의 [별도 근거](../evidence/object-reference-gc/README.md)는 whole GET 검증이나 운영 GC 성공과 구분한다.

## 반드시 보호할 자료

DB job이 남아 있으면 상태·나이와 관계없이 해당 run의 raw/result prefix 전체를 보호한다. `STAGING`, `QUEUED`, `COMPLETED + PENDING`, 점유 slot, PENDING outbox, PAUSED_OPERATOR·UNKNOWN은 보호 사유다. 완료한 EXPORTED·TERMINATED도 삭제 허가가 아니다. 백업·실패 근거가 참조한 자료와 미등록 객체 역시 보호한다.

schema/enum/중복 JSON key·잘못된 참조·미래 clock은 입력을 거부한다. 오래된 inventory·불완전 DB/LIST·모르는 상태는 후보를 억제한다. 이 경계는 [기존 보존 계획기](../../infra/maintenance/README.md)의 JOB/RAW/EXPORT 전부 보호 규칙을 대체하지 않는다.

## 새 disposable Garage의 검증

원래 K3s Garage와 기존 부하·crash 시험 Garage에 DELETE·repair·vacuum을 실행하지 않는다. 새 고정 operation의 internal Docker network·metadata/data named volume 2개와 fresh node/RPC secret/bucket-only credential만 사용한다. 기존 node identity·layout·key를 복제하지 않는다.

새 Garage는 pinned image, UID/GID 1000, read-only root·cap-drop·no-new-privileges, CPU 1·memory 1GiB를 사용한다. RPC는 컨테이너 loopback, S3는 internal network만 사용하며 published host port는 없다. SQLite metadata/RF1/compression 1과 정수 `block_size=1048576`을 명시한다. [v2.4.1 capacity parser](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/util/config.rs)는 정수 byte를 허용하므로 `1M` 같은 문자열 해석에 의존하지 않는다.

Host 중단 기준은 RAM 여유 4GiB·disk 여유 20GiB·free inode 100,000과 OOM/swap 증가 없음이다. 실제 volume identity·canonical 새 경로·symlink 없음·빈 초기 data 상태를 확인한다. 고정한 새 full container ID·label·mount·image·limit가 달라지면 중단한다.

정확한 합성 A/B/C/D 네 key를 한 번씩 PUT하고 전체 GET한다. A/B는 같은 2MiB payload, C는 별도 2MiB, D는 별도 128KiB다. 실제 데이터 블록은 공유 S 2개·고유 T 2개·보호 U 1개를 기대한다. block 이름은 문서 SHA-256이 아닌 [Blake2b-512 앞 32바이트](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/util/data.rs)와 비교한다.

합성 계획기는 `database:null`, `noApplicationDatabase:true`를 명시한다. B의 EXPORTED와 D의 PENDING은 합성 reference fixture이며 실제 DB 사실이 아니다. A/C 두 정확한 key만 후보여야 한다. 별도 수동 실험 도구가 이 두 key를 다시 전체 GET·hash·size로 확인한 뒤 각 1회 DELETE한다. prefix 일괄 삭제·planner 자동 apply는 제공하지 않는다.

## 논리 삭제와 물리 회수의 구분

Garage의 [DeleteObject](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/api/s3/delete.rs)는 delete marker를 기록하며 없는 key에도 204를 반환할 수 있다. 따라서 DELETE 전 실제 whole GET과 뒤의 404를 함께 기록한다. 204·404만으로 disk가 회수됐다고 표현하지 않는다.

[v2.4.1 block GC](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/block/manager.rs)는 refcount가 0이 된 뒤 600초 지연과 610초 resync 예약을 사용한다. 내부 refcount 변경 시각과 API 응답은 같은 시각이 아니다. 실제 시험은 C DELETE **요청 시작**부터 최대 900초, 10초 이하 간격으로 파일 집합을 관측한다. 두 C 블록의 회수가 서로 다른 poll에 보일 수 있으며 보호 S/U 세 블록의 소실·새 unknown 블록은 실패다.

성공은 C 두 블록 파일 소실, 공유 S/U 세 블록 유지, B/D whole GET 불변과 A/C 404를 모두 요구한다. 회수량은 소실 전 C 두 파일의 실제 allocated bytes 합이며 논리 A의 2MiB까지 추가해 세지 않는다. metadata marker·directory·host free-space delta를 섞지 않는다. metadata table의 [24시간 tombstone GC](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/src/table/gc.rs)와 metadata DB 파일 축소는 이 짧은 시험의 대상이 아니다.

실제 2차 검증에서는 PUT 4회·정확한 A/C DELETE 2회와 GET 21회(whole GET·404·LIST 포함)를 수행했다. 초기 블록 5개 중 고유 C의 두 블록은 요청 시작 후 602.916467초에 마지막으로 보였고, 612.963607초의 첫 부재 관측에서 보호 블록 세 개와 B/D 전체 bytes가 유지됐다. 회수된 실제 allocated 합은 2,105,344 bytes였다. 11/11 검사를 통과했으며 이 짧은 한 번의 자연 회수를 운영 GC·장기 용량·정확한 SLA로 확대하지 않는다.

## 실패와 보존

PUT·DELETE intent는 private `0600` 새 영수증에 먼저 기록한다. timeout/unknown outcome은 자동 재실행·재접수·기존 결과 덮어쓰기를 하지 않는다. 자연 GC가 900초 안에 확인되지 않으면 실패/미관측으로 남기며 clock 변경·repair·vacuum·block purge로 성공으로 바꾸지 않는다.

첫 시도는 실제 `garage v2.4.1 [features: ...]`를 version 정규식이 잘못 거부해 PUT·DELETE 전에 실패했다. 기존 소스·실패 영수증·정상 종료한 container·volume 2개를 보존한다. 2차는 실제 출력 회귀 검사를 추가하고 모든 resource/bucket/key 경계를 새로 만든다.

종료는 소유한 정확한 full container ID에 TERM만 보내고 최대 130초 기다린다. 정상 exit 0/143·non-OOM을 요구하며 강제 kill/delete fallback은 없다. 새 Docker named volume은 기존 PVC 정리 계획기의 지원 대상이 아니므로 자동 정리하지 않고 보존한다. 원본 SQL·기존 object whole GET 및 원본 workload/host의 최종 보존 검증은 별도 실제 영수증과 연결한다.

## 운영 GC를 만들기 전 남은 일

영속 job tombstone·삭제 intent, admission/worker 조율, run ID 재사용 금지, outbox/Kafka replay horizon, 백업 의존성과 보존 기한, 삭제 직전 재수집·재계산·identity 조건, 부분 삭제·unknown outcome 복구가 필요하다. 현재 순수 planner나 격리 A/C 실험으로 이 프로토콜을 구현했다고 주장하지 않는다. 운영 객체 삭제, metadata DB 축소, RF>1·HA·장기간 용량 검증은 별도 범위다.
