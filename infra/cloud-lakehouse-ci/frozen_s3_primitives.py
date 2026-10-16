"""Exact pure signing/XML primitives extracted from the earlier pinned reader.
No native Client, capability, mutation, main or cluster validator is included.
"""
import hashlib
import hmac
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contract import require, sha
MIB = 1024**2


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError('S3_REDIRECT_FORBIDDEN')


def xml(raw, expected):
    require(len(raw) <= MIB and b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(), 'BOUNDED_XML_REQUIRED')
    root = ET.fromstring(raw)
    for node in root.iter(): node.tag = node.tag.rsplit('}', 1)[-1]
    require(root.tag == expected, 'S3_XML_ERROR_OR_UNEXPECTED_RESPONSE')
    return root


def canonical_query(pairs):
    quote = lambda text: urllib.parse.quote(str(text), safe='-_.~')
    return '&'.join(k + '=' + v for k, v in sorted((quote(k), quote(v)) for k, v in pairs))


def signature(method, host, uri, query, body, access, secret, moment, extra=None):
    at = moment.strftime('%Y%m%dT%H%M%SZ'); date = moment.strftime('%Y%m%d'); payload = sha(body)
    headers = {'host': host, 'x-amz-content-sha256': payload, 'x-amz-date': at, **(extra or {})}
    signed = ';'.join(sorted(headers))
    canonical_headers = ''.join(key + ':' + ' '.join(headers[key].split()) + '\n' for key in sorted(headers))
    canonical = '\n'.join((method, uri, query, canonical_headers, signed, payload))
    scope = date + '/garage/s3/aws4_request'
    text = '\n'.join(('AWS4-HMAC-SHA256', at, scope, sha(canonical.encode())))
    key = ('AWS4' + secret).encode()
    for part in (date, 'garage', 's3', 'aws4_request'): key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    headers['Authorization'] = ('AWS4-HMAC-SHA256 Credential=' + access + '/' + scope + ', SignedHeaders=' + signed
                                + ', Signature=' + hmac.new(key, text.encode(), hashlib.sha256).hexdigest())
    return headers, canonical
