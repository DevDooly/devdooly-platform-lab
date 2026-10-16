# Iceberg capture 공개 요약 schema 2 후보

현재는 C-only 소스 후보이며 새 Cloud 실행 결과가 아닙니다. 변경 대상은 `run_capture.py`와 그 검사 파일뿐입니다. prep·archive·bounded process·guard·원래 producer·SQL·자원 한도·600초 clock은 변경하지 않습니다. 첫 실행 `38876152951`의 schema 1 원문은 Linux 56개 통과와 `PREP_NOT_VERIFIED` 실패 기록으로 그대로 보존합니다. 새 후보의 Windows 합성 검사나 다음 Linux 결과를 그 실행에 소급하지 않습니다.

기존 공개 필드와 PASS 조건을 유지하고 `schemaVersion`을 2로 바꾸며, 다음 네 키의 `diagnostic`을 항상 추가합니다.

| 키 | 계약 |
| --- | --- |
| `stageAttempted` | CLI의 `PREP`·`COMPOSITE`·`SUMMARY`, 또는 같은 소스의 정확한 composite receipt에서 관측한 고정 `lastStage`. 시도한 단계이며 완료를 뜻하지 않습니다. |
| `failureCode` | 성공이면 null. 실패에서 CLI가 잡은 정확한 `ValueError`의 단일 문자열 인자가 검토된 literal 집합에 있을 때만 그 고정 코드이며, 나머지는 `UNKNOWN`입니다. 임의 uppercase 메시지나 반환된 private composite failureCode는 공개하지 않습니다. |
| `lastPrepChild` | 관측이 없거나 형식·권한·안정성 검증에 실패하면 null. 유효한 고정 이름 receipt 중 `startedMonotonic`이 가장 늦은 한 건만 작은 필드로 투영합니다. 동률도 null입니다. 최초 실패가 아니라 마지막으로 관측한 작업이며 정리 명령일 수 있습니다. |
| `prepCleanup` | 유효한 같은 실행 `prep-result.private.json`이 없으면 null. 있으면 `knownColdCid`, `coldIdentityBound`, `coldRemovalAttempted`, `coldRemovedAndAbsent` 네 boolean만 담습니다. known/bound=false는 Docker 자원이 없다는 증거가 아닙니다. |

`lastPrepChild`의 exact 키는 `name`, `class`, `outcome`, `returnCode`, `stdoutBytes`, `stderrBytes`, `timedOut`, `childStarted`, `childReaped`입니다. `childStarted`와 `childReaped`는 해당 소유 명령의 Popen/CLI 프로세스 관측이며 Docker container의 시작·종료를 뜻하지 않습니다. returnCode는 관측되지 않으면 null이고, 두 byte 수는 실제 받아들인 prefix의 크기입니다. 전체 provider 출력을 다 받았거나 EOF를 확인했다는 공개 주장이 아닙니다.

이름은 frozen prep의 16개 label로 제한합니다. class는 `JAVA_VERSION`, `JAVAC_VERSION`, `IMAGE_PULL`, `IMAGE_INSPECT`, `COLD_CREATE`, `COLD_INSPECT`, `CLASSPATH_EXPORT`, `ICEBERG_DOWNLOAD`, `MAIN_COMPILE`, `COLD_REMOVE`, `COLD_ABSENCE`입니다. outcome은 `START_FAILED`, `EXITED_ZERO`, `EXITED_NONZERO`, `TIMED_OUT`, `STDOUT_LIMIT_EXCEEDED`, `STDERR_LIMIT_EXCEEDED`, `OWN_CHILD_REAP_UNVERIFIED`, `OUTPUT_OR_CONTROL_IO_FAILED`, `PRIVATE_OUTPUT_IO_UNVERIFIED`, `PREP_CUTOFF_EXCEEDED`로 제한합니다. 정확한 label 매핑과 129개 검토 코드 literal은 새 CLI의 고정 상수이며 실행 중 다른 파일에서 목록을 확장하지 않습니다.

composite 단계는 `PREP`, `ORIGINAL_MAIN`, `PRODUCER_PROOFS`, `WRITERS_BEFORE`, `LOAD_CLOSED_COPIES`, `DECODER`, `WRITERS_AFTER`, `NORMALIZE`, `COMPLETED`입니다. 전체 receipt key/type/source와 authority SHA가 일치할 때만 사용합니다. 누락·오류 때 CLI의 고정 단계로 남으며 private failureCode를 복사하지 않습니다.

metadata reader는 이번 CLI가 새로 선택한 canonical `.local/closed-copy-prep-<nonce>`만 읽습니다. `.local`과 prep root의 현재 소유자·0700·held directory FD를 확인하며, 고정 파일명에 대해 nofollow·일반 파일·single link·현재 소유자·0600·16KiB 상한·lstat/fstat 전후 identity·전체 길이를 확인합니다. intent의 source commit·prep SHA·decoder SHA·기존 lock SHA·600초/40초 예산을 묶습니다. `argvSha256`와 stream SHA는 private receipt의 형식 검증에만 쓰고 공개하지 않습니다. stdout/stderr 파일·argv·환경·CID·PID·경로·provider 예외 원문·private proof를 반환하지 않습니다.

diagnostic 읽기 실패는 최초에 잡은 literal 실패 코드를 바꾸지 않습니다. 누락·손상·종료 미관측을 0이나 성공으로 보완하지 않으며, 기존 업무 count의 null과 정책상 `objectCandidateCount=0`을 유지합니다. 새 정보는 실패 구분용이며 원인 단정·자동 재시도·정리 범위 확대·guard 완화의 근거로 쓰지 않습니다.

검사: 기존 8개 + 새 6개 = 14개입니다. Windows의 첫 합성 실행은 13개 통과·실제 POSIX reader 1개 skip·실패/오류 0개입니다. Linux 전체 예정 수는 기존 다른 검사 48개 + 이 CLI 14개 = 62개이며 아직 실행하지 않았습니다. Linux openat/owner/mode 검사와 새 prep/Cloud 호환성 성공을 주장하지 않습니다.
