"""Fresh malformed-message fixture owner. Definitions only; no import-time I/O.

The original two-role owner is immutable. Every mutation below first binds a
full resource ID to this run/source/nonce, image, creation and mount/network spec.
"""
from pathlib import Path
import datetime as dt
import json
import os
import re
import time

LABEL = 'platform-lab.invalid-message'
ROLES = {'kafka', 'db', 'garage', 'jvm'}
SHA = re.compile(r'[a-f0-9]{64}')
IMAGES = {
    'kafka': 'apache/kafka:4.3.1@sha256:ccd1314e47ec76909e01f86308b4dcf2064f19f7c89759234322314b0e319e26',
    'db': 'mariadb:11.8.9@sha256:6422478cb8e159f080fb1d8ccf65101e26fe51385787fde7d16c3b165a331f15',
    'garage': 'dxflrs/garage@sha256:0d7c74fc8ca6fef68a5a941c0e7558c8b1e92ba3588fa7505400e1350456c796',
    'jvm': 'eclipse-temurin:21-jdk@sha256:3e3c176ffed168beb42c607be9bc1639b466cf00261a0fb04425562c9d0c5c2b'}
MEMORY = {'kafka': 1073741824, 'db': 1073741824, 'garage': 536870912, 'jvm': 2147483648}
TMPFS = {
    'kafka': {'/var/lib/kafka/data': 'rw,size=256m,uid=1000,gid=1000,mode=0700',
              '/etc/kafka/secrets': 'rw,size=1m,uid=1000,gid=1000,mode=0700',
              '/mnt/shared/config': 'rw,size=4m,uid=1000,gid=1000,mode=0700'},
    'db': {'/var/lib/mysql': 'rw,size=512m,mode=0750'},
    'garage': {'/meta': 'rw,size=64m,uid=1000,gid=1000,mode=0700',
               '/data': 'rw,size=128m,uid=1000,gid=1000,mode=0700', '/tmp': 'rw,size=32m'},
    'jvm': {'/tmp': 'rw,size=256m,mode=1777'}}


def require(value):
    if not value:
        raise ValueError('OWNED_INVALID_MESSAGE_RESOURCE_UNVERIFIED')


def pairs(values):
    result = {}
    for key, value in values:
        require(key not in result)
        result[key] = value
    return result


def env_map(values):
    require(type(values) is list and len(values) <= 128)
    result = {}
    for row in values:
        require(type(row) is str and '=' in row and len(row) <= 16384)
        key, value = row.split('=', 1)
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) and key not in result)
        result[key] = value
    require(sum(len(row.encode()) for row in values) <= 65536)
    return result


def mount_check(value, profile):
    host, config = value['HostConfig'], value['Config']
    require(host.get('Tmpfs') == profile['tmpfs'])
    binds = profile['binds']
    requested = host.get('Mounts') or []
    require(type(requested) is list and len(requested) == len(binds))
    seen = set()
    for item in requested:
        target = item.get('Target')
        require(item.get('Type') == 'bind' and target in binds and target not in seen)
        source, writable = binds[target]
        require(item.get('Source') == source and item.get('ReadOnly', False) is (not writable))
        seen.add(target)
    require(seen == set(binds))
    actual = value.get('Mounts')
    require(type(actual) is list)
    seen, actual_binds = set(), set()
    for item in actual:
        target = item.get('Destination')
        require(type(target) is str and target not in seen)
        seen.add(target)
        if item.get('Type') == 'bind':
            require(target in binds)
            source, writable = binds[target]
            require(item.get('Source') == source and item.get('RW') is writable
                    and item.get('Propagation') == 'rprivate')
            actual_binds.add(target)
        else:
            require(item.get('Type') == 'tmpfs' and target in profile['tmpfs']
                    and item.get('Source') in (None, '', 'tmpfs') and item.get('RW') is True)
    require(actual_binds == set(binds))
    declared = config.get('Volumes')
    require(declared is None or type(declared) is dict
            and set(declared) <= set(profile['tmpfs']) | set(binds))


def container_check(value, row, state, labels):
    profile = row['profile']
    role = row['role']
    require(row['image'] == IMAGES[role] and profile['memory'] == MEMORY[role]
            and profile['tmpfs'] == TMPFS[role] and profile['readonly'] is (role in {'garage', 'jvm'}))
    if role in {'kafka', 'garage'}:
        require(profile['user'] == '1000:1000')
    if role == 'jvm':
        require(profile['user'] == state['runtimeUser'])
    host, config, status = value['HostConfig'], value['Config'], value['State']
    require(config['Image'] == row['image'] and value['Image'] == row['imageId']
            and config.get('User', '') == profile['user']
            and config.get('Entrypoint') == profile['entrypoint'] and config.get('Cmd') == profile['cmd']
            and env_map(config['Env']) == profile['env']
            and all(config.get('Labels', {}).get(key) == val for key, val in labels.items()))
    require(host['NetworkMode'] == row['networkMode'] and host.get('PortBindings') in (None, {})
            and host.get('Binds') in (None, []) and host.get('Privileged') is False
            and host.get('ReadonlyRootfs') is profile['readonly']
            and host.get('NanoCpus') == 1000000000 and host.get('Memory') == profile['memory']
            and host.get('MemorySwap') == profile['memory'] and host.get('PidsLimit') == 256
            and host.get('AutoRemove') is False and host.get('RestartPolicy') == {'Name': 'no', 'MaximumRetryCount': 0})
    require(host.get('CapAdd') in (None, [])
            and (host.get('CapDrop') in (None, []) if row['role'] == 'db' else host.get('CapDrop') == ['ALL'])
            and host.get('SecurityOpt') in (['no-new-privileges'], ['no-new-privileges:true']))
    require(all(host.get(key) in ('', None) for key in ('PidMode', 'UTSMode', 'UsernsMode'))
            and host.get('IpcMode') == 'private'
            and all(host.get(key) in (None, []) for key in ('Devices', 'DeviceRequests', 'VolumesFrom', 'Links')))
    if row['role'] == 'kafka':
        nets = [item for item in state['resources'] if item['kind'] == 'network']
        require(len(nets) == 1 and row['networkMode'] == nets[0]['id'])
        links = value['NetworkSettings']['Networks']
        require(type(links) is dict and len(links) in ({0, 1} if status['Status'] == 'created' else {1}))
        if links:
            require(next(iter(links.values()))['NetworkID'] in ('', nets[0]['id'])
                    if status['Status'] == 'created' else next(iter(links.values()))['NetworkID'] == nets[0]['id'])
    else:
        brokers = [item for item in state['resources'] if item.get('role') == 'kafka']
        require(len(brokers) == 1 and row['networkMode'] == 'container:' + brokers[0]['id'])
    mount_check(value, profile)


class OwnedDocker:
    def __init__(self, base, task, state, deadline):
        self.base, self.task, self.state, self.deadline = base, task, state, deadline
        self.cleaning = False
        require(type(state['schemaVersion']) is int and state['schemaVersion'] == 1
                and state['scope'] == 'ISOLATED_INVALID_MESSAGE_RUNTIME'
                and re.fullmatch(r'[0-9]{1,18}', state['runId'])
                and re.fullmatch(r'[a-f0-9]{40}', state['sourceCommit'])
                and re.fullmatch(r'[a-f0-9]{32}', state['nonce']))
        self.labels = {LABEL: state['nonce'], LABEL + '.source': state['sourceCommit'], LABEL + '.run': state['runId']}
        self.prefix = 'platform-invalid-message-' + state['runId'] + '-' + state['nonce']
        (task / 'docker-config').mkdir(mode=0o700, exist_ok=True)

    def save(self):
        self.base.save_state(self.task, self.state)

    def call(self, args, deadline=None):
        return self.base.command(['/usr/bin/docker', '--host=unix:///var/run/docker.sock', *args],
            min(self.deadline, deadline or self.deadline), limit=1048576,
            environment={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'DOCKER_CONFIG': str(self.task / 'docker-config')})

    def image(self, image, *, allow_pull=False):
        require(not self.state['resources'])
        require(image in IMAGES.values())
        if allow_pull:
            require(self.call(['pull', image])[0] == 0)
        status, raw, _ = self.call(['image', 'inspect', image])
        value = json.loads(raw, object_pairs_hook=pairs)
        require(status == 0 and type(value) is list and len(value) == 1)
        value = value[0]
        repo_digest = image.split('@')[0].rsplit(':', 1)[0] + '@' + image.split('@')[1]
        require(value['Os'] == 'linux' and value['Architecture'] == 'amd64'
                and repo_digest in value['RepoDigests'] and re.fullmatch(r'sha256:[a-f0-9]{64}', value['Id']))
        return {'id': value['Id'], 'env': env_map(value['Config']['Env']),
                'user': value['Config'].get('User', ''), 'cmd': value['Config'].get('Cmd'),
                'entrypoint': value['Config'].get('Entrypoint')}

    def inspect(self, row, *, initializing=False, allow_paused=False):
        require(type(row) is dict and row['kind'] in {'network', 'container'} and SHA.fullmatch(row['id'])
                and row['name'] == self.prefix + '-' + ('network' if row['kind'] == 'network' else row['role']))
        command = ['network', 'inspect'] if row['kind'] == 'network' else ['inspect']
        status, raw, _ = self.call([*command, row['id']])
        value = json.loads(raw, object_pairs_hook=pairs)
        require(status == 0 and type(value) is list and len(value) == 1)
        value = value[0]
        require(value['Id'] == row['id'] and value['Name'] == (row['name'] if row['kind'] == 'network' else '/' + row['name']))
        created = value['Created']
        require(type(created) is str and re.fullmatch(r'[0-9]{4}-[0-9T:.\-]+Z', created))
        if initializing:
            require('createdAt' not in row and dt.datetime.fromisoformat(row['intendedAt'].replace('Z', '+00:00'))
                    <= dt.datetime.fromisoformat(created.replace('Z', '+00:00')) <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1))
        else:
            require(created == row['createdAt'])
        if row['kind'] == 'network':
            require(value['Internal'] is True and value['Driver'] == 'bridge'
                    and all(value['Labels'].get(key) == val for key, val in self.labels.items()))
        else:
            require(row['role'] in ROLES)
            current = value['State']
            require(type(current['Running']) is bool and type(current['Paused']) is bool
                    and current['Status'] in {'created', 'running', 'paused', 'exited'}
                    and current['Running'] is (current['Status'] in {'running', 'paused'})
                    and current['Paused'] is (current['Status'] == 'paused')
                    and (not current['Paused'] or row['role'] == 'kafka' and allow_paused and self.cleaning))
            if 'startedAt' in row:
                require(current['StartedAt'] == row['startedAt'] and value['RestartCount'] == 0)
            container_check(value, row, self.state, self.labels)
        if initializing:
            row['createdAt'] = created
            self.save()
        return value

    def _create(self, kind, suffix, args, **fields):
        require(len(self.state['resources']) < 5 and suffix in ROLES | {'network'})
        name = self.prefix + '-' + suffix
        listing = ['network', 'ls', '--filter', 'name=^' + name + '$', '--format', '{{.ID}}'] if kind == 'network' else ['ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}']
        code, raw, _ = self.call(listing)
        require(code == 0 and raw.strip() == b'' and not any(item['name'] == name for item in self.state['resources']))
        row = {'kind': kind, 'name': name, 'id': None, 'phase': 'CREATE_INTENT',
               'intendedAt': dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z'), **fields}
        self.state['resources'].append(row)
        self.save()
        labels = [item for key, val in self.labels.items() for item in ('--label', key + '=' + val)]
        code, raw, _ = self.call([*args[0], *labels, *args[1]])
        require(code == 0 and SHA.fullmatch(raw.decode('ascii', 'replace').strip()))
        row.update(id=raw.decode('ascii').strip(), phase='CREATED')
        self.save()
        self.inspect(row, initializing=True)
        return row

    def network(self):
        name = self.prefix + '-network'
        return self._create('network', 'network', [['network', 'create', '--internal', '--driver', 'bridge'], [name]])

    def container(self, role, image, image_info, network_mode, profile, *, env_file=None):
        require(role in ROLES and image == IMAGES[role] and profile['memory'] == MEMORY[role]
                and profile['tmpfs'] == TMPFS[role] and profile['readonly'] is (role in {'garage', 'jvm'}))
        name = self.prefix + '-' + role
        options = ['create', '--name', name, '--network', network_mode, '--cpus', '1',
            '--memory', str(profile['memory']), '--memory-swap', str(profile['memory']), '--pids-limit', '256',
            '--security-opt', 'no-new-privileges', '--restart', 'no']
        if profile['user']:
            options += ['--user', profile['user']]
        if role != 'db':
            options += ['--cap-drop', 'ALL']
        if profile['readonly']:
            options += ['--read-only']
        for target, properties in profile['tmpfs'].items():
            options += ['--tmpfs', target + ':' + properties]
        for target, (source, writable) in profile['binds'].items():
            require(Path(source).resolve(strict=True).is_relative_to(self.task.resolve(strict=True)))
            options += ['--mount', 'type=bind,src=' + source + ',dst=' + target + ('' if writable else ',readonly')]
        if env_file is not None:
            require(env_file.parent == self.task)
            options += ['--env-file', str(env_file)]
        if profile['entrypoint'] != image_info['entrypoint']:
            require(type(profile['entrypoint']) is list and len(profile['entrypoint']) == 1)
            options += ['--entrypoint', profile['entrypoint'][0]]
        command = [] if profile['cmd'] == image_info['cmd'] else profile['cmd']
        return self._create('container', role, [options, [image, *(command or [])]], role=role,
            image=image, imageId=image_info['id'], networkMode=network_mode, profile=profile)

    def start(self, row):
        before = self.inspect(row)
        require(before['State']['Status'] == 'created')
        require(self.call(['start', row['id']])[0] == 0)
        value = self.inspect(row)
        require(value['State']['Running'] is True and value['State']['Paused'] is False
                and not value['State']['StartedAt'].startswith('0001-01-01'))
        row['startedAt'] = value['State']['StartedAt']
        self.save()

    def unpause(self, broker):
        require(self.cleaning)
        value = self.inspect(broker, allow_paused=True)
        require(broker['role'] == 'kafka')
        if value['State']['Paused']:
            require(self.call(['unpause', broker['id']])[0] == 0)
            require(self.inspect(broker)['State']['Status'] == 'running')

    def execute(self, row, args, deadline=None):
        require(self.inspect(row)['State']['Status'] == 'running')
        return self.call(['exec', row['id'], *args], deadline)

    def cleanup(self):
        self.cleaning = True
        resources = self.state.get('resources')
        if type(resources) is not list or len(resources) > 5:
            return False
        kafka = [row for row in resources if row.get('role') == 'kafka' and row.get('phase') != 'REMOVED']
        try:
            require(len(kafka) <= 1)
            if kafka:
                self.unpause(kafka[0])
        except Exception:
            return False
        clean = True
        for row in reversed(resources):
            try:
                if row['phase'] == 'REMOVED':
                    continue
                value = self.inspect(row)
                if row['kind'] == 'container' and value['State']['Running']:
                    require(self.call(['stop', '--time', '10', row['id']])[0] == 0)
                    require(self.inspect(row)['State']['Running'] is False)
                command = ['network', 'rm'] if row['kind'] == 'network' else ['rm']
                require(self.call([*command, row['id']])[0] == 0)
                listing = ['network', 'ls', '--no-trunc'] if row['kind'] == 'network' else ['ps', '-a', '--no-trunc']
                code, raw, _ = self.call([*listing, '--filter', 'id=' + row['id'], '--format', '{{.ID}}'])
                require(code == 0 and raw.strip() == b'')
                row['phase'] = 'REMOVED'
                self.save()
            except Exception:
                clean = False
        return clean
