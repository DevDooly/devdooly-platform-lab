# 외부 보관한 역사적 백업의 파일 검증

2026-10-11 외부에 보관한 네 구성요소의 파일 bytes·metadata 복원, 빈 WAL 조건의 읽기 전용 SQLite 무결성 검사, 분리한 Jenkins 키의 새 비공개 파일 조립을 확인했다. **첫 restore 실패는 그대로 남고 후속 검증만 각각 통과했다.** 현재8-job 백업이나 K3s/Jenkins application 복구 검증은 아니다.

첫 실제 파일 drill에서는 네 구성요소를 인증했고 두 tar의 member 2,688개, regular/hardlink 1,907개 전체 bytes와 numeric owner/mode/mtime을 복원 사본과 비교했다. 그러나 SQLite를 열기 전에 `ONLINE_BACKUP_EXPECTED_NO_WAL_OR_JOURNAL_COMPANIONS`로 실패했다. **원래 restore receipt는 false로 보존했다.**

당시 백업 소스는 SQLite online backup과 quick_check 후 destination 연결을 명시적으로 닫지 않은 채 tar를 만들었다. Python의 `with sqlite3.connect(...)`는 commit/rollback만 수행하고 close하지 않는다. 따라서 sidecar가 없어야 한다는 복원 validator의 가정은 producer가 보장하지 않았다. WAL 존재를 손상으로 해석하거나 파일을 삭제해 성공 처리하지 않았다. [Python connection context](https://docs.python.org/3.10/library/sqlite3.html#how-to-use-the-connection-context-manager), [SQLite WAL의 지속 상태](https://sqlite.org/wal.html#the_wal_file)

| 별도 관측 | 실제 확인 범위 |
| --- | --- |
| Metadata-only inventory | DB 16,408,576 bytes, WAL 존재·0 bytes, SHM 32,768 bytes, rollback journal 부재. archive metadata·전체 SHA와 동일. SQLite 연결0 |
| Empty-WAL 읽기 검사 | 실제 Python3.10.12/SQLite3.37.2, query_only readback1, integrity_check의 유일한 ok, 명시 close. DB/WAL/SHM 전체 identity·SHA 전후 동일 |
| 분리 키 | 이미 인증한 256바이트 key의 metadata·기록된 SHA 재확인. 원래 Jenkins Home의 master.key는 의도적으로 제외되어 부재 유지 |
| 새 별도 파일 조립 | 256바이트 한 파일을 새 root-private 0700 조립 폴더의0600 파일로 복사·fsync. 전체 bytes constant-time 일치와 source identity 불변, 원래 Home 무변경 |

SQLite 후속 검사는 검증된 빈 WAL에만 `mode=ro&immutable=1`을 사용했다. Nonempty WAL이나 rollback journal이 있으면 연결 전에 거부한다. 사용자 데이터 SELECT·행 출력, checkpoint, journal_mode 변경, sidecar 삭제는 하지 않았다. CPU-time30초/address-space256MiB/wall120초로 제한했으며 live K3s DB가 아닌 이미 종료한 파일 drill의 비공개 사본을 읽었다. [SQLite immutable/read-only](https://www.sqlite.org/uri.html#uriimmutable)

Jenkins key는 별도 인증 파일로 보관했다. 후속 조립은 새 별도 폴더에서 파일 한 개만 만들었으며 기존 Home에 넣거나 큰 Home을 다시 복사하지 않았다. Jenkins를 시작하거나 credential 복호화를 검증하지 않았다. 별도 읽기 평가에서 원래 unit은 exit1의 failed 상태이고 process·cgroup이 없음을 확인했다. 원래 unit의 stop/reset과 restore 재실행은 모두0이다. [요약 JSON](summary.json)은 이 독립 결과를 분리하며 key 값·key SHA·SQL·DB 행·실제 경로·주소·UID는 공개하지 않는다.

첫 실패와 후속 좁은 검증은 각각 다른 scope와 전체 receipt SHA로 연결한다. 이 문서의 파일 검증 완료를 원래 실패 성공으로 바꾸거나, ACL/xattr 전체 복원·현재 운영 상태와 동등한 백업·전체 cluster/application restore 성공으로 확대하지 않는다. SQL dump는 인증·파일 bytes만 확인했으며 import하지 않았다. 현재 운영 보존 확인은 별도 S3 운영 증거의 해당 시점 결과와 구분한다.
