# 출처와 검토 범위

이 공개 예제는 2026-10-18 개인 Platform Lab의 기존 운영 GC 후속 계획을 바탕으로 AI coding assistant가 설계·Java 코드·합성 테스트·문서를 제안한 작업이다. 회사 코드·업무 데이터·실제 수율 공식·비공개 장애 로그·자격증명을 사용하지 않았다. 실제 객체 이름이나 과거 운영 inventory를 합성 입력으로 복제하지 않았다.

기존 [`object_reference_plan.py`](../../infra/maintenance/object_reference_plan.py), [공개 계약](../../infra/maintenance/OBJECT_REFERENCE_PLAN.md), [ADR0012](../../docs/adr/0012-reference-protection-and-isolated-gc.md), [운영 GC의 남은 조건](../../docs/runbooks/object-reference-gc.md)을 검토해 다음 범위를 골랐다.

- 채택: 참조/pin 변경의 revision, tombstone+intent의 명시적 원자 경계, 닫힌 run의 새 참조 차단, intent/대상 세대에 묶은 재전달, UNKNOWN 결과의 관측 조정.
- 제외: 운영 planner 연결, 삭제 adapter, SQL migration, credential·S3·HTTP, 실제 crash/영속 복원, 물리 GC나 성능 수치.
- 검증 계획: 새로운 프로토콜의 다섯 합성 전이 시나리오. 기존 KEEP 검사나 격리 Garage 실제 11/11을 새 코드의 운영 검증으로 재사용하지 않는다.

AI가 작성한 설계와 테스트, 정적 peer 검토, 실제 Java/JUnit 실행, 저장소 소유자의 사람 검토는 서로 다른 근거다. 이 문서는 사람 검토·실제 채택·운영 효과가 완료됐다고 주장하지 않는다. 실행한 검사와 한계는 해당 commit의 CI/PR 기록에 사실대로 연결한다. 합성 모델 통과를 실제 데이터 삭제의 승인이나 운영 안전성 보장으로 표현하지 않는다.
