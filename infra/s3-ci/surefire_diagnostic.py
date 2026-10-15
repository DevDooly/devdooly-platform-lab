"""Read-only bounded Surefire projection. Diagnostic data never grants test success."""
import os
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET

RAW_METHODS = (
    'realSdkPutGetHeadListDeleteAndStoreRetryVerifyActualBytes',
    'realCoordinatorStagesAndRepeatPreservesQueuedAndCompletedMetadata',
    'realExistingCorruptionIsRetainedAndDbRemainsStagingWithoutDispatch',
    'realObjectSurvivesFailedDbMarkAndIsReverifiedOnRetry',
)
EXPORT_METHOD = 'actualResultAndFailuresAreVerifiedBeforeReleaseAndRepeatsCannotReleaseNextJobsSlot'
SUITES = {
    'io.github.devdooly.platformlab.jobs.GarageRawSourceIT': RAW_METHODS,
    'io.github.devdooly.platformlab.jobs.exporting.VerifiedResultExportIT': (EXPORT_METHOD,),
}
FRAMES = {
    'io.github.devdooly.platformlab.jobs.GarageRawSourceIT': 'GarageRawSourceIT.java',
    'io.github.devdooly.platformlab.jobs.exporting.VerifiedResultExportIT': 'VerifiedResultExportIT.java',
    'io.github.devdooly.platformlab.jobs.S3ClientFactory': 'S3ClientFactory.java',
    'io.github.devdooly.platformlab.jobs.S3RawSourceStore': 'S3RawSourceStore.java',
    'io.github.devdooly.platformlab.jobs.SourceStagingService': 'SourceStagingService.java',
    'io.github.devdooly.platformlab.jobs.LabJobService': 'LabJobService.java',
    'io.github.devdooly.platformlab.jobs.CanonicalSource': 'CanonicalSource.java',
    'io.github.devdooly.platformlab.jobs.VerifiedSourceReader': 'VerifiedSourceReader.java',
    'io.github.devdooly.platformlab.jobs.exporting.S3ResultExportStore': 'S3ResultExportStore.java',
    'io.github.devdooly.platformlab.jobs.exporting.ResultExportService': 'ResultExportService.java',
    'io.github.devdooly.platformlab.jobs.exporting.ExportBundle': 'ExportBundle.java',
}
CATEGORIES = {
    'java.lang.AssertionError': 'ASSERTION_FAILURE',
    'org.opentest4j.AssertionFailedError': 'ASSERTION_FAILURE',
    'software.amazon.awssdk.services.s3.model.S3Exception': 'S3_SERVICE_EXCEPTION',
    'software.amazon.awssdk.services.s3.model.NoSuchKeyException': 'S3_SERVICE_EXCEPTION',
    'software.amazon.awssdk.services.s3.model.NoSuchBucketException': 'S3_SERVICE_EXCEPTION',
    'software.amazon.awssdk.core.exception.ApiCallTimeoutException': 'AWS_API_TIMEOUT',
    'software.amazon.awssdk.core.exception.ApiCallAttemptTimeoutException': 'AWS_API_TIMEOUT',
    'software.amazon.awssdk.core.exception.SdkClientException': 'AWS_CLIENT_EXCEPTION',
    'software.amazon.awssdk.core.exception.AbortedException': 'AWS_CLIENT_EXCEPTION',
    'java.sql.SQLException': 'SQL_EXCEPTION',
    'java.sql.SQLSyntaxErrorException': 'SQL_EXCEPTION',
    'java.sql.SQLIntegrityConstraintViolationException': 'SQL_EXCEPTION',
    'org.springframework.jdbc.BadSqlGrammarException': 'SQL_EXCEPTION',
    'org.springframework.dao.DataAccessResourceFailureException': 'SQL_EXCEPTION',
    'org.springframework.beans.factory.BeanCreationException': 'SPRING_BEAN_INITIALIZATION',
    'org.springframework.beans.factory.UnsatisfiedDependencyException': 'SPRING_BEAN_INITIALIZATION',
    'java.lang.IllegalStateException': 'ILLEGAL_STATE',
    'java.lang.IllegalArgumentException': 'ILLEGAL_ARGUMENT',
    'java.io.IOException': 'IO_EXCEPTION',
}
S3_CLASS = r'software\.amazon\.awssdk\.services\.s3\.model\.(?:S3Exception|NoSuchKeyException|NoSuchBucketException)'
S3_DIAGNOSTICS = re.compile(r'^(?:Caused by: )?' + S3_CLASS
    + r': [^\r\n]{0,8192}\(Service: S3, Status Code: ([1-5][0-9]{2}), Request ID: [^,\r\n)]{1,1024}'
      r'(?:, Extended Request ID: [^\r\n)]{1,1024})?\)(?: \(SDK Attempt Count: [1-9][0-9]?\))?$')
FRAME = re.compile(r'^\s*at (?:app//)?([A-Za-z_$][A-Za-z0-9_.$]{0,255})\.[A-Za-z_$<>][A-Za-z0-9_$<>]{0,127}'
                   r'\(([A-Za-z][A-Za-z0-9_]{0,100}\.java):([0-9]{1,4})\)\s*$')
CAUSE = re.compile(r'^(?:Caused by: |Suppressed: )?([A-Za-z_$][A-Za-z0-9_.$]{0,255}):')


def empty_diagnostics():
    return {'schemaVersion': 1, 'scope': 'BOUNDED_FRESH_EXPECTED_SUREFIRE_DIAGNOSTICS_ONLY',
            'freshReportsGatePassed': False, 'mavenExitCode': None,
            'collection': 'NOT_COLLECTED_COMMAND_NOT_COMPLETED', 'aggregateCounts': None,
            'suites': [], 'rawTextOrValuesPublished': False, 'diagnosticGrantsSuccess': False}


def report_paths(directory):
    return [Path(directory) / ('TEST-' + name + '.xml') for name in SUITES]


def problem_projection(node):
    text = ''.join(node.itertext())[:65536]
    categories = {CATEGORIES.get(node.get('type', ''), 'UNRECOGNIZED_EXCEPTION')}
    frames, statuses = [], set()
    for line in text.splitlines()[:1024]:
        cause = CAUSE.match(line.strip())
        if cause:
            categories.add(CATEGORIES.get(cause.group(1), 'UNRECOGNIZED_EXCEPTION'))
        matched = S3_DIAGNOSTICS.fullmatch(line.strip())
        if matched:
            statuses.add(int(matched.group(1)))
        frame = FRAME.fullmatch(line)
        if frame:
            class_name, file_name, line_number = frame.groups()
            expected = FRAMES.get(class_name.split('$', 1)[0])
            item = {'file': file_name, 'line': int(line_number)}
            if expected == file_name and 1 <= item['line'] <= 5000 and item not in frames and len(frames) < 8:
                frames.append(item)
    return {'kind': 'FAILURE' if node.tag == 'failure' else 'ERROR',
            'exceptionCategories': sorted(categories)[:8],
            's3HttpStatuses': sorted(statuses)[:4], 'knownPublicSourceFrames': frames,
            'messageOrStackTextPublished': False}


def suite_projection(raw, name, methods):
    if not 0 < len(raw) <= 4*1024**2 or b'\0' in raw or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
        raise ValueError('BOUNDED_XML_WITHOUT_DTD_REQUIRED')
    # Surefire emits UTF-8. Do not let ElementTree auto-detect UTF-16 and
    # process a DTD whose interleaved NUL bytes bypassed the ASCII token guard.
    raw.decode('utf-8')
    root = ET.fromstring(raw)
    if root.tag != 'testsuite' or root.get('name') != name:
        raise ValueError('EXACT_EXPECTED_SUITE_REQUIRED')
    declared = {}
    for field in ('tests', 'failures', 'errors', 'skipped'):
        value = root.get(field, '')
        if re.fullmatch(r'(?:0|[1-9][0-9]{0,3})', value) is None or int(value) > 1000:
            raise ValueError('BOUNDED_SUITE_COUNTER_REQUIRED')
        declared[field] = int(value)
    cases = root.findall('testcase')
    actual = {'tests': len(cases), 'failures': sum(len(case.findall('failure')) for case in cases),
              'errors': sum(len(case.findall('error')) for case in cases),
              'skipped': sum(len(case.findall('skipped')) for case in cases)}
    if declared != actual or len(cases) > 1000:
        raise ValueError('ACTUAL_NODES_MUST_MATCH_COUNTERS')
    known = {method: {'present': False, 'outcome': 'UNOBSERVED'} for method in methods}
    problems, unknown_count, omitted_problems = [], 0, 0
    for case in cases:
        method = case.get('name')
        recognised = method in known and case.get('classname') == name
        if recognised and known[method]['present']:
            raise ValueError('NO_DUPLICATE_KNOWN_CASES')
        nodes = case.findall('failure') + case.findall('error')
        if len(nodes) + len(case.findall('skipped')) > 1:
            raise ValueError('ONE_CASE_OUTCOME_REQUIRED')
        if recognised:
            known[method] = {'present': True, 'outcome': 'FAILURE' if case.find('failure') is not None
                            else 'ERROR' if case.find('error') is not None
                            else 'SKIPPED' if case.find('skipped') is not None else 'PASS'}
        else:
            unknown_count += 1
        for node in nodes:
            if len(problems) == 8:
                omitted_problems += 1
                continue
            problem = problem_projection(node)
            problem['knownMethod'] = method if recognised else None
            problem['unknownMethod'] = not recognised
            problems.append(problem)
    return {'suite': name, 'collection': 'OBSERVED_COMPLETE_XML', 'counts': actual,
            'knownMethods': known, 'unrecognisedCaseCount': unknown_count,
            'problems': problems, 'omittedProblemCount': omitted_problems}


def collect(directory, maven_exit_code):
    result = empty_diagnostics()
    if type(maven_exit_code) is not int or not -255 <= maven_exit_code <= 255:
        return result
    result.update(freshReportsGatePassed=True, mavenExitCode=maven_exit_code, collection='OBSERVED_EXPECTED_REPORTS')
    for name, methods in SUITES.items():
        record = {'suite': name, 'collection': 'UNOBSERVED', 'counts': None,
                  'knownMethods': {method: {'present': None, 'outcome': 'UNOBSERVED'} for method in methods},
                  'unrecognisedCaseCount': None, 'problems': [], 'omittedProblemCount': None}
        path = Path(directory) / ('TEST-' + name + '.xml')
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 4*1024**2:
                    raise ValueError('BOUNDED_REGULAR_REPORT_REQUIRED')
                raw = stream.read(4*1024**2+1)
                after = os.fstat(stream.fileno())
            if (len(raw) != before.st_size or (before.st_ino, before.st_mtime_ns, before.st_size)
                    != (after.st_ino, after.st_mtime_ns, after.st_size)):
                raise ValueError('COMPLETE_STABLE_REPORT_REQUIRED')
            record = suite_projection(raw, name, methods)
        except FileNotFoundError:
            record['collection'] = 'MISSING'
        except Exception:
            record['collection'] = 'UNOBSERVED_INVALID_OR_PARTIAL'
        result['suites'].append(record)
    if all(row['counts'] is not None for row in result['suites']):
        result['aggregateCounts'] = {key: sum(row['counts'][key] for row in result['suites'])
                                     for key in ('tests', 'failures', 'errors', 'skipped')}
    else:
        result['collection'] = 'PARTIAL_OR_UNOBSERVED_REPORTS'
    return result
