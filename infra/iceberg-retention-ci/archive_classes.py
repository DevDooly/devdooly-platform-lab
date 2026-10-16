"""Manual bounded JAR export and new class artifact checks. No commands/network."""
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re
import stat
import zipfile

MAX_JARS, MAX_JAR, MAX_TOTAL = 512, 128*1024**2, 1024**3
MAX_ARCHIVE, MAX_HEADERS, MAX_ZIP_ENTRIES = MAX_TOTAL+16*1024**2, 3072, 512000
MAX_CLASSPATH_REFS = 4096
MAX_EXPORTED_MANIFEST, MAX_TOTAL_MANIFEST = 8*1024**2, 32*1024**2
CLASS = re.compile(r'org/apache/iceberg/ClosedCopyDecoder(?:\$[A-Za-z0-9_$]+)?\.class')
DIRECTORIES = {'org','org/apache','org/apache/iceberg'}


def require(value, code):
    if not value: raise ValueError(code)


def identity(info):
    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,
        info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def _octal(raw):
    value = raw.rstrip(b'\0 ').lstrip(b' ')
    require(not value or re.fullmatch(b'[0-7]+',value), 'TAR_OCTAL_FIELD_REQUIRED')
    return 0 if not value else int(value,8)


def _text(raw):
    value, separator, rest = raw.partition(b'\0')
    require(not separator or not rest.strip(b'\0'), 'TAR_HIDDEN_TEXT_REJECTED')
    try: result = value.decode('ascii')
    except UnicodeError: raise ValueError('TAR_ASCII_NAME_REQUIRED') from None
    require(result and len(result) <= 255, 'TAR_BOUNDED_NAME_REQUIRED')
    return result


def _path(name, *, directory=False):
    require(type(name) is str and name.isascii() and '\\' not in name and not name.startswith('/')
        and len(name) <= 255 and not any(c in name for c in ('\0','\r','\n',':')), 'TAR_SAFE_RELATIVE_NAME_REQUIRED')
    if directory and name.endswith('/'): name = name[:-1]
    parts = name.split('/')
    require(1 <= len(parts) <= 8 and all(re.fullmatch('[A-Za-z0-9][A-Za-z0-9._+-]{0,199}',p)
        and p not in ('.','..') for p in parts), 'TAR_SAFE_COMPONENTS_REQUIRED')
    return name


def _pax_times(raw):
    """Only ignored time metadata; never apply path/linkpath/size overrides."""
    require(0 < len(raw) <= 4096, 'PAX_TIME_METADATA_BOUND')
    position, fields = 0, set()
    while position < len(raw):
        space = raw.find(b' ',position)
        require(space > position and re.fullmatch(b'[1-9][0-9]{0,3}',raw[position:space]), 'PAX_EXACT_RECORD_LENGTH_REQUIRED')
        length = int(raw[position:space]); end = position+length
        require(space < end <= len(raw) and raw[end-1:end] == b'\n', 'PAX_EXACT_RECORD_LENGTH_REQUIRED')
        key, separator, value = raw[space+1:end-1].partition(b'=')
        require(separator and key in (b'mtime',b'atime',b'ctime') and key not in fields
            and re.fullmatch(rb'-?[0-9]{1,12}(?:\.[0-9]{1,9})?',value), 'ONLY_UNIQUE_PAX_TIME_METADATA')
        fields.add(key); position = end
    require(position == len(raw) and 1 <= len(fields) <= 3, 'PAX_TIME_METADATA_BOUND')


def _read_exact(stream, size):
    raw = stream.read(size)
    require(type(raw) is bytes and len(raw) == size, 'TAR_COMPLETE_BYTES_REQUIRED')
    return raw


def _consume_tar(stream, on_directory, on_file):
    """Raw tar headers; callbacks must consume exactly the bounded file size."""
    seen, directories, count, total, headers = set(), set(), 0, 0, 0
    while True:
        header = _read_exact(stream,512); headers += 1
        require(headers <= MAX_HEADERS, 'TAR_HEADER_COUNT_BOUND')
        if header == bytes(512):
            require(_read_exact(stream,512) == bytes(512), 'TAR_TWO_ZERO_END_BLOCKS_REQUIRED')
            while True:
                extra = stream.read(512)
                if not extra: break
                require(len(extra) == 512 and extra == bytes(512), 'TAR_TRAILING_DATA_REJECTED')
            require('jars' in directories and 1 <= count <= MAX_JARS, 'NONEMPTY_JARS_ROOT_REQUIRED')
            return
        expected = _octal(header[148:156])
        require(expected == sum(header[:148])+8*32+sum(header[156:]), 'TAR_HEADER_CHECKSUM_REQUIRED')
        require(header[257:263] in (b'ustar\0',b'ustar ') and header[263:265] in (b'00',b' \0'), 'ONLY_USTAR_HEADER_REQUIRED')
        name = _text(header[:100])
        prefix = header[345:500]
        if prefix.strip(b'\0'): name = _text(prefix)+'/'+name
        size, kind = _octal(header[124:136]), header[156:157]
        require(not header[157:257].strip(b'\0'), 'TAR_LINK_TARGET_REJECTED')
        if kind in (b'x',b'g'):
            require(0 < size <= 4096, 'PAX_TIME_METADATA_BOUND')
            _path(name); _pax_times(_read_exact(stream,size))
            padding = (-size)%512
            require(not padding or _read_exact(stream,padding) == bytes(padding), 'TAR_ZERO_PADDING_REQUIRED')
            continue
        require(kind in (b'0',b'\0',b'5'), 'TAR_ONLY_DIRECTORY_OR_REGULAR_JAR')
        name = _path(name,directory=kind == b'5')
        require(name == 'jars' or name.startswith('jars/'), 'ONLY_EXACT_JARS_ROOT_REQUIRED')
        require(name not in seen, 'DUPLICATE_TAR_MEMBER_REJECTED'); seen.add(name)
        parent = name.rsplit('/',1)[0] if '/' in name else None
        require(parent is None or parent in directories, 'TAR_PARENT_DIRECTORY_MUST_PRECEDE_CHILD')
        if kind == b'5':
            require(size == 0 and len(directories) < 1024, 'TAR_DIRECTORY_BOUND_REQUIRED')
            directories.add(name); on_directory(name)
        else:
            require(name != 'jars' and name.endswith('.jar') and 0 < size <= MAX_JAR, 'ONLY_BOUNDED_REGULAR_JAR_REQUIRED')
            count += 1; total += size
            require(count <= MAX_JARS and total <= MAX_TOTAL, 'JAR_COUNT_AND_TOTAL_BOUND')
            on_file(name,size,stream)
            padding = (-size)%512
            require(not padding or _read_exact(stream,padding) == bytes(padding), 'TAR_ZERO_PADDING_REQUIRED')


def _read_export_manifest(archive, entry, budget):
    """Reserve the whole declared size before bounded decompression and EOF/CRC."""
    size = entry.file_size
    require(type(size) is int and size >= 0, 'JAR_MANIFEST_DECLARED_SIZE_BOUND')
    require(size != 0, 'JAR_MANIFEST_DECLARED_EMPTY')
    require(size <= MAX_EXPORTED_MANIFEST, 'JAR_MANIFEST_DECLARED_SIZE_BOUND')
    require(type(budget) is list and len(budget) == 1 and type(budget[0]) is int
        and 0 <= budget[0] <= MAX_TOTAL_MANIFEST - size, 'JAR_MANIFEST_AGGREGATE_BYTES_BOUND')
    budget[0] += size
    chunks, remaining = [], size
    with archive.open(entry, 'r') as stream:
        while remaining:
            requested = min(65536, remaining)
            chunk = stream.read(requested)
            require(type(chunk) is bytes and 0 < len(chunk) <= requested,
                'JAR_MANIFEST_READ_MISMATCH')
            chunks.append(chunk); remaining -= len(chunk)
        extra = stream.read(1)
        require(type(extra) is bytes and extra == b'', 'JAR_MANIFEST_READ_MISMATCH')
    raw = b''.join(chunks)
    require(len(raw) == size, 'JAR_MANIFEST_READ_MISMATCH')
    return raw


def _scan_jar(source, manifest_reader, *, manifest_budget=None):
    """Scan central entries and a bounded manifest; never follow classpath URLs."""
    try:
        with zipfile.ZipFile(source,'r') as archive:
            entries = archive.infolist()
            require(0 < len(entries) <= MAX_ZIP_ENTRIES, 'ZIP_ENTRY_COUNT_BOUND')
            manifests, references = [], []
            for entry in entries:
                name = entry.orig_filename
                require(name == entry.filename and 0 < len(name) <= 4096 and '\0' not in name
                    and '\\' not in name and not name.startswith('/') and ':' not in name
                    and all(part not in ('.','..') for part in name.rstrip('/').split('/')), 'ZIP_SAFE_ENTRY_NAME_REQUIRED')
                # Multi-release class names can also shadow Java21's main.
                relative = re.sub(r'^META-INF/versions/[1-9][0-9]*/','',name)
                require(not CLASS.fullmatch(relative), 'DECODER_CLASS_SHADOW_IN_SPARK_JAR')
                if name.upper() == 'META-INF/MANIFEST.MF': manifests.append(entry)
            require(len(manifests) <= 1, 'ONE_UNAMBIGUOUS_JAR_MANIFEST_REQUIRED')
            if manifests:
                entry = manifests[0]
                if manifest_budget is None:
                    # Public/default locked-JAR policy is deliberately unchanged.
                    require(0 < entry.file_size <= 65536, 'JAR_MANIFEST_BYTES_BOUND')
                    with archive.open(entry,'r') as stream: raw = stream.read(65537)
                    require(len(raw) == entry.file_size and len(raw) <= 65536, 'JAR_MANIFEST_BYTES_BOUND')
                else:
                    raw = _read_export_manifest(archive, entry, manifest_budget)
                references = manifest_reader(raw) or []
        return references
    except (zipfile.BadZipFile,zipfile.LargeZipFile,UnicodeError,EOFError,RuntimeError,NotImplementedError):
        raise ValueError('VALID_BOUNDED_JAR_ZIP_REQUIRED') from None


def _manifest(raw, on_classpath, *, maximum=65536):
    require(type(raw) is bytes and 0 < len(raw) <= maximum and b'\0' not in raw
        and raw[-1:] in (b'\n',b'\r'), 'STRICT_BOUNDED_JAR_MANIFEST_REQUIRED')
    # JAR logical lines use CR/LF bytes and a leading ASCII space continuation;
    # Unicode line separators are values, never additional attribute boundaries.
    lines = raw.replace(b'\r\n',b'\n').replace(b'\r',b'\n').split(b'\n')
    attributes, previous = {}, None
    def finish():
        classpath = b''
        for name, chunks in attributes.items():
            value = b''.join(chunks)
            try: value.decode('utf-8')
            except UnicodeError: raise ValueError('JAR_MANIFEST_UTF8_REQUIRED') from None
            if name == b'class-path': classpath = value
        on_classpath(classpath)
    for line in lines:
        if not line:
            finish(); attributes,previous = {},None; continue
        if line.startswith(b' '):
            require(previous is not None, 'JAR_MANIFEST_CONTINUATION_REJECTED')
            attributes[previous].append(line[1:]); continue
        name,separator,value = line.partition(b': ')
        require(separator and re.fullmatch(b'[A-Za-z0-9_-]{1,70}',name), 'JAR_MANIFEST_ATTRIBUTE_REQUIRED')
        name = name.lower()
        require(name not in attributes, 'JAR_MANIFEST_DUPLICATE_ATTRIBUTE_REJECTED')
        attributes[name] = [value]; previous = name
    finish()


def scan_jar(source):
    """Public/default scan still rejects every nonempty manifest Class-Path."""
    _scan_jar(source, _manifest_no_classpath)


def _manifest_no_classpath(raw):
    def reject(value):
        require(not value.strip(), 'JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED')
    _manifest(raw, reject)


def _classpath_token(raw):
    require(type(raw) is bytes and 1 <= len(raw) <= 255 and raw.endswith(b'.jar'),
        'JAR_MANIFEST_CLASSPATH_TOKEN_REJECTED')
    parts = raw.split(b'/')
    require(1 <= len(parts) <= 8 and all(re.fullmatch(rb'[A-Za-z0-9][A-Za-z0-9._+-]{0,199}', p)
        and p not in (b'.', b'..') for p in parts), 'JAR_MANIFEST_CLASSPATH_TOKEN_REJECTED')
    return raw.decode('ascii')


def _manifest_closed_references(raw):
    references = []
    def collect(value):
        # Only ASCII spaces separate tokens. Other whitespace is conservatively
        # rejected, rather than reinterpreted by a URL or filesystem parser.
        for token in value.split(b' '):
            if token:
                require(len(references) < MAX_CLASSPATH_REFS, 'JAR_MANIFEST_CLASSPATH_REFERENCE_BOUND')
                references.append(_classpath_token(token))
    _manifest(raw, collect, maximum=MAX_EXPORTED_MANIFEST)
    return references


def _closed_classpath_map(rows, references):
    """Validate every reference against the complete whole-verified export map."""
    require(type(rows) is list and 1 <= len(rows) <= MAX_JARS,
        'JAR_MANIFEST_CLASSPATH_EXPORT_MAP_REQUIRED')
    names, total = set(), 0
    for row in rows:
        require(type(row) is dict and set(row) == {'name', 'bytes', 'sha256'}
            and type(row['name']) is str and row['name'].endswith('.jar')
            and type(row['bytes']) is int and 0 < row['bytes'] <= MAX_JAR
            and type(row['sha256']) is str and re.fullmatch('[a-f0-9]{64}', row['sha256']),
            'JAR_MANIFEST_CLASSPATH_EXPORT_MAP_REQUIRED')
        _path('jars/' + row['name'])
        require(row['name'] not in names, 'JAR_MANIFEST_CLASSPATH_EXPORT_MAP_REQUIRED')
        names.add(row['name']); total += row['bytes']
    require(total <= MAX_TOTAL and type(references) is dict and set(references) == names,
        'JAR_MANIFEST_CLASSPATH_EXPORT_MAP_REQUIRED')
    graph, reference_count = {}, 0
    for name in sorted(names):
        tokens = references[name]
        require(type(tokens) is list, 'JAR_MANIFEST_CLASSPATH_EXPORT_MAP_REQUIRED')
        targets = []
        prefix = name.rsplit('/', 1)[0] + '/' if '/' in name else ''
        for token in tokens:
            reference_count += 1
            require(reference_count <= MAX_CLASSPATH_REFS, 'JAR_MANIFEST_CLASSPATH_REFERENCE_BOUND')
            require(type(token) is str and token.isascii(), 'JAR_MANIFEST_CLASSPATH_TOKEN_REJECTED')
            canonical = _classpath_token(token.encode('ascii'))
            target = prefix + canonical
            require(target in names, 'JAR_MANIFEST_CLASSPATH_TARGET_MISSING')
            targets.append(target)
        # Keep duplicate edges and source order. The traversal below visits each
        # vertex once, so duplicates and closed cycles cannot expand the scope.
        graph[name] = tuple(targets)
    visited, steps = set(), 0
    for root in sorted(names):
        if root in visited: continue
        pending = [root]
        while pending:
            name = pending.pop(); steps += 1
            require(steps <= MAX_JARS + MAX_CLASSPATH_REFS, 'JAR_MANIFEST_CLASSPATH_CLOSURE_BOUND')
            if name in visited: continue
            require(name in names, 'JAR_MANIFEST_CLASSPATH_TARGET_MISSING')
            visited.add(name); pending.extend(graph[name])
    require(visited == names, 'JAR_MANIFEST_CLASSPATH_CLOSURE_BOUND')
    return graph


def _linux():
    require(os.name == 'posix' and all(hasattr(os,n) for n in ('O_NOFOLLOW','O_DIRECTORY','O_CLOEXEC','getuid')), 'LINUX_PRIVATE_ARTIFACT_IO_REQUIRED')


def _directory_fd(stack, path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.resolve(strict=True) == path
        and not path.is_symlink(), 'CANONICAL_PRIVATE_DIRECTORY_REQUIRED')
    fd = os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC); stack.callback(os.close,fd)
    info = os.fstat(fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid(), 'OWNED_PRIVATE_DIRECTORY_REQUIRED')
    require(identity(path.lstat()) == identity(info), 'PRIVATE_DIRECTORY_IDENTITY_CHANGED')
    return path,fd,info


def unpack_jars(archive, new_empty_dir):
    """Caller creates a fresh private0700 dir; returns names relative to jars/."""
    _linux(); result = []; references = {}; reference_count = 0; manifest_budget = [0]
    try:
        with ExitStack() as stack:
            root,root_fd,before = _directory_fd(stack,new_empty_dir)
            require(stat.S_IMODE(before.st_mode) == 0o700 and not os.listdir(root_fd), 'FRESH_EMPTY_PRIVATE_JAR_OUTPUT_REQUIRED')
            archive = Path(archive).absolute(); first = archive.lstat()
            require(archive.parent.resolve(strict=True) == archive.parent and stat.S_ISREG(first.st_mode)
                and first.st_nlink == 1 and first.st_uid == os.getuid() and 1024 <= first.st_size <= MAX_ARCHIVE,
                'BOUNDED_OWN_REGULAR_ARCHIVE_REQUIRED')
            archive_fd = os.open(archive,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC); stack.callback(os.close,archive_fd)
            require(identity(first) == identity(os.fstat(archive_fd)), 'ARCHIVE_OPEN_IDENTITY_CHANGED')
            directories = {'':root_fd}
            def directory(name):
                parent = name.rsplit('/',1)[0] if '/' in name else ''
                base = name.rsplit('/',1)[-1]
                os.mkdir(base,0o755,dir_fd=directories[parent])
                fd = os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directories[parent]); stack.callback(os.close,fd)
                os.fchmod(fd,0o755); directories[name] = fd
            def jar(name,size,stream):
                nonlocal reference_count
                parent,base = name.rsplit('/',1)
                fd = os.open(base,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o444,dir_fd=directories[parent])
                sha = hashlib.sha256(); remaining = size
                with os.fdopen(fd,'wb') as output:
                    os.fchmod(output.fileno(),0o444)
                    while remaining:
                        chunk = _read_exact(stream,min(65536,remaining)); remaining -= len(chunk); sha.update(chunk); output.write(chunk)
                    output.flush(); os.fsync(output.fileno())
                actual = os.stat(base,dir_fd=directories[parent],follow_symlinks=False)
                require(stat.S_ISREG(actual.st_mode) and actual.st_nlink == 1 and actual.st_uid == os.getuid()
                    and stat.S_IMODE(actual.st_mode) == 0o444 and actual.st_size == size, 'EXACT_NEW_READONLY_JAR_REQUIRED')
                read_fd = os.open(base,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directories[parent])
                with os.fdopen(read_fd,'rb') as readback:
                    require(identity(actual) == identity(os.fstat(readback.fileno())), 'NEW_JAR_READBACK_IDENTITY_CHANGED')
                    verified = hashlib.sha256(); count = 0
                    while True:
                        chunk = readback.read(65536)
                        if not chunk: break
                        count += len(chunk); require(count <= size, 'NEW_JAR_READBACK_BOUND'); verified.update(chunk)
                    require(count == size and verified.digest() == sha.digest(), 'NEW_JAR_READBACK_WHOLE_SHA_CHANGED')
                    readback.seek(0)
                    refs = _scan_jar(readback, _manifest_closed_references, manifest_budget=manifest_budget)
                    reference_count += len(refs)
                    require(reference_count <= MAX_CLASSPATH_REFS, 'JAR_MANIFEST_CLASSPATH_REFERENCE_BOUND')
                    references[name.removeprefix('jars/')] = refs
                    require(identity(actual) == identity(os.fstat(readback.fileno()))
                        == identity(os.stat(base,dir_fd=directories[parent],follow_symlinks=False)), 'NEW_JAR_CHANGED_DURING_ZIP_SCAN')
                result.append({'name':name.removeprefix('jars/'),'bytes':size,'sha256':sha.hexdigest()})
            with os.fdopen(os.dup(archive_fd),'rb') as stream: _consume_tar(stream,directory,jar)
            require(identity(first) == identity(os.fstat(archive_fd)) == identity(archive.lstat()), 'ARCHIVE_CHANGED_DURING_UNPACK')
            _closed_classpath_map(result, references)
            root_key = lambda info:(info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)
            require(root_key(os.fstat(root_fd)) == root_key(root.lstat()) == root_key(before),
                'JAR_OUTPUT_ROOT_IDENTITY_CHANGED')
        return sorted(result,key=lambda row:row['name'])
    except OSError: raise ValueError('PRIVATE_JAR_IO_FAILED') from None


def class_header(raw):
    require(type(raw) is bytes and 8 <= len(raw) <= 1024**2 and raw[:4] == b'\xca\xfe\xba\xbe'
        and int.from_bytes(raw[6:8],'big') == 65, 'JAVA21_CLASS_HEADER_REQUIRED')


def _class_tree(stack, newdir, *, sealed):
    path,fd,before = _directory_fd(stack,newdir)
    require(path.name == 'classes' and path.parent.stat().st_uid == os.getuid()
        and stat.S_IMODE(path.parent.stat().st_mode) == 0o700, 'ONLY_FRESH_PRIVATE_CLASSES_TARGET')
    require(not sealed or stat.S_IMODE(before.st_mode) in (0o555,0o755), 'SEALED_CLASS_DIRECTORY_MODE_REQUIRED')
    files, directories = [], [(fd,before)]
    def walk(parent,prefix):
        for name in sorted(os.listdir(parent)):
            relative = prefix+name; info = os.stat(name,dir_fd=parent,follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                require(relative in DIRECTORIES and info.st_uid == os.getuid()
                    and (not sealed or stat.S_IMODE(info.st_mode) in (0o555,0o755)), 'ONLY_OWN_CLASS_PACKAGE_DIRECTORIES')
                child = os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent); stack.callback(os.close,child)
                require(identity(info) == identity(os.fstat(child)), 'CLASS_DIRECTORY_OPEN_CHANGED')
                directories.append((child,info)); walk(child,relative+'/')
            else:
                require(CLASS.fullmatch(relative) and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and info.st_uid == os.getuid() and 8 <= info.st_size <= 1024**2
                    and (not sealed or stat.S_IMODE(info.st_mode) == 0o444), 'ONLY_OWN_SINGLE_LINK_JAVA21_CLASSES')
                child = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent); stack.callback(os.close,child)
                require(identity(info) == identity(os.fstat(child)), 'CLASS_FILE_OPEN_CHANGED')
                chunks, remaining = [], info.st_size
                while remaining:
                    chunk = os.read(child,min(65536,remaining)); require(chunk, 'COMPLETE_COMPILED_CLASS_BYTES_REQUIRED')
                    chunks.append(chunk); remaining -= len(chunk)
                require(not os.read(child,1) and identity(info) == identity(os.fstat(child))
                    == identity(os.stat(name,dir_fd=parent,follow_symlinks=False)), 'COMPILED_CLASS_CHANGED_DURING_READ')
                raw = b''.join(chunks); class_header(raw)
                files.append((child,{'path':relative,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},info,parent,name))
                require(len(files) <= 64, 'COMPILED_CLASS_COUNT_BOUND')
    walk(fd,'')
    require(any(row['path'] == 'org/apache/iceberg/ClosedCopyDecoder.class' for _,row,_,_,_ in files), 'EXACT_DECODER_MAIN_CLASS_REQUIRED')
    for child,_,info,parent,name in files:
        require(identity(os.fstat(child)) == identity(os.stat(name,dir_fd=parent,follow_symlinks=False)) == identity(info),
            'CLASS_IDENTITY_CHANGED_AFTER_TREE_READ')
    for child,info in directories:
        require(identity(os.fstat(child)) == identity(info), 'CLASS_DIRECTORY_CHANGED_DURING_TREE_READ')
    require(identity(path.lstat()) == identity(os.fstat(fd)), 'CLASSES_ROOT_CHANGED')
    return files,directories


def compiled_classes(newdir):
    _linux()
    try:
        with ExitStack() as stack:
            files,_ = _class_tree(stack,newdir,sealed=True)
            return sorted((row for _,row,_,_,_ in files),key=lambda row:row['path'])
    except OSError: raise ValueError('COMPILED_CLASS_IO_FAILED') from None


def seal_new_classes(newdir):
    """Only caller's newly compiled private classes tree, never a source/JAR path."""
    _linux()
    try:
        with ExitStack() as stack:
            files,directories = _class_tree(stack,newdir,sealed=False)
            expected = sorted((row for _,row,_,_,_ in files),key=lambda row:row['path'])
            for fd,_,_,_,_ in files: os.fchmod(fd,0o444)
            for fd,_ in reversed(directories): os.fchmod(fd,0o555)
        actual = compiled_classes(newdir)
        require(actual == expected, 'SEALED_CLASS_WHOLE_BYTES_CHANGED')
        return actual
    except OSError: raise ValueError('NEW_CLASS_SEAL_FAILED') from None
