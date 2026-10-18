# 검증한 추출 트리 안의 실제 부재만 구분하는 후보

실제 네 번째 실행 `38890545126`은 Linux 73개 검사를 통과한 뒤 PREP에서 `JAR_MANIFEST_CLASSPATH_TARGET_MISSING`를 기록했습니다. 공개 요약 SHA는 `78e07be0b1116224507481de08f15a8792b26277d7734e79b2b6e8883d4dd1af`입니다. 특정 JAR·참조 이름은 여전히 미확인이며, 이 결과를 decoder·원래 workload 성공으로 바꾸지 않습니다. 원래 `5c135` archive·`9a4e` prep·실패 기록은 보존합니다.

[공식 Java 21 JAR 규격](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html#class-path-attribute)은 참조를 context JAR 기준으로 해석하며 찾지 못한 대상을 무시한다고 설명합니다. 이 후보는 그 모든 관대한 동작을 허용하지 않습니다. 기존 안전한 ASCII 상대 `.jar` 문법과 전체 export 경계를 통과하고 실제 부재까지 확인한 참조만 별도로 구분합니다. URL·scheme·`..`·percent·query·fragment·directory alias는 계속 거부합니다.

## 데이터와 검증 흐름

기존 cold 컨테이너는 같은 pinned image ID·never-started·read-only·mount 없음으로 검증합니다. 고정 `docker cp <CID>:/opt/spark/jars -`의 전체 tar를 EOF까지 읽고 JAR 전체 SHA와 manifest CRC를 확인합니다. JAR나 manifest를 다시 쓰거나 경로를 평탄화하지 않습니다. decoder도 같은 image ID의 원래 `/opt/spark/jars/*`를 사용하며 `/opt/decoder` 두 입력 외에는 mount가 없습니다. 이 source 계약으로 상대 경로의 대응을 유지합니다.

기본 두 인수 `_closed_classpath_map(rows, references)`는 그대로이며 누락 참조를 계속 거부합니다. 기본 locked `scan_jar`도 64KiB·nonempty Class-Path 거부를 유지합니다.

unpack 내부의 새 검증은 private parent 0700 아래 `jars` 트리만 읽습니다. 각 디렉터리를 nofollow FD로 열고 bounded `scandir(fd)`로 검사합니다. regular JAR의 정확한 집합은 기존 rows와 같아야 합니다. 원래 tar의 디렉터리 집합에는 empty directory도 포함하며 unpack 마지막에 실제 트리와 일치시킵니다. 디렉터리는 현재 소유자·0755·안정된 identity, 파일은 현재 소유자·0444·single-link·정확한 크기·전체 SHA를 요구합니다. symlink·extra file·다른 타입·case alias·경로 교체를 거부합니다.

모든 알려진 JAR를 다시 whole-SHA·ZIP entry/shadow·전체 manifest 문법/참조로 검사합니다. manifest당 8MiB·검사 한 번의 전체 32MiB·모든 참조 4,096개 한도는 유지합니다. ZIP의 모든 entry payload CRC를 검사한다고 주장하지 않습니다. 기존 검사는 중앙 entry 목록과 manifest CRC를 읽으며, JAR 전체 bytes는 SHA로 검증합니다.

알려진 파일 집합에 없는 참조는 helper 안에서 만든 FD resolver만 처리합니다. 안전한 descendant의 최종 이름 또는 첫 없는 ancestor를 실제 `stat(..., follow_symlinks=False, dir_fd=...)`로 읽고 정확한 `ENOENT`만 부재로 기록합니다. present directory·file ancestor·symlink·case alias·`EACCES`·`ENOTDIR` 등은 부재로 인정하지 않습니다. 부재 직후 parent identity와 bounded child 목록을 다시 확인하고, 전체 검사 끝에서도 모든 held FD와 실제 경로 identity·child 목록을 재확인합니다. caller의 passed boolean이나 missing-name 목록을 authority로 받지 않습니다.

private receipt에는 전체 디렉터리/파일 identity, 원래 참조, PRESENT graph, 실제 `ENOENT` 위치와 manifest 누적 bytes를 포함합니다. 부재 항목은 graph node가 되지 않고 나머지 PRESENT 참조만 원래 strict closure로 검증합니다. 모든 manifest 대상이 존재하거나 필요한 dependency가 해결됐다는 주장은 하지 않습니다.

## javac 전후 연결

prep 변경은 `classpath_inventory`의 반환 digest 한 줄뿐입니다. 기존 JAR rows와 새 전체 트리·부재 receipt를 함께 RAM에서 canonical hash합니다. 원래 prepare의 javac 직전/직후 digest equality가 이 확장된 값을 비교하므로 extra empty directory·새 파일·사라진 부재·identity 변화도 attestation을 막습니다. raw receipt를 새로운 공개 schema에 넣지 않으며 기존 private digest field를 사용합니다.

이는 신뢰한 source caller와 한 번의 통제된 javac child 모델입니다. 같은 UID의 적대적인 host process를 sandbox로 막았다는 주장은 하지 않습니다. 디렉터리 mode를 0555로 바꿔도 같은 UID는 chmod할 수 있으므로 이를 별도 권한 방어로 주장하지 않습니다. 새 helper는 최대 1,024개 디렉터리와 512개 파일의 FD를 보유하고 기존 unpack FD가 함께 열릴 수 있습니다. 낮은 FD 한도에서는 고정 IO 실패로 닫히며 기존 자원 한도를 넓히지 않습니다.

## 고정 실패 코드와 검사 상태

새 고정 코드는 `JAR_CLASSPATH_TREE_REQUIRED`, `JAR_CLASSPATH_TREE_EXACT`, `JAR_CLASSPATH_TREE_CHANGED`, `JAR_CLASSPATH_CASE_ALIAS_REJECTED`, `JAR_CLASSPATH_ABSENCE_UNVERIFIED`, `JAR_CLASSPATH_TREE_IO_FAILED`입니다. 이후 별도 CLI/UI 검토로만 연결하며 임의 exception이나 raw 이름·값·본문은 공개하지 않습니다.

새 archive method 5개와 prep method 2개를 작성했습니다. 기존 archive method 중 두 개는 새 정책에 맞게 기대값만 조정했습니다. 실제 부재 unpack 성공 뒤 기본 strict map은 여전히 거부하는지 확인하고, 큰 manifest는 초기 scan과 독립 트리 재검증 두 번을 읽는지 확인합니다. prep의 기존 shadow 검사 한 개는 확장된 digest hook만 mock하고 shadow 거부가 먼저인지 유지합니다. 나머지 기존 test body는 그대로입니다.

검사는 기본 strict map·전체 참조 개수·boolean 비권한·bounded iterator, 실제 POSIX 트리/empty directory/leaf·ancestor ENOENT, present directory·file ancestor·case alias·symlink·non-ENOENT, extra file·hardlink·whole bytes/mode 변화·새 empty directory, ENOENT 직후 target 생성·root alias를 겨냥합니다. prep 검사는 receipt 변화가 digest에 반영되고 전후 실패가 attestation을 막으며 자기 cold actor만 정리하는 경계를 확인합니다.

root와 독립 peer의 전체 검토 후 허가된 Windows 합성 검사 한 번을 실행했습니다. 실제 archive 24개·prep 8개, 합계 32개 중 24개 통과·8개 POSIX 건너뜀·실패/오류 0개입니다. 실행 전후 네 소스의 전체 hash가 같고 intent·stdout·stderr·result를 보존했습니다. 재실행하거나 CLI 검사를 반복하지 않았습니다. 전체 Linux 예정 수는 기존 73개에 새 7개를 더한 80개이며 아직 미실행입니다. 이 Windows 결과는 POSIX 부재 검증·새 Linux 성공·실제 classpath 호환성·capture 성공을 뜻하지 않습니다.
