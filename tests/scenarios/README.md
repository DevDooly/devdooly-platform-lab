# 합성 데이터 시나리오

[sensor-validation-v1.json](sensor-validation-v1.json)은 seed 42 센서 입력의 기대 결과를 처리 구현과 별도로 정의합니다. 생성기는 `apps/api/.../SyntheticScenario.java`, 판정기는 `SensorProcessor.java`입니다. API 검증 기록에는 이 파일의 12개 판정을 실제 HTTP 응답과 하나씩 비교한 결과가 있습니다.

처음 3건이 정상 처리된 뒤 중복 ID, 잘못된 시간, 센서별 역순 시간, 범위 초과 값을 넣고 나머지 정상 데이터와 중복 ID를 추가합니다. 값의 정상 범위는 0~100이며 마지막 성공 시각만 센서별 watermark를 갱신합니다.

회사 데이터와 실제 수율 알고리즘을 포함하지 않습니다. 공개 실행 API는 아직 제공하지 않습니다.
