"""Offline local vendor hash gate. No download, build, extraction or execution."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile

EXPECTED={
    'org.apache.iceberg:iceberg-spark-runtime-4.1_2.13:1.11.0':('iceberg-spark-runtime-4.1_2.13-1.11.0.jar','org/apache/iceberg/spark/SparkCatalog.class'),
    'org.apache.iceberg:iceberg-aws-bundle:1.11.0':('iceberg-aws-bundle-1.11.0.jar','software/amazon/awssdk/services/s3/S3Client.class'),
    'org.postgresql:postgresql:42.7.14':('postgresql-42.7.14.jar','org/postgresql/Driver.class'),
}


def require(value,code):
    if not value:raise ValueError(code)


def lock_rows(lock):
    rows=lock['jars'];require(len(rows)==3 and {v['coordinate'] for v in rows}==set(EXPECTED),'EXACT_THREE_PINNED_COORDINATES')
    for row in rows:
        require(row['filename']==EXPECTED[row['coordinate']][0] and re.fullmatch('[a-f0-9]{64}',row.get('sha256') or ''),
            'UNRESOLVED_OR_UNREVIEWED_VENDOR_SHA_MUST_BLOCK_BUILD')
    return rows


def validate(lock,directory):
    rows=lock_rows(lock);total=0;result=[]
    for row in rows:
        path=directory/row['filename'];info=path.lstat()
        require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and 0<info.st_size<=768*1024**2,'BOUNDED_REGULAR_VENDOR_JAR')
        total+=info.st_size;require(total<=1536*1024**2,'BOUNDED_TOTAL_VENDOR_BYTES')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024**2),b''):digest.update(chunk)
        require(digest.hexdigest()==row['sha256'],'ACTUAL_VENDOR_BYTES_SHA_MISMATCH')
        with zipfile.ZipFile(path) as jar:
            member=jar.getinfo(EXPECTED[row['coordinate']][1]);require(member.file_size<=4*1024**2,'BOUNDED_SELECTED_CLASS')
            with jar.open(member) as stream:header=stream.read(8)
            require(len(header)==8 and header[:4]==b'\xca\xfe\xba\xbe' and 52<=int.from_bytes(header[6:8],'big')<=65,
                'SELECTED_VENDOR_CLASS_JAVA_21_COMPATIBLE_MAJOR')
        result.append({'filename':row['filename'],'sha256':row['sha256'],'bytes':info.st_size,
            'selectedClassMajor':int.from_bytes(header[6:8],'big')})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--lock',type=Path,required=True)
    parser.add_argument('--vendor',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=validate(json.loads(args.lock.read_bytes()),args.vendor)
    with args.output.open('x',encoding='ascii',newline='\n') as stream:
        stream.write(''.join(v['sha256']+'  /opt/spark/jars/'+v['filename']+'\n' for v in result))
    print(json.dumps({'passed':True,'scope':'OFFLINE_VENDOR_BYTES_AND_SELECTED_CLASS_HEADERS_ONLY','jarCount':3,
        'runtimeCompatibilityVerified':False,'imageBuilt':False}))


if __name__=='__main__':main()
