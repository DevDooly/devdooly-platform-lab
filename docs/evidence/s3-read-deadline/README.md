# S3 응답 전체 읽기 제한과 Garage 격리 검증

AWS SDK의 동기 HTTP transport를 `UrlConnectionHttpClient`에서 `Apache5HttpClient`로 바꾸고, 느리게 계속 도착하는 응답 본문을 읽을 때도 호출 제한 안에서 중단되는지 검증했다. SDK는 `2.55.16`을 유지했다. 실제 Linux 기본 회귀와 별도 Garage 시험은 통과했으며 **이 기록은 미니 PC 운영 배포 검증이 아니다.**

## 실제 결과

[GitHub Actions 실행 38810996381](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38810996381), 소스 [`918f0e791591abdc10d0b166f4d5c8181114686b`](https://github.com/DevDooly/devdooly-platform-lab/commit/918f0e791591abdc10d0b166f4d5c8181114686b)의 저장된 결과를 대조했다. 기본 검증과 선택형 S3 시험은 별도 job이며 두 결과를 각각 확인했다.

| 검증 | 실제 결과 | 범위 |
| --- | --- | --- |
| 기본 Linux JUnit | 30 suites, 211개, 실패·오류·skip 0 | API와 독립 Java 예제의 기본 회귀 합계 |
| `GarageRawSourceIT` | 4개, 실패·오류·skip 0 | H2 MariaDB mode와 실제 Garage |
| `VerifiedResultExportIT`의 선택 사례 | 1개, 실패·오류·skip 0 | 실제 MariaDB와 실제 Garage |
| 자체 시험 자원 종료 | 컨테이너 3개 종료, 두 relay 종료·join | 강제 kill과 자동 시험 재시도 없음 |

원본 읽기 시험 네 개 모두가 실제 MariaDB를 사용한 것은 아니다. 이 네 사례는 실제 SDK의 PUT·GET·HEAD·LIST·DELETE와 전체 바이트 검증, DB 표시 실패 뒤 객체 재검증, 손상 객체 보존 및 dispatch 방지, 같은 작업의 재접수 보존을 다룬다. export 사례는 실제 MariaDB에서 결과·실패 파일의 저장 확인 뒤 슬롯을 해제하고, 반복 호출이 다음 작업의 슬롯을 해제하지 못하는지 검사한다. 다섯 시험은 운영 데이터 대신 새 schema·bucket·key와 합성 입력을 사용했다.

시험한 adapter class와 패키징된 API JAR 안의 class가 같음을 확인했다. JAR은 `92,724,910` bytes, SHA256은 `bae57d6556f93d52699ba687dc573e99986beffa012f902534a4c594e4e5dbad`다. 이는 OCI 이미지나 미니 PC에서 실행한 프로세스의 검증을 대신하지 않는다.

## 읽기 제한과 그대로 둔 정책

[S3ClientFactory](https://github.com/DevDooly/devdooly-platform-lab/blob/918f0e791591abdc10d0b166f4d5c8181114686b/apps/api/src/main/java/io/github/devdooly/platformlab/jobs/S3ClientFactory.java)는 전체 호출 30초·한 시도 10초·연결 3초·socket 대기 8초와 최대 시도 3회 설정을 그대로 유지한다. 최대 시도 3회는 초기 시도와 최대 두 재시도를 뜻하며 모든 요청이 세 번 실행된다는 뜻은 아니다. Garage용 선택적 request checksum 정책과 응답 전체 크기·SHA256 검증도 유지했다.

[S3ManagedReadDeadlineTest](https://github.com/DevDooly/devdooly-platform-lab/blob/918f0e791591abdc10d0b166f4d5c8181114686b/apps/api/src/test/java/io/github/devdooly/platformlab/jobs/S3ManagedReadDeadlineTest.java)의 두 loopback 사례는 socket inactivity timeout보다 짧은 간격으로 응답을 계속 보낸다. 시험에서는 전체 호출 제한을 1.5초로 지정하고 1~4초 안의 timeout, 첫 GET 한 번·PUT 0회, 서버가 관측한 첫 응답 연결 종료, 같은 client의 다음 정상 읽기까지 요구한다. 이 시험값은 운영 30초 기본값을 줄인 설정이나 운영 지연 SLA가 아니다. 느린 응답 fixture는 loopback HTTP 서버이며 위의 실제 Garage 호환성 다섯 사례와 구분한다.

구형 transport를 사용한 Linux 실패 두 건에서는 timeout 원인이 관측돼도 호출 종료까지 각각 `110.141초`, `110.317초`가 걸려 기존 1~4초 검사를 벗어났다. 같은 구형 transport의 Windows와 다른 Cloud 실행에서는 통과한 결과도 있어 항상 재현되는 현상이라고 단정하지 않는다. 새 transport의 통과로 이전 실패 기록을 지우거나 JDK 내부의 단일 원인까지 확정하지 않았다.

## 격리와 공개 자료

GitHub runner의 새 internal Docker network를 사용하고 Docker port를 공개하지 않았다. host의 numeric loopback listener 두 개가 실제 소유 container·network endpoint에만 연결하며, 시험 전 TCP positive control과 실행 후 종료·join을 확인했다. relay는 payload를 해석하거나 기록하지 않았다. 미니 PC에는 연결하지 않았다. 앞선 port guard 실패의 원인은 이 성공으로 확정하지 않는다.

[summary.json](summary.json)은 실제 실행의 공개 summary `4,624` bytes를 수정 없이 복사한 파일이다. SHA256은 `5b3a6e9e17600112595942e94ea1c661af0a9cd0f1dd63bed932a800b02d50a0`이며 관측 시각은 `2026-10-15T21:39:06.044005Z`다. 기본 JUnit 211개 합계는 별도로 내려받은 30개 XML을 대조한 결과이고, 이 JSON의 `tests:5`와 합치거나 서로 바꾸어 표기하지 않는다. raw XML·로그·SQL·주소·port·credential 값은 공개하지 않는다.

이 검증으로 운영 API·worker의 이미지 pin이나 데이터를 바꾸지 않았다. 실제 운영 전환에는 같은 검증 소스의 OCI 확인, 단계별 API·웹→worker 변경, 기존 데이터와 자원 보존 및 실제 S3 동작 확인이 별도로 필요하다.
