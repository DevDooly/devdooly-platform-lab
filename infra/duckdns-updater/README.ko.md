# 단일 DuckDNS IPv4 갱신기

미배포 후보다. 계정·도메인을 생성하거나 서비스를 설치·실행한 결과가 아니다. 실제 도메인과 토큰은 이 저장소에 기록하지 않는다.

`duckdns_update.py`는 고정 private 파일 `/etc/devdooly-platform-lab/duckdns/domain`과 `token`만 읽는다. 최종 디렉터리 root/0700, 파일 root-owned regular/nlink1/0600이 필요하다. 고정 부모의 소유·쓰기 권한, nofollow fd와 읽기 전후 identity를 검증하고 조건이 맞지 않으면 요청 전에 거부한다. 권한을 자동 수정하지 않는다. `domain`에는 label 하나의 전체 `*.duckdns.org` 이름, `token`에는 계정 토큰을 둔다. 파일 끝 LF 하나만 허용한다.

curl URL은 stdin config로만 전달한다. argv/env/로그에 토큰을 넣지 않으며 curlrc·proxy·CA override·SSLKEYLOGFILE을 상속하지 않는다. 고정 HTTPS API·기본 CA·IPv4·HTTP/1.1·자동 IPv4 감지·요청 한 번만 사용한다. redirect·retry·HTTP fallback·IPv6/TXT/clear 요청은 없다. curl15초, parent20초와 종료 wait2초, stdout128B 상한을 적용한다. curl 8.4 미만의 길이 미상 body 제한 차이는 parent reader로 보완한다. [DuckDNS API](https://www.duckdns.org/spec.jsp), [curl 옵션](https://curl.se/docs/manpage.html#--config)

curl exit0·HTTP200·정확한 OK 응답만 `UPDATE_ACCEPTED`다. 그 외에는 fixed 결과와 exit1이며 원문 응답·예외를 남기지 않는다. timeout은 서버에서 갱신했는지 불명확할 수 있어 즉시 재요청하지 않는다. 접수 성공은 DNS 전파·외부 접속·TLS 인증서 발급 검증이 아니다. 기존 AAAA의 값과 변경 여부는 검사하지 않는다. 계정 토큰의 서버 권한 범위 자체를 이 프로그램이 축소하지는 않는다.

systemd 두 파일은 설치하지 않은 템플릿이다. service의 고정 실행 경로는 `/opt/devdooly-platform-lab/duckdns-updater/duckdns_update.py`이며 Ubuntu의 기존 `/usr/bin/python3`, `/usr/bin/curl`, 기본 CA store 읽기가 필요하다. timer의 `OnActiveSec=5min`과 최근 service 활성 기준 `OnUnitActiveSec=5min`은 OR 조건으로, 유효한 예정 시각 중 먼저 도래한 조건에 jitter·Accuracy 지연을 더한다. 실행 이력이 없는 새 서비스는 timer 활성 5분이 첫 기준이지만, 최근 수동 실행이 있으면 그 활성 기준 다음 5분이 먼저 올 수 있다. 기준 시각이 이미 지난 경우도 실제 manager의 다음 예정 시각을 확인하며, timer를 켠 뒤 항상 최소 5분을 기다린다고 보장하지 않는다. OnBootSec는 쓰지 않는다. 같은 unit의 active oneshot은 겹쳐 시작하지 않으며 module 직접 중복 실행은 지원 절차가 아니다. 다음 정기 회차는 한 요청 내부 재시도와 구분한다. [systemd timer 기준](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)

2026-10-18 Windows에서 `test_duckdns_update.py`의 fake fd/stat/child 기반 4개 검사가 failure0/error0/skip0으로 통과했고 child 종료와 검사 대상 5파일의 전후 동일을 확인했다. 실제 UID·root 권한·curl·DNS·systemd에 의존하지 않는 합성 검증이며, 실제 갱신·배포·DNS 전파를 검증한 결과가 아니다. 검증한 코드·테스트·두 unit은 유지했으며 Linux 검증은 아직 대기 중이다. 설치·파일 공급·토큰 회전·첫 실제 갱신과 DNS 확인은 별도 구축·검증 단계다. 토큰을 명령줄·채팅·공개 Git 파일에 복사하는 설치 예제는 제공하지 않는다.
