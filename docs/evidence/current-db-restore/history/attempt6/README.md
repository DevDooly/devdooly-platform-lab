# 현재 V1–V4 DB 백업·격리 복원 진행 기록

**논리 dump 생성까지 완료했고, 격리 DB 복원과 내용 대조는 아직 실행하지 않았습니다.** [안전한 진행 요약](summary.json)은 스키마·행 수·단계별 결과와 증거 SHA만 담습니다. SQL, BLOB, 접속 정보, Secret, 자원 UID, 원문 dump와 비공개 실행 기록은 게시하지 않습니다.

운영 애플리케이션 소스는 `74a8e98844a8fea0653951136ede0e7de0d7ac08`, 이번 실행에서 선택한 main은 `5c9b34d3b0a3508ebf6f78254e59a3f9131c71a2`입니다. 두 값의 역할은 다릅니다. 이 문서는 해당 시험의 시점 기록이며 현재 서비스 상태나 이후 실행 성공을 보장하지 않습니다.

| 확인 항목 | 실제 결과 |
| --- | --- |
| 현재 스키마 | V1–V4의 8개 테이블, 64개 컬럼, CHECK 15개, 제약 28개, 인덱스 컬럼 17개, 외래키 관계 3개를 읽고 root가 전체 메타데이터 검토 |
| 업무·운영 행 수 | demo_run 9, demo_outcome 1,096, lab_job 8, lab_outbox 16, slot·policy·runtime 각 1, Flyway history 4 |
| 새 a6 preflight | 실제 통과, 승인한 스키마 SHA와 동일 |
| 새 a6 backup | 논리 dump 생성 단계 통과. 복원으로 dump 내용을 검증한 상태는 아님 |
| 격리 시험 자원 | 최초 생성 응답 해석에서 중단. 별도 읽기 진단에서 저장된 7개 응답의 identity와 현재 Namespace·StatefulSet·PVC의 UID/spec 일치 확인 |
| 당시 cold 상태 | 시험 DB replicas 0, Pod 0, PVC Pending·volume 미할당. 이 기록으로 cleanup 완료를 주장하지 않음 |
| 복원·전체 내용 대조 | **미실행**. 시험 DB, worker, Spring, Flyway 시작 없음 |

`lab_runtime`을 제외한 7개 테이블의 행과 전체 스키마는 백업 전후 대조 대상이고, `lab_runtime`의 heartbeat·stage는 시점 값으로 별도 취급합니다. IDLE 관측은 새 업무 접수의 동결을 뜻하지 않습니다. BLOB은 길이·전체 바이트 해시를 포함하는 계약이며, DOUBLE은 숫자 round-trip 비교 범위입니다. 저장된 DOUBLE의 비트 동일성이나 runtime lease 복원은 주장하지 않습니다. DB dump와 외부 객체의 동시점 복구도 아직 검증하지 않았습니다.

실패 기록은 그대로 보존합니다.

- **a3:** 읽기 캡처 후 `MIGRATION_CHECK_CLAUSE_CHANGED`. CHECK 15개 중 13개는 기존 token과 같았고, 두 named CHECK만 AND 묶음의 불필요한 괄호가 제거된 관측형이었습니다. 이후 후보는 해당 두 exact 관측형만 허용합니다.
- **a5:** `SAME_VERSION_DUMP_TOOL_REQUIRED`. 실제 도구는 MariaDB 11.8.9의 modern version line을 반환했습니다. 이후 후보가 그 exact line을 추가로 허용했으며, a5에서는 dump가 생성되지 않았습니다.
- **a6:** `INVALID_KUBERNETES_RESPONSE`. 최초 create 명령은 종료 코드 0이었지만, 저장된 응답은 단일 List가 아닌 공백으로 구분된 JSON 문서 7개였습니다. 이후 별도 유한 단계 진단도 전체 성공은 아닙니다. 실제 Pod collection의 kind는 `List`였고, 진단 helper의 `PodList` 조건 때문에 `COLD_COMPARISON`에서 실패했습니다. 그 진단의 선행 응답·UID/spec 확인 결과와 전체 실패 결과를 함께 남깁니다.

이 설명과 새 소스 후보가 이전 실패 receipt를 성공으로 바꾸지는 않습니다. 다음 단계는 정확한 소유 자원의 cold 상태와 저장된 응답 연결을 바탕으로 정리 조건을 검토하고, **새 operation**에서 격리 DB 복원·8개 테이블 스키마/내용 대조·명시적 종료를 수행하는 것입니다. fresh CI/preflight와 승인한 스키마 SHA가 다시 일치해야 하며, 예전 freshness receipt는 재사용하지 않습니다.

이 기록은 [복구 runbook](../../../../runbooks/lab-recovery.md)의 현재 DB 복원 과제 중간 결과입니다. 전체 archive, K3s, Jenkins 애플리케이션 복구의 완료 근거로 사용하지 않습니다.
