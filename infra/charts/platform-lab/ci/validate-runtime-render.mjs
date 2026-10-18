// Local policy and JSON schema checks only; no Kubernetes or remote operation.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const chart = path.join(root, 'infra/charts/platform-lab');
const require = createRequire(path.join(root, 'apps/lab-web/package.json'));
const YAML = require('yaml');
const binary = process.env.HELM_BINARY || path.join(root, '.local/tools/helm-4.3.0/windows-amd64/helm.exe');
const output = path.join(root, '.local/runtime-helm-render');
fs.mkdirSync(output, { recursive: true });
const env = {...process.env, HELM_CACHE_HOME: path.join(root,'.local/tools/helm-home/cache'),
  HELM_CONFIG_HOME: path.join(root,'.local/tools/helm-home/config'), HELM_DATA_HOME: path.join(root,'.local/tools/helm-home/data')};
const kubeVersion = '1.36.5';
function helm(args) {
  const result = spawnSync(binary,args,{cwd:root,env,encoding:'utf8',maxBuffer:32*1024*1024});
  if (result.error) throw result.error;
  return result;
}
function success(args) { const result=helm(args); assert.equal(result.status,0,result.stderr||result.stdout); return result.stdout; }
const fixture = path.join(chart,'ci/lint-values.yaml');
const runtimeFixture = path.join(chart,'ci/runtime-lint-values.yaml');
const common = ['--namespace','platform-lab','--kube-version',kubeVersion,'-f',fixture];
const runtimeCommon = [...common,'-f',runtimeFixture];
const version=success(['version','--short']).trim(); assert.equal(version,'v4.3.0+gbec5b06');
const lint=success(['lint',chart,...runtimeCommon,'--strict']);
const rendered=success(['template','lab',chart,...runtimeCommon]);
fs.writeFileSync(path.join(output,'lint.txt'),lint); fs.writeFileSync(path.join(output,'runtime-fixture.yaml'),rendered);
function parse(value) { return YAML.parseAllDocuments(value).map(doc=>{assert.equal(doc.errors.length,0);return doc.toJSON();}).filter(Boolean); }
const docs=parse(rendered), baseline=parse(success(['template','lab',chart,...common]));
const checks=[];
function check(name,condition) { assert.ok(condition,name);checks.push(name); }
const workloads=docs.filter(doc=>['Deployment','StatefulSet'].includes(doc.kind));
const component=name=>workloads.find(doc=>doc.metadata.labels['app.kubernetes.io/component']===name);
const kafka=component('kafka'),garage=component('garage'),worker=component('worker');
const pods=[kafka,garage,worker].map(doc=>doc.spec.template.spec);
const containers=pods.flatMap(pod=>pod.containers);
const envValue=(container,name)=>container.env?.find(value=>value.name===name)?.value;
const kafkaContainer=kafka.spec.template.spec.containers[0], workerContainer=worker.spec.template.spec.containers[0];
check('Disabled runtime preserves all seven existing resource objects and creates none',baseline.length===7&&
  !baseline.some(doc=>['kafka','garage','worker'].includes(doc.metadata.labels?.['app.kubernetes.io/component'])));
check('Enabling runtime creates exactly twelve namespaced resource objects with no Secret or RBAC',docs.length===12&&
  docs.every(doc=>['ServiceAccount','Service','Deployment','StatefulSet'].includes(doc.kind)));
check('Runtime enablement leaves existing API web and database manifests identical',baseline.every(before=>
  JSON.stringify(docs.find(after=>after.kind===before.kind&&after.metadata.name===before.metadata.name))===JSON.stringify(before)));
check('Kafka and Garage are singleton StatefulSets with retained dedicated local-path claims',
  [kafka,garage].every(doc=>doc.kind==='StatefulSet'&&doc.spec.replicas===1&&
    Object.values(doc.spec.persistentVolumeClaimRetentionPolicy).every(value=>value==='Retain')&&
    doc.spec.volumeClaimTemplates.every(claim=>claim.spec.storageClassName==='local-path'&&claim.spec.accessModes[0]==='ReadWriteOnce'))&&
  kafka.spec.volumeClaimTemplates.length===1&&garage.spec.volumeClaimTemplates.length===2);
check('Worker is a singleton Recreate deployment with 300-second graceful termination and no HTTP port',worker.kind==='Deployment'&&
  worker.spec.replicas===1&&worker.spec.strategy.type==='Recreate'&&worker.spec.template.spec.terminationGracePeriodSeconds===300&&
  !workerContainer.ports&&JSON.stringify(workerContainer.args)===JSON.stringify(['--lab-runtime=run']));
check('No worker Service public ingress host ports host paths host namespaces or cluster API tokens',
  !docs.some(doc=>doc.kind==='Service'&&doc.metadata.labels['app.kubernetes.io/component']==='worker')&&
  docs.filter(doc=>doc.kind==='Service').every(doc=>doc.spec.type==='ClusterIP')&&
  pods.every(pod=>pod.automountServiceAccountToken===false&&!pod.hostNetwork&&!pod.hostPID&&!pod.hostIPC&&
    (pod.volumes||[]).every(volume=>!volume.hostPath)&&pod.containers.every(container=>(container.ports||[]).every(port=>!port.hostPort))));
check('Runtime processes use explicit nonroot identity RuntimeDefault no escalation and no capabilities',
  pods.every(pod=>pod.securityContext.runAsNonRoot===true&&pod.securityContext.runAsUser>0&&pod.securityContext.fsGroup>0&&
    pod.securityContext.seccompProfile.type==='RuntimeDefault'&&pod.containers.every(container=>
      container.securityContext.allowPrivilegeEscalation===false&&container.securityContext.capabilities.drop.includes('ALL'))));
check('Garage and worker have read-only roots while official Kafka configure retains its required writable config layer',
  garage.spec.template.spec.containers[0].securityContext.readOnlyRootFilesystem===true&&
  workerContainer.securityContext.readOnlyRootFilesystem===true&&kafkaContainer.securityContext.readOnlyRootFilesystem===false);
check('Kafka uses single static KRaft voter one partition RF1 no topic auto-creation and stable same PVC log paths',
  envValue(kafkaContainer,'KAFKA_NODE_ID')==='1'&&envValue(kafkaContainer,'KAFKA_PROCESS_ROLES')==='broker,controller'&&
  envValue(kafkaContainer,'KAFKA_CONTROLLER_QUORUM_VOTERS')==='1@kafka.platform-lab.svc.cluster.local:9093'&&
  envValue(kafkaContainer,'KAFKA_NUM_PARTITIONS')==='1'&&envValue(kafkaContainer,'KAFKA_DEFAULT_REPLICATION_FACTOR')==='1'&&
  envValue(kafkaContainer,'KAFKA_AUTO_CREATE_TOPICS_ENABLE')==='false'&&
  ['KAFKA_LOG_DIRS','KAFKA_METADATA_LOG_DIR'].every(name=>envValue(kafkaContainer,name).startsWith('/var/lib/kafka/data/')));
check('Static voter DNS publishes the singleton before readiness with no host-advertised listener',
  docs.find(doc=>doc.kind==='Service'&&doc.metadata.name==='kafka').spec.publishNotReadyAddresses===true&&
  docs.find(doc=>doc.kind==='Service'&&doc.metadata.name==='kafka').spec.clusterIP==='None'&&
  envValue(kafkaContainer,'KAFKA_ADVERTISED_LISTENERS')==='BROKER://kafka.platform-lab.svc.cluster.local:9092');
check('Kafka cluster ID is only an existing Secret key reference',
  kafkaContainer.env.find(value=>value.name==='CLUSTER_ID').valueFrom.secretKeyRef.name==='lint-kafka-do-not-install'&&
  !('value' in kafkaContainer.env.find(value=>value.name==='CLUSTER_ID')));
check('Garage mounts a protected existing config Secret and distinct metadata/data claims',
  garage.spec.template.spec.volumes.find(volume=>volume.name==='config').secret.secretName==='lint-garage-do-not-install'&&
  garage.spec.template.spec.volumes.find(volume=>volume.name==='config').secret.defaultMode===0o440&&
  ['metadata','data'].every(name=>garage.spec.template.spec.containers[0].volumeMounts.some(volume=>
    volume.name===name&&volume.mountPath===`/var/lib/garage/${name==='metadata'?'meta':'data'}`)));
check('Garage exposes only its S3 port through ClusterIP and no RPC admin or website Service',
  docs.find(doc=>doc.kind==='Service'&&doc.metadata.name==='garage').spec.ports.length===1&&
  docs.find(doc=>doc.kind==='Service'&&doc.metadata.name==='garage').spec.ports[0].port===3900);
check('Worker uses full service DNS endpoints and explicit independent image source identity',
  envValue(workerContainer,'LAB_RUNTIME_KAFKA_BOOTSTRAP')==='kafka.platform-lab.svc.cluster.local:9092'&&
  envValue(workerContainer,'LAB_RUNTIME_S3_ENDPOINT')==='http://garage.platform-lab.svc.cluster.local:3900'&&
  envValue(workerContainer,'DB_URL')==='jdbc:mariadb://db.platform-lab.svc.cluster.local:3306/platform_lab'&&
  envValue(workerContainer,'SOURCE_COMMIT')==='a'.repeat(40)&&envValue(workerContainer,'LAB_ENVIRONMENT')==='mini-pc'&&
  workerContainer.image.startsWith('example.invalid/lint-only/worker@sha256:'));
check('Worker DB password and S3 credentials are existing Secret references with no literal value',
  ['DB_PASSWORD','LAB_RUNTIME_S3_ACCESS_KEY_ID','LAB_RUNTIME_S3_SECRET_ACCESS_KEY'].every(name=>{
    const value=workerContainer.env.find(value=>value.name===name);return !('value'in value)&&!!value.valueFrom.secretKeyRef;
  }));
check('All runtime containers have CPU memory ephemeral storage requests and limits',containers.every(container=>
  ['requests','limits'].every(kind=>['cpu','memory','ephemeral-storage'].every(name=>!!container.resources[kind][name]))));
const lock=JSON.parse(fs.readFileSync(path.join(root,'infra/image-lock.json'),'utf8'));
check('Both platform runtime images exactly match their immutable repository image locks',
  kafkaContainer.image===lock.images['apache/kafka:4.3.1']&&
  garage.spec.template.spec.containers[0].image===lock.images['garage:2.4.1-linux-amd64']);
const alternate=parse(success(['template','lab',chart,...runtimeCommon,'--namespace','runtime-dns-check']));
const alternateWorker=alternate.find(doc=>doc.metadata.labels['app.kubernetes.io/component']==='worker').spec.template.spec.containers[0];
check('Runtime service endpoints follow the actual release namespace without hardcoding it',
  envValue(alternateWorker,'LAB_RUNTIME_KAFKA_BOOTSTRAP')==='kafka.runtime-dns-check.svc.cluster.local:9092'&&
  envValue(alternateWorker,'LAB_RUNTIME_S3_ENDPOINT')==='http://garage.runtime-dns-check.svc.cluster.local:3900');
const staged=parse(success(['template','lab',chart,...runtimeCommon,'--set','runtime.worker.enabled=false']));
check('Staged bootstrap can enable only the two storage services before the worker starts',staged.length===11&&
  !staged.some(doc=>doc.metadata.labels['app.kubernetes.io/component']==='worker'));
const changedApi=parse(success(['template','lab',chart,...common,'--set','api.environment=mini-pc']));
check('API observation environment can explicitly report mini-pc while default remains k3s',
  envValue(changedApi.find(doc=>doc.metadata.labels['app.kubernetes.io/component']==='api'&&doc.kind==='Deployment').spec.template.spec.containers[0],'LAB_ENVIRONMENT')==='mini-pc');
// Kafka observation adds only a fixed opt-in API environment block. These are render checks,
// not broker, worker liveness, Secret existence, deployment, or observation-success evidence.
const observationPrefix = 'LAB_KAFKA_OBSERVATION_';
const observationNames = ['ENABLED', 'BOOTSTRAP', 'TOPIC', 'GROUP', 'EXPECTED_CLUSTER_ID']
  .map(suffix => observationPrefix + suffix);
const apiManifest = list => list.find(doc => doc.kind === 'Deployment' &&
  doc.metadata.labels?.['app.kubernetes.io/component'] === 'api');
const firstContainer = manifest => manifest.spec.template.spec.containers[0];
const disabledApi = apiManifest(docs), disabledApiContainer = firstContainer(disabledApi);
const disabledObservationEnv = disabledApiContainer.env.filter(value => value.name.startsWith(observationPrefix));
check('Disabled Kafka observation contains only its explicit false flag and no target settings',
  JSON.stringify(disabledObservationEnv) === JSON.stringify([{name: observationNames[0], value: 'false'}]));
const explicitDisabled = success(['template', 'lab', chart, ...runtimeCommon,
  '--set', 'api.kafkaObservation.enabled=false']);
check('Explicitly disabled Kafka observation preserves default rendered bytes including the API',
  explicitDisabled === rendered);
const observationCommon = [...runtimeCommon, '--set', 'api.environment=mini-pc',
  '--set-string', 'api.sourceCommit=' + 'b'.repeat(40)];
const preparedObservation = parse(success(['template', 'lab', chart, ...observationCommon]));
const observationEnabledArgs = [...observationCommon, '--set', 'api.kafkaObservation.enabled=true'];
const observationEnabled = parse(success(['template', 'lab', chart, ...observationEnabledArgs]));
const preparedApi = apiManifest(preparedObservation), observationApi = apiManifest(observationEnabled);
const observationApiContainer = firstContainer(observationApi);
const enabledObservationEnv = observationApiContainer.env.filter(value => value.name.startsWith(observationPrefix));
check('Opt-in observation retains the resource set and changes only the existing API Deployment',
  observationEnabled.length === preparedObservation.length && preparedObservation.every(before =>
    before === preparedApi || JSON.stringify(observationEnabled.find(after =>
      after.kind === before.kind && after.metadata.name === before.metadata.name)) === JSON.stringify(before)));
const observationStrippedApi = structuredClone(observationApi);
firstContainer(observationStrippedApi).env = firstContainer(observationStrippedApi).env
  .flatMap(value => value.name.startsWith(observationPrefix) ?
    (value.name === observationNames[0] ? [{name: value.name, value: 'false'}] : []) : [value]);
check('The complete opt-in API change is exactly the reviewed observation environment block',
  JSON.stringify(observationStrippedApi) === JSON.stringify(preparedApi) &&
  JSON.stringify(enabledObservationEnv.map(value => value.name)) === JSON.stringify(observationNames) &&
  envValue(observationApiContainer, observationNames[0]) === 'true');
const observationWorker = firstContainer(observationEnabled.find(doc =>
  doc.kind === 'Deployment' && doc.metadata.labels?.['app.kubernetes.io/component'] === 'worker'));
const observationKafka = firstContainer(observationEnabled.find(doc =>
  doc.kind === 'StatefulSet' && doc.metadata.labels?.['app.kubernetes.io/component'] === 'kafka'));
check('Observation uses the worker service DNS topic and group without a second target configuration',
  envValue(observationApiContainer, observationNames[1]) === envValue(observationWorker, 'LAB_RUNTIME_KAFKA_BOOTSTRAP') &&
  envValue(observationApiContainer, observationNames[2]) === envValue(observationWorker, 'LAB_RUNTIME_KAFKA_TOPIC') &&
  envValue(observationApiContainer, observationNames[3]) === envValue(observationWorker, 'LAB_RUNTIME_KAFKA_GROUP'));
const observationClusterRef = enabledObservationEnv.find(value => value.name === observationNames[4]);
check('Observation cluster ID uses exactly the existing Kafka cluster ID Secret key and no literal value',
  Object.keys(observationClusterRef).sort().join(',') === 'name,valueFrom' &&
  Object.keys(observationClusterRef.valueFrom).join(',') === 'secretKeyRef' &&
  JSON.stringify(observationClusterRef.valueFrom) === JSON.stringify(observationKafka.env.find(value =>
    value.name === 'CLUSTER_ID').valueFrom));
check('Observation adds no Secret RBAC ServiceAccount token S3 credentials or Secret volume to the API',
  observationEnabled.every(doc => ['ServiceAccount', 'Service', 'Deployment', 'StatefulSet'].includes(doc.kind)) &&
  observationApi.spec.template.spec.automountServiceAccountToken === false &&
  observationApi.spec.template.spec.serviceAccountName === preparedApi.spec.template.spec.serviceAccountName &&
  !observationApiContainer.envFrom && !observationApiContainer.env.some(value => value.name.startsWith('LAB_RUNTIME_S3_')) &&
  enabledObservationEnv.filter(value => value.valueFrom).length === 1 &&
  !observationApi.spec.template.spec.volumes.some(volume => volume.secret || volume.projected));
check('Observation reuses the existing API environment and source identity without overriding the worker',
  envValue(observationApiContainer, 'LAB_ENVIRONMENT') === 'mini-pc' &&
  envValue(observationApiContainer, 'SOURCE_COMMIT') === 'b'.repeat(40) &&
  envValue(observationWorker, 'SOURCE_COMMIT') === 'a'.repeat(40));
const observationAlternate = parse(success(['template', 'lab', chart, ...observationEnabledArgs,
  '--namespace', 'observation-dns-check',
  '--set-string', 'runtime.worker.topic=observation-dispatch-fixture',
  '--set-string', 'runtime.worker.group=observation-worker-fixture',
  '--set-string', 'runtime.kafka.existingSecret=observation-kafka-do-not-install',
  '--set-string', 'runtime.kafka.clusterIdKey=observation-cluster-id']));
const alternateObservationApi = firstContainer(apiManifest(observationAlternate));
const alternateObservationWorker = firstContainer(observationAlternate.find(doc =>
  doc.kind === 'Deployment' && doc.metadata.labels?.['app.kubernetes.io/component'] === 'worker'));
const alternateClusterRef = alternateObservationApi.env.find(value => value.name === observationNames[4]);
check('Observation follows the release namespace and shared custom topic group and cluster ID key',
  envValue(alternateObservationApi, observationNames[1]) === 'kafka.observation-dns-check.svc.cluster.local:9092' &&
  envValue(alternateObservationApi, observationNames[1]) === envValue(alternateObservationWorker, 'LAB_RUNTIME_KAFKA_BOOTSTRAP') &&
  envValue(alternateObservationApi, observationNames[2]) === 'observation-dispatch-fixture' &&
  envValue(alternateObservationApi, observationNames[2]) === envValue(alternateObservationWorker, 'LAB_RUNTIME_KAFKA_TOPIC') &&
  envValue(alternateObservationApi, observationNames[3]) === 'observation-worker-fixture' &&
  envValue(alternateObservationApi, observationNames[3]) === envValue(alternateObservationWorker, 'LAB_RUNTIME_KAFKA_GROUP') &&
  JSON.stringify(alternateClusterRef.valueFrom.secretKeyRef) === JSON.stringify({
    name: 'observation-kafka-do-not-install', key: 'observation-cluster-id'}));
// Do not require a running worker or Garage merely to read a historical EMPTY group.
const observationKafkaOnlyArgs = [...common, '--set', 'api.environment=mini-pc',
  '--set-string', 'api.sourceCommit=' + 'b'.repeat(40),
  '--set', 'api.kafkaObservation.enabled=true', '--set', 'runtime.kafka.enabled=true',
  '--set-string', 'runtime.kafka.existingSecret=lint-kafka-do-not-install'];
const observationKafkaOnly = parse(success(['template', 'lab', chart, ...observationKafkaOnlyArgs]));
check('Observation may be enabled with Kafka while worker and Garage remain disabled',
  observationKafkaOnly.length === 9 &&
  !observationKafkaOnly.some(doc => ['worker', 'garage'].includes(doc.metadata.labels?.['app.kubernetes.io/component'])) &&
  envValue(firstContainer(apiManifest(observationKafkaOnly)), observationNames[0]) === 'true');
const observationRejected = [];
for (const [name, option, value] of [
  ['Observation requires mini-pc API environment', '--set', 'api.environment=k3s'],
  ['Observation rejects unknown API source', '--set-string', 'api.sourceCommit=unknown'],
  ['Observation requires a lowercase 40-character API source', '--set-string', 'api.sourceCommit=' + 'B'.repeat(40)],
  ['Observation requires Kafka even with the worker disabled', '--set', 'runtime.kafka.enabled=false'],
  ['Observation requires an existing cluster ID Secret reference', '--set-string', 'runtime.kafka.existingSecret='],
  ['Observation rejects a string in place of its boolean opt-in', '--set-string', 'api.kafkaObservation.enabled=true'],
  ['Observation requires its enabled property', '--set', 'api.kafkaObservation.enabled=null'],
  ['Observation requires its settings object', '--set', 'api.kafkaObservation=null'],
  ['Observation cannot configure a second bootstrap target', '--set', 'api.kafkaObservation.bootstrap=other.invalid:9092'],
  ['Observation cannot embed a literal cluster ID', '--set', 'api.kafkaObservation.expectedClusterId=fixture-only'],
]) {
  const response = helm(['template', 'lab', chart, ...observationKafkaOnlyArgs, option, value]);
  assert.notEqual(response.status, 0, 'Expected rejection: ' + name);
  assert.match(response.stderr, /values don't meet the specifications of the schema/);
  observationRejected.push(name);
}
const rejected=[];
for(const [name,value]of[
  ['Kafka requires private cluster ID Secret','runtime.kafka.existingSecret='],
  ['Garage requires private config Secret','runtime.garage.existingConfigSecret='],
  ['Worker requires private S3 Secret','runtime.worker.existingS3Secret='],
  ['Worker requires explicit published image','runtime.worker.image.repository='],
  ['Worker rejects unknown source commit','runtime.worker.sourceCommit=unknown'],
  ['Worker requires Kafka enabled','runtime.kafka.enabled=false'],
  ['Worker requires Garage enabled','runtime.garage.enabled=false'],
  ['Worker cannot have competing replicas','runtime.worker.replicaCount=2'],
  ['Worker group cannot exceed the application limit','runtime.worker.group='+('g'.repeat(129))],
  ['Worker rejects insufficient shutdown grace','runtime.worker.terminationGracePeriodSeconds=30'],
  ['Kafka cannot have multiple voters with singleton declaration','runtime.kafka.replicaCount=2'],
  ['Kafka rejects mutable alternative image','runtime.kafka.image.digest=latest'],
  ['Garage rejects arbitrary shared storage class','runtime.garage.persistence.storageClass=existing-data'],
]){
  const result=helm(['template','lab',chart,...runtimeCommon,'--set',value]);
  assert.notEqual(result.status,0,'Expected rejection: '+name);
  assert.match(result.stderr,/values don't meet the specifications of the schema/);
  rejected.push(name);
}
const result={verifiedAt:new Date().toISOString(),scope:'LOCAL_RUNTIME_FIXTURE_HELM_RENDER_ONLY',helmVersion:version,
  kubernetesVersionForRendering:kubeVersion,strictLint:'PASSED',render:'PASSED',
  disabledResourceCount:baseline.length,enabledResourceCount:docs.length,bootstrapOnlyResourceCount:staged.length,
  policyChecksPassed:checks.length,checks,expectedSchemaRejectionsPassed:rejected.length,rejectedInputs:rejected,
  renderedFixtureSha256:crypto.createHash('sha256').update(rendered).digest('hex'),
  kafkaObservationSchemaRejectionsPassed:observationRejected.length, kafkaObservationRejectedInputs:observationRejected,
  kafkaObservationDefaultEnabled:false,kafkaObservationRuntimeVerified:false,
  serverDeploymentVerified:false,pvcBoundVerified:false,brokerOrS3Verified:false,runtimeJobExecutionVerified:false};
fs.writeFileSync(path.join(chart,'ci/runtime-render-validation.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
