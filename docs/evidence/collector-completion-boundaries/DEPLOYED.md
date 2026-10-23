# 관측 collector 한 파일의 운영 교체

2026-10-23 **20:17:53(KST)**에 응답 완료 시한 검사와 OS writer 잠금을 포함한 collector 코드 한 파일을 미니 PC에 반영했습니다. 실제 완료 시각은 `2026-10-23T11:17:53.114686Z`이며, 교체 실행과 별도 읽기 전용 사후 점검을 구분해 확인했습니다. 이후 [20:41 자연 회차의 수집·Pages 게시](NATURAL_PUBLICATION.md)도 별도로 확인했습니다. 아래 교체 직후 기록과 후속 수집 결과를 구분합니다.

## 교체에서 확인한 범위

| 항목 | 확인한 결과 |
| --- | --- |
| 고정 소스 | [`cb1df8656220a48dd1a61cedf73bcc097cf4e549`의 collector](https://github.com/DevDooly/devdooly-platform-lab/blob/cb1df8656220a48dd1a61cedf73bcc097cf4e549/infra/observation/platform_collector.py) |
| 새 코드 | 20,725바이트, SHA-256 `d87742d75e046a292615e078b279e01d22243c8d2b5d95f39258cd91945c05cf` |
| 직렬화 | 기존 외부 cycle lock의 같은 inode에서 nonblocking 배타 잠금 획득. 전후 알려진 host·collector 직접 실행 수 0, 이전 child lock 부재 확인 |
| 백업·교체 | 새 root 전용 0700 백업 디렉터리·0600 이전 코드 사본과 새 임시 파일을 각각 exclusive 생성·검증. 원자 rename 1회·fsync·새 코드 readback 확인 |
| 코드 보존 | 계약 파일과 service·timer 두 unit의 pin·identity 보존 |
| 상태 보존 | 교체 중 조회한 service·timer 상태가 전후 일치 |
| 실행 결과 | `ONE_COLLECTOR_CODE_REPLACED / VERIFIED`, 자동 재시도·자동 원복 없음 |
| 사용하지 않은 동작 | credential 파일 읽기 0, 설정·state·비밀 파일 쓰기 0, 외부 API 요청 0, 서비스 제어·수동 trigger 0 |

기존 O_EXCL 수집기는 새 OS 잠금과 상호 배제되지 않으므로, 유휴 상태와 외부 cycle lock을 먼저 확인하고 교체했습니다. 경합 확인 과정의 프로세스 인수는 서버 RAM에서 역할을 대조하는 데만 사용했고 원문을 출력하거나 저장하지 않았습니다. backup·temp의 공개 코드 내용 외에 토큰·개인키·설정 본문·관리 응답·프로세스 인수 원문을 공개하지 않습니다.

## 별도 읽기 전용 사후 확인

교체 후 collector의 새 pin·20,725바이트와 root 소유·0600·regular file·단일 링크를 다시 확인했습니다. service·timer 파일 pin도 유지됐고 당시 service는 inactive/dead, timer는 active/waiting·enabled였습니다. cycle lock은 관측 당시 미점유였으며 이전 child lock은 없었습니다. 이 점검은 새 잠금을 얻거나 수집을 실행하지 않았습니다.

당시 상태 JSON은 기존 계약으로 검증한 뒤 제한된 projection만 전후 대조했습니다. 선택한 `latestAttempt`의 완료 시각·상태·오류 코드와 `lastSuccess`의 수집 시각·main 소스·배포 소스 값이 같았습니다. 기존 기록은 `2026-10-23T11:10:05.156905Z`의 성공으로, **교체 전에 수집한 값**입니다. 이 선택된 필드의 동일성은 전체 상태 JSON의 바이트 동일성이나 내부 모든 값의 불변을 보장하지 않습니다. 이 교체 직후 점검만으로 새 수집 성공을 증명하지 않으며, 실제 후속 성공은 아래 별도 근거를 따릅니다.

## 후속 자연 회차 확인 완료

예상했던 다음 기존 자연 회차는 실제로 2026-10-23 **20:41:12(KST)**에 시작해 20:41:17에 완료했습니다. timer 주기를 줄이거나 수동으로 cycle을 호출하지 않았습니다. [자연 게시 근거](NATURAL_PUBLICATION.md)와 [공개 요약](summary.json)에서 다음 항목을 연결했습니다.

1. 교체 뒤 service 시작과 timer의 보고 시각 상관관계, 새 collector pin 유지를 확인했습니다.
2. 새 platform 수집 완료 `11:41:15.086039 UTC`와 서버에서 선택해 읽은 시각·main/API 소스를 해당 artifact에 대조했습니다.
3. 같은 invocation의 Pages39947822996·attempt1, build·deploy 성공과 공개 JSON3개의 전체 bytes 일치를 확인했습니다.

timer가 유일한 시작 원인이었다는 증명이나 초보다 세밀한 실제 인과관계의 확인은 아닙니다. 운영 SIGKILL 복구·서비스 재시작·장기 가용성·전체 처리 시간의 hard deadline을 검증했다고 주장하지 않습니다. 응답 완료 시한과 OS 잠금의 실제 격리 Linux 시험은 [별도 오프라인 근거](README.md)를 따릅니다. Pages 토큰 교체·별도 환경의 K3s/Jenkins 기동 복원·자원 예산 정책·PR #102 보류는 유지합니다.
