/** Curated public personal-Lab records. These are historical evidence, never a live status feed. */
export const evidenceTopics = [
  { id: 'java', label: 'Java · Spring Boot' },
  { id: 'kafka', label: 'Kafka' },
  { id: 'kubernetes', label: 'Kubernetes · Helm' },
  { id: 'delivery', label: 'CI/CD' },
  { id: 'iceberg', label: 'Iceberg' },
  { id: 'llm', label: 'AI 활용 · 검증 과정' },
] as const;

export const evidenceScopes = [
  { id: 'mini-pc', label: '미니 PC' },
  { id: 'cloud', label: 'Cloud 격리' },
  { id: 'windows', label: 'Windows 개인 예제' },
  { id: 'ci', label: 'GitHub Linux CI' },
] as const;

export type EvidenceTopic = typeof evidenceTopics[number]['id'];
export type EvidenceScope = typeof evidenceScopes[number]['id'];
export interface EvidenceItem {
  id: string;
  topics: readonly EvidenceTopic[];
  scope: EvidenceScope;
  state: 'verified' | 'pending';
  title: string;
  description: string;
  boundary: string;
  recordedOn: string | null;
  source: string;
  evidence: string;
  evidenceLabel?: string;
  recordLabel?: string;
  screen?: string;
}

const repo = 'https://github.com/DevDooly/devdooly-platform-lab';
const recordSource = 'dc050fb5adc714cada8a6d29b9d733ada446d454';
const kafkaSource = 'f7b5567963f9a34a34d5f201fb2ed747bdf7652a';

export const evidenceItems: readonly EvidenceItem[] = [
  {
    id: 'kafka-lag-recovery', topics: ['java', 'kafka'], scope: 'cloud', state: 'verified',
    title: '소비자 종료 중 쌓인 메시지 이어 읽기',
    description: '12건 중 4건을 읽고 종료한 뒤 6건을 추가했습니다. 같은 그룹의 새 소비자가 남은 14건을 읽고 확인해 lag 14에서 0으로 돌아오는 과정을 검증했습니다.',
    boundary: '새 격리 broker의 정상 consumer 종료·재가입 시험입니다. 운영 worker·DB/export·강제 중단·고가용성 검증은 아닙니다.',
    recordedOn: '2026-10-20',
    source: `${repo}/blob/5e22dbecfa4da458a563fd5fa1fc4c9c34a7ef17/infra/kafka-lag-recovery-ci/KafkaLagRecoveryIT.java`,
    evidence: `${repo}/blob/main/docs/evidence/kafka-lag-recovery/README.md`, evidenceLabel: '실제 4단계·읽기·정리 근거',
    recordLabel: '격리 복구 IT 1/1', screen: '#kafka-lag-recovery',
  },
  {
    id: 'java-runtime', topics: ['java'], scope: 'mini-pc', state: 'verified',
    title: 'Java 작업 처리와 파일 확인',
    description: 'Spring Boot 작업 처리와 export를 구현하고, 배포한 서비스의 결과 파일과 기존 데이터 보존을 확인했습니다.',
    boundary: '당시 배포 검증 기록입니다. 현재 가용성이나 처리량 SLA를 뜻하지 않습니다.',
    recordedOn: '2026-10-15',
    source: `${repo}/tree/74a8e98844a8fea0653951136ede0e7de0d7ac08/apps/api`,
    evidence: `${repo}/blob/${recordSource}/docs/evidence/s3-runtime-rollout/README.md`, screen: '#job-observation',
  },
  {
    id: 'kafka-isolated', topics: ['java', 'kafka'], scope: 'cloud', state: 'verified',
    title: 'Commit · LSO · lag를 구분한 조회',
    description: 'CI7의 고정 IT1에서 NO_COMMIT, 양수·0 lag와 미완료 transaction, 소스 보존과 자기 자원 정리를 확인했습니다.',
    boundary: '새 broker의 격리 시험입니다. 신규 미니 PC 관측 연결과 Kafka ACL은 별도입니다.',
    recordedOn: '2026-10-18',
    source: `${repo}/blob/${kafkaSource}/apps/api/src/main/java/io/github/devdooly/platformlab/jobs/observation/ReadOnlyKafkaAdmin.java`,
    evidence: `${repo}/blob/${recordSource}/docs/evidence/kafka-observation/CI_ATTEMPT_7.md`, evidenceLabel: 'CI7 검증 근거', screen: '#kafka-observation',
  },
  {
    id: 'kubernetes-runtime', topics: ['kubernetes'], scope: 'mini-pc', state: 'verified',
    title: 'Helm으로 배포한 상시 worker',
    description: 'K3s에 API·worker·저장소를 배포하고 Argo CD 상태, 연속 작업의 처리·파일 확인·슬롯 해제를 검증했습니다.',
    boundary: '개인 단일 노드 Lab의 과거 기록입니다. 고가용성이나 전체 클러스터 복원 검증은 아닙니다.',
    recordedOn: '2026-10-15', source: `${repo}/tree/ed5815e7d72c6ea4f52456d902b7407c7a4a67b0/infra/charts/platform-lab`,
    evidence: `${repo}/blob/${recordSource}/docs/evidence/runtime-deployment/README.md`, screen: '#platform',
  },
  {
    id: 'delivery-gate', topics: ['delivery', 'kubernetes'], scope: 'mini-pc', state: 'verified',
    title: '실패한 변경을 배포 전에 차단',
    description: '같은 소스의 Jenkins·Actions 검증, 이미지 게시와 GitOps 배포를 연결하고 실제 테스트 실패 차단·이전 이미지 복구를 확인했습니다.',
    boundary: '검증한 배포·복구 시나리오입니다. 자격증명 회전과 무중단 배포는 별도입니다.',
    recordedOn: '2026-10-11', source: `${repo}/blob/cd48da4eaf0dd5ae245f7caa890c99f5ba92db17/Jenkinsfile`,
    evidence: `${repo}/blob/${recordSource}/docs/evidence/cicd-gate/README.md`, screen: '#platform',
  },
  {
    id: 'iceberg-retention', topics: ['iceberg'], scope: 'cloud', state: 'verified',
    title: 'Iceberg metadata로 보존 계획 만들기',
    description: '9차 실행의 닫힌 metadata·inventory를 순수 계획기에 연결했습니다. 스냅샷3·객체20의 결과는 모두 KEEP입니다.',
    boundary: '정지한 격리 데이터의 보존 계획입니다. snapshot 만료·객체 삭제·Parquet 내용 해석은 수행하지 않았습니다.',
    recordedOn: '2026-10-18',
    source: `${repo}/tree/5862ba0c617d17d4c51382bccaa0266253974e82/infra/maintenance`,
    evidence: `${repo}/blob/${recordSource}/docs/evidence/iceberg-capture/ATTEMPT_9.md`, screen: '#iceberg-capture',
  },
  {
    id: 'ai-java-example', topics: ['java', 'llm'], scope: 'windows', state: 'verified',
    title: 'AI 제안을 테스트와 측정으로 검토',
    description: '개인 합성 Java 예제로 UTC 오류 회귀와 같은 답을 구하는 두 알고리즘을 비교하고, AI 제안·검증 과정을 기록했습니다.',
    boundary: 'Windows 합성 예제의 테스트·JMH 측정이며 사람 검토는 대기 중입니다. LLM 자체의 개선 효과·모델 운영·회사 실무 성과를 입증하지 않습니다.',
    recordedOn: '2026-10-15', source: `${repo}/blob/${recordSource}/examples/java-window-analysis/PROVENANCE.md`,
    evidence: `${repo}/blob/${recordSource}/docs/evidence/ai-window-analysis/README.md`, recordLabel: '측정 기록 · 사람 검토 대기', screen: '#ai-window',
  },
  {
    id: 'kafka-mini-pc-pending', topics: ['kafka', 'kubernetes'], scope: 'mini-pc', state: 'verified',
    title: 'Kafka 관측의 자연 갱신 확인',
    description: 'API·host 수집기를 연결하고 원래 30분 타이머의 자연 실행 2회를 확인했습니다. 호스트 수집본의 전체 필드와 게시 artifact·공개 HTTP의 전체 bytes를 대조했습니다.',
    boundary: '자연 회차 2개·간격 1개를 확인한 기록입니다. 장기간 가용성·ACL·자격증명 회전·실시간 API 연결은 별도입니다.',
    recordedOn: '2026-10-18',
    source: `${repo}/tree/245d61a5749760a20918ab091d9410ce6735b1c0/apps/api`,
    evidence: `${repo}/blob/main/docs/evidence/kafka-observation/natural-timer.summary.json`, evidenceLabel: '자연 2회·공개 게시 근거', recordLabel: '자연 관측·파일 대조', screen: '#kafka-observation',
  },
  {
    id: 'public-read-gateway-internal', topics: ['kubernetes', 'delivery'], scope: 'mini-pc', state: 'verified',
    title: '내부 게이트웨이 조회·접근 진단',
    description: '허용된 클라이언트의 조회 6개와 잘못된 요청 3개의 제한을 확인했습니다. 다른 클라이언트의 연결 거절을 전후 정상 조회와 함께 기록하고 시험 자원 정리·기존 상태 보존을 확인했습니다.',
    boundary: 'NetworkPolicy만의 결과인지는 확인하지 않았습니다. Node·host·NAT 경로·외부 HTTPS·공개 실시간 API는 별도입니다.',
    recordedOn: '2026-10-18',
    source: `${repo}/tree/1a9365fbad66fcc8e0cf5ab3cf957c1f70dc15fe/infra/charts/platform-lab`,
    evidence: `${repo}/blob/main/docs/evidence/public-read-gateway-internal/README.md`, evidenceLabel: '조회·진단·보존 기록', recordLabel: '내부 조회·접근 진단', screen: '#platform',
  },
  {
    id: 'java-retention-model', topics: ['java'], scope: 'ci', state: 'verified',
    title: '합성 Java 모델 · 객체 보존과 재전달',
    description: '오래된 계획·참조 보호·부분 결과·재전달·전체 확인을 immutable RAM 전이로 다룹니다. 고정 소스의 Linux CI에서 5개 시나리오를 통과했습니다.',
    boundary: '순수 Java 합성 모델입니다. 실제 DB·저장소 삭제·물리 GC·SLA를 검증하지 않으며 운영 KEEP 정책은 유지합니다.',
    recordedOn: '2026-10-18',
    source: `${repo}/tree/7166ce84e03a69b2b0f1c853c3394d295f664af2/examples/java-object-retention-protocol`,
    evidence: `${repo}/actions/runs/39127247057`, evidenceLabel: 'Linux CI 5/5 · 소스 7166ce84', recordLabel: 'Linux CI 5/5',
  },
  {
    id: 'public-read-https', topics: ['kafka', 'kubernetes', 'delivery'], scope: 'mini-pc', state: 'verified',
    title: '외부 HTTPS 조회와 공개 화면 연결',
    description: '외부 환경에서 HTTPS 조회와 허용 경로·Origin·method의 응답을 검증하고, 미니 PC의 작업·Kafka 관측을 공개 화면에 연결했습니다.',
    boundary: '확인 시점의 읽기 전용 조회 기록입니다. 장기간 가용성이나 서버 장애 복구 검증은 별도입니다.',
    recordedOn: '2026-10-18',
    source: `${repo}/tree/772d14973ac2ecf647efb496863d6f0f10cb700c/infra/public-https-smoke`,
    evidence: `${repo}/blob/main/docs/evidence/public-read-https/README.md`, evidenceLabel: '외부 조회·공개 화면 기록', recordLabel: '시점별 외부 조회 검증', screen: '#platform',
  },
  {
    id: 'kafka-acl-isolated', topics: ['java', 'kafka', 'delivery'], scope: 'cloud', state: 'verified',
    title: 'DESCRIBE 조회와 선택 RPC·인증 거부',
    description: '새 격리 Kafka에서 필요한 조회와 다른 대상·쓰기 요청 5개, 잘못된 비밀번호 거부를 확인했습니다. 선택한 상태·소스 보존과 소유 자원 정리도 확인했습니다.',
    boundary: '합성 SASL/ACL 시험 1건입니다. 모든 쓰기 차단·TLS 기밀성·모든 JVM thread 종료·SLA를 검증한 결과가 아닙니다.',
    recordedOn: '2026-10-19',
    source: `${repo}/tree/83e141eaf2d3269920ec8599fcd49241dd8f160b/infra/kafka-acl-ci`,
    evidence: `${repo}/blob/main/docs/evidence/kafka-acl/README.md`, evidenceLabel: '허용 조회·거부 6건·보존 근거', recordLabel: '격리 ACL IT 1/1',
  },
  {
    id: 'cloud-iceberg-expiration', topics: ['iceberg', 'delivery'], scope: 'cloud', state: 'verified',
    title: 'Snapshot 만료와 공유 파일 보존',
    description: '새 합성 warehouse에서 snapshot 1개와 불필요한 data 파일 1개를 만료했습니다. tag·최근 snapshot의 공유 파일과 행, 후속 조회·소스 보존과 소유 컨테이너 정리를 확인했습니다.',
    boundary: '새 Cloud 격리 시험입니다. 운영 KEEP는 유지하며 물리 GC·볼륨 삭제·공간 회수·SLA를 검증한 결과가 아닙니다.',
    recordedOn: '2026-10-19',
    source: `${repo}/tree/482d3ca4b564282feceb31f392c6a981302a7c2d/infra/cloud-lakehouse-expiration`,
    evidence: `${repo}/blob/main/docs/evidence/cloud-iceberg-expiration/README.md`, evidenceLabel: '만료·공유 파일·행·정리 근거', recordLabel: 'snapshot 1개 만료 · 3개 보존', screen: '#snapshot-expiration',
  },
];
