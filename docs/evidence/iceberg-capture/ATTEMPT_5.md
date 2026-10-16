# Closed-copy capture 시도 5: Linux 80개·prep 확인, 정규화 결과 미확인

소스 `316853f72108638607819120f808edb773c21bf4`의 [새 실행 38895409421](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38895409421)은 저장소 검증과 실제 Linux 80개·skip0을 통과했습니다. 공개 요약은 prep 검증, 원래 main 한 번 호출·반환 0, 새 decoder 컨테이너 정지·attach CLI 회수를 확인했지만, `NORMALIZE` 단계에서 `SUMMARY_NOT_VERIFIED`로 실패했습니다. 기존 workflow의 rerun이 아닌 새 소스의 첫 시도입니다.

[원문 summary](attempt-5.summary.json)의 상태는 `FAILED`·`passed:false`이며 고정 실패 코드는 `UNKNOWN`, `decoderReasonCodes`는 빈 배열입니다. 이 공개 기록으로 정확한 예외·실패 원인, decoder exit 0, 유효한 decoded graph 또는 완전한 normalization을 확인하지 않습니다. 빈 reason 배열도 decoder 성공의 증거가 아닙니다.

| 확인 항목 | 이번 실행의 기록 |
| --- | --- |
| 저장소 검증 | 성공 |
| Linux source-pinned 검사 | UID0·Python 3.12.3·80개, 실패 0·오류 0·skip 0 |
| 검사 전후 source bytes | 동일 |
| compiler prep 검증 | true |
| 원래 main | 한 번 호출·반환 0 확인 |
| 새 decoder | 컨테이너 정지·attach CLI 회수 확인; 종료 코드 0은 공개되지 않음 |
| 같은 실행의 stopped actors·clock 통합 검증 | false, 검증 미확인 |
| inventory 생성·모든 객체 KEEP 검증 | 각각 false, 검증 미확인 |
| 다섯 관측 count | 모두 null |
| 객체 삭제 후보 | 0, KEEP-only 정책값 |
| 실패 분류·시도한 단계·고정 코드 | `SUMMARY_NOT_VERIFIED` / `NORMALIZE` / `UNKNOWN` |
| prep cold 정리 | known CID·identity binding·제거 시도·제거 후 부재 확인 네 flag 모두 true |

마지막 prep 명령은 `cold-export-absence` / `COLD_ABSENCE`, `EXITED_ZERO`, returnCode 0·timeout false·수신 stdout/stderr 각각 0 bytes입니다. 해당 Popen/CLI 프로세스의 시작·reap과 prep cold 컨테이너 제거·부재는 별개로 기록합니다. 이 마지막 명령만으로 최초 실패 원인을 특정하지 않습니다. 새 decoder의 정지 확인을 원래 모든 actor의 통합 검증이나 전체 capture 성공으로 확대하지 않습니다. False 검증 flag는 호출 0회·자원 부재·객체 삭제를 뜻하지 않으며 null을 관측된 0으로 바꾸지 않습니다.

원래 workload 단일 600초, 별도 prep 최대 600초와 cleanup reserve 40초를 유지했습니다. Snapshot expiration·객체 삭제·미니 PC 접촉·live table 독립검증·Parquet 내용 decode·과거 metadata 복원은 수행하지 않았다는 공개 flag를 보존합니다. [시도 1](ATTEMPT_1.md)의 일반 PREP 실패와 원인·정리 미확인, [시도 2](ATTEMPT_2.md)의 Class-Path 거부, [시도 3](ATTEMPT_3.md)의 manifest 바이트 guard와 구체적 분기 미확인, [시도 4](ATTEMPT_4.md)의 참조 대상 누락은 각각 보존하며 이번 결과를 이전 원인으로 소급하지 않습니다. 다음 수정 범위와 새 검사 수는 아직 정하지 않았습니다.

[검사·실행 metadata](attempt-5.validation.json)의 `offlineLinux.actualRuntimeCalled:false`는 오프라인 검사 단계에만 한정됩니다. GitHub 실행 생성 시각 `2026-10-16T11:41:12Z`, 갱신 시각 `2026-10-16T11:46:39Z`는 workflow metadata입니다. Summary에 없는 capture 시각을 만들지 않습니다.

CLI SHA-256은 `7c84ff6b32114196293158f67cebbd91198e80fd349cbb1a32a3bfd856c93315`, runtime manifest SHA-256은 `c8a3d89458bca95a98547472816c5fb35f922aea934cd7da1a0cd4534c0c6fbf`입니다. Prep proof SHA는 summary의 공개 hash일 뿐 private 원문을 읽은 기록이 아닙니다. [실행 절차](../../runbooks/iceberg-closed-copy-capture.md)는 source 계약이며 전체 capture 성공 근거를 대신하지 않습니다.

원문 summary는 **1,759 bytes / SHA-256 `a7976a9cb3d81c349be87be4e3959d982f0b4adadef758d1615228f9cbe48fa5`**, 공개 validation은 **2,383 bytes / SHA-256 `0324e27992836e261a6bd8b7cedf3e6cbcc21ca57f9dfcf7cb9c95cbac13a62b`**입니다. Summary는 byte-exact 복사본이며 validation은 이미 UTF-8/LF인 byte-exact 복사본입니다. Private proof·provider 원문 로그·argv·Env·자격증명은 읽거나 게시하지 않았습니다. 공개 CI 로그에서는 허용된 Linux 검사 JSON만 추출했고 전체 로그를 저장하지 않았습니다.
