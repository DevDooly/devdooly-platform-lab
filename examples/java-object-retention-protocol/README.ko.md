# 객체 보존·삭제 intent의 합성 Java 모델

이 예제는 Java 21의 immutable RAM 상태에서 객체 보존과 삭제 intent의 순서를 설명한다. 한 합성 run, `RAW_SAMPLE`·`RESULT_SAMPLE` 두 고정 alias, 합성 세대 번호만 다룬다. 실제 key·bucket·run ID·주소·자격증명, 기존 inventory/plan JSON을 받는 입력 경로는 없다. main 코드는 JDK만 사용하며 DB·저장소 adapter·CLI·실제 삭제 기능은 없다.

기존 [객체 참조 보호 계획기](../../infra/maintenance/OBJECT_REFERENCE_PLAN.md)는 운영 DB run·unknown 객체를 모두 KEEP하고 `applyEnabled:false`를 유지한다. [기존 격리 Garage GC](../../docs/runbooks/object-reference-gc.md)는 별도 실제 시험이다. 그 KEEP/자연 GC 결과를 이 모델의 운영 검증이나 삭제 허가로 사용하지 않는다.

## 설명하려는 문제

무참조 계획을 만든 뒤 새 참조나 backup pin이 생길 수 있다. tombstone과 저장소 요청은 한 transaction으로 묶이지 않으며, timeout이면 실제 결과도 모를 수 있다. 부분 확인 뒤 run을 다시 열거나 같은 요청을 자동 재발행하면 이 경계를 숨기게 된다.

모델은 다음 순서를 보여준다. `propose`의 plan은 허가가 아니다. `tombstone`이 실제 현재 상태의 revision·대상 세대·300초 기한·retention/replay horizon/outbox/reference coverage의 합성 안전성·현재 참조/pin을 다시 확인한다. 같은 RAM 전이에서 run을 닫고 intent와 객체별 action을 함께 만든다. 모든 참조 생성자와 backup 절차가 이 경계에 참여하고 backup pin을 먼저 확보한다는 모델 가정이다.

## 상태와 결정

run 상태는 `ACTIVE → TOMBSTONED → COMPLETE`다. `COMPLETE`여도 intent와 객체 결과를 남기며 ACTIVE로 되돌리는 전이와 run ID 재사용 기능은 없다. `initial`은 독립 합성 시나리오를 시작하는 factory이며 기존 run의 재접수·복원을 뜻하지 않는다. 실제 시스템 전체의 run ID 유일성 저장은 구현하지 않는다.

객체별 상태는 `READY`, `IN_FLIGHT`, `UNKNOWN`, `ABSENT_CONFIRMED`다. `ActionId`는 고정 intent alias와 정확한 객체 alias/세대를 결합한다. content hash가 같다는 이유로 다른 key를 같은 대상으로 간주하지 않는다. 이 예제의 세대 번호는 합성 identity token이며 실제 Garage의 versioning/조건부 DELETE 지원을 주장하지 않는다.

| 조건 | 결과 |
| --- | --- |
| plan 미래/300초+1ns, revision/대상 변경 | 고정 거부 사유, 입력 상태 유지 |
| retention/replay/outbox/reference coverage UNKNOWN 또는 BLOCKED | `ELIGIBILITY_BLOCKED`, intent 없음 |
| 현재 참조 또는 backup pin 존재 | 보호 사유, ACTIVE 유지 |
| tombstone 뒤 참조/pin 추가 | `RUN_CLOSED`, 원 intent/대상 유지 |
| READY action 선택 | IN_FLIGHT, 순수 action 데이터 한 개 반환 |
| 진행 중 같은 intent 재전달 | `AWAITING_RESULT`, 새 action 없음 |
| timeout/불확실 또는 같은 세대의 존재 관측 | UNKNOWN, 자동 재발행 없음 |
| UNKNOWN인 상태에서 resume | `RECONCILIATION_REQUIRED`, 새 action 없음 |
| 정확한 action/대상의 합성 부재 관측 | 해당 객체만 확인; 둘 다 확인된 때 COMPLETE |
| 같은 확인 재전달 | `REPLAY_NOOP`; 다른 intent/세대나 모순된 결과는 거부 |

참조·pin의 추가와 제거는 revision을 올린다. 따라서 추가→제거 뒤 다시 비어 보여도 옛 plan의 revision과 달라 ABA를 거부한다. 시간은 caller의 `Instant`로 비교하며 clock을 조회하거나 보정하지 않는다. 목록·set·map은 방어 복사하고 거부/no-op은 원 snapshot 객체를 유지한다.

`nextAction`은 완료한 객체를 건너뛰고 아직 미발행인 다음 객체만 선택한다. 보관한 immutable 상태를 다시 전달하는 것이 여기의 resume다. IN_FLIGHT/UNKNOWN은 재발행하지 않으며 별도의 정확한 합성 관측으로 조정해야 한다. `PRESENT_SAME_GENERATION`도 진행 중 요청의 실패를 확정하지 않으므로 UNKNOWN으로 남긴다.

## 검증 시나리오

JUnit 테스트 소스에는 다음 다섯 시나리오가 있다. 실제 실행 결과는 해당 소스 commit의 CI/실행 기록에서 확인해야 하며 테스트 파일의 존재만으로 통과를 주장하지 않는다.

1. 정확한 300초/+1ns/미래 plan, 참조 추가→제거 ABA와 바뀐 대상 세대.
2. backup pin·활성 참조·안전성 UNKNOWN/BLOCKED의 보호와 tombstone 뒤 늦은 참조/pin 거부.
3. A 확인+B UNKNOWN의 부분 결과, 존재 관측과 resume에서 재발행·재개방 없음.
4. 재전달 시 진행 중 action 중복 선택 없음, 같은 저장된 RAM 상태로 B만 재개, intent/세대 불일치 거부와 확인 no-op.
5. 두 정확한 부재 관측 전 완료 없음, 전체 확인 뒤에도 intent/대상·닫힌 상태 유지.

Java 21과 Maven 환경에서는 저장소 루트에서 다음 명령으로 이 모듈만 검증할 수 있다. 기존 Java 예제와 같은 parent 4.1.1이 JUnit·compiler/surefire plugin 버전을 관리한다. main runtime에는 Spring/서버/JMH 의존성이 없다.

```sh
mvn -B -ntp -f examples/java-object-retention-protocol/pom.xml verify
```

## 이 모델이 증명하지 않는 것

직렬 RAM 전이는 실제 DB transaction/CAS·다중 writer 차단·영속 tombstone/intent·프로세스 중단 후 복원을 구현하지 않는다. 모델 밖 actor, backup workflow, Kafka replay horizon과 outbox의 진실을 독립 검증하지 않는다. 모든 안전성 값과 부재 관측은 합성 입력이다. 실제 DB와 저장소 사이의 원자성, HTTP204/404의 의미, 네트워크 timeout 결과, 정확히 한 번의 저장소 변경을 보장하지 않는다.

`ABSENT_CONFIRMED`와 COMPLETE는 합성 모델의 논리적 부재 확인이다. 물리 블록 회수·공유 블록 보호·metadata tombstone GC·DB 파일 축소·운영 용량이나 SLA의 증거가 아니다. 운영 삭제·Secret 접근·실제 데이터 변경·기존 planner의 후보 승격으로 연결하는 코드는 없다. [AI 제안과 검토 범위](PROVENANCE.md)를 함께 읽는다.
