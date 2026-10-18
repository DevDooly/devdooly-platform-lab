# Kafka 관측 격리 IT 실행기

현재는 **C에서 작성한 미실행 후보**다. Python 경계 테스트, Maven/Java, Docker/Kafka, workflow를 실행하지 않았다. 실제 성공 결과가 생기기 전까지 배포·운영 검증으로 표시하지 않는다.

GitHub-hosted Ubuntu24.04에서 수동 opt-in으로만 실행한다. 기본값은 false이고 다른 Spark/S3/Cloud/Iceberg opt-in과 함께 선택할 수 없다. 기존 API verify 뒤 같은 runner에서 실행하며 Mini PC·기존 Docker/K3s·기존 데이터를 사용하지 않는다.

## 실행 순서

1. `prepare`는 source manifest의 API106개/실행기/경계 테스트/image-lock을 검사한다. inherited Maven 설정과 환경을 비우고 task 전용 user/global settings, 공개 repository, wrapper home으로 **정상 API verify**를 수행한다. settings에는 자격증명·proxy·profile 없이 `mirrorOf=*`의 `https://repo.maven.apache.org/maven2` mirror만 둬 transitive POM의 다른 repository도 차단한다. 기존 POM/래퍼의 공개 Maven Central 의존성만 준비한다. Windows `.m2`·도구·target·credential을 전송하지 않는다.
2. wrapper가 실제 만든 Maven distribution을 owned wrapper-home 아래에서 유일하게 찾는다. 실제 Maven3.10.0/Java21과 정상 API XML의 **정확한216개 actual testcase/failure0/error0/skip0**을 검사한다. 현재 base191+Service19+Controller6이며 source/test 변경 때는 새 후보에서 다시 검토한다. tool 전체와 immutable JAR/POM/ZIP payload를 고정한다. `maven.user.home`은 현재 checked-in wrapper3.3.4 JAR에서 system property 우선 분기를 확인한 뒤 `MAVEN_OPTS`로 전달한다. 경로 hash를 추정하지 않는다.
3. `run`은 준비 상태·source/tool/payload를 재검사하고 Docker의 **로컬 Unix socket**만 사용한다. 빈 task 전용 Docker config를 지정해 Docker context/registry credential 환경을 상속하지 않는다. 기존 image-lock의 Kafka4.3.1/Temurin21 JDK digest를 pull·확인한 뒤에는 다운로드하지 않는다.
4. 새 internal network와 bounded tmpfs의 singleton KRaft broker를 만든다. broker/controller는 자기 namespace의 숫자 loopback19092/19093만 듣는다. TCP 준비 확인은 exact owned broker CID 안에서 실행한다. 외부 포트·host network·운영 bind mount/PVC는 없다.
5. test JVM은 exact broker CID의 network namespace에 들어간다. source allowlist만 새 API 폴더에 복사해 **기존 target 없이 offline fresh compile**하고 KafkaObservationIT의 고정 method **1개만** 실행한다. task의 공개 Maven cache/tool 및 빈 settings만 제한된 경로로 mount한다. test process는 runner UID/GID, read-only root, cap drop, CPU1/memory1GiB/pids256이다.
6. 실제 JVM container exit0, 새 XML의 IT1/failure0/error0/skip0 및 Linux/Java21, source/tool/payload 전후 일치, owned broker/JVM/network 정리를 모두 확인해야 통과한다. API inventory는 **최상위 target 출력만 제외**하며 `src/main/java/target` 같은 실제 source 패키지를 숨기지 않는다. 반복 실행·시험 재시도·광범위 prune는 없다.

정상 API 준비는900초, image 준비는600초, Kafka/IT는300초, cleanup은90초로 나눈다. Kafka는 CPU1/memory1GiB/pids256/heap512MiB/data tmpfs256MiB, JVM은 heap768MiB/tmp128MiB를 사용한다. JUnit IT 자체 한도는180초다. 물리 디스크 I/O의 커널 정지를 강제로 취소하는 주장은 하지 않으며 최종 source 검사 뒤 deadline을 다시 검사해 늦은 성공을 차단한다.

## 실패와 정리

자원 생성 전에 부재를 확인하고 intent를 ledger에 기록한다. 성공 응답의 full64 ID를 저장한 뒤 typed label/이름/image/network 및 최초 Created 값을 확인·저장한다. 이후 Created 값이 정확히 같아야 한다. 실제 HostConfig의 CPU1/memory1GiB/swap추가0/pids256, User·cap·security·namespace, broker의 기대 tmpfs만, JVM의 owned bind4개와 tmpfs만 허용한다. 이미지의 별도 VOLUME/anonymous mount가 있으면 실패로 보존하며 기존 volume 삭제를 추정하지 않는다. 생성 timeout·잘못된 ID·id=null 등 결과가 불명확하면 새 자원을 만들거나 이름만으로 추정 삭제하지 않는다. 해당 실행은 실패하고 새 disposable runner 종료로 격리한다.

cleanup은 ledger의 exact ID만 사용하고 JVM→broker→network 순서로 정리한다. stop 뒤 actual stopped state, remove 뒤 daemon의 ID 조회 결과가 빈 값인지 확인한다. identity 불일치·unknown deletion은 실패다. workflow의 always cleanup은 중단된 실행의 known-ID 정리만 보완한다. cleanup 재호출은 이미 REMOVED/CLEANED 상태를 반환하며 IT를 재실행하지 않는다.

로컬 CLI process-group 종료는 daemon의 container 종료와 다르다. command timeout/출력 초과는 로컬 group만 종료하며, daemon 자원은 별도의 exact-ID cleanup/actual stopped·absent 확인이 필요하다. source guard 실패도 run의 finally 경계 안에서 처리하고 cleanup의 typed/unknown 실패를 FAILED public JSON으로 남긴다. source 불변·XML·cleanup을 모두 확인하지 못하면 PASSED를 쓰지 않는다. 파일시스템 자체 쓰기 실패로 JSON을 저장할 수 없는 경우에도 성공으로 대체하지 않는다.

private 상태·Maven/IT 로그·raw Docker 응답은 공개 artifact에 넣지 않는다. 공개 allowlist JSON 하나만 업로드한다. source/runtime hash, XML 검증 count/skip, 고정 assertion 검증 boolean, source 유지·owned cleanup 여부를 담는다. **새 Kafka 수치 관측 payload는 만들지 않는다.** LSO3/lag2→0 등은 pin된 test method의 assertions가 통과한 범위다. Kafka ACL·HTTP endpoint·Mini PC·전체 JVM thread 종료 검증 flag는 false다.

## 검증 후보

`test_run_once.py`는 Docker/Java/socket을 시작하지 않는 의미 있는 경계24개를 준비했다. unknown create/timeout의 무재시도·무추정삭제, typed inspect/id=null, Created 변화, 실제 cap/memory/namespace·anonymous/비소유 mount, source 실패와 cleanup unknown의 FAILED JSON, exact216 정상 API XML, nested target 패키지 거부, 삭제 후 부재 미확인, source/도구 변조, expired deadline, IT XML skip/추가 method/다른 런타임, public PASS gate를 검사한다. **아직 실행하지 않았다.** Linux 테스트는 `O_NOFOLLOW` 파일 검사 경계를 사용한다. Windows 통과를 가정하지 않는다.

workflow는 원본 capture의 CLI/runtime/Linux86 핀과 Pages main 제한·permissions를 바꾸지 않는다. 별도 요청한 전체 `tests/observation` Linux 검사는 Node/npm 준비 후 추가하며 Kafka opt-in 변경과 독립 diff로 검토한다.
