"""Synthetic RAM tar/zip/class bytes; POSIX tests are honestly OS-gated."""
import hashlib
import io
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import archive_classes as a


def jar(name='example/Valid.class',manifest=None):
    result = io.BytesIO()
    with zipfile.ZipFile(result,'w') as archive:
        archive.writestr(name,b'SYNTHETIC')
        if manifest is not None:archive.writestr('META-INF/MANIFEST.MF',manifest)
    return result.getvalue()


def member(name,raw=b'',kind=tarfile.REGTYPE,size=None):
    info = tarfile.TarInfo(name); info.type = kind; info.size = len(raw) if size is None else size
    return info.tobuf(format=tarfile.USTAR_FORMAT)+raw+bytes((-len(raw))%512)


def tar(*members): return b''.join(members)+bytes(1024)


def pax(key,value):
    body = key+b'='+value+b'\n'; length = len(body)+2
    while True:
        raw = str(length).encode()+b' '+body
        if len(raw) == length: return raw
        length = len(raw)


def consume(raw):
    directories,files = [],{}
    def read(name,size,source): files[name] = a._read_exact(source,size)
    a._consume_tar(io.BytesIO(raw),directories.append,read)
    return directories,files


def class_bytes(major=65): return b'\xca\xfe\xba\xbe\0\0'+major.to_bytes(2,'big')+b'SYNTHETIC_CLASS_BODY'


class PureArchiveContracts(unittest.TestCase):
    def test_manual_tar_whole_bytes_and_only_ignored_pax_time_metadata(self):
        payload = jar(); metadata = pax(b'mtime',b'1760000000.123456789')+pax(b'ctime',b'1760000000')
        raw = tar(member('PaxHeaders/jars',metadata,tarfile.XHDTYPE),member('jars/',kind=tarfile.DIRTYPE),
            member('jars/example.jar',payload))
        directories,files = consume(raw)
        self.assertEqual(['jars'],directories); self.assertEqual({'jars/example.jar':payload},files)
        a.scan_jar(io.BytesIO(files['jars/example.jar']))
        self.assertEqual(hashlib.sha256(payload).hexdigest(),hashlib.sha256(files['jars/example.jar']).hexdigest())

    def test_pax_override_duplicate_malformed_and_special_members_never_extract(self):
        good = member('jars/',kind=tarfile.DIRTYPE); marker=b'SYNTHETIC_SECRET_NEVER_RETURN'
        for key,value in ((b'path',b'../../secret'),(b'linkpath',marker),(b'size',b'999'),(b'unknown',marker)):
            with self.assertRaises(ValueError) as caught: consume(tar(member('PaxHeaders/jars',pax(key,value),tarfile.XHDTYPE),good))
            self.assertNotIn(marker.decode(),str(caught.exception))
        for payload in (pax(b'mtime',b'1')+pax(b'mtime',b'2'),b'999 mtime=1\n',pax(b'mtime',b'NaN')):
            with self.assertRaises(ValueError): consume(tar(member('PaxHeaders/jars',payload,tarfile.XHDTYPE),good))
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE,tarfile.BLKTYPE,tarfile.FIFOTYPE,tarfile.GNUTYPE_LONGNAME):
            with self.assertRaises(ValueError): consume(tar(good,member('jars/example.jar',kind=kind)))
        with self.assertRaises(ValueError): consume(tar(member('PaxHeaders/jars',kind=tarfile.XHDTYPE,size=4097),good))

    def test_exact_root_path_duplicate_ascii_checksum_padding_and_eof_guards(self):
        root=member('jars/',kind=tarfile.DIRTYPE); data=member('jars/a.jar',jar())
        for name in ('/jars/a.jar','jars/../a.jar','other/a.jar','jars//a.jar','jars/a.txt'):
            with self.assertRaises(ValueError): consume(tar(root,member(name,jar())))
        for raw in (tar(root,data,data),tar(root,root,data),tar(root,data)+b'TRAILING',tar(root,data)[:-600],
                tar(root,member('jars/no-parent/a.jar',jar()))):
            with self.assertRaises(ValueError): consume(raw)
        changed=bytearray(tar(root,data));changed[0]^=1
        with self.assertRaises(ValueError):consume(bytes(changed))
        bad=tarfile.TarInfo('jars/a.jar').tobuf(format=tarfile.USTAR_FORMAT);bad=bytearray(bad)
        bad[5]=0xff;bad[148:156]=b' '*8;checksum=sum(bad);bad[148:156]=('%06o\0 '%checksum).encode()
        with self.assertRaises(ValueError): consume(tar(root,bytes(bad)))

    def test_declared_size_count_and_whole_total_bounds_precede_file_callback(self):
        root=member('jars/',kind=tarfile.DIRTYPE)
        with self.assertRaises(ValueError): consume(tar(root,member('jars/huge.jar',size=a.MAX_JAR+1)))
        payload=jar()
        with patch.object(a,'MAX_TOTAL',len(payload)+1):
            with self.assertRaises(ValueError): consume(tar(root,member('jars/a.jar',payload),member('jars/b.jar',payload)))
        with patch.object(a,'MAX_JARS',1):
            with self.assertRaises(ValueError): consume(tar(root,member('jars/a.jar',payload),member('jars/b.jar',payload)))

    def test_all_jar_entries_scanned_for_main_nested_multirelease_and_traversal(self):
        a.scan_jar(io.BytesIO(jar('org/example/Valid.class')))
        a.scan_jar(io.BytesIO(jar(manifest=b'Manifest-Version: 1.0\r\nOther-Attribute: legitimate\r\n continued\r\nClass-Path: \r\n\r\n')))
        for name in ('org/apache/iceberg/ClosedCopyDecoder.class','org/apache/iceberg/ClosedCopyDecoder$Nested.class',
                'META-INF/versions/21/org/apache/iceberg/ClosedCopyDecoder.class','../outside.class','/absolute.class'):
            with self.assertRaises(ValueError): a.scan_jar(io.BytesIO(jar(name)))
        with patch.object(a,'MAX_ZIP_ENTRIES',0):
            with self.assertRaises(ValueError): a.scan_jar(io.BytesIO(jar()))
        with self.assertRaises(ValueError):a.scan_jar(io.BytesIO(b'not-a-jar'))
        for manifest in (b'Manifest-Version: 1.0\nClass-Path: ../unscanned.jar\n',
                b'Class-Path: file:/outside.jar\n',b'cLaSs-PaTh: ../unscan\n ned.jar\n',
                b'Class-Path: \n ../unscanned.jar\n',b'Other: value\nother: duplicate\n',
                b' continuation-without-attribute\n',b'Manifest-Version: 1.0\n'+bytes(65537)):
            with self.assertRaises(ValueError):a.scan_jar(io.BytesIO(jar(manifest=manifest)))

    def test_only_exact_java21_class_headers(self):
        a.class_header(class_bytes())
        for raw in (b'',b'not-class',class_bytes(64),class_bytes(66),'SYNTHETIC_SECRET',class_bytes()+bytes(1024**2)):
            with self.assertRaises(ValueError): a.class_header(raw)


@unittest.skipUnless(os.name=='posix','Actual Linux openat/ownership/mode/readback are unavailable on Windows')
class PosixArtifactContracts(unittest.TestCase):
    def test_actual_new_jar_write_readback_modes_and_shadow_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);base.chmod(0o700);archive=base/'export.tar';output=base/'new';output.mkdir();output.chmod(0o700)
            payload=jar();archive.write_bytes(tar(member('jars/',kind=tarfile.DIRTYPE),member('jars/a.jar',payload)))
            rows=a.unpack_jars(archive,output)
            self.assertEqual([{'name':'a.jar','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}],rows)
            self.assertEqual(0o444,stat.S_IMODE((output/'jars/a.jar').stat().st_mode))
            with self.assertRaises(ValueError):a.unpack_jars(archive,output)
            original=archive.read_bytes();foreign=base/'foreign';foreign.mkdir();foreign.chmod(0o700)
            shadow=base/'shadow.tar';shadow.write_bytes(tar(member('jars/',kind=tarfile.DIRTYPE),member('jars/shadow.jar',jar('org/apache/iceberg/ClosedCopyDecoder.class'))))
            with self.assertRaises(ValueError):a.unpack_jars(shadow,foreign)
            self.assertEqual(original,archive.read_bytes())

    def test_only_new_class_tree_sealed_and_extra_link_wrong_header_rejected_before_chmod(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);base.chmod(0o700);classes=base/'classes';package=classes/'org/apache/iceberg';package.mkdir(parents=True)
            main=package/'ClosedCopyDecoder.class';main.write_bytes(class_bytes());main.chmod(0o644)
            original=base/'original.jar';original.write_bytes(b'ORIGINAL');original.chmod(0o600)
            rows=a.seal_new_classes(classes);self.assertEqual(rows,a.compiled_classes(classes))
            self.assertEqual(0o444,stat.S_IMODE(main.stat().st_mode));self.assertEqual(0o555,stat.S_IMODE(classes.stat().st_mode))
            self.assertEqual(0o600,stat.S_IMODE(original.stat().st_mode));self.assertEqual(b'ORIGINAL',original.read_bytes())
            for path in (classes,classes/'org',classes/'org/apache',package):path.chmod(0o755)
            main.chmod(0o644);extra=package/'Foreign.class';extra.write_bytes(class_bytes())
            with self.assertRaises(ValueError):a.seal_new_classes(classes)
            self.assertEqual(0o644,stat.S_IMODE(main.stat().st_mode));extra.unlink()
            link=package/'ClosedCopyDecoder$Linked.class';os.link(main,link)
            with self.assertRaises(ValueError):a.seal_new_classes(classes)
            link.unlink();main.write_bytes(class_bytes(64))
            with self.assertRaises(ValueError):a.seal_new_classes(classes)


def closed_graph(payloads):
    rows=[{'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        for name,raw in payloads.items()]
    references={name:a._scan_jar(io.BytesIO(raw),a._manifest_closed_references)
        for name,raw in payloads.items()}
    return a._closed_classpath_map(rows,references)


class ClosedClasspathContracts(unittest.TestCase):
    def test_forward_nested_folded_duplicate_and_cycle_references_are_closed_without_rewriting(self):
        payloads={'a.jar':jar(manifest=b'Manifest-Version: 1.0\nClass-Path: b.jar b.jar \n lib/c.jar\n\n'),
            'b.jar':jar(manifest=b'Class-Path: a.jar\n'),
            'lib/c.jar':jar(manifest=b'Class-Path: d.jar\n'),
            'lib/d.jar':jar(),'orphan.jar':jar()}
        original=dict(payloads);graph=closed_graph(payloads)
        self.assertEqual(graph,{'a.jar':('b.jar','b.jar','lib/c.jar'),'b.jar':('a.jar',),
            'lib/c.jar':('lib/d.jar',),'lib/d.jar':(),'orphan.jar':()})
        self.assertEqual(payloads,original)
        # A future archive member is not guessed into a partial inventory.
        with self.assertRaisesRegex(ValueError,'JAR_MANIFEST_CLASSPATH_TARGET_MISSING'):
            closed_graph({'a.jar':payloads['a.jar']})

    def test_unsafe_url_alias_directory_nonascii_and_missing_references_never_escape(self):
        marker=b'SYNTHETIC_PRIVATE_REFERENCE_DO_NOT_ECHO'
        for token in (b'../'+marker+b'.jar',b'/outside.jar',b'file:/outside.jar',b'https://example.invalid/x.jar',
                b'//outside/x.jar',b'x%2ejar',b'x.jar?private='+marker,b'x.jar#'+marker,b'./x.jar',
                b'lib//x.jar',b'lib/../x.jar',b'lib/',b'lib\\x.jar',b'x.JAR',b'x.jar\tb.jar',b'\t',
                b'\x0b',b'\xc3\xa9.jar'):
            with self.subTest(token=token),self.assertRaises(ValueError) as caught:
                closed_graph({'a.jar':jar(manifest=b'Class-Path: '+token+b'\n'),'x.jar':jar()})
            self.assertNotIn(marker.decode(),str(caught.exception))
        for token in (b'missing.jar',b'X.jar',b'lib/x.jar'):
            with self.subTest(token=token),self.assertRaisesRegex(ValueError,'JAR_MANIFEST_CLASSPATH_TARGET_MISSING'):
                closed_graph({'a.jar':jar(manifest=b'Class-Path: '+token+b'\n'),'x.jar':jar()})

    def test_export_map_exactness_and_reference_bounds_are_not_caller_booleans(self):
        payload=jar();rows=[{'name':'a.jar','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]
        valid={'a.jar':[]}
        variants=[([],valid), (rows+rows,valid), (rows,{}), (rows,{'a.jar':[],'foreign.jar':[]}),
            ([dict(rows[0],bytes=True)],valid),([dict(rows[0],sha256='unknown')],valid),
            ([dict(rows[0],extra='SYNTHETIC_PRIVATE')],valid),(rows,{'a.jar':()}),
            (rows,{'a.jar':['../a.jar']}),(rows,{'a.jar':['a.jar?query']})]
        for altered,refs in variants:
            with self.subTest(altered=altered,refs=refs),self.assertRaises(ValueError):
                a._closed_classpath_map(altered,refs)
        with patch.object(a,'MAX_CLASSPATH_REFS',1):
            with self.assertRaisesRegex(ValueError,'JAR_MANIFEST_CLASSPATH_REFERENCE_BOUND'):
                closed_graph({'a.jar':jar(manifest=b'Class-Path: a.jar a.jar\n')})
            with self.assertRaisesRegex(ValueError,'JAR_MANIFEST_CLASSPATH_REFERENCE_BOUND'):
                a._closed_classpath_map(rows,{'a.jar':['a.jar','a.jar']})

    def test_default_locked_jar_policy_and_all_target_shadow_checks_remain_strict(self):
        payload=jar(manifest=b'Manifest-Version: 1.0\nClass-Path: b.jar\n')
        before=hashlib.sha256(payload).hexdigest()
        self.assertEqual(a._scan_jar(io.BytesIO(payload),a._manifest_closed_references),['b.jar'])
        with self.assertRaisesRegex(ValueError,'JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED'):
            a.scan_jar(io.BytesIO(payload))
        self.assertEqual(before,hashlib.sha256(payload).hexdigest())
        for name in ('org/apache/iceberg/ClosedCopyDecoder.class',
                'org/apache/iceberg/ClosedCopyDecoder$Nested.class',
                'META-INF/versions/21/org/apache/iceberg/ClosedCopyDecoder.class'):
            with self.subTest(name=name),patch.object(a,'_closed_classpath_map',wraps=a._closed_classpath_map) as closure:
                with self.assertRaisesRegex(ValueError,'DECODER_CLASS_SHADOW_IN_SPARK_JAR'):
                    closed_graph({'a.jar':payload,'b.jar':jar(name)})
                closure.assert_not_called()


@unittest.skipUnless(os.name=='posix','Actual Linux closed export IO/modes require POSIX')
class PosixClosedClasspathContracts(unittest.TestCase):
    def test_whole_unpack_defers_forward_refs_and_preserves_bytes_modes_and_failed_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);base.chmod(0o700)
            first=jar(manifest=b'Class-Path: b.jar\n');second=jar(manifest=b'Class-Path: a.jar\n')
            archive=base/'closed.tar';raw=tar(member('jars/',kind=tarfile.DIRTYPE),
                member('jars/a.jar',first),member('jars/b.jar',second));archive.write_bytes(raw)
            output=base/'new';output.mkdir(mode=0o700)
            rows=a.unpack_jars(archive,output)
            self.assertEqual([row['name'] for row in rows],['a.jar','b.jar'])
            for row,payload in zip(rows,(first,second)):
                path=output/'jars'/row['name']
                self.assertEqual(path.read_bytes(),payload);self.assertEqual(row['sha256'],hashlib.sha256(payload).hexdigest())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o444)
            self.assertEqual(archive.read_bytes(),raw)
            with self.assertRaisesRegex(ValueError,'JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED'):
                a.scan_jar(output/'jars/a.jar')
            bad=base/'missing.tar';bad_raw=tar(member('jars/',kind=tarfile.DIRTYPE),member('jars/a.jar',first));bad.write_bytes(bad_raw)
            partial=base/'partial';partial.mkdir(mode=0o700)
            with self.assertRaisesRegex(ValueError,'JAR_MANIFEST_CLASSPATH_TARGET_MISSING'):
                a.unpack_jars(bad,partial)
            self.assertEqual((partial/'jars/a.jar').read_bytes(),first)
            self.assertEqual(stat.S_IMODE((partial/'jars/a.jar').stat().st_mode),0o444)
            self.assertEqual(bad.read_bytes(),bad_raw);self.assertEqual(archive.read_bytes(),raw)


def sized_manifest(size, tail=b''):
    """Synthetic folded values for exact byte-boundary tests, not a signature."""
    head = b'Manifest-Version: 1.0\nOther: \n'
    ending = b'\n' + tail
    available = size - len(head) - len(ending)
    if available < 0: raise AssertionError('Synthetic size too small')
    count, rest = divmod(available, 72)
    padding = b' ' + b'x' * (rest - 2) + b'\n' if rest >= 2 else b'\n' * rest
    result = head + (b' ' + b'x' * 70 + b'\n') * count + padding + ending
    if len(result) != size: raise AssertionError('Synthetic size mismatch')
    return result


class LargeExportedManifestContracts(unittest.TestCase):
    def test_large_signed_style_sections_full_tail_references_and_utf8_are_not_prefix_parsed(self):
        # Per-entry digest sections resemble signed manifests; no signer/authentication claim.
        sections = [b'Name: example/Entry' + str(index).encode() + b'.class\r\n'
            b'SHA-256-Digest: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\r\n\r\n'
            for index in range(1000)]
        manifest = b'Manifest-Version: 1.0\r\n\r\n' + b''.join(sections) + b'Class-Path: b.\r\n jar\r\nOther: caf\xc3\r\n \xa9\r\n\r\n'
        self.assertGreater(len(manifest), 65536)
        payload = jar(manifest=manifest); original = hashlib.sha256(payload).hexdigest(); budget = [0]
        refs = a._scan_jar(io.BytesIO(payload), a._manifest_closed_references, manifest_budget=budget)
        self.assertEqual(refs, ['b.jar']); self.assertEqual(budget, [len(manifest)])
        target = jar(); rows = [{'name': name, 'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
            for name, value in (('a.jar', payload), ('b.jar', target))]
        self.assertEqual(a._closed_classpath_map(rows, {'a.jar': refs, 'b.jar': []}),
            {'a.jar': ('b.jar',), 'b.jar': ()})
        self.assertEqual(hashlib.sha256(payload).hexdigest(), original)
        with self.assertRaisesRegex(ValueError, '^JAR_MANIFEST_BYTES_BOUND$'):
            a.scan_jar(io.BytesIO(payload))
        for suffix, code in ((b'Other: \xff\n', 'JAR_MANIFEST_UTF8_REQUIRED'),
                (b'Class-Path: ../SYNTHETIC_PRIVATE.jar\n', 'JAR_MANIFEST_CLASSPATH_TOKEN_REJECTED'),
                (b'Other: value\nother: duplicate\n', 'JAR_MANIFEST_DUPLICATE_ATTRIBUTE_REJECTED')):
            changed = jar(manifest=b'Manifest-Version: 1.0\r\n\r\n' + b''.join(sections) + suffix)
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, '^' + code + '$') as caught:
                a._scan_jar(io.BytesIO(changed), a._manifest_closed_references, manifest_budget=[0])
            self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))

    def test_export_exact_eight_mib_empty_and_one_byte_over_are_distinct_and_default_stays_64k(self):
        raw = sized_manifest(a.MAX_EXPORTED_MANIFEST); budget = [0]
        self.assertEqual(a._scan_jar(io.BytesIO(jar(manifest=raw)), a._manifest_closed_references,
            manifest_budget=budget), [])
        self.assertEqual(budget, [8 * 1024**2])
        for manifest, code in ((b'', 'JAR_MANIFEST_DECLARED_EMPTY'),
                (raw + b'\n', 'JAR_MANIFEST_DECLARED_SIZE_BOUND')):
            budget = [0]; payload = jar(manifest=manifest)
            with self.subTest(code=code), patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('Must reject before read')):
                with self.assertRaisesRegex(ValueError, '^' + code + '$'):
                    a._scan_jar(io.BytesIO(payload), a._manifest_closed_references, manifest_budget=budget)
            self.assertEqual(budget, [0])
        for manifest in (b'', sized_manifest(65537)):
            with self.assertRaisesRegex(ValueError, '^JAR_MANIFEST_BYTES_BOUND$'):
                a.scan_jar(io.BytesIO(jar(manifest=manifest)))
        a.scan_jar(io.BytesIO(jar(manifest=sized_manifest(65536))))
        with self.assertRaisesRegex(ValueError, '^JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED$'):
            a.scan_jar(io.BytesIO(jar(manifest=b'Manifest-Version: 1.0\nClass-Path: target.jar\n')))

    def test_crc_and_incomplete_or_extra_reads_fail_before_any_manifest_callback(self):
        payload = bytearray(jar(manifest=sized_manifest(70000)))
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            offset = archive.getinfo('META-INF/MANIFEST.MF').header_offset
        start = offset + 30 + int.from_bytes(payload[offset + 26:offset + 28], 'little') + int.from_bytes(payload[offset + 28:offset + 30], 'little')
        payload[start] ^= 1
        with patch.object(a, '_manifest_closed_references', wraps=a._manifest_closed_references) as parsed:
            with self.assertRaisesRegex(ValueError, '^VALID_BOUNDED_JAR_ZIP_REQUIRED$'):
                a._scan_jar(io.BytesIO(payload), parsed, manifest_budget=[0])
            parsed.assert_not_called()
        class StubArchive:
            def __init__(self, data): self.data = data; self.opens = 0
            def open(self, entry, mode): self.opens += 1; return io.BytesIO(self.data)
        entry = type('SyntheticEntry', (), {'file_size': 5})()
        for content in (b'1234', b'123456', b''):
            stub = StubArchive(content); budget = [0]
            with self.subTest(length=len(content)), self.assertRaisesRegex(ValueError, '^JAR_MANIFEST_READ_MISMATCH$'):
                a._read_export_manifest(stub, entry, budget)
            self.assertEqual(stub.opens, 1); self.assertEqual(budget, [5])
        with self.assertRaisesRegex(ValueError, '^VALID_BOUNDED_JAR_ZIP_REQUIRED$'):
            a._scan_jar(io.BytesIO(bytes(payload[:-50])), a._manifest_closed_references, manifest_budget=[0])

    def test_aggregate_32_mib_reserves_before_next_read_without_reset_or_absence_inference(self):
        payload = jar(manifest=sized_manifest(a.MAX_EXPORTED_MANIFEST)); budget = [0]
        for _ in range(4):
            self.assertEqual(a._scan_jar(io.BytesIO(payload), a._manifest_closed_references, manifest_budget=budget), [])
        self.assertEqual(budget, [32 * 1024**2])
        extra = jar(manifest=b'\n')
        with patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('Aggregate rejection must precede decompression')):
            with self.assertRaisesRegex(ValueError, '^JAR_MANIFEST_AGGREGATE_BYTES_BOUND$'):
                a._scan_jar(io.BytesIO(extra), a._manifest_closed_references, manifest_budget=budget)
        self.assertEqual(budget, [32 * 1024**2])
        self.assertEqual(a._scan_jar(io.BytesIO(jar()), a._manifest_closed_references, manifest_budget=budget), [])
        self.assertEqual(budget, [32 * 1024**2])
        for invalid in ([True], [-1], [a.MAX_TOTAL_MANIFEST + 1], [], {'used': 0}):
            with self.subTest(budget=invalid), self.assertRaisesRegex(ValueError, '^JAR_MANIFEST_AGGREGATE_BYTES_BOUND$'):
                a._scan_jar(io.BytesIO(extra), a._manifest_closed_references, manifest_budget=invalid)

    def test_chunked_values_preserve_section_duplicates_continuation_and_strict_whole_utf8(self):
        calls = []
        a._manifest(b'Other: caf\xc3\r\n \xa9\r\nClass-Path: a.\r\n jar\r\n\r\nClass-Path: b.jar\n', calls.append)
        self.assertEqual(calls, [b'a.jar', b'b.jar', b''])
        large = sized_manifest(70000, tail=b'Class-Path: b.jar\n')
        self.assertEqual(a._manifest_closed_references(large), ['b.jar'])
        with self.assertRaisesRegex(ValueError, '^STRICT_BOUNDED_JAR_MANIFEST_REQUIRED$'):
            a._manifest_no_classpath(large)
        for raw, code in ((b' Other: orphan\n', 'JAR_MANIFEST_CONTINUATION_REJECTED'),
                (b'Other: value\nother: duplicate\n', 'JAR_MANIFEST_DUPLICATE_ATTRIBUTE_REJECTED'),
                (b'Other: a\xc3\n b\n', 'JAR_MANIFEST_UTF8_REQUIRED')):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, '^' + code + '$'):
                a._manifest_closed_references(raw)


@unittest.skipUnless(os.name=='posix','Actual Linux large-manifest export IO requires POSIX')
class PosixLargeManifestContracts(unittest.TestCase):
    def test_large_manifest_whole_unpack_uses_shared_budget_and_preserves_sealed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); base.chmod(0o700); output = base/'new'; output.mkdir(mode=0o700)
            first = jar(manifest=sized_manifest(70000, tail=b'Class-Path: b.jar\n')); second = jar()
            raw = tar(member('jars/', kind=tarfile.DIRTYPE), member('jars/a.jar', first), member('jars/b.jar', second))
            archive = base/'export.tar'; archive.write_bytes(raw)
            with patch.object(a, '_read_export_manifest', wraps=a._read_export_manifest) as reader:
                rows = a.unpack_jars(archive, output)
                self.assertEqual(reader.call_count, 1); self.assertEqual(reader.call_args.args[2], [70000])
            self.assertEqual([row['name'] for row in rows], ['a.jar', 'b.jar'])
            for row, value in zip(rows, (first, second)):
                path = output/'jars'/row['name']; self.assertEqual(path.read_bytes(), value)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual(row['sha256'], hashlib.sha256(value).hexdigest())
            self.assertEqual(archive.read_bytes(), raw)


if __name__=='__main__':unittest.main()
