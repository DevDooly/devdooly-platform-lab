# Kafka 관측 공개 계약 v1 — 구현 후보

2026-10-18 · C 전용 준비. 구현/테스트/배포/게시 성공 기록이 아니다.

성공: `GET /api/kafka/observation`, HTTP 200, `Cache-Control: no-store`. 다음 **18개 필드만** 허용한다. 환경과 scope는 정확한 쌍이어야 한다.

| 필드 | 형식/조건 |
| --- | --- |
| schemaVersion | 정수 1 |
| kind | `kafka-observation` |
| synthetic | boolean true |
| environment | `ISOLATED_LAB` 또는 `MINI_PC` |
| scope | 각각 `ISOLATED_KAFKA` 또는 `DEPLOYED_KAFKA` |
| publicExecutionEnabled | boolean false |
| sourceCommit | 관측 API의 실제 소문자 hex 40자리. worker 소스/생존의 증거가 아님 |
| captureStartedAt | UTC ISO-8601, 소수 0~9자리, Z 끝 |
| capturedAt | 같은 형식, 시작 이상·최대 4초 이내·미래 금지 |
| consistency | `BOUNDED_SEQUENTIAL_READ` |
| targetFingerprint | 소문자 hex SHA-256 64자리 |
| groupState | `STABLE` 또는 `EMPTY` |
| partition | 정수 0 |
| commitState | `OBSERVED` 또는 `NO_COMMIT` |
| logStartOffset | 정수 0~9007199254740991 |
| readCommittedEndOffset | 같은 범위, start 이상. READ_COMMITTED latest의 LSO이며 비격리 log-end가 아님 |
| committedOffset | OBSERVED면 start 이상·end 이하의 정수, NO_COMMIT면 null |
| lag | OBSERVED면 end−committed, NO_COMMIT면 null. 실제 0과 미관측을 구분 |

공개 Java offset는 `long`, nullable committed/lag는 `Long`이다. 모든 중첩/최상위 추가 필드·중복 JSON key·bool을 정수로 사용·NaN/Infinity·미래/정규화되는 날짜·8KiB 초과는 거부한다. 관측 API/source/수집 구간의 기록이며 DB와 broker의 원자 snapshot·현재 worker 생존·현재 source·SLA를 뜻하지 않는다.

targetFingerprint는 UTF-8 canonical 문자열 `{"clusterId":"<private>","group":"<private>","partition":0,"schemaVersion":1,"topicUuid":"<private>"}`의 SHA-256이다. cluster-id와 topic UUID는 Kafka Uuid의 canonical 문자열, group은 검증한 ASCII 설정값이다. raw identity/주소/credentials/member/오류 원문을 공개하지 않는다. 지문은 대상 변경 감지용이며 인증/서명/비밀값 보호를 증명하지 않는다. 대상 지문 변경은 같은 시계열로 자동 병합하지 않는다.

실패: HTTP 503/no-store, 정확히 세 필드 `schemaVersion:1`, `kind:kafka-observation-error`, `code:<아래 enum>`. query string/body로 대상 설정을 받지 않으며 해당 요청은 400/no-store `INVALID_CONFIGURATION`; POST는 405다. 미설정은 0 lag 성공 대신 NOT_CONFIGURED다.

```text
NOT_CONFIGURED
INVALID_CONFIGURATION
CAPTURE_BUSY
OBSERVER_POISONED
CAPTURE_TIMEOUT
KAFKA_UNAVAILABLE
TARGET_UNVERIFIED
GROUP_UNAVAILABLE
GROUP_UNSTABLE
OFFSETS_UNVERIFIED
CLOCK_UNVERIFIED
CLOSE_UNVERIFIED
```

실제 Kafka 4.2.1 no-commit 표현은 지정한 partition의 `{tp:null}`이다. 기존 제안의 raw null metadata 거부와 빈 map 허용을 그대로 구현하지 않는다. 응답 keyset이 정확히 `{requestedTP}`이고 value가 null인 경우만 좁은 adapter에서 NO_COMMIT으로 정규화한다. raw 빈 map은 partition별 오류가 생략된 결과일 수 있으므로 거부한다. 다른 key/partial earliest/latest/항목별 오류도 실패다. 이 정규화는 공개 committed/lag를 null로 유지하며 0을 만들지 않는다. 공식 근거: [Kafka 4.2 ListConsumerGroupOffsetsResult](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/admin/ListConsumerGroupOffsetsResult.html), 로컬 4.2.1 `ListConsumerGroupOffsetsHandler`의 NONE/committedOffset<0 → map.put(tp,null), partition error → key 생략 분기 javap.

read 예산 3초는 Admin.create/DNS를 포함한다. 외부 caller 대기는 close 여유 포함 최대 4초다. service당 최초 opt-in 요청에서만 단일 소유 daemon worker를 시작하고 같은 thread에서 create/read/close한다. 늦거나 정리가 불확실한 작업은 poison/quarantine으로 이후 client 생성 0을 유지하고 이전 성공 시각을 만들지 않는다. Admin.close(Duration)의 void 정상 반환을 전체 network thread 종료 확인이라고 표현하지 않는다. close의 실제 보장 범위·불확실성은 구현 노트/공식 source에 별도로 연결하며 공개 DTO에 `clientThreadsStopped:true` 같은 필드를 만들지 않는다.

host/browser는 실패/timeout/과거 기록/잘못된 응답에서 마지막 유효 기록과 원래 시각을 유지한다. Mini PC 자동 게시에는 MINI_PC/DEPLOYED_KAFKA만 허용한다. ISOLATED_LAB 결과는 별도 시험·로컬 표시로 한정한다. 현재의 job-observation v1·worker·readiness·RBAC·운영 GitOps 값은 변경하지 않는다.
