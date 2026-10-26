export type TechnologyGuide = {
  slug: string;
  title: string;
  category: string;
  summary: string;
  problem: string;
  design: string;
  flow: string[];
  scope: string;
  learn: string[];
  settings: { name: string; purpose: string; portability: string }[];
  sources: { label: string; path: string }[];
  evidence: { label: string; path: string }[];
  related: string[];
};

/** Repository-backed explanations; actual captures are tracked in technologyScreens.ts. */
export const technologies: TechnologyGuide[] = [
  {
    slug: 'java',
    title: 'Java · Spring Boot',
    category: '서비스와 처리 규칙',
    summary: '합성 센서 입력을 검증하고 성공·실패·중복을 구분하는 서비스와, 저장된 결과를 읽는 REST API입니다.',
    problem: '같은 입력을 다시 처리하거나 worker가 중단되어도 결과와 완료 상태가 어긋나지 않아야 합니다.',
    design: '입력 판정은 SensorProcessor에 모으고, 작업 상태·결과는 DB에 남깁니다. HTTP 조회와 상시 worker의 실행 책임을 나누며 Flyway로 스키마를 관리합니다.',
    flow: ['합성 입력 검증', '작업·dispatch intent 저장', 'worker의 센서 판정', '결과·완료 상태 DB commit', 'REST API로 조회'],
    scope: 'API와 worker는 미니 PC에 배포한 기록이 있습니다. 공개 화면은 조회용입니다. 개인 합성 예제이며 회사 업무 데이터나 실제 수율 계산을 재현한 것이 아닙니다.',
    learn: ['SensorProcessor의 입력 순서와 중복·실패 판정을 읽고 고정 기대 결과와 대조합니다.', 'local-dev의 H2로 시작한 뒤 MariaDB 통합 검증을 거쳐 DB 차이를 확인합니다.', '작업 완료와 export 완료가 서로 다른 상태인 이유를 추적합니다.'],
    settings: [
      { name: 'DB_URL / DB_USERNAME / DB_PASSWORD', purpose: 'Spring datasource의 연결 대상과 계정입니다.', portability: '새 환경의 DB·앱 전용 계정으로 교체합니다. 비밀번호는 Secret 등 외부 주입을 사용합니다.' },
      { name: 'spring.jpa.hibernate.ddl-auto: validate', purpose: 'JPA는 스키마 일치를 확인하고 변경은 Flyway에 맡깁니다.', portability: '새 DB에서도 migration을 먼저 적용하고 validate를 유지합니다. 기존 DB에 적용할 때는 이력을 확인합니다.' },
      { name: 'hibernate.jdbc.time_zone: UTC', purpose: '시간 저장·해석의 기준을 통일합니다.', portability: '호스트 시간대가 달라도 UTC 의미가 같은지 시간 경계 테스트를 함께 옮깁니다.' },
    ],
    sources: [
      { label: '센서 처리 규칙', path: 'apps/api/src/main/java/io/github/devdooly/platformlab/demo/SensorProcessor.java' },
      { label: 'DB·HTTP 기본 설정', path: 'apps/api/src/main/resources/application.yml' },
      { label: '로컬 DB 실행 안내', path: 'docs/runbooks/local-compose.md' },
    ],
    evidence: [
      { label: '고정 입력의 실제 worker 처리', path: 'docs/evidence/current-worker-fixture/README.md' },
      { label: 'MariaDB·API 교체 검증', path: 'docs/evidence/compose-ci/README.md' },
    ],
    related: ['kafka', 'storage', 'web'],
  },
  {
    slug: 'kafka',
    title: 'Kafka · Kafbat',
    category: '비동기 전달과 재처리',
    summary: '작업 접수와 실행을 분리하고, 중단 뒤 같은 메시지가 돌아와도 DB 결과를 보존하는 전달 경로입니다.',
    problem: 'DB 저장과 Kafka 전송은 하나의 트랜잭션이 아닙니다. 전송 직후나 결과 저장 직후 중단되면 메시지가 다시 도착할 수 있습니다.',
    design: 'DB dispatch intent를 publisher가 읽고 broker ACK 뒤 확인 처리합니다. worker는 DB commit 뒤 offset을 수동 commit하며, 완료 작업의 재전달은 기존 결과를 보존합니다. Kafbat은 읽기 전용 UI로 연결했습니다.',
    flow: ['DB dispatch intent', 'publisher → broker ACK', 'consumer 수신', 'DB 결과 commit', 'offset commit · lag 관측'],
    scope: 'Kafka·worker와 Kafbat의 배포 기록이 있으며 중단 경계는 별도 격리 시험으로 검증했습니다. 단일 broker 실험으로, 시스템 전체 exactly-once나 HA를 보장하지 않습니다. Kafbat 읽기 전용 설정은 broker ACL과 다릅니다.',
    learn: ['ACK·DB commit·offset commit 사이에서 중단되면 무엇이 다시 실행되는지 그려 봅니다.', 'lag의 단위는 센서 행 수가 아닌 작업 메시지 수임을 구분합니다.', 'consumer group을 바꿀 때 기존 offset을 이어받지 않는 점을 확인합니다.'],
    settings: [
      { name: 'enable.auto.commit=false / max.poll.records=1', purpose: '한 번에 한 메시지를 처리하고 DB commit 뒤 offset을 직접 확인합니다.', portability: '처리량을 늘리기 전에 동시 처리·실패 시 offset 경계를 다시 설계해야 합니다.' },
      { name: 'LAB_RUNTIME_KAFKA_BOOTSTRAP', purpose: 'worker의 broker 연결 대상입니다.', portability: '현재 factory는 loopback·ClusterIP DNS와 PLAINTEXT를 전제합니다. 외부 broker는 주소 교체 외에 TLS·인증 지원이 필요합니다.' },
      { name: 'runtime.worker.topic / runtime.worker.group', purpose: 'Helm에서 작업 topic과 consumer group을 지정합니다.', portability: '새 프로젝트별로 분리하고 topic을 미리 준비합니다. 기존 group 변경은 재처리 범위를 검토합니다.' },
    ],
    sources: [
      { label: 'Kafka client 설정', path: 'apps/api/src/main/java/io/github/devdooly/platformlab/jobs/messaging/KafkaClientFactory.java' },
      { label: '명시적 전달 방식의 결정', path: 'docs/adr/0006-explicit-kafka-dispatch.md' },
      { label: 'Kafbat·관리 UI 접속 안내', path: 'docs/runbooks/service-console.md' },
    ],
    evidence: [
      { label: '중단 후 재전달 경계', path: 'docs/evidence/kafka-redelivery/README.md' },
      { label: 'consumer 재개와 lag 감소', path: 'docs/evidence/kafka-lag-recovery/README.md' },
    ],
    related: ['java', 'storage', 'kubernetes'],
  },
  {
    slug: 'storage',
    title: 'MariaDB · Garage S3',
    category: '상태와 파일 보존',
    summary: 'DB에는 작업 상태와 결과를, S3 호환 저장소에는 원본·결과·실패 파일을 보관합니다.',
    problem: 'DB 처리가 끝났어도 파일 업로드가 실패할 수 있습니다. 완료 표시와 실제 저장 성공을 따로 확인해야 합니다.',
    design: 'export intent를 바탕으로 결과·실패 파일을 만들고 저장 내용을 검증한 뒤 EXPORTED로 전환하여 실행 슬롯을 해제합니다. Garage를 통해 S3 API와 파일 무결성 확인을 학습합니다.',
    flow: ['DB 결과·export intent', '결과·실패 파일 생성', 'S3 저장', '저장 내용 확인', 'EXPORTED · 실행 슬롯 해제'],
    scope: 'DB·Garage 배포와 신규 작업의 원본·export 전체 GET 대조 기록이 있습니다. DB 논리 복원·PVC 격리 복원은 각각 별도 시험입니다. 전체 K3s/Jenkins 기동 복원과 운영 저장소 예산 정책은 보류 중입니다.',
    learn: ['COMPLETED와 EXPORTED를 구분하고 export 실패 시 슬롯이 유지되는 경계를 읽습니다.', '파일 이름·크기만 같은 경우와 전체 내용이 같은 경우를 구분합니다.', '백업 파일 확인, 격리 DB 복원, 전체 서비스 기동 복원을 서로 다른 완료 조건으로 둡니다.'],
    settings: [
      { name: 'LAB_RUNTIME_S3_ENDPOINT / LAB_RUNTIME_S3_BUCKET', purpose: 'worker가 사용하는 S3 호환 endpoint와 전용 bucket입니다.', portability: '새 프로젝트 bucket으로 분리하고 endpoint 허용 정책을 확인합니다. 실제 자격증명은 별도 주입합니다.' },
      { name: 'pathStyleAccessEnabled(true)', purpose: 'bucket을 URL 경로에 놓는 S3 주소 방식을 사용합니다.', portability: '다른 S3 서비스의 주소·TLS 방식과 호환성을 확인합니다. Garage 전용 checksum 선택을 그대로 일반화하지 않습니다.' },
      { name: 'database.persistence.storageClass / runtime.garage.persistence.storageClass', purpose: 'DB와 객체 저장소 PVC의 저장 장치를 선택합니다.', portability: '현재 chart schema는 local-path를 고정합니다. 다른 StorageClass는 values뿐 아니라 schema·템플릿·검사도 함께 검토해야 합니다. PVC 크기는 애플리케이션 예산 정책과 별개입니다.' },
    ],
    sources: [
      { label: 'S3 client·timeout·Garage 호환 설정', path: 'apps/api/src/main/java/io/github/devdooly/platformlab/jobs/S3ClientFactory.java' },
      { label: 'DB·Garage PVC 설정', path: 'infra/charts/platform-lab/values.yaml' },
    ],
    evidence: [
      { label: 'export 확인 후 슬롯 해제', path: 'docs/evidence/result-export/README.md' },
      { label: '현재 DB의 격리 논리 복원', path: 'docs/evidence/current-db-restore/README.md' },
      { label: 'Kafka·Garage PVC 격리 복원', path: 'docs/evidence/runtime-pvc-restore/README.md' },
    ],
    related: ['java', 'kafka', 'lakehouse'],
  },
  {
    slug: 'jenkins',
    title: 'Jenkins · GitHub Actions',
    category: '검증과 이미지 게시',
    summary: '같은 소스의 테스트 결과를 확인한 뒤 이미지를 게시하고, 배포 변경을 검토할 수 있도록 연결합니다.',
    problem: '테스트한 코드와 배포 이미지가 다르면 성공한 CI만으로 배포의 신뢰성을 설명할 수 없습니다.',
    design: 'Jenkins Kubernetes agent에서 Java·웹을 검증하고 소스 SHA에 상태를 남깁니다. Actions는 같은 SHA의 검증을 확인하여 이미지 게시와 GitOps 변경 제안을 담당합니다. 실제 배포 상태 관리는 Argo CD에 맡깁니다.',
    flow: ['main 소스 checkout', 'Jenkins · Actions 검증', '같은 SHA의 성공 확인', '이미지 digest 게시', 'GitOps 변경 검토'],
    scope: '실제 Jenkins 빌드·실패 시 게시 차단·배포 연결 기록이 있습니다. GitHub App 토큰은 자연 만료 후 자격증명 접근 시 갱신 한 주기를 확인했습니다. 선제 주기 갱신·개인키 교체나 모든 빌드 경로의 검증은 아닙니다.',
    learn: ['Jenkins의 단계별 결과와 source SHA, 게시 이미지 digest의 연결을 따라갑니다.', '실패한 테스트가 이미지 게시와 배포로 넘어가지 않는 근거를 읽습니다.', 'controller·일회용 agent·Argo CD가 각각 맡는 책임을 설명해 봅니다.'],
    settings: [
      { name: 'controller.numExecutors: 0 / agent.containerCap: 1', purpose: 'controller에서 빌드하지 않고 agent 수를 제한합니다.', portability: '새 클러스터의 자원에 맞게 agent 한도와 빌드 요청량을 함께 정합니다.' },
      { name: 'GITHUB_STATUS_CREDENTIAL_ID', purpose: 'Jenkinsfile이 GitHub App credential을 참조하는 이름입니다.', portability: '새 저장소에 설치한 App과 Jenkins credential을 연결합니다. 개인키·토큰을 코드에 넣지 않습니다.' },
      { name: 'disableConcurrentBuilds()', purpose: '이 Jenkins job의 중복 실행을 순서대로 대기시킵니다.', portability: '다른 job까지 제한하는 설정은 아니므로 공유 자원의 전체 동시성을 별도로 검토합니다.' },
    ],
    sources: [
      { label: 'CI 단계와 상태 전달', path: 'Jenkinsfile' },
      { label: 'controller·agent 설정', path: 'infra/platform/jenkins-values.yaml' },
      { label: '이미지 게시 절차', path: 'docs/runbooks/image-publication.md' },
    ],
    evidence: [
      { label: '정상 배포·실패 차단·이전 이미지 복귀', path: 'docs/evidence/cicd-gate/README.md' },
      { label: 'App 토큰 자연 만료와 갱신', path: 'docs/evidence/github-app-jenkins/NATURAL_EXPIRY.md' },
    ],
    related: ['kubernetes', 'java', 'web'],
  },
  {
    slug: 'kubernetes',
    title: 'K3s · Helm · Argo CD',
    category: '선언적 배포와 운영',
    summary: '애플리케이션 구성을 Helm으로 묶고 Git의 선언과 클러스터 상태를 Argo CD로 맞춥니다.',
    problem: '서버에서 수동으로 바꾼 설정만 남으면 어떤 코드와 이미지가 동작하는지 추적하거나 다른 장비에서 재현하기 어렵습니다.',
    design: 'chart는 공통 리소스 구조를, 환경 values는 검증된 이미지 digest와 배포 값을 담습니다. Argo CD가 main의 선언을 읽으며 Secret은 Git 밖에서 준비합니다. readiness와 실제 API 결과는 동기화 상태와 별도로 확인합니다.',
    flow: ['Helm chart + 환경 values', 'Git 변경 검토', 'Argo CD 동기화', 'Deployment · Service · PVC', 'readiness · 실제 결과 확인'],
    scope: 'K3s·Argo CD와 API·worker의 실제 배포·이미지 교체 기록이 있습니다. 단일 미니 PC의 검증이며 다중 노드 HA와 별도 장비의 전체 기동 복원은 완료하지 않았습니다.',
    learn: ['chart의 공통값과 home-lab 환경값을 비교해 환경별 변경점을 찾습니다.', 'Synced·Healthy·Pod Ready·업무 결과 성공이 각각 무엇을 뜻하는지 구분합니다.', '이전 image pin으로 복귀하는 절차와 데이터 migration의 호환성을 함께 읽습니다.'],
    settings: [
      { name: 'api.image.digest / runtime.worker.image.digest', purpose: '변할 수 있는 tag 대신 게시된 이미지 내용을 지정합니다.', portability: '새 registry에서 접근 가능한 digest를 검증하고 sourceCommit과 함께 기록합니다.' },
      { name: 'syncPolicy.automated.prune: false / selfHeal: true', purpose: '자동 삭제는 끄고 Git 선언과의 차이는 복구합니다.', portability: '보존할 리소스와 수동 변경 정책을 먼저 정합니다. prune 비활성화가 수동 PVC 삭제까지 막지는 않습니다.' },
      { name: 'database.existingSecret', purpose: 'chart가 생성하지 않는 기존 DB Secret을 참조합니다.', portability: '새 namespace에 Secret과 필요한 key를 먼저 준비하고 환경 values의 참조 이름을 맞춥니다.' },
    ],
    sources: [
      { label: 'Argo CD Application', path: 'gitops/bootstrap/application.yaml' },
      { label: '공통 Helm 설정', path: 'infra/charts/platform-lab/values.yaml' },
      { label: 'GitOps 구성 원칙', path: 'gitops/README.md' },
    ],
    evidence: [
      { label: 'worker·Kafka·Garage 최초 배포', path: 'docs/evidence/runtime-deployment/README.md' },
      { label: 'worker 이미지 교체와 자료 보존', path: 'docs/evidence/worker-image-rollout/README.md' },
    ],
    related: ['jenkins', 'storage', 'kafka'],
  },
  {
    slug: 'lakehouse',
    title: 'Spark · Iceberg · Trino',
    category: '테이블 처리와 시점 조회',
    summary: '객체 저장소의 파일을 Iceberg 테이블로 관리하고 Spark 변환 결과를 Trino SQL로 확인합니다.',
    problem: '파일 수가 늘거나 데이터를 다시 적재해도 어느 시점의 데이터인지, 과거 snapshot이 참조하는 파일은 무엇인지 설명할 수 있어야 합니다.',
    design: 'Garage에 Parquet·metadata를 두고 PostgreSQL JDBC catalog로 테이블을 연결합니다. Spark는 Bronze 적재·Silver 분류·compaction을, Trino는 동일 catalog의 현재·과거 snapshot 조회를 맡습니다.',
    flow: ['합성 원본', 'Spark Bronze 적재', 'Iceberg snapshot + JDBC catalog', 'Silver 분류 · compaction', 'Trino 시점 조회'],
    scope: '미니 PC의 별도 Iceberg 시험과 격리 Cloud 실행 기록입니다. 상시 운영 데이터 플랫폼 전체가 아닙니다. 새 warehouse에서 12행 보존과 현재 파일 2→1을 확인했으며 처리량 향상이나 운영 GC의 근거로 사용하지 않습니다.',
    learn: ['두 append와 compaction 뒤 snapshot·행 수·파일 수가 어떻게 달라지는지 비교합니다.', 'current 파일 수 감소와 실제 객체 삭제를 구분합니다.', 'Spark와 Trino가 같은 catalog·warehouse·S3 주소를 보도록 맞추고 시점 조회를 대조합니다.'],
    settings: [
      { name: 'iceberg.catalog.type=jdbc', purpose: 'Trino가 PostgreSQL JDBC catalog를 사용하도록 합니다.', portability: '새 DB 주소·계정과 catalog 이름·schema 버전을 Spark 설정과 맞춥니다.' },
      { name: 'spark.sql.catalog.phase6.warehouse', purpose: 'Spark Iceberg 테이블 파일의 S3 기준 경로입니다.', portability: '새 프로젝트 전용 bucket·prefix로 분리하고 Trino의 default-warehouse-dir와 대조합니다.' },
      { name: 's3.endpoint / s3.path-style-access', purpose: 'Trino의 S3 호환 저장소와 주소 방식을 지정합니다.', portability: '이식할 S3 서비스의 TLS·region·주소 방식·권한을 확인한 뒤 작은 입출력으로 검증합니다.' },
    ],
    sources: [
      { label: 'Spark 변환·catalog 설정', path: 'infra/spark-silver/spark_silver.py' },
      { label: 'Trino 고정 설정', path: 'infra/cloud-lakehouse-ci/pinned_trino_configuration.py' },
      { label: '격리 데이터 흐름 안내', path: 'infra/cloud-lakehouse-ci/README.md' },
    ],
    evidence: [
      { label: 'Spark → Trino·compaction 실제 결과', path: 'docs/evidence/cloud-lakehouse/FULL_SUCCESS.md' },
      { label: '별도 warehouse의 snapshot 만료', path: 'docs/evidence/cloud-iceberg-expiration/README.md' },
    ],
    related: ['storage', 'java', 'kubernetes'],
  },
  {
    slug: 'web',
    title: 'Astro · React · 관측 화면',
    category: '기술과 근거를 보여주는 웹',
    summary: '정적 포트폴리오 안에서 API 결과·관측 기록·검증 사례를 탐색하고 저장 파일을 다시 읽습니다.',
    problem: '숫자만 보여주면 현재 API 응답과 과거 검증 기록이 섞입니다. 조회가 실패해도 마지막 성공의 출처와 시각을 잃지 않아야 합니다.',
    design: 'Astro는 정적 페이지를 만들고 React는 조회·비교·필터를 담당합니다. 브라우저가 사용하는 공개 조회 API와 관리 UI를 구분하며, 저장 JSON은 브라우저 안에서 검증·비교합니다.',
    flow: ['Astro 정적 페이지', 'React 조회·탐색', '공개 GET 또는 저장 파일', '출처·관측 시각과 결과 표시', '비교 · JSON 내보내기'],
    scope: '공개 Pages에 배포한 웹 기능입니다. 서버가 수집한 기록과 사용자가 조회한 응답을 구분합니다. 화면의 기록만으로 현재 worker 생존이나 서비스의 장기 가용성을 증명하지 않습니다.',
    learn: ['같은 화면에서 실시간 API 응답과 저장된 기록의 출처·시각을 찾아봅니다.', 'API 조회 실패 후 이전 성공 결과와 새 오류가 어떻게 함께 남는지 읽습니다.', '저장 JSON 한 개 보기와 두 개 비교를 이용해 서버 연결 없는 분석 흐름을 익힙니다.'],
    settings: [
      { name: 'SITE_URL / SITE_BASE', purpose: '정적 배포 도메인과 하위 경로를 Astro 빌드에 지정합니다.', portability: '새 사이트의 루트 또는 저장소 하위 경로에 맞추고 내부 링크·자산 경로를 확인합니다.' },
      { name: 'API_PROXY_TARGET', purpose: '개발 서버의 /api 요청을 로컬 API로 연결합니다.', portability: '로컬 개발 대상에만 맞춥니다. 정적 배포에는 개발 proxy가 포함되지 않습니다.' },
      { name: 'PUBLIC_API_BASE_URL', purpose: '공개 빌드에서 브라우저가 조회할 API 주소입니다.', portability: '현재 검증기는 HTTPS·기본 443 포트·DNS 호스트와 /api 또는 /platform-lab/api 경로만 허용합니다. 다른 경로·포트는 검증 코드도 수정해야 합니다. 공개 GET·CORS를 맞추고 비밀값은 넣지 않습니다.' },
    ],
    sources: [
      { label: '정적 배포·개발 proxy 설정', path: 'apps/lab-web/astro.config.mjs' },
      { label: '화면 구성과 관측 연결', path: 'apps/lab-web/src/pages/index.astro' },
      { label: 'API 없이 저장 파일 읽기', path: 'docs/features/offline-event-viewer.md' },
    ],
    evidence: [
      { label: '관측 응답 순서·실패 보존', path: 'docs/evidence/browser-observation-protection/README.md' },
      { label: '공개 HTTPS 조회 연결', path: 'docs/evidence/public-read-https/README.md' },
    ],
    related: ['java', 'jenkins', 'ai'],
  },
  {
    slug: 'ai',
    title: 'AI 활용 · Java 검증 · JMH',
    category: '개선 가설을 검증하는 과정',
    summary: 'AI가 제안한 코드를 그대로 성과로 삼지 않고, 독립 기대값과 재현 가능한 측정으로 비교하는 사례입니다.',
    problem: '시간대 처리가 잘못되거나 측정에 불필요한 작업이 섞이면 빠른 코드가 잘못된 답을 내거나 개선 효과가 왜곡될 수 있습니다.',
    design: '합성 시간창을 UTC로 정규화하고 O(n²) 기준 구현과 O(n log n) sweep 구현의 결과를 대조합니다. JMH로 동일 입력의 계산 부분을 측정하며 입력 생성·파싱은 측정에서 분리합니다.',
    flow: ['합성 시간창·기대값', 'UTC 정규화', '두 알고리즘 결과 대조', '별도 JVM의 JMH 측정', '소스·오차·환경과 함께 해석'],
    scope: '독립 Java 예제의 Windows·Linux 측정 기록입니다. 운영 ETL 코드의 개선율이 아니며 기존 SensorProcessor는 이미 O(n)입니다. AI 활용 범위는 출처 문서에 구분했고 사람 소유자 검토는 PENDING입니다.',
    learn: ['offset을 잃는 오류 예제와 UTC 정규화의 기대 결과를 비교합니다.', '평균값뿐 아니라 오차·fork별 결과·할당량·실행 환경을 같이 읽습니다.', '입력 규모와 분포를 바꾸되 정확성 검증과 성능 측정을 따로 판단합니다.'],
    settings: [
      { name: '@Param size / profile', purpose: '입력 수 128~4096과 sparse·nested 분포를 고정합니다.', portability: '새 문제를 대표하는 입력 분포와 독립 기대값부터 만들고 두 구현에 같은 입력을 줍니다.' },
      { name: '@Fork(3) / @Warmup / @Measurement', purpose: '새 JVM 3개, 준비 반복, 측정 반복을 분리합니다.', portability: 'JDK·heap·GC·측정 옵션을 기록하고 다른 장비의 결과를 동일 환경 결과처럼 합치지 않습니다.' },
      { name: '@Setup(Level.Trial)', purpose: 'fixture 생성·파싱·정답 확인을 측정 구간 밖에서 수행합니다.', portability: '무엇을 빠르게 하려는지 정한 뒤 준비 비용을 포함할지 별도 측정할지 명시합니다.' },
    ],
    sources: [
      { label: '독립 예제 실행·측정 안내', path: 'examples/java-window-analysis/README.md' },
      { label: '실제 JMH 설정', path: 'examples/java-window-analysis/src/main/java/io/github/devdooly/examples/window/WindowBenchmark.java' },
      { label: 'AI 활용 출처와 범위', path: 'examples/java-window-analysis/PROVENANCE.md' },
    ],
    evidence: [
      { label: '측정 결과와 한계', path: 'docs/evidence/ai-window-analysis/README.md' },
      { label: 'Linux 별도 재현', path: 'docs/evidence/ai-window-analysis/hosted-linux-20261018/README.md' },
    ],
    related: ['java', 'web'],
  },
];
