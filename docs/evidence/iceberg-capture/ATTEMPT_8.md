# Closed-copy capture 시도8: Linux86 통과, strict JSON 검증 구간 미확인

소스 `e89a858d59910efc6de7ebd42baa840344c056ad`의 [새 실행39082460484](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39082460484)은 기본 CI와 Linux86개·UID0·Python3.12.3·실패/오류/skip0·검사 전후 source 동일을 확인했습니다. 첫 attempt이며 이전 run의 rerun이 아닙니다. 전체 capture는 `FAILED`·`SUMMARY_NOT_VERIFIED`, 시도 단계는 `NORMALIZE`, 고정 코드는 `NORMALIZE_DECODER_REPLY_JSON_UNVERIFIED`입니다.

코드는 strict JSON 검증을 시도했으나 확인하지 못한 구간입니다. 정확한 내부 원인·출력 혼입·실패한 필드·decoder 종료 코드·유효 graph 또는 수정 성공을 특정하지 않습니다.

| 경계 | 실제 공개 기록 |
| --- | --- |
| 검증 true6개 | source bytes·compiler prep·원래 main 한 번/반환0·새 decoder 정지/attach CLI 회수 |
| 검증 false3개 | 통합 stopped actors/clock·inventory 생성·전체 객체 KEEP 미확인 |
| 관측값 | 다섯 관측 count와 정규화 receipt hash는 null; objectCandidate0은 정책값 |
| 마지막 prep/정리 | cold-export-absence·COLD_ABSENCE·EXITED_ZERO·return0·stdout/stderr0·timeout false, cold 정리4flag true |

원문 [summary](attempt-8.summary.json)는 **1,791 bytes / SHA-256 `e96ca40d6bfeadfe0a8c51d73aec5c59977f418b3894470bcc4574870af2ca9e`**, [검사·실행 metadata](attempt-8.validation.json)는 **2,485 bytes / SHA-256 `e8c4738ff7a4b978259f4bbbd83e04cc5034923885d982b9ad9cb6094a0deb2c`**인 byte-exact 사본입니다. CLI SHA는 `5d583ebf1fef4aeabace71c1071a9d054ea59c679c761285063f5fcd97396857`, runtime manifest는 `bcbd7cc6f30d211f669bdc99994e6f41d3dc942ea3123a8aead1a2af31db9671`, 공개 prep proof SHA는 `bf78b5558cf71e0d5239aa46c64dd7db2c078654198c3158838bdc04315d95e3`입니다.

생성 `2026-10-18T00:21:29Z`·갱신 `2026-10-18T00:27:02Z`는 workflow metadata이며 capture 시각이 아닙니다. `offlineLinux.actualRuntimeCalled:false`는 오프라인 검사 단계에 한정됩니다. 앞선 [1](ATTEMPT_1.md)·[2](ATTEMPT_2.md)·[3](ATTEMPT_3.md)·[4](ATTEMPT_4.md)·[5](ATTEMPT_5.md)·[6](ATTEMPT_6.md)·[7](ATTEMPT_7.md)의 원문과 실패 분류는 그대로 보존합니다.

원래 workload600초·별도 prep600초·reserve40초를 유지했고 snapshot 만료·객체 삭제·미니 PC 접촉은 수행하지 않았습니다. Private proof·provider 원문 로그·argv·Env·자격증명은 읽거나 게시하지 않았습니다. 다음은 공개 source의 응답 protocol 경계를 검토하는 단계이며 수정 범위는 아직 정하지 않았습니다. [구간 계약](../../../infra/iceberg-retention-ci/REPLY_SUBPHASES.md)·[실행 절차](../../runbooks/iceberg-closed-copy-capture.md)를 따릅니다.
