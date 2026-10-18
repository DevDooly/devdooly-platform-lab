# 공개 조회 gateway 첫 격리 CI 실패

2026-10-18 UTC의 [실행 39108149207](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39108149207)은 소스 `d25caa07178c378f5a9964ca628aa638959455c9`를 사용했다. `public-read-gateway` job의 검증 단계는 07:34:07~07:34:26에 실패했다. 기존 전체 `verify` job과는 별도 결과다.

[원본 공개 요약](attempt-1-summary.json)은 375 bytes이며 `passed=false`, `phase=CLEANUP`, `ownedResourcesRemoved=false`를 기록한다. 원본 bytes를 변경하지 않았다.

이 요약에는 최초 workload 구간과 HTTP 검사 수가 없다. 원래 실패 원인, HTTP 검사의 통과 여부와 실제 자원 정리 완료는 미확인이다. `ownedResourcesRemoved=false`만으로 자원이 남아 있었다고 단정하지 않는다. 미니 PC 접촉·외부 공개·host port 게시·DB/Kafka·Spark/JVM 시작은 모두 false다.

후속 소스 검토에서 Docker container/network `ls --filter` 두 곳의 `label=` 누락을 별도 결함으로 확인했다. 삭제 후 부재 확인에도 해당 경로가 사용되므로 정리 검증을 실패시킬 수 있다. 이것이 최초 workload 실패 원인이었다고 소급하지 않는다.

비루트·read-only Nginx 구동에서 fastcgi/uwsgi/scgi의 기본 임시 경로가 쓰기 불가일 정적 위험도 확인해 기존 `/tmp` tmpfs 아래 세 경로를 명시했다. 정확한 고정 이미지 바이너리의 `-V`나 첫 실행의 구체적인 오류를 확인한 결과는 아니다.

후속 후보는 원래 workload phase, 유한한 검사 checkpoint·HTTP probe 결과와 자원별 정리 상태를 보존한다. 새 소스로 별도 CI를 검증하며 이 실패를 성공 결과로 바꾸거나 같은 실행을 재시도하지 않는다. 격리 CI 결과는 실제 미니 PC·외부 TLS·공개 API 검증과 구분한다.
