# Kafka 관측: 로컬 검증과 남은 연결

아래는 2026-10-18 로컬 검증 당시의 기록이다. 후속 [격리 CI7](CI_ATTEMPT_7.md)은 고정 IT1·skip0·source 불변·자기 자원 정리를 통과했다. 이 결과를 아래 합성/로컬 검사와 합치지 않으며 미니 PC 배포·공개 Pages의 Kafka 기록 연결은 아직 검증하지 않았다. 기존 worker의 과거 Kafka 처리·lag 기록과도 구분한다.

선택한 소스 묶음은 backend `d30e3713…`, web `0718624a…`, host `cbdbf149…`이다. 결합 웹/host 검증은 checkout `a234d405`를 기준으로 한 C overlay에서 수행했다. 이후 checkout `5862ba0c`의 Java stdout 개선·별도 Cloud capture와 범위를 구분한다. Kafka 후보를 그 checkout의 실행 코드 또는 배포 소스로 표시하지 않는다. [고정 계약](../../contracts/kafka-observation.md)은 원래52e6076e 본문을 그대로 보존하며, 그 계약 문서의 준비 당시 상태와 아래 실제 로컬 결과를 구분한다.

## 확인한 범위

| 별도 실행 | 결과 | 의미와 한계 |
| --- | --- | --- |
| 이전 Service 검사 | 19/19, 실패·오류·skip0 | 같은 Service 소스의 합성 Admin/clock/close 검사. 실제 broker 연결 아님 |
| 새 HTTP 정책 검사 | 6/6, 실패·오류·skip0 | 모의 관측 service를 쓰는 로컬 HTTP 경계. 이전19와 단일25개 실행으로 합치지 않음 |
| 이전 기본 Helm | 정책17개·schema 거부6개 | 새 runtime 검사와 다른 실행이며 반복 실행하지 않음 |
| 새 runtime Helm | 정책30개·기존 schema 거부13개·Kafka 거부10개 | 선언/render 검증이며 실제 Kubernetes 적용 아님 |
| 수정된 웹 전체 회귀 | 104/104, 실패·skip0 | 기존89+Kafka14+stdout profile1. 공개 broker 값은 만들지 않음 |
| Astro 타입·정적 빌드 | 28파일·오류/경고/hint0, build 성공 | 실제8 capture 원문1791bytes/e96ca40d 보존. Kafka 관측 asset은 없음 |
| host/Pages 합성 계약 | 48개 중46통과·POSIX 전용2개 제외 | Kafka21+job27. Node24.19.0의 실제 frontend parser interop 실행. Linux signal guard는 미검증 |
| 입력·dependency 보존 | 13,013개 원본/복사 dependency의 전후 hash 동일 | 수정된 네 실제 결과와 전체 after-check를 연결. 원본 module을 runtime 링크로 사용하지 않음 |

Java21.0.9·Maven3.10.0·Node24.19.0·Helm4.3.0의 고정 로컬 도구를 사용했다. [공개 요약 JSON](local-validation.summary.json)에 source/tool/result hash와 count·scope만 둔다. 원문 로그·로컬 경로·접속 주소·credential은 포함하지 않는다. CPU·메모리·처리량·SLA·실제 Kafka ACL 검증은 이 결과에 없다.

## 실패 기록도 유지

첫 API 실행에서 Service19는 통과했지만 HTTP6은 통과2·실패1·오류3으로 실패했다. HTTP 시험 fixture를 보정한 뒤 새 HTTP6을 별도로 실행했으며 생산 Service 소스를 고친 성과로 바꾸지 않는다. 첫 runtime Helm 역시 음성검사 인자 구성 문제로 exit1이었다. 시험 인자를 보정한 새 runtime 검증만30개 통과로 기록하며, 기존 기본17개와 단일47개 성공으로 합치지 않는다.

첫 결합 웹 실행은93 tests/91 pass/2 file failures/skip0이었다. 기존 api/observation 시험이 읽는 공개 scenario fixture가 overlay에서 빠져 있었고, tracked fixture1763bytes/b04b8ba9를 그대로 더한 뒤 전체104개를 새 실행에서 검증했다. Smoke를 포함한 소비 경로3개와 고정 file-URL·상대 import를 정적으로 확인했으며 다른 누락은 없었다. 이전 실패를 지우거나 최초 실행부터 통과한 것으로 표시하지 않는다.

## 실제로 본 화면

로컬의 **미연결 상태**만 확인했다. Desktop1265px·mobile375px에서 clientWidth와 scrollWidth가 같았고 keyboard refresh 접근을 확인했다. 성공 offset·lag·수집 시각이 보이는 운영 화면 검증은 아니다. 화면은 미관측 값을0이나 성공으로 채우지 않는다.

![로컬 Kafka 관측 미연결 카드 — desktop](screenshots/desktop.jpg)

![로컬 Kafka 관측 미연결 카드 — mobile](screenshots/mobile.jpg)

다음은 [단계별 연결 절차](../../runbooks/kafka-observation-rollout.md)에 따라 새 격리 broker 시험 → 검토한 API 배포 → host 수집 → 실제 Pages 기록 순서로 근거를 추가하는 것이다. 현재 결과를 그 후속 단계의 성공으로 확대하지 않는다.
