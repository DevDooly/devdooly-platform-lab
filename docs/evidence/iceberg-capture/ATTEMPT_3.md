# Closed-copy capture 시도 3: Linux 67개 통과, manifest 바이트 guard 실패

소스 `a03f87837af66fd3770063d9c712c4080e15d9fa`의 [새 실행 38886641237](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38886641237)은 저장소 검증과 실제 Linux 67개·skip0을 통과한 뒤 준비 단계에서 실패했습니다. 기존 workflow의 rerun이 아닌 새 소스의 첫 시도입니다. [시도 1](ATTEMPT_1.md)의 일반 PREP 실패와 원인·정리 미확인, [시도 2](ATTEMPT_2.md)의 Class-Path 거부 코드와 해당 prep 자원 정리 확인은 각각 보존합니다.

[원문 summary](attempt-3.summary.json)는 schema 2의 `status: FAILED`, `passed: false`, `failureCategory: PREP_NOT_VERIFIED`, `stageAttempted: PREP`와 `JAR_MANIFEST_BYTES_BOUND`를 기록합니다. 이 코드는 여러 manifest 바이트 검사의 공통 guard입니다. 공개 기록만으로 빈 manifest, 선언 크기 64KiB 초과, 실제 읽은 길이와 선언 크기의 불일치 중 어떤 분기인지 구분할 수 없습니다. 특정 JAR·manifest 이름이나 실제 크기를 추측하지 않습니다.

| 확인 항목 | 이번 실행의 기록 |
| --- | --- |
| 저장소 검증 | 성공 |
| Linux source-pinned 검사 | 실제 UID0·Python 3.12.3·67개, 실패 0·오류 0·skip 0 |
| 검사 전후 source bytes | 동일 |
| 준비 단계 | `JAR_MANIFEST_BYTES_BOUND`로 검증 미통과 |
| 마지막으로 관측한 prep 명령 | `failed-prep-cold-absence` / `COLD_ABSENCE`, `EXITED_ZERO`, returnCode 0·timeout false |
| 해당 명령 프로세스 | 시작·reap 확인, 수신 stdout/stderr 각각 0 bytes |
| prep cold 컨테이너 정리 | known CID·identity binding·제거 시도·제거 후 부재 확인 네 flag 모두 true |
| 원래 main·decoder·inventory | 성공 검증 미확인, 다섯 관측 count는 null |
| 객체 삭제 후보 | 0, KEEP-only 정책값 |

Linux 검사 통과는 새 실제 Class-Path 참조 closure나 prep·decoder·inventory의 성공을 뜻하지 않습니다. 마지막 명령은 실패 후 정리에서 관측한 명령이며 최초 실패 명령을 특정하지 않습니다. Popen/CLI 생성·reap과 prep cold 컨테이너 제거·부재는 서로 다른 관측입니다. 이 정리 범위를 원래 workload actor 또는 decoder의 정지로 확대하지 않습니다. False 검증 flag를 실제 호출 0회나 자원 부재로 바꾸지 않습니다.

원래 workload 단일 600초, 별도 prep 최대 600초와 cleanup reserve 40초는 유지됩니다. Snapshot expiration·객체 삭제·미니 PC 접촉·live table 독립검증·Parquet 내용 decode·과거 metadata 복원은 수행하지 않았다는 공개 flag를 보존합니다. 이 결과만으로 바이트 제한 변경이나 새 호환 구현의 성공을 주장하지 않습니다.

[검사·실행 metadata](attempt-3.validation.json)의 `offlineLinux.actualRuntimeCalled: false`는 Linux 오프라인 검사 단계에 한정되며 이후 실제 prep 실행까지 미실행이었다는 뜻이 아닙니다. GitHub 실행 생성 시각 `2026-10-16T10:21:04Z`, 갱신 시각 `2026-10-16T10:24:12Z`는 workflow metadata입니다. Summary에는 별도 기록 시각 필드가 없으므로 이 값을 capture 시각으로 만들지 않습니다.

CLI source SHA-256은 `aed428dde12b8f1e6b37ea25f3efdf6986faa9010f794c441ca2ad77b9ea064c`, runtime manifest SHA-256은 `a9704dce98583b3935e05ac759a3b0e9c8af839fb9b3fa141ad1d96a13708f18`입니다. [Class-Path 계약](../../../infra/iceberg-retention-ci/CLASSPATH_CLOSURE.md)과 [실행 절차](../../runbooks/iceberg-closed-copy-capture.md)는 source 경계이며 실제 성공 근거를 대신하지 않습니다.

원문 summary는 **1,716 bytes / SHA-256 `7b5cd2213e8beb6cf988932eb54465828205c81eeb979aef58044f75cd882340`**, validation은 **2,383 bytes / SHA-256 `69c1ccabf6a0e2f8c4c35aa8cebf3e493fcd7bc364210d177fedd6eba1d7c687`**입니다. 두 파일 모두 이미 UTF-8/LF이며 byte-exact 복사본으로 보존합니다. Private proof·provider 원문 로그·argv·Env·자격증명은 읽거나 게시하지 않았습니다. 공개 CI 로그에서는 허용된 Linux 검사 JSON만 추출했고 전체 로그를 저장하지 않았습니다.
