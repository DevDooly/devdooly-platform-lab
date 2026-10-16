# 현재 V1–V4 DB의 논리 백업·격리 복원 검증

새 a7 실행에서 현재 DB의 논리 dump를 **새 격리 DB에 한 번 가져와 전체 스키마와 내용을 대조했습니다.** 복원 단계는 통과했습니다. 종료 단계 receipt는 실패로 남았고, 별도 읽기 진단에서 시험 DB replicas 0·Pod 0·Bound/Retain 볼륨을 확인했습니다. **정상 종료 코드와 TERM 전달은 UNOBSERVED**입니다. [안전한 요약](summary.json)은 이 결과들을 분리하며 전체 단계를 성공으로 합치지 않습니다.

애플리케이션 소스는 `74a8e98844a8fea0653951136ede0e7de0d7ac08`, 선택한 main은 `5c9b34d3b0a3508ebf6f78254e59a3f9131c71a2`입니다. 아래는 2026-10-16의 a7 시험 기록이며 현재 가용성·전체 애플리케이션 복구를 뜻하지 않습니다. 원문 dump, 행·BLOB, 접속 정보, Secret, 자원 UID·서버 경로는 공개하지 않습니다.

| 단계 | 실제 결과 |
| --- | --- |
| fresh preflight | source·현재 자원·CI 유휴 시점과 승인 스키마 SHA를 새로 확인하고 통과 |
| backup | 새 논리 dump 생성 통과 |
| create-target | 별도 DB·3GiB PVC·Retain PV와 격리 경계를 확인하고 통과. a6에서 실패했던 최초 7-resource 응답 parser도 새 a7에서 통과 |
| target-preflight | 실제 빈 DB와 동일한 target identity를 확인하고 통과 |
| restore | import 1회, 재import 없음. 스키마 8개 테이블 전체·`lab_runtime` 제외 7개 테이블의 행·source BLOB 전체 bytes 대조, target 재조회 동일성과 원본 DB 자료 보존 확인 |
| 원래 stop | 종료 전 데이터 재확인과 소유 controller의 replicas 0 요청·Pod 0 관측 뒤 마지막 CRI 조회에서 실패. **receipt FALSE 유지** |
| 별도 fresh 읽기 진단 | 저장된 소유 identity/spec와 현재 Namespace·controller·PVC·PV를 대조해 DB replicas 0·Pod 0·PVC Bound·PV Retain 확인 |
| 별도 저장 stderr 진단 | 마지막 CRI 조회의 `codeNotFound` signature 관측. exit code·정상 TERM·GC 원인은 입증하지 않음 |

승인 스키마는 8개 테이블·64개 컬럼·CHECK 15개·제약 28개·인덱스 컬럼 17개·외래키 관계 3개입니다. 행 수는 demo_run 9, demo_outcome 1,096, lab_job 8, lab_outbox 16, slot·policy·runtime 각 1, Flyway history 4입니다. 승인한 SHA만 재사용했고 fresh CI/preflight receipt와 단계별 proof는 새 a7에 묶었습니다. 이전 실패 operation을 재실행하거나 시계를 초기화하지 않았습니다.

`lab_runtime`은 백업 시점의 journal을 역사적 값으로 가져왔습니다. live heartbeat·stage·DB session lease를 복구한 것이 아닙니다. worker·Spring·Flyway를 시작하지 않았고, 가져온 Flyway history는 애플리케이션 migration 실행을 뜻하지 않습니다. DOUBLE은 숫자 round-trip 비교 범위이며 저장 비트 동일성을 주장하지 않습니다. DB 프로그램·event·grant의 복원이나 DB·S3의 동시점 전체 애플리케이션 복구도 검증하지 않았습니다.

종료의 관측 범위는 복원 성공과 별개입니다. 원래 stop의 종료 전 target/source 데이터 재확인은 통과했지만 마지막 CRI inspect가 실패해 컨테이너 exit를 받지 못했습니다. 후속 진단은 저장된 stderr만 서버 RAM에서 읽어 NotFound code signature를 확인했으며 새 CRI/Kubernetes 명령을 실행하지 않았습니다. 이를 GC의 확정 원인이나 정상 exit의 증거로 바꾸지 않습니다. 다른 fresh 읽기 진단의 DB 0·Pod 0·Bound/Retain 확인도 원래 stop FALSE를 수정하지 않습니다. 복원 자료가 있는 새 볼륨은 보관하며 이전 13개 기준에 맞추려고 삭제하지 않습니다.

이전 [a6 진행 문서와 요약](history/attempt6/README.md)은 별도 시점 기록으로 보존합니다. a3의 CHECK 표현 차이, a5의 도구 version line, a6의 JSON document stream 실패와 별도 진단 실패를 유지했습니다. a6의 데이터 없는 cold 자원은 별도 소유 조건의 정리 뒤 새 a7로 진행했으며, a7의 복원 통과를 예전 실패 receipt에 소급하지 않습니다.

다음 작업은 보관된 새 복원 볼륨을 이후 점검 기준에 명시적으로 등록하고 이 종료 관측의 한계를 포함해 근거를 연결하는 것입니다. [복구 runbook](../../runbooks/lab-recovery.md)의 현재 DB 논리 복원 범위는 추가 확인했지만, K3s·Jenkins application 기동·전체 archive 복원·재부팅·장애 중 복구·SLA는 여전히 별도입니다.
