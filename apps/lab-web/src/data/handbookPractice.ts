export type HandbookPractice = {
  application: string;
  example: string;
  changes: { label: string; path: string; detail: string }[];
  verify: string[];
  caseLink?: { label: string; path: string };
};

export const handbookPractice: Record<string, HandbookPractice> = {
  java: {
    application: '입력을 검증해 결과를 저장하고 별도 API로 읽는 배치 서비스에 적용할 수 있습니다. 판정 규칙과 작업 완료 처리를 분리하면 같은 규칙을 재시도와 조회 검증에도 사용할 수 있습니다.',
    example: '장비 종류별로 허용 범위가 다른 검사 서비스라면 먼저 합성 입력의 정상값, 경계값, 잘못된 값에 대해 기대 결과를 정한 뒤 판정 규칙을 바꿉니다.',
    changes: [
      { label: '센서 판정 규칙', path: 'apps/api/src/main/java/io/github/devdooly/platformlab/demo/SensorProcessor.java', detail: '판정 조건을 바꿀 때 처리 순서와 실패·중복 구분이 어떻게 달라지는지 먼저 확인합니다.' },
      { label: '입력별 기대값', path: 'apps/api/src/test/java/io/github/devdooly/platformlab/demo/SensorProcessorTest.java', detail: '새 경계의 바로 아래·같은 값·바로 위를 합성 입력으로 만들고 기대 상태와 이유를 직접 지정합니다.' },
      { label: '로컬 실행 설정', path: 'apps/api/src/main/resources/application-local-dev.yml', detail: '작은 로컬 실행의 DB 설정을 확인합니다. 별도 DB에 연결할 때는 해당 환경에서 앱 전용 계정과 연결값을 주입합니다.' },
    ],
    verify: [
      'API 모듈에서 Maven 검증을 실행하고 정상·경계·실패·중복 입력의 상태와 이유를 기대값과 대조합니다.',
      '로컬 조회에서 같은 작업의 ID, 결과 순서, 상태별 건수가 저장된 결과와 맞는지 확인합니다.',
    ],
  },
  kafka: {
    application: '처리 시간이 긴 파일 검사나 보고서 생성에서 접수와 실행을 나눌 때 적용할 수 있습니다. 작업 ID로 저장된 결과를 식별하면 같은 요청이 다시 도착했을 때 이미 끝난 업무 처리를 반복하지 않아도 됩니다.',
    example: '새 검사 서비스에는 전용 topic과 consumer group을 사용합니다. 처리 완료 메시지가 다시 도착했을 때 결과 행은 늘지 않고 메시지 처리는 정상적으로 마무리되는지 격리 환경에서 확인합니다.',
    changes: [
      { label: 'Topic과 consumer group', path: 'infra/charts/platform-lab/values.yaml', detail: '별도 환경의 values에서 runtime.worker.topic과 group을 정합니다. 새 group에는 기존 group의 offset이 이어지지 않으므로 시작 위치와 처리할 메시지 범위를 함께 정합니다.' },
      { label: 'Kafka 연결과 poll 설정', path: 'apps/api/src/main/java/io/github/devdooly/platformlab/jobs/messaging/KafkaClientFactory.java', detail: '브로커 연결 방식과 auto commit 설정을 확인합니다. 배치 수신이나 동시성을 늘릴 때는 실패가 섞인 경우에도 어떤 offset을 확정할 수 있는지 먼저 정합니다.' },
      { label: '재전달 검증', path: 'apps/api/src/test/java/io/github/devdooly/platformlab/jobs/messaging/DispatchWorkerTest.java', detail: '업무 완료 전 실패와 완료된 작업 재수신의 기대 동작을 각각 확인합니다.' },
    ],
    verify: [
      'worker 테스트에서 DB 완료 확인 전에는 메시지가 확정되지 않는지 확인합니다.',
      '격리된 topic에서 완료 작업이 재전달된 뒤 같은 작업 ID의 결과 수와 consumer group의 commit 위치를 각각 비교합니다.',
    ],
    caseLink: { label: 'Kafka 재전달 사례', path: 'cases/kafka-redelivery/' },
  },
  storage: {
    application: '처리 이력은 DB에 남기고 사용자가 내려받을 산출물은 객체 저장소에 둘 때 적용할 수 있습니다. 두 저장 경계를 나누면 파일 저장 도중 끊겨도 처리 결과를 기준으로 이어갈 수 있습니다.',
    example: '일괄 검사 보고서에서 전체 결과와 실패 목록을 각각 JSON으로 저장하고, 두 객체를 읽어 예상 내용과 일치한 뒤 작업을 닫습니다. 재시도 시 이미 검증할 수 있는 파일은 재사용합니다.',
    changes: [
      { label: 'S3 연결과 주소 방식', path: 'apps/api/src/main/java/io/github/devdooly/platformlab/jobs/S3ClientFactory.java', detail: '새 전용 bucket과 endpoint를 구성하고, 대상 서비스의 region·TLS·주소 방식과 checksum 호환성을 각각 확인합니다.' },
      { label: '파일 형식과 객체 키', path: 'apps/api/src/main/java/io/github/devdooly/platformlab/jobs/exporting/ExportBundle.java', detail: '파일 형식이나 키의 버전을 바꿀 때 기존 결과의 조회와 재시도에 필요한 호환 범위를 정합니다. 같은 DB 기록을 다시 내보낼 때 동일한 내용을 만들 수 있어야 합니다.' },
      { label: '기존 파일과 새 파일 확인', path: 'apps/api/src/main/java/io/github/devdooly/platformlab/jobs/exporting/S3ResultExportStore.java', detail: '정상 객체, 객체가 없는 응답, 기존 내용 불일치의 처리 경계를 읽습니다. 새 저장소를 붙일 때 각 응답이 기대한 의미와 일치하는지 확인합니다.' },
    ],
    verify: [
      '격리 bucket에서 결과·실패 문서를 각각 내려받아 예상 바이트와 SHA-256을 대조합니다.',
      '중단 뒤 같은 작업을 이어서 두 문서를 확인하고, 처리 결과 행은 보존되며 export 완료와 슬롯 해제가 함께 확정되는지 확인합니다.',
    ],
    caseLink: { label: 'MariaDB·Garage S3 복구 사례', path: 'cases/storage-recovery/' },
  },
  jenkins: {
    application: '여러 CI 도구를 쓰더라도 이미지 게시의 기준을 하나의 소스 커밋으로 정할 수 있습니다. 테스트 상태와 이미지 digest를 같은 커밋으로 연결하면 배포 후보가 검증한 코드와 일치하는지 추적할 수 있습니다.',
    example: '새 서비스의 단위 테스트와 웹 빌드를 Jenkins에서 수행하고, 같은 커밋의 검증이 성공했을 때만 해당 이미지를 격리 registry에 게시하도록 구성합니다.',
    changes: [
      { label: '검증 단계와 상태 이름', path: 'Jenkinsfile', detail: '새 모듈의 빌드·검사 명령을 넣고 소스 SHA에 결과가 기록되는지 확인합니다. 상태 이름을 바꾸면 이를 읽는 게시 workflow의 조건도 함께 맞춥니다.' },
      { label: '이미지 게시 조건', path: '.github/workflows/publish-images.yml', detail: '테스트용 저장소에서 허용한 브랜치와 이미지 경로를 지정하고, 게시 조건이 검증한 동일 커밋을 가리키는지 확인합니다.' },
      { label: 'Jenkins 실행 자원', path: 'infra/platform/jenkins-values.yaml', detail: '새 환경의 빌드 agent 한도와 자원 요청량을 실행할 테스트의 메모리 요구에 맞춥니다.' },
    ],
    verify: [
      '격리 저장소에서 실패한 커밋의 상태가 기록되고 해당 이미지 게시 단계에 진입하지 않는지 확인합니다.',
      '성공한 커밋의 상태, 이미지 digest, 배포 후보가 가리키는 소스 SHA를 한 줄씩 대조합니다.',
    ],
    caseLink: { label: '빌드·배포·롤백 사례', path: 'cases/cicd-delivery/' },
  },
  kubernetes: {
    application: '동일한 애플리케이션을 개발·검증 환경에 반복 배치할 때 Helm 템플릿과 환경별 값을 분리합니다. Argo CD가 읽는 Git 변경에 배포 의도를 남기면 선언과 실제 클러스터 상태를 비교할 수 있습니다.',
    example: '새 검증 namespace에 읽기 전용 API를 구성할 때, 검증한 이미지 digest와 전용 Secret 참조를 환경 값에 넣고 먼저 Helm이 생성하는 YAML을 확인합니다.',
    changes: [
      { label: '공통 Helm 값', path: 'infra/charts/platform-lab/values.yaml', detail: '포트·자원·Secret 참조의 기본값을 확인하고 새 환경에만 필요한 값은 별도의 values에 둡니다.' },
      { label: '값의 허용 범위', path: 'infra/charts/platform-lab/values.schema.json', detail: '다른 저장 방식이나 복제 구성을 도입한다면 schema가 허용하는 값과 템플릿의 전제를 함께 확인합니다.' },
      { label: 'Argo CD 대상 환경', path: 'gitops/bootstrap/application.yaml', detail: '새 저장소와 전용 namespace의 source·destination을 지정합니다. 배포 전에 렌더된 리소스가 의도한 대상과 맞는지 확인합니다.' },
    ],
    verify: [
      '별도 환경 값으로 Helm lint와 template을 실행하고 생성된 namespace, 이미지 digest, Secret 참조를 검토합니다.',
      '격리 클러스터에 적용하는 경우 Argo CD의 동기화 상태와 Pod Ready를 확인한 뒤 실제 API 조회 결과도 대조합니다.',
    ],
    caseLink: { label: 'GitOps 적용과 이미지 복귀 사례', path: 'cases/cicd-delivery/' },
  },
  lakehouse: {
    application: '배치 변환 결과의 변경 이력을 남기고 특정 적재 시점의 데이터를 읽어야 할 때 적용할 수 있습니다. Spark는 데이터를 쓰고, Iceberg는 snapshot과 파일 참조를 관리하며, Trino는 같은 테이블을 SQL로 조회합니다.',
    example: '일별 센서 데이터를 적재한 뒤 작은 파일을 합치는 실험에서는 행의 내용, 최신 snapshot의 파일 수, 이전 snapshot의 조회 결과를 각각 비교합니다.',
    changes: [
      { label: 'Spark 변환과 입력 snapshot', path: 'infra/spark-silver/spark_silver.py', detail: '변환 열과 고정 입력 조건을 함께 확인합니다. 다른 데이터를 실험할 때는 합성 fixture와 기대 결과를 별도로 만들고 전용 warehouse에서 실행합니다.' },
      { label: 'Trino catalog 연결', path: 'infra/cloud-lakehouse-ci/pinned_trino_configuration.py', detail: 'JDBC catalog와 warehouse가 Spark 쪽 설정과 같은 테이블을 가리키도록 맞춥니다. 새 환경의 연결 정보는 실행 시 주입합니다.' },
      { label: '격리 실험 순서', path: 'infra/cloud-lakehouse-ci/README.md', detail: '별도 저장 경로에서 적재·조회·파일 병합 순서를 확인하고 각 단계의 snapshot ID를 기록합니다.' },
    ],
    verify: [
      'Trino에서 현재와 이전 snapshot의 행 수와 기대 행을 각각 조회해 비교합니다.',
      'Compaction 전후의 데이터 내용과 현재 snapshot의 파일 수를 비교합니다. 파일 수가 줄었을 때 이전 snapshot도 계속 읽히는지 확인합니다.',
    ],
  },
  web: {
    application: '정적인 기술 문서와 상호작용이 필요한 조회 화면을 한 사이트에 구성할 수 있습니다. 저장된 관측을 보여줄 때 출처와 원래 시각을 표시하면 사용자가 현재 조회 결과와 과거 기록을 구별할 수 있습니다.',
    example: '새 프로젝트의 실행 결과 페이지에서 공개 API 조회가 실패하면 오류를 표시하되, 이전에 성공한 결과와 그 관측 시각은 그대로 읽을 수 있도록 구성합니다.',
    changes: [
      { label: '정적 배포 경로와 로컬 proxy', path: 'apps/lab-web/astro.config.mjs', detail: 'SITE_BASE를 배포 경로에 맞춥니다. API_PROXY_TARGET은 개발 서버의 연결 대상이므로 공개 환경의 API 연결 설정과 따로 확인합니다.' },
      { label: '공개 조회 주소 계약', path: 'apps/lab-web/src/lib/public-api-base.ts', detail: '공개 API의 도메인과 경로를 정할 때 주소 검증 조건과 API 측 CORS 설정을 함께 확인합니다. 브라우저에 전달되는 설정에는 공개 주소만 사용합니다.' },
      { label: '관측과 화면 연결', path: 'apps/lab-web/src/pages/index.astro', detail: '새 조회 화면에서 실시간 응답과 기록의 시각·상태가 각각 어디에 표시되는지 확인하고 연결을 바꿉니다.' },
    ],
    verify: [
      '웹 타입 검사와 빌드 뒤 저장소 하위 경로에서 문서 링크, 직접 URL 접속, 정적 자산을 확인합니다.',
      '로컬 예제에서 조회 성공 뒤 다음 조회를 실패시키고, 화면에 오류와 직전 성공 결과·원 시각이 함께 남는지 확인합니다.',
    ],
  },
  ai: {
    application: 'AI가 제안한 처리 개선을 검증할 때 독립 기대값으로 정확성을 확인한 다음 동일 입력의 계산 비용을 측정합니다. 개선 가설마다 무엇을 측정에 포함했는지 기록합니다.',
    example: '서로 다른 UTC offset을 가진 합성 시간창으로 겹치는 시간과 최대 동시 세션 수를 계산합니다. 경계 입력의 답을 직접 정해 기준 구현과 sweep 구현을 비교합니다.',
    changes: [
      { label: '독립 기대값과 경계 입력', path: 'examples/java-window-analysis/src/test/java/io/github/devdooly/examples/window/WindowAnalysisTest.java', detail: '시간대·인접 경계·완전히 포함된 구간을 추가할 때 테스트 기대값을 구현 결과와 별개로 계산합니다.' },
      { label: 'JMH 입력 분포와 측정 범위', path: 'examples/java-window-analysis/src/main/java/io/github/devdooly/examples/window/WindowBenchmark.java', detail: '두 구현에 동일한 입력 규모와 분포를 주고, fixture 생성과 정답 확인은 측정 구간 밖에 둡니다.' },
      { label: '재현 절차와 결과 해석', path: 'examples/java-window-analysis/README.md', detail: '실행 명령과 JDK·입력 분포·측정 설정을 기록해 다른 환경의 수치와 비교할 때 기준을 남깁니다.' },
    ],
    verify: [
      '예제의 Maven 검증을 실행하고 두 구현이 독립 기대값과 일치하는지 확인합니다.',
      '같은 환경과 입력에서 JMH 평균·오차와 fork별 결과를 비교하고 격리 예제에서 측정한 범위를 함께 기록합니다.',
    ],
  },
};
