"""Actual reader expressions with inert readers; no PySpark/JAR/network use."""
import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
import run_ci

ROOT=Path(__file__).resolve().parents[2]
SILVER=ROOT/'infra/spark-silver/spark_silver.py'
BOOTSTRAP=Path(__file__).with_name('bootstrap_spark.py')
OLD_SILVER_SHA='189ec387433784e4623ba8b24efeeeed40b90213b2582450170ba687bcf067ec'
OLD_BOOTSTRAP_SHA='d44e05c8ecf188ba0f50dda797a4b15a7e3ce5fc101ce3d3017b8a5c9fc18b60'
OLD_RUNNER_SHA='45ecfcf27c762bdf4375f6bacc49b24b5ebbd888f001ae1fc90c010fae8cd340'


class Reader:
    def __init__(self):self.calls=[]
    def option(self,key,value):
        if key!='versionAsOf':raise AssertionError('LEGACY_OR_UNKNOWN_TIME_TRAVEL_OPTION')
        self.calls.append(('option',key,value));return self
    def table(self,table):self.calls.append(('table',table));return self
    def select(self,*fields):self.calls.append(('select',fields));return self


def read_expression(path,function):
    tree=ast.parse(path.read_text('utf-8'));fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef)and node.name==function)
    expressions=[node.value for node in ast.walk(fn)if isinstance(node,ast.Assign)
        and isinstance(node.value,ast.Call)and any(isinstance(child,ast.Call)and isinstance(child.func,ast.Attribute)
            and child.func.attr=='option'for child in ast.walk(node.value))]
    if len(expressions)!=1:raise AssertionError('ONE_ACTUAL_SNAPSHOT_READER_EXPRESSION')
    return compile(ast.Expression(expressions[0]),str(path),'eval')


class SnapshotOptions(unittest.TestCase):
    def test_actual_silver_expression_passes_exact_bigint_as_version_as_of_string(self):
        expression=read_expression(SILVER,'run')
        for sid in (9007199254740993,9223372036854775807):
            reader=Reader();fields=('input_sequence','source_sha256');table='phase6.bronze.synthetic_events'
            result=eval(expression,{'spark':SimpleNamespace(read=reader),'snapshot_id':sid,'SOURCE_TABLE':table,'FIELDS':fields})
            self.assertIs(reader,result)
            self.assertEqual([('option','versionAsOf',str(sid)),('table',table),('select',fields)],reader.calls)

    def test_actual_bootstrap_both_time_travel_reads_use_same_modern_option_without_rounding(self):
        expression=read_expression(BOOTSTRAP,'execute');table='phase6.bronze.synthetic_events';fields=('input_sequence',)
        snapshots=[{'snapshot_id':9007199254740993},{'snapshot_id':9223372036854775807}]
        for index in range(2):
            reader=Reader()
            eval(expression,{'spark':SimpleNamespace(read=reader),'snapshots':snapshots,'index':index,
                'silver':SimpleNamespace(SOURCE_TABLE=table),'FIELDS':fields})
            self.assertEqual(('option','versionAsOf',str(snapshots[index]['snapshot_id'])),reader.calls[0])

    def test_silver_and_bootstrap_only_change_one_option_literal_preserving_every_other_byte(self):
        for path,old in ((SILVER,OLD_SILVER_SHA),(BOOTSTRAP,OLD_BOOTSTRAP_SHA)):
            raw=path.read_bytes()
            self.assertEqual(1,raw.count(b"option('versionAsOf',"));self.assertNotIn(b"option('snapshot-id',",raw)
            restored=raw.replace(b"option('versionAsOf',",b"option('snapshot-id',")
            self.assertEqual(old,hashlib.sha256(restored).hexdigest())

    def test_runner_binds_new_module_and_only_its_one_frozen_pin_changes(self):
        current=hashlib.sha256(SILVER.read_bytes()).hexdigest()
        self.assertEqual(current,run_ci.MODULES['spark_silver.py']);self.assertNotEqual(OLD_SILVER_SHA,current)
        raw=Path(run_ci.__file__).read_bytes();self.assertEqual(1,raw.count(current.encode()))
        self.assertEqual(OLD_RUNNER_SHA,hashlib.sha256(raw.replace(current.encode(),OLD_SILVER_SHA.encode())).hexdigest())


if __name__=='__main__':unittest.main()
