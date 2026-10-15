# Iceberg 데이터 흐름 검증 준비

상태: **PREPARED_NOT_RUN — 실제 조회·재시작 검증 미완료**.

포트폴리오에 원본 6개 → 12개 적재, 두 Iceberg 스냅샷의 시점 조회, Trino 재시작 뒤 같은 데이터를 읽는 과정을 보여줄 화면을 준비했습니다. Bronze 원본 12개와 기존 Java 처리 결과의 성공 7·실패 3·중복 2는 집계 기준이 다릅니다. 실제 검증 JSON은 아직 게시하지 않았으며 화면에는 준비 상태가 표시됩니다.

첫 준비 단계의 실패와 시간 예산 만료를 보존했습니다. 후속 이미지 캐시 확인은 완료했으나 새로운 기준 시점 검사 중 SSH가 끊겼고 그 원격 실행 결과는 확인하지 못했습니다. PostgreSQL·Trino 서버를 시작하는 단계는 실행하지 않았습니다. 이전 결과를 성공으로 바꾸거나 확인되지 않은 snapshot ID·재시작 결과를 채우지 않습니다.

화면의 입력 계약은 [iceberg-dataflow.ts](../../../apps/lab-web/src/lib/iceberg-dataflow.ts), 렌더링은 [IcebergDataflowCard.tsx](../../../apps/lab-web/src/components/IcebergDataflowCard.tsx)에 있습니다. 공개 필드를 엄격히 제한하고 64-bit snapshot ID는 문자열로 보존합니다. 불완전한 조회·재시작·종료·보존 근거는 성공 카드로 표시하지 않습니다.

이번 화면 후보에서 웹 테스트 48개, Astro 타입 검사(오류·경고 0개), GitHub Pages 경로 빌드와 390px 화면의 준비 상태를 확인했습니다. 이는 서버의 Iceberg 동작 검증을 대신하지 않습니다.

다음 순서는 원격 결과 확인 → 명시적인 실행 시간과 유휴 CI 확인 → 격리 조회·재시작 → 전용 workload 정지 → 원본 작업·객체 보존 확인 → 실제 정적 기록 연결입니다. Spark Silver 적재, compaction, Airflow는 별도 후속 범위입니다.
