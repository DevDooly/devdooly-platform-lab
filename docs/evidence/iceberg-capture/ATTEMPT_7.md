# Closed-copy capture 시도 7: Linux 85개 통과, 응답 binding 검증 구간 미확인

소스 `bf0445457935510d0372494840b546d51f92e1fc`의 [새 실행 39081027632](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39081027632)은 저장소 검증과 실제 Linux 85개·UID0·skip0을 통과했습니다. 공개 요약은 compiler prep, 원래 main 한 번 호출·반환 0, 새 decoder 컨테이너 정지·attach CLI 회수를 확인했지만 전체 결과는 `FAILED`·`SUMMARY_NOT_VERIFIED`입니다. 기존 workflow의 rerun이 아닌 이 소스의 첫 시도입니다.

[원문 summary](attempt-7.summary.json)의 시도 단계는 `NORMALIZE`, 고정 진단 코드는 `NORMALIZE_DECODER_REPLY_BINDING_UNVERIFIED`입니다. 이는 **응답 전체 증명과 frame·descriptor·actor 관계의 검증을 시도했으나 확인하지 못한 구간**입니다. 이 구간은 전체 증명의 JSON 해석도 포함하므로 코드만으로 특정 hash 불일치·오염·실패한 필드·정확한 내부 원인·decoder 종료 코드·graph 상태를 단정하지 않습니다. 진단이 세분화됐다는 사실이 원인 수정이나 전체 capture 성공의 증거는 아닙니다. `decoderReasonCodes:[]`는 decoder 성공 또는 오류 부재를 뜻하지 않습니다.

| 확인 항목 | 이번 실행의 기록 |
| --- | --- |
| 저장소 검증 | 성공 |
| Linux source-pinned 검사 | UID0·Python 3.12.3·85개, 실패 0·오류 0·skip 0 |
| 검사 전후 source bytes | 동일 |
| compiler prep | 검증 true |
| 원래 main | 한 번 호출·반환 0 확인 |
| 새 decoder | 컨테이너 정지·attach CLI 회수 확인; 종료 코드는 공개되지 않음 |
| 같은 실행의 stopped actors·clock 통합 검증 | false, 검증 미확인 |
| inventory 생성·전체 객체 KEEP 검증 | 각각 false, 검증 미확인 |
| 다섯 관측 count / 정규화 receipt hash | 모두 null / null |
| 객체 삭제 후보 | 0, KEEP-only 정책값 |
| 실패 분류·시도 단계·고정 코드 | `SUMMARY_NOT_VERIFIED` / `NORMALIZE` / `NORMALIZE_DECODER_REPLY_BINDING_UNVERIFIED` |
| prep cold 정리 | known CID·identity binding·제거 시도·제거 후 부재 확인 네 flag 모두 true |

마지막 prep 명령은 `cold-export-absence` / `COLD_ABSENCE`, `EXITED_ZERO`, returnCode 0·timeout false·수신 stdout/stderr 각각 0 bytes입니다. 해당 Popen/CLI 시작·reap과 prep cold 컨테이너 제거·부재를 별개로 기록합니다. 마지막 prep 명령의 0을 decoder exit 0 또는 graph 성공으로 해석하지 않습니다. False 검증 flag는 호출 0회·자원 부재·객체 삭제를 뜻하지 않으며 null은 관측된 0이 아닙니다.

원래 workload 단일 600초, 별도 prep 최대 600초와 cleanup reserve 40초를 유지합니다. Snapshot expiration·객체 삭제·미니 PC 접촉·live table 독립검증·Parquet 내용 decode·과거 metadata 복원을 수행하지 않았다는 공개 flag를 보존합니다. [시도1](ATTEMPT_1.md)·[시도2](ATTEMPT_2.md)·[시도3](ATTEMPT_3.md)·[시도4](ATTEMPT_4.md)·[시도5](ATTEMPT_5.md)·[시도6](ATTEMPT_6.md)의 실패는 변경하지 않습니다. 특히 실제5의 `NORMALIZE/UNKNOWN`과 실제6의 parent `NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED`를 이번 하위 구간 코드로 다시 해석하지 않습니다. 다음 원인 조사·수정 또는 추가 진단 범위는 아직 정하지 않았습니다.

[검사·실행 metadata](attempt-7.validation.json)의 `offlineLinux.actualRuntimeCalled:false`는 오프라인 검사 단계에만 한정됩니다. GitHub 실행 생성 시각 `2026-10-17T23:58:28Z`, 갱신 시각 `2026-10-18T00:03:30Z`는 workflow metadata이며 summary에 없는 capture 시각을 만들지 않습니다.

CLI SHA-256은 `b283da01f5bba010e0cd1945963d4ce3860a0ca57f81597470a23bb5adf548cb`, runtime manifest SHA-256은 `6b362710597d77ee7a37a59a39aef5e3d6ff59d1f509ca0103192b104a0340fc`입니다. 공개 prep proof SHA는 `cfd21f7bd03b090d2b88cf7049f53e7d883c9dc7b5703424ef767cd4c8777396`이며 private 원문을 읽은 증거가 아닙니다. [하위 구간 계약](../../../infra/iceberg-retention-ci/DECODER_PHASES.md)과 [실행 절차](../../runbooks/iceberg-closed-copy-capture.md)는 source 경계이며 전체 capture 성공을 대신하지 않습니다.

원문 summary는 **1,794 bytes / SHA-256 `70d95a4be42339d4acf231528e1e92443acfaf022867cf35d22f54c4310cdc79`**, 공개 validation은 **2,485 bytes / SHA-256 `9056ef2443f5d7a26431cb6dc778060a410d1b2f54b802d856a77fa2d1653d85`**입니다. 두 파일 모두 이미 수집된 UTF-8/LF의 byte-exact 사본입니다. Private proof·provider 원문 로그·argv·Env·자격증명은 읽거나 게시하지 않았습니다. 공개 CI 로그에서는 허용된 Linux 검사 JSON만 추출했고 전체 로그를 저장하지 않았습니다.
