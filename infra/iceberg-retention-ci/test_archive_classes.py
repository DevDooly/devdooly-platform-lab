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


if __name__=='__main__':unittest.main()
