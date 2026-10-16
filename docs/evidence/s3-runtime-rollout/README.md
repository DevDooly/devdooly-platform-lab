# S3 transport 운영 반영과 실제 이미지 SDK 읽기

애플리케이션 source `74a8e98844a8fea0653951136ede0e7de0d7ac08`의 API/web을 [PR52](https://github.com/DevDooly/devdooly-platform-lab/pull/52), worker를 [PR53](https://github.com/DevDooly/devdooly-platform-lab/pull/53)로 순서대로 반영했다. API/web GitOps revision은 `8cc84c101d4fff62484d23ef44d517fd680b6dbc`, 최종 worker revision은 `b63fedfa62a81d03d35d3ef515e24bc8e43f414c`다. 실제 API 이미지와 전체 JAR·클래스 바이트를 연결한 뒤, **같은 이미지의 별도 JVM에서 원본 객체 3개 whole GET**을 검증했다. 운영 API JVM 내부 호출을 관측한 시험은 아니다.

기본 [Actions 38814779596](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38814779596)는 API191 + Java 예제20 = JUnit211, failure/error/skip 0이다. Jenkins45와 [publication 38815274591](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38815274591)의 같은 source를 사용했다. 격리 Garage6의 5 IT와 기본 JUnit211은 별도 검증이다. [기존 transport·Garage 증거](../s3-read-deadline/README.md)와 구분한다.

| 관측 | 실제 결과 |
| --- | --- |
| API/web | 배포 후 별도 읽기 재확인에서 source/OCI/CRI/Ready 확인. pre-merge NotReady 전환과 old exit는 미관측 |
| Worker | 새 Pod NotReady→Ready 실제 관측. 새 source/runtime 시작 확인. old worker exit code는 UNOBSERVED |
| 배포 후 보존 | 2026-10-15 23:12:57 UTC: 업무 SQL·8 jobs·16 export metadata, 원본24 + native12 whole GET, Kafka8/8/lag0 |
| 배포 JAR | 2026-10-15 23:25:02 UTC: 실제 API Pod/RS/CRI/PID/boot 연결 뒤 전체 bytes/SHA와 unique6 클래스 확인 |
| Offline | 실제 JAR로 별도4 payload classes compile, parser/body15 사례 통과. 이 offline 단계의 client/network 요청은 0 |
| 실제 SDK | 2026-10-15 23:45:37 UTC: Apache5, whole GET3, API calls3, attempts3, retries0, maxAttempts3, client close, 정상 exit0 |
| 정리 | 해당 Job·Pod·ConfigMap 2개 정리와 임시 읽기 전용 Secret·키 회수 각각 실제 검증 |
| SDK 이후 보존 | 2026-10-16 00:02:58 UTC: 업무 SQL·작업 8개·export 정보 16개, 원본 24개 + native 12개 whole GET, Kafka 8/8/lag 0, PVC·PV 각 13개·Docker 60개 보존. 임시 SDK 자원과 키 부재 확인 |

SDK canary는 배포된 OCI image에서 Spring을 시작하지 않고 실제 `S3ClientFactory`로 client를 생성했다. SDK2.55.16의 선택된 metrics를 엄격히 확인했고, 설정된 최대 시도 3회를 유지한 상태에서 실제 세 호출 모두 한 번씩 성공했다. raw 1,100 bytes, result 2,379 bytes, failures 1,438 bytes의 전체 SHA와 크기를 원본 증거와 비교했다. 임시 자격증명은 기존 단일 bucket 읽기만 허용하며 write/owner/createBucket 권한은 없었다. 삭제는 생성한 canary 자원·임시 credential에만 적용했고 원본 객체는 삭제하지 않았다. 별도 프로세스의 읽기 성공을 PUT 호환성, 장애·재시도 주입, latency/SLA 또는 부하 용량으로 확대하지 않는다.

배포 후 보존의 원본24개는 기존 8개 작업의 raw/result/failures이고 native12개는 이전 Trino 증거에 등록된 객체다. 보존 수집기는 36개 전체 bytes를 저장 사본과 비교하고 SQL/S3 쓰기나 workload 변경을 하지 않는다. 이 범위는 native 저장소의 모든 추가 객체를 조사했다는 뜻이 아니다. SDK GET3은 이 36개 중 기존 원본3개를 별도로 읽은 것이며, 서로 다른 객체 39개로 합산하지 않는다. 각 보존 관측은 해당 시점의 결과다.

최초 API/web watcher의 `APPLICATION_UID_SPEC_UNCHANGED` 실패는 그대로 보존했다. 당시 Application snapshot이 없어 원인은 UNPROVEN이다. 별도 `POST_DEPLOY_READ_ONLY_APIWEB_RECONCILIATION` 통과를 원래 watcher 성공으로 바꾸지 않았다. worker watcher는 통과했으나 원래 collection은 종료 후 unit의 ControlGroup 검증에서 실패했다. 후속 실측에서 빈 ControlGroup과 같은 성공 종료를 확인한 `POST_EXIT_SUCCESS_WATCH_COLLECTION_RECONCILIATION`으로 증거를 연결하고 이미 종료한 전용 unit 하나만 정리했다. old worker의 실제 exit code는 확인하지 못했다.

최초 SDK 이후 보존 수집도 whole GET 전에 `FIXED_SAFE_GARAGE_KEY_INVENTORY`로 실패했다. 수집기가 Garage ListKeys의 실제 다섯 필드를 두 필드로 잘못 가정한 계약 오류를 확인했고, 원래 실패 기록을 보존한 별도 수집기에서만 실제 형식 검사와 전체 row 비교를 교정했다. 이 실패를 원본 데이터 변경이나 S3 GET 실패로 해석하지 않는다.

API image index는 `sha256:e128652b6a28704bc2cb0a1e8bec318948df8dd467ed660b12d22c921d720399`, web은 `sha256:12b2220ffce0b5ec765f8a98a042579f3546338878f140e249580c6488db847f`다. anonymous registry/index→amd64→config/CRI와 실제 Pod source를 묶었다. PropertiesLauncher를 바꿀 수 있는 image loader/JVM 환경 이름 부재도 별도로 검증했으며 환경 값은 공개하지 않는다.

실제 API JAR는 92,724,910 bytes, SHA-256 `bae57d6556f93d52699ba687dc573e99986beffa012f902534a4c594e4e5dbad`였다. 읽기 전후 같은 process·파일 identity와 전체 SHA를 확인했으며 collector는 JAR/SDK/Spring을 실행하지 않았다. 기존 compiler 출력의 `sourceCommit:null`, `deployedImageVerified:false`는 수정하지 않고 실제 attestation으로 source74와 연결했다. 새 교차 기록 비교에서 앞선 source918f 격리 Garage6의 JAR 전체 SHA·크기와 같았지만, 같은 commit·환경을 뜻하지 않는다. 기존 `historicalGarageEvidenceLinked:false`와 연구용 b7fd JAR의 source 미관측 기록도 그대로다.

[공개 요약 JSON](summary.json)은 count·source·digest·관측 scope만 담는다. SQL·객체 키·Pod/unit UID·주소·경로·credential·환경 값은 공개하지 않는다. 먼저 동결한 SDK `NOT_RUN` 증거는 당시 기록으로 보존하고, 이 새 버전은 실제 별도 실행·정리·후속 보존 receipt에 근거한다.
