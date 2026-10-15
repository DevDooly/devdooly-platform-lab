"""Pure API target binding and one-peer policy plan. No kube/curl requests."""
import argparse
import copy
import ipaddress
import json
from pathlib import Path
import re
import render_plan as render


def require(value, code):
    if not value: raise ValueError(code)


def selector(value):
    require(isinstance(value, dict) and 0 < len(value) <= 16
        and all(isinstance(k, str) and isinstance(v, str) and 0 < len(k) <= 253
                and re.fullmatch(r'[A-Za-z0-9./_-]+', k) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}', v)
                for k, v in value.items()), 'ACTUAL_NONEMPTY_API_SERVICE_SELECTOR_REQUIRED')
    return copy.deepcopy(value)


def target_binding(namespace, service, pod, endpoints, policies):
    require(namespace['metadata']['name'] == service['metadata']['namespace'] == pod['metadata']['namespace'] == 'platform-lab'
            and namespace['metadata']['labels']['kubernetes.io/metadata.name'] == 'platform-lab'
            and service['metadata']['name'] == endpoints['metadata']['name'] == 'api'
            and endpoints['metadata']['namespace'] == 'platform-lab', 'ONLY_EXISTING_API_NAMESPACE_SERVICE')
    spec = service['spec']; selected = selector(spec['selector'])
    address = ipaddress.ip_address(spec['clusterIP'])
    require(spec['type'] == 'ClusterIP' and address.is_private and not address.is_loopback and not spec.get('externalIPs')
            and all(pod['metadata'].get('labels', {}).get(k) == v for k, v in selected.items()), 'ACTUAL_PRIVATE_SERVICE_TO_SELECTED_API_POD')
    ports = [v for v in spec['ports'] if v['port'] == 8080 and v.get('protocol', 'TCP') == 'TCP']
    require(len(ports) == 1, 'ONE_API_SERVICE_PORT_8080')
    target = ports[0]['targetPort']
    if isinstance(target, str):
        targets = [v for c in pod['spec']['containers'] for v in c.get('ports', []) if v.get('name') == target and v.get('protocol', 'TCP') == 'TCP']
        require(len(targets) == 1 and targets[0]['containerPort'] == 8080, 'ACTUAL_NAMED_API_TARGET_PORT')
    else: require(type(target) is int and target == 8080, 'ACTUAL_NUMERIC_API_TARGET_PORT')
    status = pod['status']; containers = status.get('containerStatuses', [])
    require(status['phase'] == 'Running' and not pod['metadata'].get('deletionTimestamp') and len(containers) == 1
            and containers[0]['ready'] is True and 'running' in containers[0]['state']
            and re.fullmatch(r'containerd://[a-f0-9]{64}', containers[0]['containerID']), 'ACTUAL_READY_API_CONTAINER')
    subsets = endpoints.get('subsets', [])
    require(len(subsets) == 1 and not subsets[0].get('notReadyAddresses') and len(subsets[0].get('addresses', [])) == 1,
            'ONE_READY_API_ENDPOINT')
    endpoint = subsets[0]['addresses'][0]; ref = endpoint.get('targetRef', {})
    require(endpoint['ip'] == status['podIP'] and ref.get('kind') == 'Pod' and ref.get('uid') == pod['metadata']['uid']
            and ref.get('name') == pod['metadata']['name'] and ref.get('namespace') == 'platform-lab'
            and any(v['port'] == 8080 and v.get('protocol', 'TCP') == 'TCP' for v in subsets[0]['ports']), 'ACTUAL_ENDPOINT_POD_UID_AND_PORT_BINDING')
    require(isinstance(policies, list) and len(policies) <= 128
            and not any('Ingress' in v['spec'].get('policyTypes', ['Ingress']) for v in policies),
            'ORIGINAL_API_INGRESS_MUST_ALREADY_BE_UNISOLATED')
    for obj in (namespace, service, pod, endpoints):
        require(isinstance(obj['metadata']['uid'], str) and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', obj['metadata']['uid']), 'ACTUAL_KUBERNETES_UID_REQUIRED')
    return {'namespaceUid': namespace['metadata']['uid'], 'serviceUid': service['metadata']['uid'],
            'podUid': pod['metadata']['uid'], 'containerId': containers[0]['containerID'],
            'endpointUid': endpoints['metadata']['uid'], 'address': str(address), 'selector': selected}


def build(observed_service_selector):
    selected = selector(observed_service_selector)
    peer = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'platform-lab'}},
            'podSelector': {'matchLabels': selected}}
    policy = render.resource('NetworkPolicy', 'temporary-api-positive-control-plan2',
        {'podSelector': render.selector('trino'), 'policyTypes': ['Egress'],
         'egress': [{'to': [peer], 'ports': [{'protocol': 'TCP', 'port': 8080}]}]}, api='networking.k8s.io/v1')
    return {'schemaVersion': 1, 'status': 'PREPARED_NOT_RUN', 'policy': policy,
        'target': {'namespace': 'platform-lab', 'service': 'api', 'port': 8080, 'path': '/api/jobs/observation', 'method': 'GET'},
        'requiredSequence': ['DENY_SAME_TARGET', 'ALLOW_SAME_TARGET_200', 'REMOVE_ONLY_OWN_TEMPORARY_POLICY', 'DENY_SAME_TARGET_AGAIN'],
        'requiredPrivateBindingFields': ['namespaceUid', 'serviceUid', 'podUid', 'containerId', 'endpointUid', 'address', 'selector'],
        'curlConnectSeconds': 2, 'curlTotalSeconds': 3, 'originalNamespaceMutationPlanned': False,
        'liveTargetBindingVerified': False, 'networkRequestsPerformed': 0, 'driverImplemented': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-selector-json', required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); require(len(args.api_selector_json) <= 4096, 'BOUNDED_SELECTOR_JSON')
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(build(json.loads(args.api_selector_json)), stream, indent=2); stream.write('\n')


if __name__ == '__main__': main()
