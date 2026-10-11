// Local Helm policy checks only. Never connects to a cluster or creates a Secret.
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
const output = path.join(root, '.local/app-helm-render');
fs.mkdirSync(output, { recursive: true });
const binary = process.env.HELM_BINARY || path.join(root, '.local/tools/helm-4.3.0/windows-amd64/helm.exe');
const env = { ...process.env,
  HELM_CACHE_HOME: path.join(root, '.local/tools/helm-home/cache'),
  HELM_CONFIG_HOME: path.join(root, '.local/tools/helm-home/config'),
  HELM_DATA_HOME: path.join(root, '.local/tools/helm-home/data'),
};
const kubeVersion = '1.36.5';
function helm(args) {
  const result = spawnSync(binary, args, { cwd: root, env, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
  if (result.error) throw result.error;
  return result;
}
function success(args) {
  const result = helm(args);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout;
}
const helmVersion = success(['version', '--short']).trim();
assert.equal(helmVersion, 'v4.3.0+gbec5b06');
const fixture = path.join(chart, 'ci/lint-values.yaml');
const common = ['--values', fixture, '--kube-version', kubeVersion];
const lint = success(['lint', chart, ...common, '--strict']);
const rendered = success(['template', 'lab', chart, '--namespace', 'platform-lab', ...common]);
fs.writeFileSync(path.join(output, 'lint.txt'), lint);
fs.writeFileSync(path.join(output, 'fixture.yaml'), rendered);
const parsed = YAML.parseAllDocuments(rendered);
for (const document of parsed) assert.equal(document.errors.length, 0);
const docs = parsed.map(document => document.toJSON()).filter(Boolean);
const checks = [];
function check(name, condition) {
  assert.ok(condition, name);
  checks.push(name);
}
const workloads = docs.filter(doc => ['Deployment', 'StatefulSet'].includes(doc.kind));
const pods = workloads.map(doc => doc.spec.template.spec);
const containers = pods.flatMap(pod => pod.containers);
const component = name => workloads.find(doc => doc.metadata.labels['app.kubernetes.io/component'] === name);
const api = component('api');
const web = component('web');
const db = component('database');
const apiUpstreamHost = manifest => manifest.spec.template.spec.containers[0].env?.find(
  item => item.name === 'API_UPSTREAM_HOST')?.value;
check('Web dynamic DNS uses the fully-qualified API Service name for the release namespace',
  apiUpstreamHost(web) === 'api.platform-lab.svc.cluster.local');
const alternateNamespace = 'dns-regression-check';
const alternateDocs = YAML.parseAllDocuments(success([
  'template', 'lab', chart, '--namespace', alternateNamespace, ...common,
])).map(document => document.toJSON()).filter(Boolean);
check('Web API DNS follows a different release namespace without hardcoding platform-lab',
  apiUpstreamHost(alternateDocs.find(document => document.kind === 'Deployment' &&
    document.metadata.labels['app.kubernetes.io/component'] === 'web')) ===
    `api.${alternateNamespace}.svc.cluster.local`);
check('Seven resources: one service account, three Services, two Deployments and one StatefulSet',
  docs.length === 7 && workloads.length === 3 &&
  docs.filter(doc => doc.kind === 'Service').length === 3 &&
  docs.filter(doc => doc.kind === 'ServiceAccount').length === 1);
check('No Secret, RBAC, ingress, gateway, cluster-scoped resources or standalone storage objects',
  docs.every(doc => ['ServiceAccount', 'Service', 'Deployment', 'StatefulSet'].includes(doc.kind)));
check('ClusterIP only, headless db identity, api:8080 Nginx and db:3306 JDBC',
  docs.filter(doc => doc.kind === 'Service').every(doc => doc.spec.type === 'ClusterIP') && db.spec.serviceName === 'db' &&
  docs.find(doc => doc.kind === 'Service' && doc.metadata.name === 'db').spec.clusterIP === 'None' &&
  docs.find(doc => doc.kind === 'Service' && doc.metadata.name === 'api').spec.ports[0].port === 8080 &&
  docs.find(doc => doc.kind === 'Service' && doc.metadata.name === 'db').spec.ports[0].port === 3306);
check('No host network, PID, IPC, host port or hostPath',
  pods.every(pod => !pod.hostNetwork && !pod.hostPID && !pod.hostIPC &&
    (pod.volumes || []).every(volume => !volume.hostPath) &&
    pod.containers.every(container => (container.ports || []).every(port => !port.hostPort))));
check('Single replica per workload and Recreate for the sample bootstrap API',
  workloads.every(doc => doc.spec.replicas === 1) && api.spec.strategy.type === 'Recreate');
check('Service account and all Pods disable Kubernetes API token automount',
  docs.find(doc => doc.kind === 'ServiceAccount').automountServiceAccountToken === false &&
  pods.every(pod => pod.automountServiceAccountToken === false));
check('API and web run nonroot with read-only root, RuntimeDefault, no escalation and no capabilities',
  [api, web].every(doc => {
    const pod = doc.spec.template.spec;
    return pod.securityContext.runAsNonRoot === true && pod.securityContext.runAsUser > 0 &&
      pod.securityContext.seccompProfile.type === 'RuntimeDefault' &&
      pod.containers.every(c => c.securityContext.readOnlyRootFilesystem === true &&
        c.securityContext.allowPrivilegeEscalation === false &&
        c.securityContext.capabilities.drop.includes('ALL'));
  }));
check('Writable /tmp is isolated in bounded emptyDir for both app containers',
  [api, web].every(doc => doc.spec.template.spec.volumes.find(v => v.name === 'tmp')?.emptyDir.sizeLimit &&
    doc.spec.template.spec.containers[0].volumeMounts.some(v => v.name === 'tmp' && v.mountPath === '/tmp')));
check('API startup/liveness exclude DB while readiness uses the DB-aware health group',
  api.spec.template.spec.containers[0].startupProbe.httpGet.path === '/actuator/health/liveness' &&
  api.spec.template.spec.containers[0].livenessProbe.httpGet.path === '/actuator/health/liveness' &&
  api.spec.template.spec.containers[0].readinessProbe.httpGet.path === '/actuator/health/readiness');
check('DB startup/readiness use the official healthcheck; liveness checks only the TCP listener',
  ['startupProbe', 'readinessProbe'].every(key =>
    JSON.stringify(db.spec.template.spec.containers[0][key].exec.command) ===
      JSON.stringify(['healthcheck.sh', '--connect', '--innodb_initialized'])) &&
  db.spec.template.spec.containers[0].livenessProbe.tcpSocket.port === 'mysql');
const passwordEnv = containers.flatMap(c => c.env || []).filter(e => /PASSWORD$/.test(e.name));
check('All three password references use only the existing Secret and no literal value',
  passwordEnv.length === 3 && passwordEnv.every(e => !('value' in e) &&
    e.valueFrom?.secretKeyRef?.name === 'lint-only-do-not-install') &&
  new Set(passwordEnv.map(e => e.valueFrom.secretKeyRef.key)).size === 2);
const claim = db.spec.volumeClaimTemplates[0];
check('Dedicated 10Gi local-path PVC remains on StatefulSet removal and scale-down',
  db.spec.volumeClaimTemplates.length === 1 && claim.spec.storageClassName === 'local-path' &&
  claim.spec.resources.requests.storage === '10Gi' && claim.spec.accessModes[0] === 'ReadWriteOnce' &&
  Object.values(db.spec.persistentVolumeClaimRetentionPolicy).every(v => v === 'Retain'));
check('Every container has CPU, memory and ephemeral storage requests/limits',
  containers.every(c => ['requests', 'limits'].every(kind =>
    ['cpu', 'memory', 'ephemeral-storage'].every(key => !!c.resources[kind][key]))));
const lock = JSON.parse(fs.readFileSync(path.join(root, 'infra/image-lock.json'), 'utf8'));
check('MariaDB image matches the repository digest lock',
  db.spec.template.spec.containers[0].image === lock.images['mariadb:11.8.9']);
check('API/web fixture references are clearly unpublished and digest-shaped',
  [api, web].every(doc => /^example\.invalid\/lint-only\/.+@sha256:[a-f0-9]{64}$/.test(
    doc.spec.template.spec.containers[0].image)));
const rejected = [];
for (const [name, args] of [
  ['missing API/web images and existingSecret', ['template', 'lab', chart, '--kube-version', kubeVersion]],
  ['missing existingSecret', ['template', 'lab', chart, ...common, '--set', 'database.existingSecret=']],
  ['mutable/invalid API digest', ['template', 'lab', chart, ...common, '--set', 'api.image.digest=latest']],
  ['multiple API replicas', ['template', 'lab', chart, ...common, '--set', 'api.replicaCount=2']],
  ['public ingress enabled', ['template', 'lab', chart, ...common, '--set', 'ingress.enabled=true']],
  ['reuse another storage class', ['template', 'lab', chart, ...common, '--set', 'database.persistence.storageClass=existing-data']],
]) {
  const result = helm(args);
  assert.notEqual(result.status, 0, 'Expected rejection: ' + name);
  assert.match(result.stderr, /values don't meet the specifications of the schema/,
    'Expected JSON schema rejection: ' + name);
  rejected.push(name);
}
const kinds = {};
for (const doc of docs) kinds[doc.kind] = (kinds[doc.kind] || 0) + 1;
const result = {
  verifiedAt: new Date().toISOString().slice(0, 10),
  scope: 'LOCAL_FIXTURE_HELM_RENDER_ONLY',
  helmVersion, kubernetesVersionForRendering: kubeVersion,
  yamlParserVersion: require('yaml/package.json').version,
  strictLint: 'PASSED', render: 'PASSED',
  manifestCount: docs.length, kinds, policyChecksPassed: checks.length, checks,
  expectedSchemaRejectionsPassed: rejected.length, rejectedInputs: rejected,
  renderedFixtureSha256: crypto.createHash('sha256').update(rendered).digest('hex'),
  appImagesPublished: false,
  containerRuntimeVerified: false,
  mariadbIntegrationVerified: false,
  kubernetesApiDryRunVerified: false,
  serverDeploymentVerified: false,
  argoSyncVerified: false,
};
fs.writeFileSync(path.join(chart, 'ci/render-validation.json'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result, null, 2));