"""Bounded public-fixture oracle and persisted-batch replay checks; no IO clients."""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

SOURCE_SHA='39ba10d8c47dce790f3ccc9c9134fea593d6de31f1f3a7992ca61d9f554da3b5'
BATCH_ID='sensor-validation-v1-'+SOURCE_SHA[:16]
SOURCE_TABLE='phase6.bronze.synthetic_events'
TARGET_TABLE='phase6.silver.sensor_outcomes'
FIELDS=('input_sequence','event_id','sensor_id','event_time_raw','sensor_value','source_sha256')
OUTPUT_FIELDS=('batch_id',*FIELDS,'status','reason')


def require(value,code):
    if not value:raise ValueError(code)


def source_bytes():
    raw=Path(__file__).with_name('synthetic-v1.ndjson').read_bytes()
    require(len(raw)==1100 and hashlib.sha256(raw).hexdigest()==SOURCE_SHA,'EXACT_PUBLIC_V1_FIXTURE_BYTES')
    return raw


def golden_bronze():
    return [{'input_sequence':i+1,'event_id':v['eventId'],'sensor_id':v['sensorId'],'event_time_raw':v['eventTime'],
        'sensor_value':v['value'],'source_sha256':SOURCE_SHA} for i,v in enumerate(map(json.loads,source_bytes().splitlines()))]


def validate_bronze(rows):
    require(isinstance(rows,list) and rows==golden_bronze(),'ONLY_EXACT_ORDERED_TWELVE_BRONZE_ROWS')


def classify(rows):
    require(isinstance(rows,list) and 0<len(rows)<=12 and all(type(v['input_sequence'])is int for v in rows)
        and [v['input_sequence'] for v in rows]==list(range(1,len(rows)+1)),
        'BOUNDED_ORDERED_INPUT_SEQUENCE_REQUIRED')
    seen=set();latest={};result=[]
    for row in rows:
        require(set(row)==set(FIELDS),'EXACT_PUBLIC_ROW_FIELDS')
        event=row['event_id'];sensor=row['sensor_id'];value=row['sensor_value']
        if not isinstance(event,str) or not event.strip() or not isinstance(sensor,str) or not sensor.strip() \
            or type(value) not in (int,float) or not math.isfinite(value):reason='INVALID_INPUT'
        elif event in seen:reason='DUPLICATE_EVENT_ID'
        else:
            seen.add(event)
            try:
                text=row['event_time_raw'];require(isinstance(text,str) and text.endswith('Z'),'UTC_V1_TIME_REQUIRED')
                stamp=dt.datetime.fromisoformat(text[:-1]+'+00:00')
            except (ValueError,TypeError):reason='INVALID_TIMESTAMP'
            else:
                if value<0 or value>100:reason='OUT_OF_RANGE'
                elif sensor in latest and stamp<latest[sensor]:reason='OUT_OF_ORDER'
                else:reason='ACCEPTED';latest[sensor]=stamp
        status='SUCCESS' if reason=='ACCEPTED' else 'DUPLICATE' if reason=='DUPLICATE_EVENT_ID' else 'FAILED'
        result.append({'batch_id':BATCH_ID,**row,'status':status,'reason':reason})
    return result


def row_sha(rows):
    return hashlib.sha256((json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()).hexdigest()


def validate_silver(rows):
    require(rows==classify(golden_bronze()),'EXACT_PERSISTED_TWELVE_OUTCOMES_REQUIRED')
    return row_sha(rows)


def replay_action(persisted):
    if persisted==[]:return 'MERGE_FIXED_BATCH_ONCE'
    validate_silver(persisted)
    return 'READ_ONLY_IDENTICAL_BATCH_NO_WRITE'
