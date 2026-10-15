import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import run_s3_ci as runner
import surefire_diagnostic as diagnostic


class SurefireProjection(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(os, 'O_NOFOLLOW', getattr(os, 'O_NOFOLLOW', 0), create=True)
        patcher.start(); self.addCleanup(patcher.stop)
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def write(self, suite, cases, *, errors=0, failures=0, skipped=0):
        root = ET.Element('testsuite', name=suite, tests=str(len(cases)), errors=str(errors), failures=str(failures), skipped=str(skipped))
        properties = ET.SubElement(root,'properties')
        ET.SubElement(properties,'property',name='user.timezone',value='Asia/Seoul')
        for name, kind, exception_type, body in cases:
            case = ET.SubElement(root,'testcase',name=name,classname=suite)
            if kind:
                child = ET.SubElement(case,kind,type=exception_type,message='private-message-never-output')
                child.text = body
        path = self.folder/('TEST-'+suite+'.xml');ET.ElementTree(root).write(path,encoding='utf-8')
        return path

    def success(self):
        for suite,methods in diagnostic.SUITES.items():
            self.write(suite,[(name,None,None,None)for name in methods])

    def test_complete_five_cases_have_actual_counts_without_diagnostic_success_grant(self):
        self.success(); value=diagnostic.collect(self.folder,0)
        self.assertEqual(value['aggregateCounts'],{'tests':5,'failures':0,'errors':0,'skipped':0})
        self.assertTrue(all(case['present'] and case['outcome']=='PASS' for suite in value['suites'] for case in suite['knownMethods'].values()))
        self.assertFalse(value['diagnosticGrantsSuccess'])
        self.assertNotIn('passed',value)
        self.assertEqual(runner.test_summary(self.folder)['tests'],5)

    def test_before_all_unknown_test_name_and_messages_never_publish(self):
        suite=next(iter(diagnostic.SUITES))
        self.write(suite,[('private-token-or-beforeall-name','error','private.credential.Class',
            'private-token https://private.example/bucket?credential=private-secret\n')],errors=1)
        value=diagnostic.collect(self.folder,1); row=value['suites'][0]
        self.assertEqual(row['counts'],{'tests':1,'failures':0,'errors':1,'skipped':0})
        self.assertEqual(row['unrecognisedCaseCount'],1)
        self.assertIsNone(row['problems'][0]['knownMethod'])
        self.assertTrue(row['problems'][0]['unknownMethod'])
        self.assertEqual(row['problems'][0]['exceptionCategories'],['UNRECOGNIZED_EXCEPTION'])
        self.assertIsNone(value['aggregateCounts'])
        encoded=json.dumps(value)
        for private in ('private-token','private.example','private-secret','credential.Class','private-message'):
            self.assertNotIn(private,encoded)

    def test_exact_s3_sdk_status_and_known_source_frames_only(self):
        suite=next(iter(diagnostic.SUITES));method=diagnostic.SUITES[suite][0]
        body=('java.lang.AssertionError: private-value\n'
              'Caused by: software.amazon.awssdk.services.s3.model.S3Exception: hidden-bucket '
              '(Service: S3, Status Code: 403, Request ID: private-request) (SDK Attempt Count: 1)\n'
              '\tat io.github.devdooly.platformlab.jobs.GarageRawSourceIT.method(GarageRawSourceIT.java:123)\n'
              '\tat io.github.devdooly.platformlab.jobs.S3RawSourceStore$Inner.read(S3RawSourceStore.java:88)\n'
              '\tat private.secret.Class.method(private.java:1)\n'
              '\tat io.github.devdooly.platformlab.jobs.S3RawSourceStore.read(private.java:9)\n'
              '\tat io.github.devdooly.platformlab.jobs.S3RawSourceStore.read(S3RawSourceStore.java:5001)\n')
        self.write(suite,[(method,'failure','java.lang.AssertionError',body)],failures=1)
        value=diagnostic.collect(self.folder,1);problem=value['suites'][0]['problems'][0]
        self.assertEqual(problem['exceptionCategories'],['ASSERTION_FAILURE','S3_SERVICE_EXCEPTION'])
        self.assertEqual(problem['s3HttpStatuses'],[403])
        self.assertEqual(problem['knownPublicSourceFrames'],[{'file':'GarageRawSourceIT.java','line':123},{'file':'S3RawSourceStore.java','line':88}])
        for secret in ('hidden-bucket','private-request','private-value','private.secret','private.java'):
            self.assertNotIn(secret,json.dumps(value))
        with self.assertRaises(RuntimeError):runner.test_summary(self.folder)

    def test_unrelated_status_text_is_not_an_s3_http_observation(self):
        for body in ('status=403', 'java.lang.IllegalStateException: (Service: S3, Status Code: 403, Request ID: x)',
                     'software.amazon.awssdk.services.s3.model.S3Exception: (Service: Other, Status Code: 403, Request ID: x)',
                     'software.amazon.awssdk.services.s3.model.S3Exception: (Service: S3, Status Code: 999, Request ID: x)'):
            node=ET.Element('error',type='java.lang.IllegalStateException');node.text=body
            self.assertEqual(diagnostic.problem_projection(node)['s3HttpStatuses'],[])

    def test_missing_and_partial_xml_remain_unobserved_not_zero(self):
        self.success();paths=diagnostic.report_paths(self.folder)
        paths[0].write_bytes(b'<testsuite')
        value=diagnostic.collect(self.folder,1)
        self.assertIsNone(value['aggregateCounts'])
        self.assertIsNone(value['suites'][0]['counts'])
        self.assertTrue(all(item['present'] is None for item in value['suites'][0]['knownMethods'].values()))
        paths[0].unlink();value=diagnostic.collect(self.folder,1)
        self.assertEqual(value['suites'][0]['collection'],'MISSING')
        self.assertIsNone(value['suites'][0]['counts'])

    def test_oversize_dtd_and_nofollow_failures_are_not_parsed_or_published(self):
        suite=next(iter(diagnostic.SUITES));methods=diagnostic.SUITES[suite]
        for raw in (b'x'*(4*1024**2+1),b'<!DOCTYPE x [<!ENTITY secret "credential">]><testsuite/>'):
            with self.assertRaises(ValueError):diagnostic.suite_projection(raw,suite,methods)
        with mock.patch.object(diagnostic.os,'open',side_effect=OSError('private-path')):
            value=diagnostic.collect(self.folder,1)
        self.assertIsNone(value['aggregateCounts'])
        self.assertNotIn('private-path',json.dumps(value))

    def test_utf16_xml_cannot_hide_dtd_entity_from_the_raw_token_guard(self):
        suite=next(iter(diagnostic.SUITES));methods=diagnostic.SUITES[suite]
        document='<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE testsuite [<!ENTITY x "secret-value">]><testsuite name="x">&x;</testsuite>'
        for encoding in ('utf-16','utf-16-le','utf-16-be'):
            with self.assertRaises((ValueError,UnicodeError)):
                diagnostic.suite_projection(document.encode(encoding),suite,methods)

    def test_counter_mismatch_unknown_suite_and_duplicate_known_cases_are_rejected(self):
        suite=next(iter(diagnostic.SUITES));method=diagnostic.SUITES[suite][0]
        for cases in ([(method,None,None,None)]*2,[(method,None,None,None)]):
            path=self.write(suite,cases)
            tree=ET.parse(path)
            if len(cases)==1:tree.getroot().set('tests','2');tree.write(path)
            value=diagnostic.collect(self.folder,1)
            self.assertIsNone(value['suites'][0]['counts'])
        path=self.write(suite,[(method,None,None,None)])
        tree=ET.parse(path);tree.getroot().set('name','private-unexpected-suite');tree.write(path)
        value=diagnostic.collect(self.folder,1)
        self.assertIsNone(value['suites'][0]['counts'])
        self.assertNotIn('private-unexpected-suite',json.dumps(value))

    def test_cause_categories_and_source_frames_are_bounded(self):
        body='Caused by: software.amazon.awssdk.core.exception.ApiCallTimeoutException: private\n'
        body+=''.join('\tat io.github.devdooly.platformlab.jobs.GarageRawSourceIT.method(GarageRawSourceIT.java:%s)\n'%n for n in range(1,30))
        node=ET.Element('error',type='java.lang.IllegalStateException');node.text=body
        value=diagnostic.problem_projection(node)
        self.assertIn('AWS_API_TIMEOUT',value['exceptionCategories'])
        self.assertEqual(len(value['knownPublicSourceFrames']),8)

    def test_invalid_exit_value_cannot_leak_through_public_projection(self):
        for value in ('private-password',True,999999):
            result=diagnostic.collect(self.folder,value)
            self.assertIsNone(result['mavenExitCode'])
            self.assertIsNone(result['aggregateCounts'])
            self.assertNotIn('private-password',json.dumps(result))


if __name__ == '__main__':
    unittest.main()
