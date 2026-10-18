# 같은 Cloud warehouse에서 Trino 정상 재기동

2026-10-18 새 GitHub hosted Linux 환경에서 Trino를 정상 종료한 뒤 새 컨테이너로 한 번 재기동했습니다. 두 lifecycle이 같은 PostgreSQL JDBC catalog와 Garage warehouse를 읽었으며 검증과 정리가 통과했습니다.

- [실제 실행 39131250407](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39131250407)
- [실행 소스 b6f6b5dc](https://github.com/DevDooly/devdooly-platform-lab/tree/b6f6b5dcd929411d797d9508281a8d4049416ca4/infra/cloud-lakehouse-restart)
- [공개 요약 원본](summary.json): SHA-256 `ad534a850648466bf739d54d0b22d8643ccba42204aa4a75e25cbe404c913274`, 2,808 bytes

| 검사 | 실제 결과 |
| --- | --- |
| Trino SELECT | 재기동 전후 각각 10개, 결과와 행 fingerprint 동일 |
| Bronze 시점별 행 | 전후 모두 6 / 12 / 12 |
| Silver | 전후 모두 12행, snapshot 3개·현재 파일 1개 |
| catalog·warehouse | 두 JDBC pointer와 전체 객체 20개의 bytes 동일, 기존 객체 14개 보존 |
| 정상 종료·자원 | 두 차례 TERM 요청 후 실제 exit 143, PostgreSQL·Garage 프로세스와 중지된 Spark state 유지 |
| 정리·시간 | 검증된 자체 컨테이너·initializer 중지, 단일 workload clock 164,141ms / 600초 |

원 소스와 frozen 입력의 전후 동일, 고정 이미지, fresh volume, 재시도 없음도 확인했습니다. 이미지 pull·JAR 검증·build 준비 시간은 workload clock에서 제외되며, 위 시간은 성능 목표나 SLA가 아닙니다. 실제 신호 전달 자체를 직접 관측했다고 주장하지 않습니다.

이번 시험은 새 ephemeral Cloud 환경에서의 정상 종료와 새 Trino 컨테이너 교체입니다. 미니 PC 접속, 기존 Cloud 저장소 복구, 같은 CID의 Docker restart, 호스트 장애·HA·장기 가용성 검증은 포함하지 않습니다. volume 삭제·snapshot 만료·object GC를 수행하지 않았습니다. 이전 시험 기록도 변경하지 않았습니다.

공개 요약에는 합성 데이터의 검사 결과만 포함합니다. 원 command/log, CID·PID, cgroup·volume 이름, credential과 전체 객체 사본은 게시하지 않습니다.
