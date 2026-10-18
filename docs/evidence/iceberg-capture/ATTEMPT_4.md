# Closed-copy capture 시도 4: Linux 73개 통과, 참조 대상 누락 guard 실패

소스 `a00ddbccf859c249637f65303654dee659130bdc`의 [새 실행 38890545126](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38890545126)은 저장소 검증과 실제 Linux 73개·skip0을 통과한 뒤 준비 단계에서 실패했습니다. 기존 workflow의 rerun이 아닌 새 소스의 첫 시도입니다. [시도 1](ATTEMPT_1.md)의 일반 PREP 실패·원인과 정리 미확인, [시도 2](ATTEMPT_2.md)의 Class-Path 거부 코드, [시도 3](ATTEMPT_3.md)의 manifest 바이트 guard와 구체적 분기 미확인은 각각 보존합니다.

[원문 summary](attempt-4.summary.json)는 schema 2의 `status: FAILED`, `passed: false`, `failureCategory: PREP_NOT_VERIFIED`, `stageAttempted: PREP`와 `JAR_MANIFEST_CLASSPATH_TARGET_MISSING`을 기록합니다. 이는 참조 대상 누락을 거부한 고정 코드입니다. 특정 JAR·token·경로는 공개 기록에서 알 수 없으며, 어떤 참조인지 또는 실제 JVM에서 어떻게 처리되는지 이 요약만으로 확정하지 않습니다. 이 결과를 이전 manifest 바이트 guard 실패의 원인으로 소급하지 않습니다.

| 확인 항목 | 이번 실행의 기록 |
| --- | --- |
| 저장소 검증 | 성공 |
| Linux source-pinned 검사 | 실제 UID0·Python 3.12.3·73개, 실패 0·오류 0·skip 0 |
| 검사 전후 source bytes | 동일 |
| 준비 단계 | `JAR_MANIFEST_CLASSPATH_TARGET_MISSING`으로 검증 미통과 |
| 마지막으로 관측한 prep 명령 | `failed-prep-cold-absence` / `COLD_ABSENCE`, `EXITED_ZERO`, returnCode 0·timeout false |
| 해당 명령 프로세스 | 시작·reap 확인, 수신 stdout/stderr 각각 0 bytes |
| prep cold 컨테이너 정리 | known CID·identity binding·제거 시도·제거 후 부재 확인 네 flag 모두 true |
| 실제 Class-Path closure·prep·compile·decoder·inventory | 성공 검증 미확인 |
| 다섯 관측 count | null |
| 객체 삭제 후보 | 0, KEEP-only 정책값 |

마지막 명령은 실패 후 정리에서 관측한 명령이며 최초 실패 명령을 특정하지 않습니다. Popen/CLI 생성·reap은 prep cold 컨테이너 제거·부재와 별개입니다. 해당 prep 자원의 정리 확인을 원래 workload actor·decoder의 정지나 전체 capture 성공으로 확대하지 않습니다. False 검증 flag는 실제 호출 0회나 자원 부재를 뜻하지 않으며 null을 관측된 0으로 바꾸지 않습니다.

원래 workload 단일 600초, 별도 prep 최대 600초와 cleanup reserve 40초를 유지합니다. Snapshot expiration·객체 삭제·미니 PC 접촉·live table 독립검증·Parquet 내용 decode·과거 metadata 복원은 수행하지 않았다는 공개 flag를 보존합니다. Linux 73개 통과는 이 source의 검사 결과이며 다음 호환 정책이나 새 source의 성공으로 채택하지 않습니다.

[검사·실행 metadata](attempt-4.validation.json)의 `offlineLinux.actualRuntimeCalled: false`는 Linux 오프라인 검사 단계에 한정되며 이후 실제 prep 실행까지 미실행이었다는 뜻이 아닙니다. GitHub 실행 생성 시각 `2026-10-16T10:56:46Z`, 갱신 시각 `2026-10-16T10:59:55Z`는 workflow metadata입니다. Summary에는 별도 기록 시각 필드가 없으므로 이 값을 capture 시각으로 만들지 않습니다.

CLI source SHA-256은 `9999315e0c4832020e13fa21c26ddb864880ddc44588f35d0be09687ac9de342`, runtime manifest SHA-256은 `6aea1d3987d4a258718f4fd242d05ff1364a73cf4772272260975fce7eb172cd`입니다. [Manifest 한도](../../../infra/iceberg-retention-ci/MANIFEST_BOUNDS.md)와 [실행 절차](../../runbooks/iceberg-closed-copy-capture.md)는 source 경계이며 실제 성공 근거를 대신하지 않습니다.

원문 summary는 **1,729 bytes / SHA-256 `78e07be0b1116224507481de08f15a8792b26277d7734e79b2b6e8883d4dd1af`**, validation은 **2,383 bytes / SHA-256 `b5b36d9b3c3bc1156c41cc906d1812eee002633fdc517533dad380698f3df554`**입니다. 두 파일 모두 이미 UTF-8/LF이며 byte-exact 복사본으로 보존합니다. Private proof·provider 원문 로그·argv·Env·자격증명은 읽거나 게시하지 않았습니다. 공개 CI 로그에서는 허용된 Linux 검사 JSON만 추출했고 전체 로그를 저장하지 않았습니다.
