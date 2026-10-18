"""Explicit local synthetic Java protocol check; never part of offline discovery.

Requires existing, whole-hash locked local inputs and a fresh C: work directory.
It does not download, contact Docker/Kafka/GitHub, or read capture artifacts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
JAVA_RELATIVE = 'src/org/apache/iceberg/ClosedCopyDecoder.java'
ORIGINAL_SHA = 'd7f9fbab4e1951e5364dcec7e78b8aa1b86531ba034a4c1748b47158a80399d9'
FIXTURE_SHA = '7fa95160b89e549b3f11079d9459223c0254260dbff08ee2cb6eaf7e6b017e98'
RUNTIME_SHA = 'd6ea6c5d099288daeb7d5a92061bd3d7d8f296492632b42378e5f2f0e3066242'
SLF4J_SHA = '44508fd1576500688c790b190acdd16fec4f8c79a3e0b900afd70503cf055f55'
JAVA_SHA = 'b92ee09627964a55dbe0c17980a53ce378b2759276b98547981bb6c1f51c6394'
JAVAC_SHA = '292f4241811d27bd8b86761566ce0bab0ab7270f39d3d26b946b636043fbbbac'
MAX_REPLY = 4 * 1024 * 1024
INVALID_FRAME = b'NOTFRAME'
MAPPER_NOISE = b'SYNTHETIC_MAPPER_STDOUT_CANARY'
DECODE_NOISE = b'SYNTHETIC_DECODE_STDOUT_CANARY'
OLD_MAPPER = '''  static final ObjectMapper JSON;
  static {
    JsonFactory factory = new JsonFactory();
    factory.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
    factory.setStreamReadConstraints(StreamReadConstraints.builder().maxNestingDepth(64)
        .maxStringLength(8192).maxNumberLength(128).build());
    JSON = new ObjectMapper(factory);
  }
'''
NEW_MAPPER = '''  private static final class JsonHolder {
    static final ObjectMapper JSON;
    static {
      JsonFactory factory = new JsonFactory();
      factory.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
      factory.setStreamReadConstraints(StreamReadConstraints.builder().maxNestingDepth(64)
          .maxStringLength(8192).maxNumberLength(128).build());
      JSON = new ObjectMapper(factory);
    }
  }
'''
MAIN = '  public static void main(String[] args) {\n'
MAIN_ROUTING = MAIN + '    final java.io.PrintStream protocolOut = System.out;\n    System.setOut(System.err);\n'
OLD_WRITE = "      System.out.write(raw); System.out.write('\\n'); System.out.flush();"
NEW_WRITE = "      protocolOut.write(raw); protocolOut.write('\\n'); protocolOut.flush();"


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def original_source(candidate):
    """Only invert the reviewed holder, seven references and main stream change."""
    text = candidate.decode('utf-8', 'strict')
    require(text.count(NEW_MAPPER) == 1 and text.count('JsonHolder.JSON.') == 7
            and text.count(MAIN_ROUTING) == 1 and text.count(NEW_WRITE) == 1
            and text.count('System.setOut(') == 1, 'EXACT_STDOUT_SOURCE_TRANSFORM_REQUIRED')
    original = text.replace(NEW_MAPPER, OLD_MAPPER).replace('JsonHolder.JSON.', 'JSON.')
    original = original.replace(MAIN_ROUTING, MAIN).replace(NEW_WRITE, OLD_WRITE).encode('utf-8')
    require(sha(original) == ORIGINAL_SHA, 'WHOLE_ORIGINAL_DECODER_SOURCE_REQUIRED')
    return original


def noisy_source(candidate):
    text = candidate.decode('utf-8', 'strict')
    sites = (
        ('    static {\n      JsonFactory factory',
         '    static {\n      System.out.println("SYNTHETIC_MAPPER_STDOUT_CANARY");\n      JsonFactory factory'),
        ('  static ObjectNode decode(InputStream input, long budgetMillis) {\n',
         '  static ObjectNode decode(InputStream input, long budgetMillis) {\n    System.out.println("SYNTHETIC_DECODE_STDOUT_CANARY");\n'),
    )
    for before, after in sites:
        require(text.count(before) == 1, 'EXACT_SYNTHETIC_NOISE_SITE_REQUIRED')
        text = text.replace(before, after)
    inverse = text
    for before, after in reversed(sites):
        require(inverse.count(after) == 1, 'EXACT_SYNTHETIC_NOISE_INVERSE_REQUIRED')
        inverse = inverse.replace(after, before)
    require(inverse.encode('utf-8') == candidate, 'SYNTHETIC_NOISE_COPY_SOURCE_BOUND_REQUIRED')
    return text.encode('utf-8')


def fixture_source(raw):
    """Adapt only mapper access in the pinned, already public synthetic writer."""
    require(sha(raw) == FIXTURE_SHA, 'EXACT_PUBLIC_SYNTHETIC_FIXTURE_REQUIRED')
    text = raw.decode('utf-8', 'strict')
    count = text.count('ClosedCopyDecoder.JSON')
    require(count > 0 and 'fixtureMapper()' not in text, 'EXACT_FIXTURE_MAPPER_SITES_REQUIRED')
    helper = '''  static org.apache.iceberg.shaded.com.fasterxml.jackson.databind.ObjectMapper fixtureMapper() {
    try {
      Class<?> owner;
      try { owner = Class.forName("org.apache.iceberg.ClosedCopyDecoder$JsonHolder"); }
      catch (ClassNotFoundException ignored) { owner = ClosedCopyDecoder.class; }
      java.lang.reflect.Field field = owner.getDeclaredField("JSON"); field.setAccessible(true);
      return (org.apache.iceberg.shaded.com.fasterxml.jackson.databind.ObjectMapper) field.get(null);
    } catch (ReflectiveOperationException problem) { throw new AssertionError("SYNTHETIC_MAPPER_ACCESS", problem); }
  }
'''
    site = '  static final PartitionSpec SPEC = PartitionSpec.unpartitioned();\n'
    require(text.count(site) == 1, 'EXACT_FIXTURE_ADAPTER_SITE_REQUIRED')
    adapted = text.replace('ClosedCopyDecoder.JSON', 'fixtureMapper()').replace(site, site + helper)
    inverse = adapted.replace(site + helper, site).replace('fixtureMapper()', 'ClosedCopyDecoder.JSON')
    require(inverse.encode('utf-8') == raw and adapted.count('fixtureMapper()') == count + 1,
            'WHOLE_PUBLIC_SYNTHETIC_FIXTURE_INVERSE_REQUIRED')
    return adapted.encode('utf-8')


LIBRARY_PROBE = b'''package org.apache.iceberg;
public final class DecoderLibraryStdoutProbe {
  public static void main(String[] args) throws Exception {
    java.io.PrintStream before = System.out;
    Class.forName("org.apache.iceberg.ClosedCopyDecoder");
    if (System.out != before) throw new AssertionError("CLASS_LOAD_STDOUT_IDENTITY");
    var result = ClosedCopyDecoder.decode(new java.io.ByteArrayInputStream("NOTFRAME".getBytes(java.nio.charset.StandardCharsets.US_ASCII)), 5000);
    if (System.out != before || !result.path("status").asText().equals("REJECTED")
        || !result.path("reasonCodes").get(0).asText().equals("FRAME_MAGIC"))
      throw new AssertionError("PURE_DECODE_STDOUT_IDENTITY");
    System.err.println("SYNTHETIC_LIBRARY_STDOUT_IDENTITY_PRESERVED");
  }
}
'''


def stable(path, maximum, expected=None):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not path.is_symlink()
            and 0 < before.st_size <= maximum, 'BOUNDED_REGULAR_LOCAL_INPUT_REQUIRED')
    with path.open('rb') as stream:
        first = os.fstat(stream.fileno()); raw = stream.read(maximum + 1); last = os.fstat(stream.fileno())
    after = path.lstat()
    shared = lambda value: (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode),
                             value.st_mode & ~0o111, value.st_size, value.st_mtime_ns)
    local = lambda value: (shared(value), value.st_mode, value.st_ctime_ns,
                           getattr(value, 'st_birthtime_ns', None),
                           getattr(value, 'st_file_attributes', None), getattr(value, 'st_reparse_tag', None))
    if os.name == 'nt':
        # All locked inputs were observed before selecting this Windows-only bridge.
        # Preserve full mode/ctime/attributes within each API and all other shared fields.
        modes_equal = before.st_mode == first.st_mode
        observed_exe_mode = (path.suffix.lower() == '.exe'
                             and (before.st_mode ^ first.st_mode) == 0o111
                             and (before.st_mode & 0o111) == 0o111 and (first.st_mode & 0o111) == 0)
        births = tuple(getattr(value, 'st_birthtime_ns', None) for value in (before, first, last, after))
        identity_stable = (shared(before) == shared(first) == shared(last) == shared(after)
                           and local(before) == local(after) and local(first) == local(last)
                           and (modes_equal or observed_exe_mode)
                           and all(type(value) is int for value in births) and len(set(births)) == 1)
    else:
        # Preserve full mode and the original cross-API ctime comparison outside Windows.
        identity = lambda value: (shared(value), value.st_mode, value.st_ctime_ns)
        identity_stable = identity(before) == identity(first) == identity(last) == identity(after)
    require(identity_stable and len(raw) == before.st_size and (expected is None or sha(raw) == expected),
            'LOCAL_INPUT_IDENTITY_OR_WHOLE_SHA_CHANGED')
    return raw


def save(path, raw):
    if type(raw) is not bytes:
        raw = (json.dumps(raw, sort_keys=True, indent=2) + '\n').encode('ascii')
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'SYNTHETIC_REPLY_DUPLICATE_KEY')
        result[key] = value
    return result


def reply(raw):
    require(0 < len(raw) <= MAX_REPLY and raw.endswith(b'\n') and not raw.endswith(b'\n\n'),
            'ONE_BOUNDED_SYNTHETIC_JSON_LINE_REQUIRED')
    text = raw.decode('utf-8', 'strict')
    require(not text.startswith('\ufeff'), 'SYNTHETIC_REPLY_BOM_REJECTED')
    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=lambda unused: require(False, 'SYNTHETIC_REPLY_FINITE_REQUIRED'))


def command(argv, cwd, input_bytes, timeout, stdout_max=MAX_REPLY):
    """Bound both pipe drains while running; no raw output is printed or persisted."""
    require(type(input_bytes) is bytes and len(input_bytes) <= 32 * 1024 * 1024
            and 0 < timeout <= 30, 'SYNTHETIC_CHILD_BOUND_REQUIRED')
    input_path = cwd / 'stdin.bin'; save(input_path, input_bytes)
    exceeded = threading.Event(); chunks = {'stdout': bytearray(), 'stderr': bytearray()}; failures = []
    def drain(stream, name, maximum):
        try:
            while True:
                block = stream.read(8192)
                if not block: return
                if len(chunks[name]) + len(block) > maximum:
                    exceeded.set(); return
                chunks[name].extend(block)
        except Exception:
            failures.append(name); exceeded.set()
    with input_path.open('rb') as incoming:
        child = subprocess.Popen(argv, cwd=cwd, stdin=incoming, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        workers = [threading.Thread(target=drain, args=(child.stdout, 'stdout', stdout_max), daemon=True),
                   threading.Thread(target=drain, args=(child.stderr, 'stderr', 65536), daemon=True)]
        for worker in workers: worker.start()
        cutoff = time.monotonic() + timeout
        try:
            while child.poll() is None and not exceeded.is_set() and time.monotonic() < cutoff:
                time.sleep(0.01)
            if child.poll() is None:
                child.kill(); child.wait(timeout=3)
                raise ValueError('SYNTHETIC_CHILD_OUTPUT_BOUND' if exceeded.is_set() else 'SYNTHETIC_CHILD_TIMEOUT')
            for worker in workers: worker.join(timeout=2)
            require(not any(worker.is_alive() for worker in workers) and not exceeded.is_set()
                    and not failures, 'SYNTHETIC_CHILD_DRAIN_BOUND_REQUIRED')
            return child.returncode, bytes(chunks['stdout']), bytes(chunks['stderr'])
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=3)
            for stream in (child.stdout, child.stderr): stream.close()
            for worker in workers: worker.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--runtime-jar', type=Path, required=True)
    parser.add_argument('--slf4j-jar', type=Path, required=True)
    parser.add_argument('--synthetic-fixture-source', type=Path, required=True)
    parser.add_argument('--work-root', type=Path, required=True, help='Fresh absolute C: directory under an existing parent')
    args = parser.parse_args()
    require(os.name == 'nt' and args.work_root.is_absolute() and args.work_root.drive.lower() == 'c:'
            and args.work_root.parent.is_dir() and not args.work_root.exists()
            and not args.work_root.parent.is_symlink(), 'FRESH_EXPLICIT_C_LOCAL_WORK_ROOT_REQUIRED')
    require(not any(name in os.environ for name in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'CLASSPATH')),
            'LOCAL_JAVA_OPTION_INJECTION_REJECTED')
    args.java_home = args.java_home.resolve()
    args.runtime_jar = args.runtime_jar.resolve()
    args.slf4j_jar = args.slf4j_jar.resolve()
    args.synthetic_fixture_source = args.synthetic_fixture_source.resolve()
    candidate_path = HERE / JAVA_RELATIVE
    candidate = stable(candidate_path, 131072); original = original_source(candidate)
    fixture = stable(args.synthetic_fixture_source, 131072, FIXTURE_SHA)
    runtime = stable(args.runtime_jar, 48000000, RUNTIME_SHA)
    logging = stable(args.slf4j_jar, 131072, SLF4J_SHA)
    java, javac = args.java_home / 'bin/java.exe', args.java_home / 'bin/javac.exe'
    stable(java, 1048576, JAVA_SHA); stable(javac, 1048576, JAVAC_SHA)
    work = args.work_root.resolve()
    require(work.drive.lower() == 'c:' and not work.exists(), 'RESOLVED_FRESH_C_WORK_ROOT_REQUIRED')
    work.mkdir(mode=0o700)
    pins = {'candidate': sha(candidate), 'original': ORIGINAL_SHA, 'fixture': FIXTURE_SHA,
            'runtime': RUNTIME_SHA, 'slf4j': SLF4J_SHA, 'java': JAVA_SHA, 'javac': JAVAC_SHA}
    save(work / 'intent.json', {'scope': 'SYNTHETIC_DECODER_STDOUT_PROTOCOL_ONLY', 'sourceSha256': pins,
        'actualArtifactRead': False, 'networkRequested': False, 'cloudClasspathParityClaimed': False,
        'automaticRetry': False})
    results = {}; passed = False; failure = None; ordinal = 0; staged_pins = []
    def stage_source(path, raw):
        save(path, raw); staged_pins.append((path, len(raw), sha(raw)))
    def run(name, argv, input_bytes=b'', timeout=10, stdout_max=MAX_REPLY):
        nonlocal ordinal
        ordinal += 1; folder = work / ('child-' + str(ordinal)); folder.mkdir(mode=0o700)
        code, out, err = command(argv, folder, input_bytes, timeout, stdout_max)
        results[name] = {'exitCode': code, 'stdoutBytes': len(out), 'stdoutSha256': sha(out),
                         'stderrBytes': len(err), 'stderrSha256': sha(err)}
        return code, out, err
    try:
        code, out, err = run('java-version', [str(java), '-version'], stdout_max=65536)
        require(code == 0 and b'version "21.0.9"' in err, 'LOCKED_LOCAL_JAVA21_REQUIRED')
        code, out, err = run('javac-version', [str(javac), '-version'], stdout_max=65536)
        require(code == 0 and out.strip() == b'javac 21.0.9' and not err, 'LOCKED_LOCAL_JAVAC21_REQUIRED')
        jars = work / 'jars'; jars.mkdir(mode=0o700)
        stage_source(jars / 'iceberg-runtime.jar', runtime); stage_source(jars / 'slf4j-api.jar', logging)
        classpath = os.pathsep.join((str(jars / 'iceberg-runtime.jar'), str(jars / 'slf4j-api.jar')))
        variants = {'original': original, 'candidate': candidate, 'noisy': noisy_source(candidate)}
        adapted_fixture = fixture_source(fixture); classes = {}
        for name, raw in variants.items():
            stage = work / name; stage.mkdir(mode=0o700)
            target = stage / 'ClosedCopyDecoder.java'; stage_source(target, raw)
            helper = stage / 'ClosedCopyDecoderFixture.java'; stage_source(helper, adapted_fixture)
            probe = stage / 'DecoderLibraryStdoutProbe.java'; stage_source(probe, LIBRARY_PROBE)
            empty = stage / 'empty-source'; empty.mkdir(mode=0o700)
            compiled = stage / 'classes'; compiled.mkdir(mode=0o700); classes[name] = compiled
            code, out, err = run('compile-' + name, [str(javac), '-J-Xmx256m', '-J-XX:ActiveProcessorCount=1',
                '--release', '21', '-proc:none', '-implicit:none', '-sourcepath', str(empty), '-cp', classpath,
                '-d', str(compiled), str(target), str(helper), str(probe)], timeout=30, stdout_max=65536)
            require(code == 0 and not out and len(err) <= 65536, 'CLEAN_SYNTHETIC_COMPILATION_REQUIRED')
            rows = sorted(path.relative_to(compiled).as_posix() for path in compiled.rglob('*.class'))
            require(0 < len(rows) <= 64 and all(re.fullmatch(
                r'org/apache/iceberg/(?:ClosedCopyDecoder(?:\$[A-Za-z0-9_]+)*|ClosedCopyDecoderFixture(?:\$[A-Za-z0-9_]+)*|DecoderLibraryStdoutProbe)\.class', row)
                for row in rows), 'ONLY_BOUNDED_SYNTHETIC_CLASSES_REQUIRED')
            if name != 'original': require('org/apache/iceberg/ClosedCopyDecoder$JsonHolder.class' in rows,
                                          'NEW_HOLDER_COMPILED_CLASS_REQUIRED')
            results['compile-' + name]['classCount'] = len(rows)
        def argv(name, main_class, extra=()):
            return [str(java), '-Xms16m', '-Xmx256m', '-XX:ActiveProcessorCount=1', '-cp',
                    os.pathsep.join((str(classes[name]), classpath)), main_class, *extra]
        code, frame, err = run('public-synthetic-writer-frame', argv('original', 'org.apache.iceberg.ClosedCopyDecoderFixture',
            ('--emit-synthetic-frame',)), timeout=30)
        require(code == 0 and frame.startswith(b'ICCPY001'), 'PUBLIC_WRITER_GENERATED_SYNTHETIC_FRAME_REQUIRED')
        replies = {}
        for name in variants:
            for suffix, data, expected_code, expected_status in (('invalid', INVALID_FRAME, 3, 'REJECTED'),
                                                               ('graph', frame, 0, 'DECODED')):
                code, out, err = run(name + '-' + suffix,
                    argv(name, 'org.apache.iceberg.ClosedCopyDecoder', ('--budget-millis', '5000')), data)
                decoded = reply(out)
                require(code == expected_code and decoded.get('status') == expected_status,
                        'EXACT_SYNTHETIC_CLI_STATUS_REQUIRED')
                if suffix == 'invalid': require(decoded.get('reasonCodes') == ['FRAME_MAGIC'], 'SYNTHETIC_INVALID_MAGIC_REQUIRED')
                if name == 'noisy':
                    require(err.count(MAPPER_NOISE) == 1 and err.count(DECODE_NOISE) == 1
                            and MAPPER_NOISE not in out and DECODE_NOISE not in out,
                            'SYNTHETIC_NOISE_MUST_ONLY_REACH_STDERR')
                replies[(name, suffix)] = out
        for suffix in ('invalid', 'graph'):
            require(replies[('original', suffix)] == replies[('candidate', suffix)] == replies[('noisy', suffix)],
                    'WHOLE_SYNTHETIC_REPLY_EQUIVALENCE_REQUIRED')
        code, out, err = run('candidate-library-stdout-identity', argv('candidate', 'org.apache.iceberg.DecoderLibraryStdoutProbe'))
        require(code == 0 and err.count(b'SYNTHETIC_LIBRARY_STDOUT_IDENTITY_PRESERVED') == 1,
                'PURE_LIBRARY_STDOUT_IDENTITY_REQUIRED')
        stable(candidate_path, 131072, pins['candidate']); stable(args.synthetic_fixture_source, 131072, FIXTURE_SHA)
        stable(args.runtime_jar, 48000000, RUNTIME_SHA); stable(args.slf4j_jar, 131072, SLF4J_SHA)
        stable(java, 1048576, JAVA_SHA); stable(javac, 1048576, JAVAC_SHA)
        for path, size, digest in staged_pins: stable(path, size, digest)
        passed = True
    except Exception as error:
        failure = str(error) if type(error) is ValueError and re.fullmatch('[A-Z0-9_]{1,96}', str(error)) else 'SYNTHETIC_STDOUT_PROTOCOL_CHECK_FAILED'
    save(work / 'result.json', {'scope': 'SYNTHETIC_DECODER_STDOUT_PROTOCOL_ONLY', 'passed': passed,
        'failureCode': failure, 'sourceSha256': pins, 'commands': results, 'actualArtifactRead': False,
        'cloudClasspathParityClaimed': False, 'osCpuMemoryLimitMeasured': False, 'networkRequested': False,
        'automaticRetry': False, 'libraryQuietOutputClaimed': False})
    print(json.dumps({'scope': 'SYNTHETIC_DECODER_STDOUT_PROTOCOL_ONLY', 'passed': passed, 'failureCode': failure}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
