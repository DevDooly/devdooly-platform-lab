// Offline render checks. Output must be a new directory outside the source tree.
// This program never installs dependencies or contacts/applies to a cluster.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { gunzipSync } from 'node:zlib';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const chart = path.join(root, 'infra/charts/platform-lab');
const gateway = path.join(root, 'infra/public-gateway');
const digest = data => crypto.createHash('sha256').update(data).digest('hex');
const approvedHelm = '2f65add9f1d5c96fc70ad70f06f1c47b3ef21bee4a9f086d861bb138429e9c13';
const approvedLinuxArchive = '86584a54def73570558f66f5111cc53dfed56689637ae32c1201205d494f54fb';
const baselineSourceManifestHash = '4f385f7011eee90b62a66976f20bb46225a21dc95956867b504d228faf9bf282';
const baselineHash = '1862ec4a796a4ec860a78e84c35bb8ebf2db483ffe432974cd62ee88a0173a32';
const receiptHash = '826971e2d3ddbacfe78da710405bb4cb58b7b73d1fb2a691ada10981a168d347';
const policyManifestHash = 'e2aeac75256bfcfb65adddf1fe9d6da569b8574f2fa42b292b5e12f138b68951';
const expectedImage = 'nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94';
const component = 'public-read-gateway';
const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  assert.ok(['--helm', '--helm-archive', '--baseline', '--baseline-receipt', '--yaml-require-from', '--output'].includes(key), 'unknown argument');
  assert.ok(process.argv[index + 1] && !args.has(key), 'missing or repeated argument');
  args.set(key, path.resolve(process.argv[index + 1]));
}
assert.ok(['win32', 'linux'].includes(process.platform), 'only the approved Windows/Linux tools are supported');
assert.equal(args.size, process.platform === 'linux' ? 6 : 5, 'explicit tool and input paths are required');
for (const key of ['--helm', '--baseline', '--baseline-receipt', '--yaml-require-from', '--output']) assert.ok(args.has(key), 'required path');
if (process.platform === 'linux') assert.ok(args.has('--helm-archive'), 'Linux requires its verified archive');
const output = args.get('--output');
const inside = (parent, child) => {
  const relative = path.relative(parent, child);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
};
assert.ok(!inside(root, output) && !inside(output, root), 'output must not overlap the source tree');
assert.ok(!fs.existsSync(output), 'output directory must be fresh');
fs.mkdirSync(output, { recursive: true });
const report = {
  schemaVersion: 1, scope: 'OFFLINE_OPTIONAL_GATEWAY_HELM_RENDER',
  passed: false, phase: 'PRECONDITIONS', failureCode: 'NONE',
  helmInvocations: 0, checks: [], expectedFailureInputs: [],
  sourceBytesUnchanged: false, helmExecutableUnchanged: false,
  clusterAccessRequested: false, appliedToCluster: false,
  dnsReachabilityVerified: false, networkConnectivityVerified: false,
  schedulerAdmissionVerified: false, argoPermissionChanged: false,
  dependencyInstallationRequested: false,
};
let sourceBefore;
let helmBefore;
function check(code, condition) {
  report.lastCheck = code;
  assert.ok(condition, code);
  report.checks.push(code);
}
function equal(code, actual, expected) {
  report.lastCheck = code;
  assert.deepEqual(actual, expected, code);
  report.checks.push(code);
}
function regularRead(filename, maximum = 1024 * 1024) {
  const stat = fs.lstatSync(filename);
  assert.ok(stat.isFile() && !stat.isSymbolicLink() && stat.size <= maximum, 'regular bounded file required');
  return fs.readFileSync(filename);
}
function sourceSnapshot() {
  const paths = [];
  const visit = directory => {
    for (const name of fs.readdirSync(directory).sort()) {
      const filename = path.join(directory, name);
      const stat = fs.lstatSync(filename);
      assert.ok(!stat.isSymbolicLink(), 'source symlinks are forbidden');
      if (stat.isDirectory()) visit(filename);
      else paths.push(filename);
    }
  };
  visit(chart);
  for (const filename of [
    'gitops/bootstrap/application.yaml', 'gitops/bootstrap/project.yaml',
    'gitops/environments/home-lab/values.yaml', 'gitops/environments/home-lab/runtime.yaml',
    'infra/image-lock.json', 'infra/platform/versions.lock.json',
    '.github/workflows/public-gateway-chart.yml', 'docs/runbooks/public-read-gateway-chart.md',
    'docs/evidence/public-read-gateway-chart/README.md',
    'docs/evidence/public-read-gateway-chart/local-final2-failure.json',
    'docs/evidence/public-read-gateway-chart/local-final3-summary.json',
  ]) paths.push(path.join(root, filename));
  visit(gateway);
  assert.ok(paths.length <= 128, 'source file bound');
  const records = paths.sort().map(filename => {
    const data = regularRead(filename);
    return { path: path.relative(root, filename).replaceAll(path.sep, '/'), bytes: data.length, sha256: digest(data) };
  });
  assert.ok(records.reduce((total, item) => total + item.bytes, 0) <= 8 * 1024 * 1024, 'source byte bound');
  return records;
}
function main() {
  sourceBefore = sourceSnapshot();
  fs.writeFileSync(path.join(output, 'source-before.json'), `${JSON.stringify(sourceBefore, null, 2)}\n`);
  helmBefore = digest(regularRead(args.get('--helm'), 80 * 1024 * 1024));
  if (process.platform === 'win32') {
    check('APPROVED_WINDOWS_HELM_BINARY', helmBefore === approvedHelm);
  } else {
    const versions = JSON.parse(regularRead(path.join(root, 'infra/platform/versions.lock.json')));
    check('EXISTING_LINUX_HELM_ARCHIVE_PIN', versions.helm.version === 'v4.3.0' &&
      versions.helm.linuxAmd64.sha256 === approvedLinuxArchive &&
      versions.helm.linuxAmd64.url === 'https://get.helm.sh/helm-v4.3.0-linux-amd64.tar.gz');
    const archive = regularRead(args.get('--helm-archive'), 32 * 1024 * 1024);
    check('LINUX_ARCHIVE_BYTES_VERIFIED', digest(archive) === approvedLinuxArchive);
    const tar = gunzipSync(archive, { maxOutputLength: 96 * 1024 * 1024 });
    let offset = 0;
    let members = 0;
    let matchingMembers = 0;
    while (offset + 512 <= tar.length) {
      const header = tar.subarray(offset, offset + 512);
      if (header.every(byte => byte === 0)) break;
      members += 1;
      assert.ok(members <= 16, 'archive member bound');
      const name = header.subarray(0, 100).toString('utf8').split('\0')[0];
      const isUstar = header.subarray(257, 263).toString('ascii') === 'ustar\0' &&
        header.subarray(263, 265).toString('ascii') === '00';
      const prefix = isUstar ? header.subarray(345, 500).toString('utf8').split('\0')[0] : '';
      const fullName = prefix ? `${prefix}/${name}` : name;
      const octal = header.subarray(124, 136).toString('ascii').replaceAll('\0', '').trim();
      assert.ok(/^[0-7]+$/.test(octal), 'bounded regular tar size');
      const size = Number.parseInt(octal, 8);
      assert.ok(size <= 80 * 1024 * 1024 && offset + 512 + size <= tar.length, 'archive payload bound');
      if (fullName === 'linux-amd64/helm') {
        assert.ok(header[156] === 0 || header[156] === 48, 'Helm member must be regular');
        matchingMembers += 1;
        check('LINUX_EXECUTABLE_IS_EXACT_ARCHIVE_MEMBER', digest(tar.subarray(offset + 512, offset + 512 + size)) === helmBefore);
      }
      offset += 512 + Math.ceil(size / 512) * 512;
    }
    check('ONE_LINUX_HELM_MEMBER', matchingMembers === 1);
    report.helmArchiveSha256 = approvedLinuxArchive;
  }
  const baseline = regularRead(args.get('--baseline'));
  const receiptBytes = regularRead(args.get('--baseline-receipt'));
  check('IMMUTABLE_BASELINE_HASH', digest(baseline) === baselineHash && baseline.length === 25810);
  const receipt = JSON.parse(receiptBytes);
  if (process.platform === 'win32') {
    check('IMMUTABLE_WINDOWS_BASELINE_RECEIPT_HASH', digest(receiptBytes) === receiptHash);
  } else {
    check('ACTUAL_PINNED_LINUX_BASELINE_RECEIPT', receipt.scope === 'PINNED_MAIN_K_LINUX_OFFLINE_BASELINE' &&
      receipt.sourceManifestSha256 === baselineSourceManifestHash && receipt.helmArchiveSha256 === approvedLinuxArchive &&
      receipt.helmExecutableSha256 === helmBefore && receipt.returnCode === 0 && receipt.stderrBytesDiscarded === 0 &&
      receipt.renderBytes === 25810 && receipt.sourceBytesUnchanged === true &&
      receipt.clusterAccessRequested === false && receipt.appliedToCluster === false);
  }
  check('BASELINE_IS_ACTUAL_MAIN_K_RENDER', receipt.passed === true && receipt.objectCount === 12 &&
    receipt.mainCommit === '13447fa88987050f64e47c01684ecb9c233b34fb' &&
    receipt.namespaceInput === 'platform-lab' && receipt.releaseName === 'lab' &&
    receipt.kubeVersionInput === '1.36.5' && receipt.renderSha256 === baselineHash);
  const require = createRequire(args.get('--yaml-require-from'));
  const YAML = require('yaml');
  const parse = bytes => {
    const documents = YAML.parseAllDocuments(bytes.toString('utf8'), { uniqueKeys: true });
    for (const document of documents) assert.equal(document.errors.length, 0, 'render YAML errors');
    return documents.map(document => document.toJSON()).filter(Boolean);
  };
  const policyBytes = regularRead(path.join(gateway, 'runtime-manifest.json'));
  check('VALIDATED_POLICY_MANIFEST', digest(policyBytes) === policyManifestHash);
  const policyManifest = JSON.parse(policyBytes);
  equal('POLICY_COHORT_SIZE', policyManifest.files.length, 8);
  for (const file of policyManifest.files) {
    check('POLICY_FLAT_PATH', /^[a-zA-Z0-9_.-]+$/.test(file.path));
    const bytes = regularRead(path.join(gateway, file.path));
    check('POLICY_COHORT_FILE', bytes.length === file.bytes && digest(bytes) === file.sha256);
  }
  const policy = {};
  for (const filename of ['nginx.conf', 'proxy.inc']) {
    const bytes = regularRead(path.join(chart, 'files/public-gateway', filename));
    equal('POLICY_BUNDLE_BYTE_PARITY', bytes, regularRead(path.join(gateway, filename)));
    policy[filename] = bytes.toString('utf8');
  }
  const lockBytes = regularRead(path.join(root, 'infra/image-lock.json'));
  check('EXISTING_IMAGE_LOCK_UNCHANGED', digest(lockBytes) === '3a0b222ca246d8353c9e07febed03f8828a6f53068fe3cf7afbd84291403db08');
  check('PINNED_IMAGE_MATCHES_COHORT', policyManifest.images.nginx === expectedImage &&
    JSON.parse(lockBytes).images['nginx:stable-alpine'] === expectedImage);
  const project = parse(regularRead(path.join(root, 'gitops/bootstrap/project.yaml')))[0];
  equal('APP_PROJECT_EXACT_SEVEN_NAMESPACED_KINDS', project.spec.namespaceResourceWhitelist, [
    { group: 'apps', kind: 'Deployment' }, { group: 'apps', kind: 'StatefulSet' },
    { group: '', kind: 'Service' }, { group: '', kind: 'ConfigMap' },
    { group: '', kind: 'PersistentVolumeClaim' }, { group: '', kind: 'ServiceAccount' },
    { group: 'networking.k8s.io', kind: 'NetworkPolicy' },
  ]);
  equal('APP_PROJECT_DEDICATED_DESTINATION', project.spec.destinations, [
    { namespace: 'platform-lab', server: 'https://kubernetes.default.svc' },
  ]);
  equal('APP_PROJECT_NO_CLUSTER_SCOPED_PERMISSION', project.spec.clusterResourceWhitelist, []);
  equal('APP_PROJECT_IDENTITY', [project.metadata.name, project.metadata.namespace], ['platform-lab', 'argocd']);
  const dirs = Object.fromEntries(['cache', 'config', 'data', 'plugins', 'tmp'].map(name => {
    const directory = path.join(output, name);
    fs.mkdirSync(directory);
    return [name, directory];
  }));
  const env = {
    TMP: dirs.tmp, TEMP: dirs.tmp, TMPDIR: dirs.tmp,
    HELM_CACHE_HOME: dirs.cache, HELM_CONFIG_HOME: dirs.config, HELM_DATA_HOME: dirs.data,
    HELM_PLUGINS: dirs.plugins, KUBECONFIG: path.join(output, 'no-cluster-config'),
  };
  // Preserve the user's home identity; only Helm/TMP directories are task-specific.
  for (const key of ['SystemRoot', 'SYSTEMROOT', 'WINDIR', 'HOME', 'USERPROFILE']) {
    if (process.env[key] !== undefined) env[key] = process.env[key];
  }
  check('HOME_AND_USERPROFILE_UNCHANGED', env.HOME === process.env.HOME && env.USERPROFILE === process.env.USERPROFILE);
  const helm = parameters => {
    report.helmInvocations += 1;
    assert.ok(report.helmInvocations <= 32, 'Helm invocation bound');
    const result = spawnSync(args.get('--helm'), parameters, {
      cwd: root, env, windowsHide: true, timeout: 30000, maxBuffer: 2 * 1024 * 1024,
    });
    assert.ok(!result.error && result.signal === null && Number.isInteger(result.status), 'bounded Helm process failure');
    return result;
  };
  const version = helm(['version', '--short']);
  const versionText = version.stdout.toString('utf8');
  const observedVersion = /^v[0-9]+\.[0-9]+\.[0-9]+(?:\+[A-Za-z0-9.-]+)?\r?\n?$/.test(versionText) ? versionText.trim() : null;
  report.helmVersionDiagnostic = {
    returnCode: version.status, stdoutBytes: version.stdout.length,
    stderrBytesDiscarded: version.stderr.length, semver: observedVersion,
  };
  check('HELM_VERSION_4_3_0', version.status === 0 && version.stderr.length === 0 && observedVersion === 'v4.3.0+gbec5b06');
  // Historical K comparison is separate from a render using current live-environment values.
  const valueRoot = path.join(path.dirname(args.get('--baseline-receipt')),
    process.platform === 'linux' ? 'baseline-source' : 'workspace');
  const baselineSourceBytes = regularRead(path.join(chart, 'ci/public-gateway-main-k-source.json'));
  check('PINNED_MAIN_K_PUBLIC_SOURCE_MANIFEST', digest(baselineSourceBytes) === baselineSourceManifestHash);
  const baselineSources = JSON.parse(baselineSourceBytes);
  for (const name of ['gitops/environments/home-lab/values.yaml', 'gitops/environments/home-lab/runtime.yaml']) {
    const expected = baselineSources.files.find(file => file.path === name);
    const bytes = regularRead(path.join(valueRoot, name));
    check('MAIN_K_FIXED_RENDER_VALUES', bytes.length === expected.bytes && digest(bytes) === expected.sha256);
  }
  const common = ['--values', path.join(valueRoot, 'gitops/environments/home-lab/values.yaml'),
    '--values', path.join(valueRoot, 'gitops/environments/home-lab/runtime.yaml'), '--kube-version', '1.36.5'];
  const render = (name, extra = [], namespace = 'platform-lab', release = 'lab', reject = false) => {
    report.phase = name;
    const result = helm(['template', release, chart, '--namespace', namespace, ...common, ...extra]);
    if (reject) {
      check(name, result.status !== 0 && result.stdout.length === 0);
      report.expectedFailureInputs.push(name);
      return;
    }
    check(`${name}_EXIT_ZERO`, result.status === 0 && result.stderr.length === 0);
    fs.writeFileSync(path.join(output, `${name}.yaml`), result.stdout);
    return { bytes: result.stdout, docs: parse(result.stdout) };
  };
  const disabled = render('DEFAULT_DISABLED');
  equal('DEFAULT_DISABLED_BYTE_EXACT_TO_12_RESOURCE_BASELINE', disabled.bytes, baseline);
  equal('DEFAULT_DISABLED_RESOURCE_COUNT', disabled.docs.length, 12);
  const explicitFalse = render('EXPLICIT_FALSE', ['--set', 'publicReadGateway.enabled=false']);
  equal('EXPLICIT_FALSE_BYTE_EXACT_TO_BASELINE', explicitFalse.bytes, baseline);
  const enabled = render('ENABLED', ['--values', path.join(chart, 'ci/public-gateway-enabled-values.yaml')]);
  const isGateway = document => document.metadata.labels?.['app.kubernetes.io/component'] === component;
  const old = enabled.docs.filter(document => !isGateway(document));
  const added = enabled.docs.filter(isGateway);
  equal('ENABLED_PRESERVES_ALL_12_EXISTING_OBJECTS', old, disabled.docs);
  equal('ONLY_FOUR_GATEWAY_OBJECTS', added.map(document => document.kind).sort(), ['ConfigMap', 'Deployment', 'NetworkPolicy', 'Service']);
  const select = kind => added.find(document => document.kind === kind);
  const cm = select('ConfigMap');
  const deploy = select('Deployment');
  const service = select('Service');
  const network = select('NetworkPolicy');
  equal('CONFIGMAP_DECODED_BYTES_MATCH_VERIFIED_POLICIES', cm.data, policy);
  const selector = {
    'app.kubernetes.io/name': 'platform-lab', 'app.kubernetes.io/instance': 'lab',
    'app.kubernetes.io/component': component,
  };
  for (const object of added) {
    check('GATEWAY_NAMES_SAFE_AND_IDENTICAL', object.metadata.name === 'lab-platform-lab-public-read' && object.metadata.name.length <= 63);
    check('GATEWAY_HAS_NO_NAMESPACE_OVERRIDE', object.metadata.namespace === undefined);
  }
  equal('DEPLOYMENT_REPLICA_ONE_RECREATE', [deploy.spec.replicas, deploy.spec.strategy], [1, { type: 'Recreate' }]);
  equal('DEPLOYMENT_FIXED_SELECTOR', deploy.spec.selector.matchLabels, selector);
  equal('POD_FIXED_LABELS', deploy.spec.template.metadata.labels, selector);
  equal('POLICY_CHECKSUM_ANNOTATIONS', deploy.spec.template.metadata.annotations, {
    'checksum/public-read-nginx': digest(Buffer.from(policy['nginx.conf'])),
    'checksum/public-read-proxy': digest(Buffer.from(policy['proxy.inc'])),
  });
  const pod = deploy.spec.template.spec;
  equal('POD_FIXED_SECURITY', pod.securityContext, {
    runAsNonRoot: true, runAsUser: 101, runAsGroup: 101, fsGroup: 101,
    fsGroupChangePolicy: 'OnRootMismatch', seccompProfile: { type: 'RuntimeDefault' },
  });
  check('NO_TOKEN_AND_EXISTING_SA_ONLY', pod.automountServiceAccountToken === false && pod.serviceAccountName === 'lab-platform-lab');
  check('NO_HOST_OR_PRIVILEGED_POD_FEATURES', ['hostNetwork', 'hostPID', 'hostIPC', 'initContainers', 'ephemeralContainers', 'imagePullSecrets'].every(key => !(key in pod)));
  equal('ONE_CONTAINER', pod.containers.length, 1);
  const container = pod.containers[0];
  equal('FIXED_NGINX_IMAGE_AND_COMMAND', [container.name, container.image, container.command, container.args],
    [component, expectedImage, ['nginx'], ['-c', '/etc/public-gateway/nginx.conf', '-g', 'daemon off;']]);
  equal('CONTAINER_FIXED_SECURITY', container.securityContext, {
    allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: ['ALL'] },
  });
  equal('FIXED_RESOURCE_BUDGET', container.resources, {
    requests: { cpu: '25m', memory: '32Mi', 'ephemeral-storage': '32Mi' },
    limits: { cpu: '250m', memory: '128Mi', 'ephemeral-storage': '64Mi' },
  });
  equal('ONLY_HTTP_CONTAINER_PORT_NO_HOSTPORT', container.ports, [{ name: 'http', containerPort: 8080 }]);
  check('NO_ENV_OR_SECRET_REFERENCE', !('env' in container) && !('envFrom' in container));
  for (const key of ['startupProbe', 'livenessProbe', 'readinessProbe']) {
    const probe = container[key];
    equal('PROBE_LISTENER_ONLY', probe.tcpSocket, { port: 'http' });
    check('NO_HTTP_OR_EXEC_PROBE', !('httpGet' in probe) && !('exec' in probe));
  }
  equal('ONLY_READONLY_POLICY_AND_MEMORY_TMP_VOLUMES', pod.volumes, [
    { name: 'policy', configMap: { name: cm.metadata.name, defaultMode: 292 } },
    { name: 'tmp', emptyDir: { medium: 'Memory', sizeLimit: '16Mi' } },
  ]);
  equal('ONLY_DECLARED_MOUNTS', container.volumeMounts, [
    { name: 'policy', mountPath: '/etc/public-gateway', readOnly: true }, { name: 'tmp', mountPath: '/tmp' },
  ]);
  equal('CLUSTERIP_SERVICE_ONLY', service.spec, {
    type: 'ClusterIP', selector, ports: [{ name: 'http', port: 8080, targetPort: 'http', protocol: 'TCP' }],
  });
  const peer = value => ({ ...selector, 'app.kubernetes.io/component': value });
  equal('FIXED_NETWORK_POLICY_CLIENT_API_AND_DNS_ONLY', network.spec, {
    podSelector: { matchLabels: selector }, policyTypes: ['Ingress', 'Egress'],
    ingress: [{ from: [{ podSelector: { matchLabels: peer('public-read-client') } }], ports: [{ protocol: 'TCP', port: 8080 }] }],
    egress: [
      { to: [{ podSelector: { matchLabels: peer('api') } }], ports: [{ protocol: 'TCP', port: 8080 }] },
      { to: [{ namespaceSelector: { matchLabels: { 'kubernetes.io/metadata.name': 'kube-system' } },
        podSelector: { matchLabels: { 'k8s-app': 'kube-dns' } } }], ports: [{ protocol: 'UDP', port: 53 }, { protocol: 'TCP', port: 53 }] },
    ],
  });
  const explicitEmptyProxy = render('EXPLICIT_EMPTY_TRUSTED_PROXY', [
    '--values', path.join(chart, 'ci/public-gateway-enabled-values.yaml'),
    '--set-string', 'publicReadGateway.trustedProxyCidr=',
  ]);
  equal('EMPTY_TRUSTED_PROXY_PRESERVES_ENABLED_BYTES', explicitEmptyProxy.bytes, enabled.bytes);
  const proxyExamples = ['10.23.45.67/32', '172.31.23.45/32', '192.168.23.45/32'];
  for (const [index, cidr] of proxyExamples.entries()) {
    const rendered = render(`TRUSTED_PROXY_PRIVATE_${index + 1}`, [
      '--values', path.join(chart, 'ci/public-gateway-enabled-values.yaml'),
      '--set-string', `publicReadGateway.trustedProxyCidr=${cidr}`,
    ]);
    const expected = structuredClone(enabled.docs);
    expected.find(document => document.kind === 'NetworkPolicy').spec.ingress.push({
      from: [{ ipBlock: { cidr } }], ports: [{ protocol: 'TCP', port: 8080 }],
    });
    equal('TRUSTED_PROXY_ADDS_ONLY_ONE_HOST_8080_INGRESS', rendered.docs, expected);
  }
  const disabledProxy = render('DISABLED_WITH_TRUSTED_PROXY', [
    '--set', 'publicReadGateway.enabled=false',
    '--set-string', 'publicReadGateway.trustedProxyCidr=10.23.45.67/32',
  ]);
  equal('TRUSTED_PROXY_DOES_NOT_ENABLE_GATEWAY', disabledProxy.bytes, baseline);
  for (const [name, value] of [
    ['WIDE_PREFIX', '10.23.45.67/24'], ['OUTSIDE_RFC1918', '203.0.113.42/32'],
    ['BELOW_PRIVATE_172', '172.15.23.45/32'], ['ABOVE_PRIVATE_172', '172.32.23.45/32'],
    ['LOOPBACK', '127.0.0.1/32'], ['IPV6', 'fd00::1/128'],
    ['INVALID_OCTET', '10.256.1.2/32'], ['LEADING_ZERO', '10.01.2.3/32'],
    ['TRAILING_NEWLINE', '10.23.45.67/32\n'], ['NULL', null],
    ['BOOLEAN', true], ['ARRAY', ['10.23.45.67/32']],
  ]) {
    const fixture = path.join(output, `TRUSTED_PROXY_${name}_REJECTED.json`);
    fs.writeFileSync(fixture, `${JSON.stringify({ publicReadGateway: { enabled: true, trustedProxyCidr: value } })}\n`);
    render(`TRUSTED_PROXY_${name}_REJECTED`, ['--values', fixture], 'platform-lab', 'lab', true);
  }
  const alternate = render('ALTERNATE_NAMESPACE_DISABLED', [], 'gateway-disabled-check');
  check('DISABLED_OTHER_NAMESPACE_CREATES_NO_GATEWAY', !alternate.docs.some(isGateway) && alternate.docs.length === 12);
  render('ENABLED_WRONG_NAMESPACE_REJECTED', ['--set', 'publicReadGateway.enabled=true'], 'gateway-disabled-check', 'lab', true);
  const longRelease = render('LONG_RELEASE_ENABLED', ['--set', 'publicReadGateway.enabled=true'], 'platform-lab', 'g'.repeat(53));
  const longGateway = longRelease.docs.filter(isGateway);
  check('LONG_RELEASE_GATEWAY_NAMES_BOUNDED_AND_IDENTICAL', longGateway.length === 4 &&
    longGateway.every(object => object.metadata.name.length <= 63 && /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/.test(object.metadata.name)) &&
    new Set(longGateway.map(object => object.metadata.name)).size === 1);
  for (const [name, value] of [
    ['STRING_ENABLED_REJECTED', { enabled: 'true' }],
    ['NULL_OBJECT_REJECTED', null],
    ['NULL_ENABLED_REJECTED', { enabled: null }],
    ['UPSTREAM_OVERRIDE_REJECTED', { enabled: true, upstream: 'example.invalid' }],
    ['IMAGE_OVERRIDE_REJECTED', { enabled: true, image: 'example.invalid/image' }],
    ['REPLICA_OVERRIDE_REJECTED', { enabled: true, replicas: 2 }],
    ['RESOURCE_OVERRIDE_REJECTED', { enabled: true, resources: {} }],
    ['NODEPORT_OVERRIDE_REJECTED', { enabled: true, service: { type: 'NodePort' } }],
  ]) {
    const fixture = path.join(output, `${name}.json`);
    fs.writeFileSync(fixture, `${JSON.stringify({ publicReadGateway: value })}\n`);
    render(name, ['--values', fixture], 'platform-lab', 'lab', true);
  }
  report.disabledObjectCount = disabled.docs.length;
  report.enabledObjectCount = enabled.docs.length;
  report.addedObjectKinds = added.map(document => document.kind).sort();
  report.baselineRenderSha256 = digest(disabled.bytes);
  report.enabledRenderSha256 = digest(enabled.bytes);
  report.policyManifestSha256 = policyManifestHash;
  report.appProjectNetworkPolicyPermission = 'DECLARED_IN_SOURCE_NOT_APPLIED_BY_THIS_CHECK';
  report.renderValueScope = 'PINNED_MAIN_K_FIXTURE_NOT_LIVE_ENVIRONMENT';
  report.phase = 'COMPLETE';
  report.passed = true;
}
try {
  main();
} catch (error) {
  report.passed = false;
  report.failureCode = error?.code === 'ERR_ASSERTION' ? 'ASSERTION_FAILED' : 'LOCAL_VALIDATION_FAILED';
  // No raw source paths, process stderr or exception text are published.
} finally {
  if (sourceBefore) {
    try {
      const sourceAfter = sourceSnapshot();
      fs.writeFileSync(path.join(output, 'source-after.json'), `${JSON.stringify(sourceAfter, null, 2)}\n`);
      report.sourceBytesUnchanged = JSON.stringify(sourceBefore) === JSON.stringify(sourceAfter);
    } catch { report.sourceBytesUnchanged = false; }
  }
  if (helmBefore) {
    try { report.helmExecutableUnchanged = digest(regularRead(args.get('--helm'), 80 * 1024 * 1024)) === helmBefore; }
    catch { report.helmExecutableUnchanged = false; }
  }
  if (!report.sourceBytesUnchanged || !report.helmExecutableUnchanged) {
    report.passed = false;
    report.phase = 'POSTCONDITIONS';
    report.failureCode = 'SOURCE_OR_EXECUTABLE_CHANGED';
  }
  fs.writeFileSync(path.join(output, 'render-validation.json'), `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(report)}\n`);
  if (!report.passed) process.exitCode = 1;
}
