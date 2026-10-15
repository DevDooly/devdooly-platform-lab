"""Synthetic Docker/cgroup records verify only the bounded role PID budget change."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import compose_plan as plan
import run_ci as runner
from test_oom_diagnostic import sample


def inventory():
    result = {}
    for role, letter in (('postgres', 'a'), ('garage', 'b'), ('spark', 'c')):
        spark = role == 'spark'
        result[letter * 64] = {'Id': letter * 64,
            'Config': {'Labels': {'com.docker.compose.project': 'synthetic-project', 'com.docker.compose.service': role}},
            'HostConfig': {'Privileged': False, 'PortBindings': None, 'NanoCpus': 1000000000 if spark else 500000000,
                'Memory': 3 * 1024**3 if spark else 512 * 1024**2, 'PidsLimit': 512 if spark else 256},
            'NetworkSettings': {'Networks': {'synthetic-project_trial': {}}},
            'State': {'Running': True, 'ExitCode': 0, 'OOMKilled': False}}
    return result


def inspect_inventory(values):
    attempt = runner.Attempt(Path('/synthetic'), 'synthetic-project')
    def command(argv, **kwargs):
        if argv[1] == 'ps':
            return SimpleNamespace(stdout=('\n'.join(values) + '\n').encode())
        if argv[1] == 'inspect':
            return SimpleNamespace(stdout=json.dumps([values[argv[2]]]).encode())
        raise AssertionError('ONLY_MOCKED_READ_ONLY_DOCKER_REQUESTS')
    attempt.command = command
    return attempt.containers()


class PidBudget(unittest.TestCase):
    def test_only_spark_pid_budget_changes_in_complete_compose_plan(self):
        value = plan.plan('spark-isolated-ci:' + 'a' * 32)
        self.assertEqual({'postgres': 256, 'garage': 256, 'spark': 512},
            {role: service['pids_limit'] for role, service in value['services'].items()})
        original = copy.deepcopy(value)
        original['services']['spark']['pids_limit'] = 256
        # Golden hash was taken from the immutable complete previous plan. It
        # guards every non-PID field, including heap, CPU, memory, ports and caps.
        raw = json.dumps(original, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual('e91cedfdd5a88143707aef5c754bddf5360d5bee39914e12b28a94e31b752472', hashlib.sha256(raw).hexdigest())

    def test_actual_role_limit_rejects_old_spark_or_broadened_database_and_garage(self):
        values = inventory()
        self.assertEqual({'postgres', 'garage', 'spark'}, {v['role'] for v in inspect_inventory(values)})
        for letter, wrong in (('c', 256), ('c', 0), ('c', -1), ('c', 513), ('c', True), ('c', '512'),
                              ('a', 512), ('a', 255), ('b', 512), ('b', -1)):
            changed = copy.deepcopy(values)
            changed[letter * 64]['HostConfig']['PidsLimit'] = wrong
            with self.subTest(role=letter, limit=wrong), self.assertRaisesRegex(RuntimeError, 'ACTUAL_ROLE_PID_LIMITS'):
                inspect_inventory(changed)
        changed = copy.deepcopy(values)
        del changed['c' * 64]['HostConfig']['PidsLimit']
        with self.assertRaisesRegex(RuntimeError, 'ACTUAL_ROLE_PID_LIMITS'):
            inspect_inventory(changed)

    def test_observed_pid_max_match_does_not_use_current_count_or_lifetime_events(self):
        raw = sample().replace(b'BEGIN pids.current\n23', b'BEGIN pids.current\n65').replace(b'max 7\n', b'max 16\n')
        current = runner.parse_cgroup_sample(raw)
        previous_limit = runner.parse_cgroup_sample(raw.replace(b'BEGIN pids.max\n512', b'BEGIN pids.max\n256'))
        self.assertTrue(current['pidsLimitMatchesPlan'])
        self.assertFalse(previous_limit['pidsLimitMatchesPlan'])
        for value in (current, previous_limit):
            self.assertEqual(65, value['pidsCurrent'])
            self.assertEqual(16, value['pidsEventsMax'])
            self.assertTrue(value['memoryLimitMatchesPlan'])
        self.assertFalse(runner.empty_cgroup_diagnostic()['baselineOrDeltaMeasured'])


if __name__ == '__main__':
    unittest.main()
