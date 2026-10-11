// Local manifest policy checks; this does not access a Kubernetes cluster.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(path.join(root, 'apps/lab-web/package.json'));
const YAML = require('yaml');
const parserVersion = require('yaml/package.json').version;
const renderDir = path.join(root, '.local/platform-render');
const helmBinary = process.env.HELM_BINARY || path.join(root,
  '.local/tools/helm-4.3.0/windows-amd64/helm.exe');
const helmEnv = {
  ...process.env,
  HELM_CACHE_HOME: path.join(root,'.local/tools/helm-home/cache'),
  HELM_CONFIG_HOME: path.join(root,'.local/tools/helm-home/config'),
  HELM_DATA_HOME: path.join(root,'.local/tools/helm-home/data'),
};
function helm(args) {
  const result = spawnSync(helmBinary,args,{cwd:root,env:helmEnv,encoding:'utf8',maxBuffer:32*1024*1024});
  assert.equal(result.status,0,'Local Helm command failed: ' + args[0]);
  return result.stdout;
}
const helmVersion = helm(['version','--short']).trim();
assert.equal(helmVersion,'v4.3.0+gbec5b06','Expected the pinned Helm build');
for (const [name,chart,namespace] of [
  ['jenkins','jenkins-5.9.68.tgz','jenkins'],
  ['argocd','argo-cd-10.10.2.tgz','argocd'],
]) {
  const archive=path.join(renderDir,'charts',chart);
  const values=path.join(root,'infra/platform',name+'-values.yaml');
  fs.writeFileSync(path.join(renderDir,name+'-lint.txt'),
    helm(['lint',archive,'--values',values,'--kube-version','1.36.5','--strict']));
  fs.writeFileSync(path.join(renderDir,name+'.yaml'),
    helm(['template',name,archive,'--namespace',namespace,'--values',values,
      '--kube-version','1.36.5','--include-crds']));
}
const checks = [];
function check(name, condition) {
  assert.ok(condition, name);
  checks.push(name);
}
function parse(text) {
  const documents = YAML.parseAllDocuments(text);
  for (const document of documents) assert.equal(document.errors.length, 0, 'YAML parse errors');
  return documents.map(document => document.toJSON()).filter(Boolean);
}
function manifest(name) {
  return parse(fs.readFileSync(path.join(renderDir, name + '.yaml'), 'utf8'));
}
function one(docs, kind, name) {
  const matches = docs.filter(doc => doc.kind === kind && doc.metadata?.name === name);
  assert.equal(matches.length, 1, 'Expected one ' + kind + ' ' + name);
  return matches[0];
}
const jenkins = manifest('jenkins');
const argo = manifest('argocd');
for (const [name, docs] of [['jenkins', jenkins], ['argocd', argo]]) {
  check(name + ': services remain ClusterIP', docs.filter(doc => doc.kind === 'Service')
    .every(doc => (doc.spec.type || 'ClusterIP') === 'ClusterIP'));
  check(name + ': no ingress or gateway routes', !docs.some(doc =>
    ['Ingress','Gateway','HTTPRoute','GRPCRoute','TCPRoute','TLSRoute','UDPRoute'].includes(doc.kind)));
  const pods = docs.flatMap(doc => doc.kind === 'Pod' ? [doc.spec] :
    ['Deployment','StatefulSet','Job','DaemonSet'].includes(doc.kind) ? [doc.spec.template.spec] : []);
  check(name + ': no host networking or host ports', pods.every(pod => !pod.hostNetwork &&
    [...(pod.containers || []), ...(pod.initContainers || [])].every(container =>
      (container.ports || []).every(port => !port.hostPort))));
}
const jcascMap = one(jenkins, 'ConfigMap', 'jenkins-jenkins-jcasc-config');
const jcasc = YAML.parse(jcascMap.data['jcasc-default-config.yaml']);
check('Jenkins controller has zero executors', jcasc.jenkins.numExecutors === 0);
check('Jenkins anonymous access is disabled',
  jcasc.jenkins.authorizationStrategy.loggedInUsersCanDoAnything.allowAnonymousRead === false);
check('Jenkins signup is disabled', jcasc.jenkins.securityRealm.local.allowsSignup === false);
check('Jenkins TCP agent listener is not exposed through a Service', jenkins.filter(doc =>
  doc.kind === 'Service').every(doc => doc.spec.ports.every(port => port.port !== 50000)));
const cloud = jcasc.jenkins.clouds.map(item => item.kubernetes).find(Boolean);
check('Jenkins cloud allows one build Pod', String(cloud.containerCapStr) === '1');
check('Jenkins agents use WebSocket', cloud.webSocket === true);
const template = cloud.templates.find(item => item.name === 'default');
check('Default agent template exists and is capped at one', template?.instanceCap === 1);
check('Default template uses distinct build service account', template.serviceAccount === 'jenkins-build-agent');
check('Default template merges inherited YAML', template.yamlMergeStrategy === 'merge' &&
  template.inheritYamlMergeStrategy === true);
const inheritedPod = YAML.parse(template.yaml);
check('Default Pod does not automount API credentials', inheritedPod.spec.automountServiceAccountToken === false);
check('Default Pod uses UID/GID/fsGroup 1000', ['runAsUser','runAsGroup','fsGroup']
  .every(key => inheritedPod.spec.securityContext[key] === 1000));
const agentAccount = one(jenkins, 'ServiceAccount', 'jenkins-build-agent');
check('Build service account disables token automount', agentAccount.automountServiceAccountToken === false);
const pvc = one(jenkins, 'PersistentVolumeClaim', 'jenkins');
check('Jenkins uses the explicit 10Gi local-path PVC', pvc.spec.storageClassName === 'local-path' &&
  pvc.spec.resources.requests.storage === '10Gi');
const plugins = one(jenkins, 'ConfigMap', 'jenkins').data['plugins.txt'];
check('Pipeline JUnit and Timestamper plugins are pinned', plugins.includes('timestamper:1.30') &&
  plugins.includes('junit:1437.v12280a_c49b_50'));
check('Declarative model plugins share the pinned compatible release', ['pipeline-model-definition','pipeline-model-api','pipeline-model-extensions','pipeline-stage-tags-metadata'].every(name => plugins.includes(name + ':2.2293.v6e7193cec599')));
check('Pipeline REST API is explicitly pinned for stage evidence', plugins.includes('pipeline-rest-api:2.41'));
const argoConfig = one(argo, 'ConfigMap', 'argocd-cm').data;
const argoParams = one(argo, 'ConfigMap', 'argocd-cmd-params-cm').data;
check('Argo keeps local admin and disables anonymous access', argoConfig['admin.enabled'] === 'true' &&
  argoConfig['users.anonymous.enabled'] === 'false');
check('Argo UI exec is disabled', argoConfig['exec.enabled'] === 'false');
check('Argo server retains TLS', argoParams['server.insecure'] === 'false');
check('Argo has no persistent cache PVC', argo.every(doc => doc.kind !== 'PersistentVolumeClaim'));
check('Argo ApplicationSet is scaled to zero',
  one(argo, 'Deployment', 'argocd-applicationset-controller').spec.replicas === 0);
check('Argo Dex and Notifications are disabled', !argo.some(doc =>
  doc.metadata?.name === 'argocd-dex-server' || doc.metadata?.name === 'argocd-notifications-controller'));
const agent = YAML.parse(fs.readFileSync(path.join(root, 'infra/jenkins/agent-pod.yaml'), 'utf8'));
check('Pipeline Pod uses the expected service account and no API token', agent.spec.serviceAccountName ===
  'jenkins-build-agent' && agent.spec.automountServiceAccountToken === false);
check('Pipeline Pod keeps UID/GID/fsGroup 1000', ['runAsUser','runAsGroup','fsGroup']
  .every(key => agent.spec.securityContext[key] === 1000));
const inbound = agent.spec.containers.find(container => container.name === 'jnlp');
check('Pipeline jnlp inherits its chart image and command', inbound && !inbound.image && !inbound.command);
check('Pipeline containers cannot escalate or keep capabilities', agent.spec.containers.every(container =>
  container.securityContext?.allowPrivilegeEscalation === false &&
  container.securityContext?.capabilities?.drop?.includes('ALL')));
const imageLock = JSON.parse(fs.readFileSync(path.join(root, 'infra/image-lock.json'), 'utf8'));
check('Build images match the repository image lock', agent.spec.containers.filter(container => container.image)
  .every(container => Object.values(imageLock.images).includes(container.image)));
const pipeline = fs.readFileSync(path.join(root, 'Jenkinsfile'), 'utf8');
check('Pipeline inherits default and disables concurrent builds', pipeline.includes("inheritFrom 'default'") &&
  pipeline.includes('disableConcurrentBuilds()'));
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const describe = docs => ({
  manifestCount: docs.length,
  kinds: docs.reduce((counts, doc) => (counts[doc.kind] = (counts[doc.kind] || 0) + 1, counts), {}),
  helmTestHookCount: docs.filter(doc => String(doc.metadata?.annotations?.['helm.sh/hook'] || '')
    .split(',').some(hook => hook.trim().startsWith('test'))).length,
});
const versions = {
  verifiedAt: '2026-10-11',
  k3s: {version:'v1.36.5+k3s1', channel:'stable',
    source:'https://raw.githubusercontent.com/k3s-io/k3s/main/channel.yaml',
    linuxAmd64:{url:'https://github.com/k3s-io/k3s/releases/download/v1.36.5%2Bk3s1/k3s',
      sha256:'d73847bcd3c5fccef0115b372e2f9a91f3032dc84bbf71518a4617565294d313'},
    checksumListAmd64:{url:'https://github.com/k3s-io/k3s/releases/download/v1.36.5%2Bk3s1/sha256sum-amd64.txt',
      sha256:'ee5fa48dfc2f3d3e521170bfb52c5dd44365ac734c23857a664c27109ae2ce9a'},
    installer:{url:'https://raw.githubusercontent.com/k3s-io/k3s/v1.36.5%2Bk3s1/install.sh',
      sha256:'46177d4c99440b4c0311b67233823a8e8a2fc09693f6c89af1a7161e152fbfad'}},
  helm: {version:'v4.3.0',
    windowsAmd64:{url:'https://get.helm.sh/helm-v4.3.0-windows-amd64.zip',
      sha256:'304ea163cce4d9ad14e189c01846c6a34de9cfdfe48536ae54b2e8ba7884e67c'},
    linuxAmd64:{url:'https://get.helm.sh/helm-v4.3.0-linux-amd64.tar.gz',
      sha256:'86584a54def73570558f66f5111cc53dfed56689637ae32c1201205d494f54fb'}},
  charts: {
    jenkins:{version:'5.9.68',appVersion:'2.580.1',repository:'https://charts.jenkins.io',
      sha256:hash(path.join(renderDir,'charts/jenkins-5.9.68.tgz'))},
    argocd:{version:'10.10.2',appVersion:'v3.5.4',repository:'https://argoproj.github.io/argo-helm',
      sha256:hash(path.join(renderDir,'charts/argo-cd-10.10.2.tgz'))},
  },
  plugins:Object.fromEntries([...YAML.parse(fs.readFileSync(path.join(root,'infra/platform/jenkins-values.yaml'),'utf8')).controller.installPlugins, ...YAML.parse(fs.readFileSync(path.join(root,'infra/platform/jenkins-values.yaml'),'utf8')).controller.additionalPlugins].map(plugin => { const split=plugin.indexOf(':'); return [plugin.slice(0,split),plugin.slice(split+1)]; })),
};
check('Downloaded Helm matches the official Windows SHA256', hash(path.join(root,
  '.local/tools/helm-4.3.0/helm-v4.3.0-windows-amd64.zip')) === versions.helm.windowsAmd64.sha256);
const summary = {
  verifiedAt:'2026-10-11', scope:'LOCAL_HELM_RENDER_ONLY', helmVersion,
  kubernetesVersionForRendering:'1.36.5', yamlParserVersion:parserVersion,
  helmStrictLint:{jenkins:'PASSED',argocd:'PASSED'},
  jenkins:describe(jenkins), argocd:describe(argo), policyChecksPassed:checks.length, checks,
  serverInstallationVerified:false, jenkinsExecutionVerified:false, argoSyncVerified:false,
  limitations:[
    'No Kubernetes API server dry-run, image pull, PVC binding, plugin installation or Pipeline execution was performed.',
    'Major chart/application versions and primary plugins are pinned; transitive plugins and every platform image digest are not fully locked.',
  ],
};
for (const [file, value] of Object.entries({'versions.lock.json':versions,'render-validation.json':summary})) {
  fs.writeFileSync(path.join(root,'infra/platform',file), JSON.stringify(value,null,2) + '\n');
}
console.log(JSON.stringify({scope:summary.scope,helmVersion:summary.helmVersion,
  jenkins:summary.jenkins,argocd:summary.argocd,policyChecksPassed:checks.length,
  serverInstallationVerified:false},null,2));