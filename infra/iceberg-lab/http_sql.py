"""Prepare fixed Trino HTTP request bytes/identity offline. Never submits SQL."""
import argparse
import hashlib
import json
from pathlib import Path
from sql_plan import plan


def prepare(sql):
    if not isinstance(sql, str) or not sql.strip() or '\0' in sql or len(sql.encode()) > 65536:
        raise ValueError('BOUNDED_PUBLIC_SQL_REQUIRED')
    end = len(sql.rstrip())
    removed = sql[end-1] == ';'
    wire = sql[:end-1] + sql[end:] if removed else sql
    if wire.rstrip().endswith(';'):
        raise ValueError('MULTIPLE_TERMINAL_DELIMITERS_NOT_SUPPORTED')
    original_bytes, wire_bytes = sql.encode(), wire.encode()
    return {'schemaVersion': 1, 'scope': 'OFFLINE_TRINO_HTTP_REQUEST_IDENTITY',
            'originalSql': sql, 'wireSql': wire,
            'originalSha256': hashlib.sha256(original_bytes).hexdigest(),
            'wireSha256': hashlib.sha256(wire_bytes).hexdigest(),
            'originalBytes': len(original_bytes), 'wireBytes': len(wire_bytes),
            'normalization': 'ONE_TERMINAL_SEMICOLON_ONLY', 'terminalSemicolonRemoved': removed,
            'method': 'POST', 'path': '/v1/statement', 'automaticRetries': 0,
            'submitted': False, 'queryId': None}


def request_plan():
    sql = plan()
    statements = [{**prepare(row['sql']), 'name': row['name'], 'mutation': row['mutation']} for row in sql['statements']]
    inspection = [{**prepare(body), 'name': name, 'mutation': False} for name, body in sql['inspection'].items()]
    return {'schemaVersion': 1, 'status': 'PREPARED_NOT_RUN', 'statements': statements, 'inspection': inspection,
            'networkRequestsPerformed': 0, 'sqlExecuted': False, 'driverImplemented': False,
            'futureDriverRequirements': ['immutable intent before single POST', 'record real query id',
                'GET continuation only after accepted POST', 'no resubmit after unknown outcome']}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(request_plan(), stream, indent=2); stream.write('\n')


if __name__ == '__main__': main()
