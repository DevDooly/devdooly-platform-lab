# Java로 검증하는 UTC 구간 계산 개선

서로 다른 시계 오차와 시간대 표기를 가진 **합성 관측 세션**을 UTC로 정규화하고, 고정 시간창에서 관측된 총 시간과 최대 동시 세션 수를 계산합니다. 같은 결과를 내는 O(n²) 기준 구현과 O(n log n) sweep 구현을 비교합니다. `+09:00`을 버려 잘못 해석하는 별도 오류 예제도 포함합니다.

회사 코드·데이터·수식에서 추출한 예제가 아닙니다. 기존 ETL의 `SensorProcessor`는 이미 O(n)이며 이 프로젝트의 개선 대상이 아닙니다. 운영 API·DB·Kafka·객체 저장소와 연결하지 않는 독립 Java 21 예제입니다.

## 직접 확인하기

Java 21과 Maven을 사용합니다. 기존 저장소의 Spring Boot 4.1.1 parent에서 Java/JUnit/빌드 도구 버전 관리를 재사용하지만 Spring 런타임은 의존하지 않습니다. JMH core와 annotation processor는 [공식 1.37 tag](https://github.com/openjdk/jmh/tree/1.37)에 고정했습니다.

```sh
cd examples/java-window-analysis
mvn -B verify
java -jar target/benchmarks.jar -l
java -cp target/benchmarks.jar io.github.devdooly.examples.window.FixtureManifest
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
```

`WindowAnalysisTest`는 64ns 정수 격자에서 독립적으로 답을 구하는 2,000개 합성 사례, 입력 순서 변경, 경계 사례, 최대 4,096개 입력의 닫힌 형태 기대값을 확인합니다. `inputOffsetLossIsAnExplicitSeparateRegression`은 올바른 계산 10초와 의도적으로 잘못된 계산 0초를 함께 고정합니다. 자세한 계약은 [DESIGN.md](DESIGN.md), AI 사용 범위는 [PROVENANCE.md](PROVENANCE.md)에 있습니다.

## JMH 3 forks 실행

빌드·검증 후 **실제 소스 commit SHA**와 새 결과 디렉터리를 지정합니다. 아직 커밋하지 않은 private overlay를 측정한다면 `--source-commit`을 생략하고 null과 `UNCOMMITTED_PRIVATE_OVERLAY`로 기록합니다. 아래 경로는 예시이며 기존 결과를 덮어쓰지 않습니다.

```sh
python3 -B scripts/run_jmh.py \
  --java /path/to/java-21/bin/java \
  --source-commit <40자리-실제-commit-SHA> \
  --output-dir /path/to/new-window-jmh-result
```

128·512·2,048·4,096개 × sparse/nested × 두 알고리즘의 16조합을 각 3개의 새 JVM으로 실행합니다. 조합마다 warmup 2×500ms, 측정 5×500ms, 1 thread, 평균 시간 `us/op`, 고정 heap 256MiB·G1 GC, GC profiler의 `B/op`을 기록합니다. 이론상 반복 시간의 합은 168초이며 JVM 시작·fixture 검증·GC 비용은 별도입니다. runner는 420초 후 자신이 시작한 benchmark process group을 종료합니다.

실제 시간 측정 범위에는 endpoint 자료구조 생성과 정렬이 포함됩니다. UTC 문자열 파싱·fixture 생성·파일 I/O·기대값 검증은 `@Setup(Level.Trial)`에서 수행하여 측정에서 제외합니다. 두 메서드 모두 **정확한 동일 입력**을 분석하며 반환값은 JMH가 소비합니다. 의도적으로 잘못된 UTC parser는 성능 비교에 사용하지 않습니다.

결과는 `jmh.json`의 평균·오차·fork별 rawData, `fixtures.tsv`의 입력/정규화/결과 SHA-256, `metadata-before/after.json`의 JDK·JAR·실제 소스 파일 hash, 실행 stdout/stderr로 남깁니다. `sourceCommit`은 실행자가 제공한 값이며 소스 파일 hash와 구별됩니다. runner의 결과 검증은 16조합·3 forks·각 5회·고정 옵션·GC allocation 지표를 모두 요구합니다.

이 모듈 자체는 CPU·메모리 cgroup이나 운영 서버 보호를 구성하지 않습니다. 미니 PC에서 실행한다면 운영 서비스와 분리된 자원 범위에서 1 CPU/768MiB 및 host 여유량·OOM·swap guard를 별도로 적용하고, 무거운 CI와 겹치지 않게 실행해야 합니다. 결과를 운영 ETL 처리량, SLA, 최대 수용량으로 일반화하지 않습니다. **실제 실행 결과가 없으면 속도 개선 배수나 JMH 검증 완료를 주장하지 않습니다.**

## 공식 참고 자료

- UTC timeline 변환과 offset 보존: [Java 21 OffsetDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/OffsetDateTime.html).
- 반환값을 소비하는 이유: [JMH dead code sample](https://github.com/openjdk/jmh/blob/1.37/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).
- 상태·반복·JVM 분리 설계: [constant folding](https://github.com/openjdk/jmh/blob/1.37/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java), [loops](https://github.com/openjdk/jmh/blob/1.37/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java), [forking](https://github.com/openjdk/jmh/blob/1.37/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java).
- 독립 Maven JAR 구성: [공식 JMH archetype POM](https://github.com/openjdk/jmh/blob/1.37/jmh-archetypes/jmh-java-benchmark-archetype/src/main/resources/archetype-resources/pom.xml).
