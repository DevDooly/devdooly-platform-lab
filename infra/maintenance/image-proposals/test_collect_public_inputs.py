"""New synthetic collector boundaries; no public HTTP is performed."""
import base64
from collections import Counter
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('public_capture_under_test', BASE / 'collect_public_inputs.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
PIN_DOCUMENT = json.loads((BASE / 'public-capture-pins.json').read_bytes())
MAIN = '1a9365fbad66fcc8e0cf5ab3cf957c1f70dc15fe'


def pull(number):
    return {'number': number, 'state': 'open', 'draft': True, 'merged': False, 'auto_merge': None,
            'head': {'sha': 'a' * 40, 'ref': 'automation/lab-images/' + 'b' * 40,
                     'repo': {'full_name': collector.REPOSITORY}},
            'base': {'ref': 'main', 'sha': MAIN, 'repo': {'full_name': collector.REPOSITORY}},
            'created_at': '2020-01-01T00:00:00Z', 'updated_at': '2020-01-01T00:00:00Z',
            'user': {'login': collector.BOT, 'type': 'Bot'}, 'body': 'public synthetic fixture',
            'labels': [], 'requested_reviewers': [], 'requested_teams': [], 'assignees': [],
            'comments': 0, 'review_comments': 0, 'commits': 1, 'changed_files': 1}


class FakeReader:
    def __init__(self, mode=None):
        self.calls = 0; self.bytes = 0; self.paths = Counter(); self.mode = mode

    def get(self, path):
        self.calls += 1; self.paths[path] += 1
        if path == collector.MAIN_PATH:
            sha = 'c' * 40 if self.mode == 'main_drift' and self.paths[path] == 2 else MAIN
            return {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': sha}}
        if path.startswith('contents/'):
            item = next(row for row in PIN_DOCUMENT['files'] if path == 'contents/' + row['path'] + '?ref=' + MAIN)
            raw = (BASE / 'examples/captured-declarations' / Path(item['path']).name).read_bytes()
            if self.mode == 'source_changed': raw += b'# unreviewed\n'
            return {'type': 'file', 'path': item['path'], 'encoding': 'base64', 'sha': item['gitBlobSha'],
                    'size': item['bytes'], 'content': base64.b64encode(raw).decode()}
        number = int(path.split('/')[1])
        if '/reviews?' in path:
            if number == 74 and self.mode == 'partial_reviews': raise collector.Unverified('PARTIAL_PAGE')
            if number == 74 and self.mode == 'reviewed': return [{'id': 1, 'state': 'APPROVED'}]
            return []
        value = pull(number)
        if number == 74:
            if self.mode == 'head_drift' and self.paths[path] == 2: value['head']['sha'] = 'd' * 40
            if self.mode == 'unknown': value.pop('draft')
            if self.mode == 'human': value['user'] = {'login': 'human', 'type': 'User'}
            if self.mode == 'comments': value['comments'] = 1
            if self.mode == 'label': value['labels'] = [{'name': 'keep'}]
        return copy.deepcopy(value)


class CaptureBoundaries(unittest.TestCase):
    def capture(self, mode=None):
        reader = FakeReader(mode)
        return collector.collect(reader, PIN_DOCUMENT), reader

    def test_selected_metadata_complete_still_keeps_all_without_provenance_or_rollback(self):
        report, reader = self.capture()
        self.assertEqual(reader.calls, 52)
        self.assertTrue(report['selectedMetadataComplete'])
        self.assertEqual(report['keepCount'], 16); self.assertEqual(report['supersededCandidateCount'], 0)
        self.assertFalse(report['protectedSourcesComplete']); self.assertFalse(report['rollbackSourcesVerified'])
        self.assertFalse(report['liveWorkloadSourceVerified']); self.assertFalse(report['applyEnabled'])
        self.assertTrue(all(item['qualificationProofComplete'] is False for item in report['entries']))
        self.assertTrue(all(item['proof'] is None for item in report['plannerInput']['proposals']))
        self.assertEqual(report['plannerInput']['protectedSources']['rollback'], [])
        self.assertTrue(all(collector.allowed_path(path) for path in reader.paths))

    def test_head_drift_does_not_adopt_one_side_or_emit_a_complete_planner_input(self):
        report, reader = self.capture('head_drift')
        first = report['entries'][0]
        self.assertEqual(first['reason'], 'HEAD_OR_METADATA_DRIFT')
        self.assertIsNone(first['headSha']); self.assertIsNone(first['observedDraft'])
        self.assertIsNone(report['plannerInput'])
        self.assertEqual(reader.paths['pulls/74'], 2)

    def test_partial_review_page_is_unknown_and_never_followed(self):
        report, reader = self.capture('partial_reviews')
        self.assertEqual(report['entries'][0]['reason'], 'PARTIAL_PAGE')
        self.assertIsNone(report['plannerInput'])
        self.assertFalse(any('page=2' in path for path in reader.paths))
        self.assertEqual(reader.paths['pulls/74/reviews?per_page=100&page=1'], 1)

    def test_review_comment_label_and_human_creator_are_protected_without_inspecting_bodies(self):
        for mode in ('reviewed', 'comments', 'label', 'human'):
            with self.subTest(mode=mode):
                report, unused = self.capture(mode)
                self.assertEqual(report['entries'][0]['retention'], 'KEEP')
                self.assertTrue(report['entries'][0]['humanActivityOrProtectionObserved'])
                self.assertFalse(report['filesCommitAuthorsPublicationOrAncestryFetched'])

    def test_changed_public_values_cannot_supply_current_or_rollback_source(self):
        report, reader = self.capture('source_changed')
        self.assertFalse(report['mainStableAndPublicValuesExact'])
        self.assertEqual(report['currentDeclaredSources'], [])
        self.assertIsNone(report['plannerInput'])
        self.assertFalse(any(path.startswith('pulls/') for path in reader.paths))

    def test_unknown_metadata_is_not_replaced_with_the_historical_draft_flag(self):
        report, unused = self.capture('unknown')
        self.assertIsNone(report['entries'][0]['observedDraft'])
        self.assertIsNone(report['plannerInput'])
        self.assertEqual(report['keepCount'], 16)

    def test_changed_main_invalidates_current_declarations_and_planner_input(self):
        report, unused = self.capture('main_drift')
        self.assertEqual(report['globalFailureCode'], 'MAIN_DRIFT')
        self.assertEqual(report['currentDeclaredSources'], [])
        self.assertIsNone(report['plannerInput'])
        self.assertEqual(report['supersededCandidateCount'], 0)

    def test_unlisted_path_and_exhausted_budget_are_rejected_before_any_transport_call(self):
        reader = collector.PublicReader.__new__(collector.PublicReader)
        reader.calls = 52; reader.bytes = 0; reader.paths = Counter()
        reader.deadline = time.monotonic() + 10; reader.rate_limited = False
        with self.assertRaises(collector.Unverified): reader.get('pulls/999')
        with self.assertRaises(collector.Unverified): reader.get('pulls/74')
        self.assertEqual(reader.calls, 52)

    def test_parent_process_start_failure_saves_finite_unknown_without_network(self):
        with tempfile.TemporaryDirectory(prefix='capture-spawn-failure-', dir=BASE) as directory:
            folder = Path(directory)
            self.assertTrue(folder.resolve().is_relative_to(BASE.resolve()))
            target = folder / 'capture.json'
            with patch.object(collector.subprocess, 'run', side_effect=PermissionError('synthetic spawn denied')) as spawn, \
                 patch.object(collector, 'PublicReader', side_effect=AssertionError('network forbidden')) as network, \
                 patch.object(collector.sys, 'argv', ['collect_public_inputs.py', '--output', str(target)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                result = collector.main()
            self.assertEqual(result, 1)
            spawn.assert_called_once()
            network.assert_not_called()
            report = json.loads(target.read_bytes())
            self.assertEqual(report['failureCode'], 'OUTER_UNVERIFIED')
            self.assertEqual(report['keepCount'], 16)
            self.assertEqual(report['supersededCandidateCount'], 0)
            self.assertIsNone(report['plannerInput'])
            self.assertFalse(report['applyEnabled'])
            self.assertTrue(all(item['retention'] == 'KEEP' for item in report['entries']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
