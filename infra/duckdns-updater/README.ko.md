# 단일 DuckDNS IPv4 갱신기

아래는 구현 당시의 설계와 합성 검증 기록이다. 후속으로 갱신기 배포와 timer 활성화를 마쳤고, [실제 자연 실행 근거](../../docs/evidence/public-read-https/README.md#duckdns-timer의-자연-실행-확인)에서 마지막 trigger에 연결된 `UPDATE_ACCEPTED` 한 회를 확인했다. 모든 주기의 성공·DNS 값 지속 일치·장기간 가용성을 증명한 것은 아니다. DDNS·포트·방화벽·프록시·조회 gateway의 역할은 [현재 운영 안내](../../docs/runbooks/public-read-gateway-chart.md)를 따른다. 실제 도메인과 토큰은 이 저장소에 기록하지 않는다.

`duckdns_update.py`는 고정 private 파일 `/etc/devdooly-platform-lab/duckdns/domain`과 `token`만 읽는다. 최종 디렉터리 root/0700, 파일 root-owned regular/nlink1/0600이 필요하다. 고정 부모의 소유·쓰기 권한, nofollow fd와 읽기 전후 identity를 검증하고 조건이 맞지 않으면 요청 전에 거부한다. 권한을 자동 수정하지 않는다. `domain`에는 label 하나의 전체 `*.duckdns.org` 이름, `token`에는 계정 토큰을 둔다. 파일 끝 LF 하나만 허용한다.

curl URL은 stdin config로만 전달한다. argv/env/로그에 토큰을 넣지 않으며 curlrc·proxy·CA override·SSLKEYLOGFILE을 상속하지 않는다. 고정 HTTPS API·기본 CA·IPv4·HTTP/1.1·자동 IPv4 감지·요청 한 번만 사용한다. redirect·retry·HTTP fallback·IPv6/TXT/clear 요청은 없다. curl15초, parent20초와 종료 wait2초, stdout128B 상한을 적용한다. curl 8.4 미만의 길이 미상 body 제한 차이는 parent reader로 보완한다. [DuckDNS API](https://www.duckdns.org/spec.jsp), [curl 옵션](https://curl.se/docs/manpage.html#--config)

curl exit0·HTTP200·정확한 OK 응답만 `UPDATE_ACCEPTED`다. 그 외에는 fixed 결과와 exit1이며 원문 응답·예외를 남기지 않는다. timeout은 서버에서 갱신했는지 불명확할 수 있어 즉시 재요청하지 않는다. 접수 성공은 DNS 전파·외부 접속·TLS 인증서 발급 검증이 아니다. 기존 AAAA의 값과 변경 여부는 검사하지 않는다. 계정 토큰의 서버 권한 범위 자체를 이 프로그램이 축소하지는 않는다.

[2026-10-21 KST 완료 시한 수정](../../docs/evidence/automation-failure-boundaries/README.md#ddns의-전체-완료-시한)은 정상 wait 반환 뒤에도 부모의20초 기한을 확인합니다. fake 시계19.999초는 성공,20초·20.001초는 결과 불명으로 거부했고, 이미 join한 child를 다시 종료하지 않았습니다. 기존4개와 새1개, 합계5개 합성 검사를 통과했습니다. 이후 [운영 반영](../../docs/evidence/automation-failure-boundaries/DEPLOYED.md)에서 코드 교체와 새 자연 회차 한 번의 요청 수락을 확인했습니다. 운영의 시한 실패 경로·DNS 전파·지속 일치는 별도입니다.

systemd 두 파일은 구현 당시 미설치 템플릿으로 제공했다. 후속 배포 결과는 위 실제 근거를 따른다. service의 고정 실행 경로는 `/opt/devdooly-platform-lab/duckdns-updater/duckdns_update.py`이며 Ubuntu의 기존 `/usr/bin/python3`, `/usr/bin/curl`, 기본 CA store 읽기가 필요하다. timer의 `OnActiveSec=5min`과 최근 service 활성 기준 `OnUnitActiveSec=5min`은 OR 조건으로, 유효한 예정 시각 중 먼저 도래한 조건에 jitter·Accuracy 지연을 더한다. 실행 이력이 없는 새 서비스는 timer 활성 5분이 첫 기준이지만, 최근 수동 실행이 있으면 그 활성 기준 다음 5분이 먼저 올 수 있다. 기준 시각이 이미 지난 경우도 실제 manager의 다음 예정 시각을 확인하며, timer를 켠 뒤 항상 최소 5분을 기다린다고 보장하지 않는다. OnBootSec는 쓰지 않는다. 같은 unit의 active oneshot은 겹쳐 시작하지 않으며 module 직접 중복 실행은 지원 절차가 아니다. 다음 정기 회차는 한 요청 내부 재시도와 구분한다. [systemd timer 기준](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)

2026-10-18 Windows에서 `test_duckdns_update.py`의 fake fd/stat/child 기반 4개 검사가 failure0/error0/skip0으로 통과했고 child 종료와 검사 대상 5파일의 전후 동일을 확인했다. 실제 UID·root 권한·curl·DNS·systemd에 의존하지 않는 합성 검증이며, 이 네 검사가 실제 갱신·배포·DNS 전파를 검증한 것은 아니다. 검증한 코드·테스트·두 unit은 유지했고, 당시 Linux 검증과 설치·파일 공급·첫 실제 갱신·DNS 확인은 후속 단계로 남겼다. 이후 배포·timer 관측·외부 HTTPS 결과는 위 실제 근거와 구분하며 토큰 회전은 여전히 별도 후속이다. 토큰을 명령줄·채팅·공개 Git 파일에 복사하는 설치 예제는 제공하지 않는다.
