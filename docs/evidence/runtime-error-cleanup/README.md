# 실행 중 Error와 자원 종료 회귀 검증

2026-10-21 KST, Windows Java21.0.9·Maven3.10.0의 기존 로컬 캐시와 H2 메모리 DB로 검증했습니다. 외부 Kafka·Garage·미니 PC나 새 VM을 사용하지 않았습니다.

## 수정 전 실제 재현

기존 main의 실행 코드에 새 회귀 검사 3개를 적용해 모두 실패하는 것을 확인했습니다.

| 주입한 합성 오류 | 기존 결과 | 기대 동작 |
| --- | --- | --- |
| export 작업의 `AssertionError` | DB가 `STOPPED / STOPPED / null`로 기록됨 | 고정 `RUNTIME_FAILED`로 pause를 시도하고 원 Error 전파 |
| 첫 client 종료의 `AssertionError` | journal이 `RUNNING / IDLE / null`에 남음 | 종료 실패 pause를 시도하고 lease까지 정리 |
| 첫 client 종료 실패 뒤 남은 client | 첫 consumer만 종료 시도됨 | producer·object store까지 순서대로 종료 시도 |

이 오류들은 의도적으로 만든 `AssertionError`입니다. 실제 메모리 부족이나 프로세스 장애를 재현한 결과가 아닙니다.

## 바뀐 동작

실행기가 이미 알고 있는 첫 Error를 정상 종료로 덮지 않습니다. 소유권과 DB 쓰기가 가능하면 한 번의 최선 노력으로 `PAUSED_OPERATOR / RUNTIME_FAILED`를 기록합니다. 자원 종료에서 처음 발생한 오류는 `RESOURCE_CLOSE_FAILED`를 사용합니다. 이미 저장한 업무 실패 사유는 후속 종료 오류로 바꾸지 않습니다.

나머지 client와 lease 종료를 각각 시도한 뒤 첫 Error 객체를 그대로 다시 던집니다. 후속 진단 원문을 journal·cause·suppressed에 추가하지 않으며, 일반 Exception의 고정 메시지도 유지합니다. journal 쓰기가 실패하면 재시도하거나 `STOPPED`를 꾸미지 않고 이전 DB 상태를 남깁니다. 마지막 정상 stop이 성공한 뒤 read·lease close에서 처음 발생한 Error는 이미 기록된 stop을 소급 변경하지 않고 전파합니다.

## 수정 후 확인

- 실행기20개·자원 종료6개, 합계26개 모두 통과·skip0. 기존11개에 의미 있는 회귀15개를 추가했습니다.
- action·진행 신호·journal·client·lease의 오류 조합에서 첫 Error identity, 후속 I/O 차단, pause 1회, 남은 자원 종료, 진단 원문 미첨부를 확인했습니다.
- fresh source 폴더에서 production45개·test47개를 실제 재컴파일하고 `mvn -o -B -ntp verify` 성공: 전체233개 중222개 실행 통과·실패0·오류0·조건부 생략11개, jar 재패키징 성공.
- 생략11개는 기존 Linux 전용 `LocalRuntimeProgressTest`9개와 `RuntimeReadyProbeTest`2개입니다. Windows에서 Linux 파일 권한·소유자 검증까지 통과했다고 주장하지 않습니다.

처음 수정 후 검증에서는 복사 시각 때문에 Maven이 재컴파일을 생략한 것을 확인해 중단했습니다. 기존 실패 보고서를 보존한 뒤 빌드 결과가 없는 새 소스 폴더에서 위 검증을 완료했습니다. 이 결과는 위 두 테스트 파일과 같은 고정 소스의 로컬 회귀 근거입니다. 운영 배포·실제 JVM 치명적 장애 복구·HA·archive 기동 복원은 검증 범위가 아닙니다.

## Linux CI 확인

PR159의 main `12197d5a72b50a8e56feddb50ce09d9e31bf9f14`에서 [컨테이너CI39468011021](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39468011021)의 API233개가 모두 통과·skip0이며 verify·공개 조회 gateway job도 성공했습니다. 이미지 workflow39468369830은 gate만 성공하고 publish·GitOps 제안은 생략됐습니다. 새 이미지 게시나 미니 PC 배포 결과로 해석하지 않습니다.
