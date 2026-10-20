# 저장소 소유자 검토 메모

상태: **PENDING**. 기존 코드·테스트·측정 기록을 검토하기 위한 자료다. AI 제안과 agent 검토, 테스트 통과를 소유자의 승인이나 실제 채택으로 바꾸지 않는다. 아래 판단란은 아직 비어 있다.

## 확인할 질문

- [ ] **계약:** `coveredNanos`는 겹침을 한 번만 센 합집합이고 peak는 관측 세션 수다. 물리 센서별 중복 제거가 아니다. 최대 4,096세션·1시간 창, 잘못된 입력 거부가 필요한 문제 범위에 맞는가?
- [ ] **UTC:** offset을 `toInstant()`로 보존하고 `기록 시계−기준 시계` 오차를 빼는가? `+09:00` 오류의 올바른 10초/잘못된 0초는 별도 회귀이며 성능 비교가 아니다. NTP·오차 추정·시스템 시계 변경은 구현하지 않았다.
- [ ] **동률과 경계:** 반열린 `[시작, 종료)`에서 같은 시점의 시작/종료 delta를 합치는가? 인접 구간의 peak 1, clipping·1ns·날짜 경계·잘못된 입력과 overflow 제한을 확인한다.
- [ ] **비교:** 두 알고리즘은 같은 정규화 입력에서 정답을 내는가? 기준 O(n²)와 sweep O(n log n)에 TreeSet/TreeMap 생성·정렬 비용을 포함한다. UTC 파싱·fixture 생성·기대값 검증은 JMH trial setup으로 제외한다.
- [ ] **독립성:** 기존 Java 20개 검사, 64ns 격자의 고정 2,000사례·순서 변경·큰 fixture의 닫힌 형태 기대값을 읽는다. oracle이 정규화나 sweep을 그대로 호출하지 않는지 소유자가 판단한다.
- [ ] **오차·출처:** Windows sparse/2,048은 평균 11,933 ± 10,205 us/op로 오차가 크고 Linux도 16조합 중 2개의 오차가 평균의 25% 이상이다. 두 실행의 조건·출처를 구분하고 Windows 측정의 `sourceCommit:null`을 후속 commit으로 덮어쓰지 않는다.
- [ ] **주장:** AI는 합성 문제·구현·테스트·JMH·문서 초안을 제안했다. 회사 수식·데이터·레거시 성과의 증거가 아니며 기존 O(n) ETL을 개선한 예제도 아니다. 관측 평균 비율을 보장 개선율·AI의 인과적 효과·처리량·p95·SLA로 옮기지 않는다.

근거: [계약](../../examples/java-window-analysis/DESIGN.md) · [AI 활용 범위](../../examples/java-window-analysis/PROVENANCE.md) · [예제·검사 안내](../../examples/java-window-analysis/README.md) · [실제 Windows 기록](../evidence/ai-window-analysis/README.md) · [별도 Linux 기록](../evidence/ai-window-analysis/hosted-linux-20261018/README.md).

## 소유자가 남길 판단

판단: ☐ 채택　☐ 수정 후 채택　☐ 기각

검토한 소스·근거: ____________________

이유와 필요한 변경: ____________________

이 문서에는 선택·서명·승인된 판단을 기록하지 않았다. 소유자가 실제 검토한 뒤 해당 근거와 판단을 직접 기록할 때까지 **PENDING**을 유지한다. 새 테스트나 benchmark 실행 결과를 추가하지 않는다.
