# Closed-copy capture 시도9: 실제 metadata와 KEEP 보존 계획 연결

소스 `5862ba0c617d17d4c51382bccaa0266253974e82`의 [새 실행39085360317](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39085360317)은 기본 CI와 Linux87개·UID0·Python3.12.3·실패/오류/skip0·검사 전후 source 동일을 확인했습니다. 새 실행의 첫 attempt이며 이전 run의 rerun이나 자동 재시도가 아닙니다. 별도 capture도 `passed:true`·`DETERMINED`·`failureCategory:null`, 단계 `COMPLETED`·실패 코드 없음으로 통과했습니다.

| 경계 | 이번 실행의 공개 기록 |
| --- | --- |
| 필수 검증9개 | source bytes·compiler prep·원래 main 한 번/반환0·새 decoder 정지/attach CLI 회수·같은 실행의 stopped actors/clock·inventory 생성·전체 객체 KEEP 모두 true |
| 닫힌 metadata 입력 | 스냅샷3개·참조1개·검증용 보호 항목1개 |
| 보존 계획 | 전체 바이트를 캡처한 객체20개; 스냅샷 제안0개·객체 삭제 후보0개, 모든 객체 KEEP |
| 마지막 prep/정리 | cold-export-absence·COLD_ABSENCE·EXITED_ZERO·return0·stdout/stderr0·timeout false, cold 정리4flag true |
| 이번 범위 밖 | 스냅샷 만료·객체 삭제·미니 PC 접촉·Parquet 내용 해석·현재 운영 테이블 독립 재검증·역사 metadata 복원은 모두 false |

같은 새 실행의 중지 상태와 clock, metadata 참조 graph의 closure·정규화, 완전 inventory를 확인한 입력으로 순수 보존 계획을 만들었습니다. 20개는 이 capture의 객체 수이며 다른 Cloud·native 실행의 수치와 합산하지 않습니다. 삭제 후보0개는 KEEP 정책의 결과이고 실제 삭제나 가비지 수거의 성공을 뜻하지 않습니다. 전체 6단계·현재 서버 가용성·운영 규모 성능을 검증한 기록도 아닙니다.

원문 [summary](attempt-9.summary.json)는 **1,784 bytes / SHA-256 `24615854f798e6b8f7ab81f9e238a85e001d01877a396a9a7026617b21091f87`**, [검사·실행 metadata](attempt-9.validation.json)는 **2,694 bytes / SHA-256 `46f3a336c8b92806cb3d819ed0aa9e7b677690bfe8e317f023fb299c2828e076`**인 byte-exact 사본입니다. 공개 화면의 최신 summary와 UI fixture도 같은 원문 bytes를 사용합니다.

| 공개 소스·증거 식별자 | SHA-256 |
| --- | --- |
| CLI source | `5d583ebf1fef4aeabace71c1071a9d054ea59c679c761285063f5fcd97396857` |
| runtime manifest | `3b1b5d4b0be4298d993a93fbbf39306a6ac69abaabc876b2ae78789772bded19` |
| stdout 합성 fixture support | `37f1a8f20440d3b596adba4f6f7a46e27ef3b3ed3af90b3637d536593cc1222b` |
| prep proof | `6ee2b522ee8957e9f1d11d459939d1ab3992a56985547d5e7b4adecd02f57e35` |
| 정규화 privateReceipt의 canonical hash | `3f3c8cfee2e734e09112dbecb09253bcb1139904fb0d17f99f71f45b87b3b5c3` |

위 hash는 증거 식별자이며 private proof 원문을 공개한 것이 아닙니다. 생성 `2026-10-18T01:08:07Z`·갱신 `2026-10-18T01:13:41Z`는 workflow metadata이며 capture 시각이 아닙니다. `offlineLinux.actualRuntimeCalled:false`는 오프라인 검사 단계에 한정되며 이후 별도 fresh capture의 실행 여부를 부정하는 필드가 아닙니다. Capture 단계의 실제 PASS는 별도 conclusion과 원문 summary에 연결됩니다.

원래 workload600초·별도 prep600초·reserve40초는 실행 예산이고 처리 시간·처리량·SLA 측정값이 아닙니다. Private proof·provider 원문 로그·argv·Env·자격증명은 읽거나 게시하지 않았습니다. 공개 summary와 선택한 실행 metadata만 보존했습니다.

앞선 [1](ATTEMPT_1.md)·[2](ATTEMPT_2.md)·[3](ATTEMPT_3.md)·[4](ATTEMPT_4.md)·[5](ATTEMPT_5.md)·[6](ATTEMPT_6.md)·[7](ATTEMPT_7.md)·[8](ATTEMPT_8.md)의 실패 분류·null 값·원문과 [별도 합성 검증](STDOUT_SYNTHETIC.md)은 그대로 보존합니다. 이번 PASS를 실제8의 정확한 원인이나 stdout 혼입의 증거로 소급하지 않습니다. 이후 보존 정책·운영 규모 compaction과 다른 장애 경계는 독립 검증으로 남깁니다. [실행 절차](../../runbooks/iceberg-closed-copy-capture.md)를 따릅니다.
