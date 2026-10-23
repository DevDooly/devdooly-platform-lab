# 작업 수집기 한 파일의 운영 교체

2026-10-23 **21:18:16(KST)**에 응답 read·close 뒤 완료 시한을 검사하는 작업 수집기 코드 한 파일을 반영했습니다. 실제 완료 시각은 2026-10-23T12:18:16.815632Z입니다. 교체 실행과 별도 읽기 전용 사후 점검에서 새 코드 pin·권한과 보존 항목을 확인했습니다. 이후 **[21:42 자연 회차의 새 job 수집·Pages 게시](NATURAL_PUBLICATION.md)**를 별도로 확인했습니다.

## 코드와 검증 출처

[PR #200](https://github.com/DevDooly/devdooly-platform-lab/pull/200)의 Linux 관측179개가 생략0으로 통과했습니다. 병합 main ae351317ad5932232402c840373641d1f9c70fc3의 [관측 검사39950559544](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39950559544), [Pages39950559628](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39950559628), [컨테이너 검사39950559490](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39950559490)도 성공했습니다. 이 CI·문서 게시 결과는 운영 파일 교체나 그 뒤 새 작업 수집 성공과 구분합니다.

| 항목 | 확인한 결과 |
| --- | --- |
| 고정 소스 | [main ae351317의 job collector](https://github.com/DevDooly/devdooly-platform-lab/blob/ae351317ad5932232402c840373641d1f9c70fc3/infra/observation/job_collector.py) |
| 이전 코드 | 4,086바이트, SHA-256 23c2f544e5d59162e5bcb957426bf89cc2828e275650b01c6715a0ff129c1cda |
| 새 코드 | 4,147바이트, SHA-256 b5c59fc15e3d06af1b7db34b9036e4141800df4e3aa65e29f785b79721e8f120; root 소유·0600·일반 파일·단일 링크 |
| 직렬화·유휴 확인 | 기존 외부 cycle lock의 같은 inode에서 nonblocking 배타 잠금 획득. 알려진 host·platform·job·Kafka·Pages uploader script 인수의 일치 프로세스 수를3회 확인해 모두0 |
| 백업·교체 | 새 root0700 백업 디렉터리와 EXCL0600 이전 코드 사본·temp 생성, fsync·readback 확인. 대상 한 파일의 원자 rename1회 |
| 보존 범위 | 다른 Python 코드7개와 service·timer unit2개의 pin·identity 보존, unit 상태 전후 일치 |
| 실행 결과 | ONE_JOB_COLLECTOR_CODE_REPLACED / VERIFIED, 자동 재시도·자동 원복0 |
| 실행하지 않은 동작 | 설정·state·비밀 파일 쓰기0, 자격증명 읽기0, 외부 API0, 서비스 제어·수동 trigger0 |

교체 도구는 설정과 state 본문을 읽지 않았습니다. 프로세스 인수는 제한된 전체 프로세스 스캔에서 RAM으로만 분류했으며 원문·개별 프로세스 식별자를 출력하거나 저장하지 않았습니다. module 실행·embedded exec·다른 이름의 script까지 찾아냈다는 의미는 아닙니다.

기존 platform writer lock 파일은 계속 존재하는 것이 정상입니다. 삭제·교체·획득하지 않고 root0600·일반 파일·단일 링크와 kernel holder/blocked 각0을3회 확인했습니다. 파일 존재를 stale 오류로 처리하지 않았습니다.

## 별도 읽기 전용 사후 확인

사후 점검에서 새 작업 수집기4,147바이트·SHA·root0600과 다른 코드7개·unit2개의 pin을 다시 확인했습니다. 당시 service는 inactive/dead·success·exit0, timer는 active/waiting·enabled였고 점검 전후 unit snapshot이 같았습니다. 외부 cycle lock은 관측 당시 holder/blocked 각0이었습니다. 이 점검은 잠금을 얻거나 수집을 실행하지 않았습니다.

별도 전후 점검의 선택된 state projection은 같았습니다. platform 마지막 성공은 2026-10-23T12:11:52.567902Z, job 관측은 2026-10-23T12:11:52.658291695Z, Kafka 관측은 2026-10-23T12:11:52.966210066Z였으며 모두 교체 전 기록입니다. platform main 6ed465ea6d6caf352988caad42b44af8f8a073b1과 배포 API 소스245d61a5749760a20918ab091d9410ce6735b1c0도 각각 보존됐습니다. 이는 선택한 시각·상태·출처의 동일성이며 전체 state 본문 바이트 불변이나 새 job 수집 성공의 증명이 아닙니다.

## 배포 후 자연 회차와 Pages 연결

[21:42:49–21:42:53(KST) 자연 회차](NATURAL_PUBLICATION.md)에서 새 job pin과 교체 뒤 전진한 수집 시각·API 출처를 확인했습니다. 같은 invocation의 Pages39955401692 attempt1·head571f0ba3의 build·deploy 성공, 공개 JSON3개와 대응 artifact의 전체 bytes 일치를 연결했습니다. state와 artifact의 platform·job 시각은 nanosecond 단위로 일치하며 service 구간 비교는 보고된 초 정밀도입니다. 수동 trigger·timer 주기 단축은 하지 않았습니다.

job 단계가 실패해도 platform 게시가 성공할 수 있으므로 platform 성공만으로 새 job 성공을 주장하지 않습니다. 위 교체 전 기록이나 PR200의 Pages 성공으로 이 조건을 대신하지 않습니다. [read·close 완료 시한의 오프라인 한계](README.md)를 유지하며 전체 수집 시간의 hard deadline·장기 가용성을 검증한 결과로 확대하지 않습니다. Pages 토큰 교체·별도 K3s/Jenkins 기동 복원·자원 예산 정책·PR #102 보류는 유지합니다.
