# Closed-copy capture 시도 6: Linux 84개 통과, decoder lifecycle 검증 단계 미확인

소스 `61306712d542c8efe49bc686da8e7b3a031d72aa`의 [새 실행 38902228634](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38902228634)은 저장소 검증과 실제 Linux 84개·skip0을 통과했습니다. 공개 요약은 compiler prep, 원래 main 한 번 호출·반환 0, 새 decoder 컨테이너 정지·attach CLI 회수를 확인했지만 전체 결과는 `FAILED`·`SUMMARY_NOT_VERIFIED`입니다. 기존 workflow의 rerun이 아닌 새 소스의 첫 시도입니다.

[원문 summary](attempt-6.summary.json)의 시도 단계는 `NORMALIZE`, 고정 진단 코드는 `NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED`입니다. 이 코드는 **검증을 시도했으나 확인하지 못한 decoder lifecycle guard 구간**을 뜻합니다. 내부 원인·실패한 세부 필드·decoder 종료 코드·graph 상태를 특정하지 않으며, 어떤 수정이 필요하거나 성공했다는 증거도 아닙니다. `decoderReasonCodes:[]`를 decoder 성공 또는 오류 부재로 바꾸지 않습니다.

| 확인 항목 | 이번 실행의 기록 |
| --- | --- |
| 저장소 검증 | 성공 |
| Linux source-pinned 검사 | UID0·Python 3.12.3·84개, 실패 0·오류 0·skip 0 |
| 검사 전후 source bytes | 동일 |
| compiler prep | 검증 true |
| 원래 main | 한 번 호출·반환 0 확인 |
| 새 decoder | 컨테이너 정지·attach CLI 회수 확인; 종료 코드는 공개되지 않음 |
| 같은 실행의 stopped actors·clock 통합 검증 | false, 검증 미확인 |
| inventory 생성·전체 객체 KEEP 검증 | 각각 false, 검증 미확인 |
| 다섯 관측 count / 정규화 receipt hash | 모두 null / null |
| 객체 삭제 후보 | 0, KEEP-only 정책값 |
| 실패 분류·시도한 단계·고정 코드 | `SUMMARY_NOT_VERIFIED` / `NORMALIZE` / `NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED` |
| prep cold 정리 | known CID·identity binding·제거 시도·제거 후 부재 확인 네 flag 모두 true |

마지막 prep 명령은 `cold-export-absence` / `COLD_ABSENCE`, `EXITED_ZERO`, returnCode 0·timeout false·수신 stdout/stderr 각각 0 bytes입니다. 해당 Popen/CLI 시작·reap과 prep cold 컨테이너 제거·부재는 별개로 기록합니다. 마지막 명령만으로 최초 실패 원인을 특정하지 않습니다. 새 decoder 정지와 원래 main 반환 0을 원래 모든 actor의 통합 정지·정규화·완전 inventory 성공으로 확대하지 않습니다. False 검증 flag는 호출 0회·자원 부재·객체 삭제를 뜻하지 않으며 null은 관측된 0이 아닙니다.

원래 workload 단일 600초, 별도 prep 최대 600초와 cleanup reserve 40초를 유지합니다. Snapshot expiration·객체 삭제·미니 PC 접촉·live table 독립검증·Parquet 내용 decode·과거 metadata 복원은 수행하지 않았다는 공개 flag를 보존합니다. [시도1](ATTEMPT_1.md)·[시도2](ATTEMPT_2.md)·[시도3](ATTEMPT_3.md)·[시도4](ATTEMPT_4.md)·[시도5](ATTEMPT_5.md)의 실패를 보존합니다. 특히 실제5의 `NORMALIZE/UNKNOWN`을 이번 단계 코드로 다시 해석하지 않습니다. 다음 수정 범위와 검사 수는 아직 정하지 않았습니다.

[검사·실행 metadata](attempt-6.validation.json)의 `offlineLinux.actualRuntimeCalled:false`는 오프라인 검사 단계에만 한정됩니다. GitHub 실행 생성 시각 `2026-10-16T12:40:53Z`, 갱신 시각 `2026-10-16T12:46:24Z`는 workflow metadata이며 summary에 없는 capture 시각을 만들지 않습니다.

CLI SHA-256은 `fa8c0d6d01eddef3f6ed39036ae99dd3c1f9bc0409f13c384b61d1b31f78897b`, runtime manifest SHA-256은 `8c0dd76a436a5c5b8554015fbd90192e8514a8d261be67382335da9bbbcf1098`입니다. 공개 prep proof SHA는 `cb5cdaa73411ae9f6342615bcee9ba649f9ff6fbb40d1903b8232062e0bbdf19`이며 private 원문을 읽은 증거가 아닙니다. [정규화 단계 계약](../../../infra/iceberg-retention-ci/NORMALIZATION_PHASES.md)과 [실행 절차](../../runbooks/iceberg-closed-copy-capture.md)는 source 경계이며 실제 전체 capture 성공을 대신하지 않습니다.

원문 summary는 **1,790 bytes / SHA-256 `60156381856483932e9cdcd39659a8e9b404fabb544c13f3a0608f9f936c188b`**, 공개 validation은 **2,485 bytes / SHA-256 `160bfa8d7719ddb3a055710388b80ba0cb246ae1b829a5175fcff6c4e336996c`**입니다. Summary는 byte-exact 사본이며 validation은 이미 UTF-8/LF인 byte-exact 사본입니다. Private proof·provider 원문 로그·argv·Env·자격증명은 읽거나 게시하지 않았습니다. 공개 CI 로그에서는 허용된 Linux 검사 JSON만 추출했고 전체 로그를 저장하지 않았습니다.
