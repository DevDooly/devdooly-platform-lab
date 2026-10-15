# Spring Boot 조회 API

Java 21, Spring Boot 4.1.1, Maven Wrapper 3.3.4 (공식 bin 방식) / Maven 3.10.0을 사용합니다. JPA와 Flyway로 실행 결과와 입력별 판정을 MariaDB에 저장합니다. 회사 데이터·코드를 사용하지 않는 합성 센서 예제입니다.

## 검증과 실행

```sh
./mvnw verify
```

Windows에서는 `mvnw.cmd verify`를 사용합니다. 테스트는 별도 `test` profile의 H2이며 MariaDB 운영 검증을 대신하지 않습니다.

MariaDB 실행 정보는 환경변수로 주입합니다. 비밀번호는 저장소에 넣지 않습니다.

```sh
export SPRING_DATASOURCE_URL=jdbc:mariadb://127.0.0.1:3306/platform_lab
export SPRING_DATASOURCE_USERNAME=platform_lab
export SPRING_DATASOURCE_PASSWORD='your-local-password'
./mvnw spring-boot:run
```

기본 8080 포트입니다. 같은 스키마에 다른 애플리케이션을 연결하지 않습니다. 실제 서버 설치·DB 생성은 환경 점검 이후 별도 인프라 절차를 따릅니다.

MariaDB 없이 로컬 코드·HTTP를 확인할 때만 명시적으로 다음 profile을 켭니다. DB는 Git 제외 `target/` 아래에 저장됩니다.

```sh
./mvnw spring-boot:run -Dspring-boot.run.profiles=local-dev
```

## 구현한 범위

- `GET /api/demo/runs`, `GET /api/demo/runs/{id}`: 저장된 합성 작업 결과 조회
- `GET /api/platform/summary`, `GET /api/platform/releases`: 실제 런타임 정보와 미구성 도구 상태
- `GET /actuator/health`, `/actuator/health/readiness`: DB를 포함한 health 점검
- 고정 seed 42의 12건: 성공 7, 실패 3, 중복 2, 대기 0
- 최초 시작 시 고정 run ID를 저장하고 이후 시작에서는 이미 저장된 결과를 재사용

공개 실행 POST는 제공하지 않습니다. S3 원본 adapter와 Kafka publisher/worker는 명시적 내부 호출과 격리 검증을 추가했으며 기본 앱에는 자동 연결하지 않습니다. 기본 verify 78개와 별도 실제 Kafka·MariaDB·Garage IT 4개를 통과했습니다. [Kafka 중단·재전달 결과](../../docs/evidence/kafka-redelivery/README.md), [실행 절차](../../docs/runbooks/kafka-redelivery.md)를 연결합니다. 결과·실패 파일 export도 명시적 내부 coordinator로 구현했고 전체 두 파일 확인 후에만 슬롯을 해제합니다. 기본 verify는 97개, 별도 실제 export IT는 6개 통과했습니다. [export 근거](../../docs/evidence/result-export/README.md), [실행 절차](../../docs/runbooks/result-export.md)를 따릅니다. 상시 worker/export 실행기와 운영 배포는 후속입니다. [S3 사용·검증 절차](../../docs/runbooks/s3-source-storage.md)를 참고합니다. 현재 bootstrap은 단일 앱 인스턴스 시작을 전제로 합니다. 여러 replica가 동시에 최초 시작하는 배포 전에는 DB 잠금/별도 seed Job을 추가해야 합니다.

[API 계약](../../docs/contracts/demo-api.md), [독립 시나리오](../../tests/scenarios/sensor-validation-v1.json), [검증 기록](../../docs/evidence/api-mvp/README.md)을 참고합니다.

## 버전 근거

2026-10-11 공식 [Spring Boot 요구사항](https://docs.spring.io/spring-boot/system-requirements.html)과 [Maven 다운로드](https://maven.apache.org/download.cgi), [Maven Wrapper 3.3.4](https://maven.apache.org/tools/wrapper/)를 확인했습니다. Java 21은 Boot 4.1.1의 지원 범위에 포함됩니다. Maven 배포 SHA512를 내려받아 확인한 후 wrapper 배포 SHA256에도 고정합니다.

Wrapper jar는 공식 Maven Central 체크섬과 대조하고 wrapperSha256Sum을 고정했습니다. Java가 Maven ZIP을 검증·압축 해제하므로 비루트 JDK container에서 별도 unzip 설치가 필요하지 않습니다.
