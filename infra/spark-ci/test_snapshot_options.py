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
BOOTSTRAP_EXECUTE_AST_SHA='f231cfd9b5c70f5699b1bba8444fd8644be4bf5d7fb641c1b50f2e0df41c8579'


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

    def test_silver_bytes_and_bootstrap_computation_are_unchanged_by_diagnostics(self):
        raw=SILVER.read_bytes()
        self.assertEqual(1,raw.count(b"option('versionAsOf',"));self.assertNotIn(b"option('snapshot-id',",raw)
        self.assertEqual(OLD_SILVER_SHA,hashlib.sha256(raw.replace(b"option('versionAsOf',",b"option('snapshot-id',")).hexdigest())
        tree=ast.parse(BOOTSTRAP.read_text('utf-8'))
        execute=next(node for node in tree.body if isinstance(node,ast.FunctionDef)and node.name=='execute')
        self.assertEqual(BOOTSTRAP_EXECUTE_AST_SHA,hashlib.sha256(ast.dump(execute,include_attributes=False).encode()).hexdigest())

    def test_runner_still_binds_the_same_new_time_travel_module(self):
        current=hashlib.sha256(SILVER.read_bytes()).hexdigest()
        self.assertEqual(current,run_ci.MODULES['spark_silver.py']);self.assertNotEqual(OLD_SILVER_SHA,current)
        self.assertEqual('71bd63230704c6d880eb1208abc63ef5080448cfd46bf3295f1bc77f38ddd9f7',current)
        raw=Path(run_ci.__file__).read_bytes();self.assertEqual(1,raw.count(current.encode()))


if __name__=='__main__':unittest.main()
