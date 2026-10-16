# Closed-copy capture 시도 2: Linux 검사 통과, prep guard 실패

새 소스 `b91a7324a831454554cc6d5293aa4142fd0ba812`의 [실행 38881661893](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38881661893)은 저장소 검증과 Linux 62개·skip0을 통과한 뒤 준비 단계에서 실패했습니다. 이 실행은 이전 workflow의 rerun이 아닌 새 소스의 첫 시도입니다. [시도 1](ATTEMPT_1.md)의 일반 `PREP_NOT_VERIFIED` 실패와 원인·정리 미확인 상태는 그대로 보존합니다.

[원문 summary](attempt-2.summary.json)는 schema 2의 `status: FAILED`, `passed: false`, `failureCategory: PREP_NOT_VERIFIED`와 진단 코드 `JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED`를 기록합니다. 관측 단계는 `PREP`입니다. 이는 source에 고정된 Class-Path guard 실패 코드이며, 이 공개 기록은 특정 JAR 이름·manifest 값·참조 대상이나 해당 참조의 허용 가능성을 제공하지 않습니다. 이전 시도 실패의 원인도 이 결과로 소급해 확정하지 않습니다.

| 확인 항목 | 이번 실행의 기록 |
| --- | --- |
| 저장소 검증 | 성공 |
| Linux source-pinned 검사 | 실제 UID0·Python 3.12.3·62개, 실패 0·오류 0·skip 0 |
| 검사 전후 source bytes | 동일 |
| 새 capture 단계 | 준비 단계 실패, 원래 main·decoder 성공 미확인 |
| 마지막으로 관측한 prep 명령 | `failed-prep-cold-absence` / `COLD_ABSENCE`, `EXITED_ZERO`, returnCode 0·timeout false |
| 해당 명령 프로세스 | 시작·reap 확인, 수신 stdout/stderr 각각 0 bytes |
| prep cold 컨테이너 정리 | known CID·identity binding·삭제 시도·삭제 후 부재 확인 네 flag 모두 true |
| inventory와 다섯 관측 count | 검증 미확인, count는 null |
| 객체 삭제 후보 | 0, KEEP-only 정책값 |

마지막 prep 명령은 실패 후 정리에서 관측한 명령으로, 최초 실패 명령이라는 뜻이 아닙니다. 명령 프로세스의 reap은 Docker 컨테이너 종료 증거와 별개입니다. 위 cold 정리 flag는 해당 prep 자원에 한정하며 원래 workload actor·decoder의 정지 또는 전체 capture 성공을 뜻하지 않습니다. 다른 false 검증 flag도 호출 횟수 0이나 actor 부재로 바꾸어 해석하지 않습니다.

Snapshot expiration·객체 삭제·미니 PC 접촉·과거 metadata 복원·Parquet 내용 decode·live table 독립검증은 수행하지 않았다는 공개 flag를 유지합니다. 원래 workload 단일 600초, 별도 prep 최대 600초와 cleanup reserve 40초도 유지됩니다. 이 실패를 guard 완화나 자동 재시도의 근거로 사용하지 않습니다.

[검사·실행 metadata](attempt-2.validation.json)는 저장소 검증 성공과 Linux 검사 결과, 단계별 GitHub 시각·conclusion을 담습니다. `offlineLinux.actualRuntimeCalled: false`는 오프라인 검사 단계의 범위이며 뒤따른 실제 prep 실행까지 미실행이었다는 뜻이 아닙니다. GitHub 실행 생성 시각은 `2026-10-16T09:36:54Z`, 갱신 시각은 `2026-10-16T09:39:47Z`입니다. 원문 summary에는 별도 기록 시각 필드가 없으므로 이 시각을 summary의 capture 시각으로 만들지 않습니다.

현재 CLI source SHA-256은 `2408512f8373713ba6766364177472cfddb2d35c3210e0868cbfa2f2a77b1917`, runtime manifest SHA-256은 `53493f2dfeedee530ad152b5dc08f2c08b3d560ac39fac887820129913c8db3d`입니다. [Schema 2 계약](../../../infra/iceberg-retention-ci/SCHEMA2.md)은 고정 enum·최소 metadata 진단만 추가하며 원래 실행·정리 guard와 자원 제한을 바꾸지 않습니다.

원문 summary는 **1,733 bytes / SHA-256 `a88f6ef6bd012e9858554fd0c44d22a834141940da9b61381998ef16b7a585b9`**로 그대로 복사했습니다. 검증 metadata 원문도 이미 UTF-8/LF인 **2,383 bytes / SHA-256 `c772ec44dee79427d2b939848340ee9d41eca4612366a091d7f45c69918d0c49`**이며 게시용 validation은 byte-exact 복사본입니다. Private proof·provider 원문 로그·argv·Env·자격증명은 읽거나 게시하지 않았습니다. 공개 CI 로그에서는 허용된 Linux 검사 JSON만 추출했고 전체 로그를 저장하지 않았습니다.
