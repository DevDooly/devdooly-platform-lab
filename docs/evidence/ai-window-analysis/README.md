# AI와 함께 검증한 UTC 구간 계산 개선

**2026-10-15, 독립 합성 Java 예제의 테스트와 로컬 Windows JMH 측정을 완료했습니다.** 같은 결과를 계산하는 O(n²) 기준 구현을 O(n log n) sweep으로 바꾸고, UTC offset을 버리는 별도 오류를 테스트로 재현·수정했습니다. 회사 수율 공식·업무 데이터와 기존 운영 ETL은 사용하거나 변경하지 않았습니다.

[예제와 재현 명령](../../../examples/java-window-analysis/README.md), [계산 계약](../../../examples/java-window-analysis/DESIGN.md), [AI 활용·사람 검토 상태](../../../examples/java-window-analysis/PROVENANCE.md), [전체 공개 근거](summary.json), [페이지용 실제 관측 JSON](../../../apps/lab-web/public/observations/ai-window.latest.json)을 함께 제공합니다.

## 무엇을 개선했나

여러 관측 세션을 고정 UTC 시간창에 맞춰 **총 관측 시간과 최대 동시 세션 수**를 구합니다. 기준 구현은 모든 endpoint 사이 구간에서 모든 세션을 다시 검사합니다. 개선 구현은 같은 시점의 시작/종료 delta를 합친 뒤 시간 순으로 한 번 순회합니다. 정렬·TreeMap 갱신 비용을 포함하여 O(n log n)으로 표기합니다.

구간은 `[시작, 종료)`이므로 `[0,10)`과 `[10,20)`은 겹치지 않습니다. 기록 시계 오차가 `기록-기준`이라면 그 값을 빼고, `+09:00` 같은 offset은 실제 UTC timeline 변환에 반영합니다. 의도적 오류 fixture는 `09:00:00+09:00`의 offset을 버려 관측 시간을 0초로 잘못 계산하며, 올바른 구현의 10초 결과와 별도 테스트에서 대조합니다. 잘못된 parser와 올바른 parser의 속도를 비교한 실험은 아닙니다.

입력은 최대 4,096세션, 시간창은 최대 1시간, 알려진 시계 오차는 ±5분입니다. null·역전/동일 endpoint·offset 없는 timestamp·중복 ID·범위 초과 입력을 거부합니다. 큰 날짜 차이를 먼저 nanosecond로 바꾸지 않고 제한을 확인해 overflow를 피합니다.

## 실제 검증과 측정

- Java 테스트 **20개**, 실패·오류·skip 0. true integer endpoint로 먼저 답을 구하는 독립 64ns 격자 oracle의 고정 seed 2,000사례와 순서 변경, UTC/오차/인접·중첩·clipping 경계 사례를 확인했습니다.
- sparse/nested 두 분포의 128·512·2,048·4,096개 입력은 독립적인 닫힌 형태 기대값에 대조했습니다. sparse는 `총 시간=n×11ms, 최대 동시=1`, nested는 `총 시간=n×1ms, 최대 동시=n`입니다.
- 실제 JMH **1.37**, 16개의 메서드/parameter 조합 × 3 forks, 각 fork에서 측정 interval 5개로 총 **48개 fork JVM·240개 interval**을 기록했습니다. 결과 validator Python 테스트 3개도 통과했습니다.
- Windows 11 AMD64, 논리 CPU 16, Microsoft OpenJDK **21.0.9+10-LTS**, G1 GC, 고정 heap 256MiB, 1 thread, Asia/Seoul timezone입니다. CPU·메모리 cgroup 제한은 적용하지 않았고 미니 PC에서 측정하지 않았습니다.
- 조합별 warmup 2×500ms, 측정 5×500ms입니다. 실제 실행은 **11:08:12.086233~11:11:33.912606 UTC, 201.826초**였습니다. endpoint 자료구조 생성·정렬을 측정하며 UTC 파싱·fixture 생성·I/O·기대값 검증은 trial setup으로 제외했습니다.

아래 값은 **평균 ± JMH scoreError, us/op**입니다. scoreError는 JMH가 Student t 분포로 계산한 평균의 99.9% 신뢰구간 반폭이며, 표본·실험 조건에 영향을 받습니다. [평균 오차 계산](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/util/AbstractStatistics.java)과 [99.9% 결과 설정](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/results/Result.java)을 확인할 수 있습니다. 배수는 두 평균의 비율입니다.

| 합성 분포 | 세션 수 | 기준 O(n²), us/op | sweep O(n log n), us/op | 관측 평균 비율 |
|---|---:|---:|---:|---:|
| sparse | 128 | 77.338 ± 42.425 | 4.918 ± 0.273 | 15.72× |
| sparse | 512 | 1,303.412 ± 678.187 | 25.502 ± 0.651 | 51.11× |
| sparse | 2,048 | 11,933.210 ± 10,205.116 | 250.923 ± 11.674 | 47.56× |
| sparse | 4,096 | 30,221.977 ± 7,982.477 | 632.113 ± 12.280 | 47.81× |
| nested | 128 | 13.720 ± 0.929 | 2.834 ± 0.073 | 4.84× |
| nested | 512 | 209.586 ± 6.802 | 14.715 ± 0.422 | 14.24× |
| nested | 2,048 | 2,973.312 ± 57.831 | 98.156 ± 9.225 | 30.29× |
| nested | 4,096 | 12,918.556 ± 2,139.630 | 331.891 ± 7.542 | 38.92× |

4,096개에서 GC allocation 평균은 sparse **721,544.25→524,384.71 B/op**, nested **360,869.93→325,780.60 B/op**이었습니다. 이는 연산당 할당량이며 RSS·최대 메모리 사용량이나 메모리 limit를 뜻하지 않습니다. 모든 fork의 시간 표본과 조합별 평균 할당량은 [summary.json](summary.json)에 실제 원본에서 추출해 보존했습니다.

**sparse의 일부 기준 구현 측정은 오차가 큽니다.** 예를 들어 2,048개는 평균 11,933us에 scoreError 10,205us입니다. 짧은 warmup이 JIT 안정성을 보장하지 않으며 로컬 호스트의 영향을 분리 측정하지 않았습니다. 이 결과는 고정된 합성 분포와 실행 조건의 비교이고 median·tail latency·운영 처리량·SLA·최대 수용량이나 보장된 개선 배수가 아닙니다.

## 출처와 실패 기록

측정 대상은 아직 커밋하지 않은 private overlay였습니다. 따라서 `sourceCommit`은 **null**이며 기존 운영 앱 commit을 예제 출처로 사용하지 않았습니다. 상대 경로·크기·각 파일 SHA-256 manifest를 canonical JSON으로 만든 hash가 아래 source tree hash입니다. Git tree SHA가 아니며 실제 통합 commit은 후속 PR에서 별도로 연결해야 합니다. AI 제안과 agent 검토를 저장소 소유자의 **사람 검토 완료**로 표현하지 않습니다.

후속 Git 통합에서는 [게시 소스 일치 검사](published-source-equivalence.json)로 commit [`55483931`](https://github.com/DevDooly/devdooly-platform-lab/tree/554839313f5b19311dbd00ab8631d47d36e30777/examples/java-window-analysis)의 16개 파일 전체 바이트가 측정 manifest와 같음을 확인했습니다. 이는 소스의 일치 근거이며 해당 commit에서 JMH를 다시 실행하거나 미래 CI의 JAR이 측정 JAR과 같다고 주장하는 기록은 아닙니다. 측정 당시 `sourceCommit:null`과 사람 검토 `PENDING`은 유지합니다.

| 증거 | SHA-256 |
|---|---|
| 측정 소스 manifest | `3f4a5f710d78464214e823bdf8581bdde9dfc015cf08315a40d67fd78fb3c21e` |
| 실행 JAR, 2,892,528 bytes | `983019bbb4a06cc5011433e31233bb713fc8e5a297e32f8936ad4d2d18145e68` |
| 원본 JMH JSON, 129,818 bytes | `85305fe40f5a58ce23e69a7566f40b81628a5355ac1517d47ee318b4d60c5c82` |
| fixture TSV | `c998b73ee69673632576e40d8947a05fff27411231b0e0bdef59929af609c524` |

원본 JSON·stdout/stderr·실행 전후 metadata·실행 JAR·JUnit XML은 private 증거로 보존했고 공개 JSON에는 경로·환경 변수·인증 정보 없이 필요한 수치와 hash만 추출했습니다. runner는 전체 16조합·3 forks·5 interval·고정 옵션·finite 시간/할당량과 측정 전후 소스/JAR 불변을 검증했습니다.

성공 전 실패 기록 3개도 보존했습니다. 첫 Maven 실행은 PowerShell 옵션 인용 오류로 빌드 전에 실패했고, 다음 실행은 20개 테스트 통과 후 상위 POM의 shade transformer 병합 때문에 packaging에서 실패했습니다. 첫 runner 실행은 metadata의 파일 크기 조회 오타로 **JMH fork 0개**에서 실패했습니다. 원인을 고치고 회귀를 추가한 새 디렉터리에서 첫 실제 JMH 전체 측정을 수행했으며 전체 benchmark를 반복하여 유리한 결과를 고르지 않았습니다.

공식 자료: [JMH 1.37](https://github.com/openjdk/jmh/tree/1.37), [반환값 소비](https://github.com/openjdk/jmh/blob/1.37/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java), [fork 분리](https://github.com/openjdk/jmh/blob/1.37/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java), [Java 21 OffsetDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/OffsetDateTime.html).
