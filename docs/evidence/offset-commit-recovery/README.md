# 실제 offset commit 실패와 명시적 재개: 격리 시험 PASS

2026-10-20 12:44:26 UTC에 완료한 [여섯 번째 실행39424186853](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39424186853)이 통과했습니다. 실제 DB commit 뒤 Kafka를 일시 정지해 commit 실패와 영속 pause를 확인했고, 명시적 resume 후 완료 메시지 재전달·export·슬롯 해제까지 검증했습니다. 앞선 실패5건도 아래에 별도로 보존합니다.

실제 summary를 [단계별 카드](https://devdooly.github.io/devdooly-platform-lab/#offset-commit-recovery)에 공개했고 로컬·공개 화면 검증을 아래 범위로 완료했습니다.

## 공개 게시와 확인

[PR135](https://github.com/DevDooly/devdooly-platform-lab/pull/135)의 main `ed3f333f199c4639a2df1cfafcce58abd629cfe4`에서 [Pages39426442950](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39426442950)과 [main CI39426442955](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39426442955)가 통과했습니다. 이미지 게시와 운영 배포는 이 화면 확인의 근거로 사용하지 않습니다.

2026-10-20 13:01–13:02 UTC의 공개 페이지에서 1280×1000·390×844의 실제 결과, 기본 닫힘 상세 영역과 상태 표, 2단계 선택·End로4단계·모바일 방향키로2단계 이동을 확인했습니다. source·manifest·XML과 실행 링크는 위 실제 실행에 일치했습니다. 문서 폭은1265·375px로 viewport를 넘지 않았고 모바일 표는301px 영역 안에서463px로 스크롤됐습니다. 저장 기록의 UI 검증이며 운영 API·자료에 실행 명령을 보내지 않았습니다.

## 화면 연결과 로컬 확인

2026-10-20 12:51–12:54 UTC에 1280×1000·390×844 화면에서 네 단계 선택, Home·End·방향키 이동, 기본 닫힘 상세 영역과 업무/실행기 상태 표를 확인했습니다. 모바일 버튼은2열이고 본문은17px입니다. 문서 폭은 각각1265·375px로 viewport를 넘지 않았으며, 모바일의 넓은 표는 내부 영역만301→463px로 스크롤됩니다.

웹 전체148개 검사, 마지막 문구·실제 Card 렌더 변경에 해당하는12개 검사, Astro39파일의 오류/경고/힌트0과 최종 정적 빌드를 확인했습니다. 공개 카드는 실제 실행·소스·manifest·완료 시각·XML에 고정되며 합성 fixture나 실패·부분 기록을 성공 화면으로 표시하지 않습니다. 로컬 확인은 새 카드의 저장 기록과 화면 동작 범위입니다.

## 통과 결과와 source binding

| 근거 | 실제 값 |
| --- | --- |
| 실행 | [39424186853](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39424186853), run/trial `success` |
| 완료 시각 | `2026-10-20T12:44:26Z` |
| source | [0d49ab99bd1caccf8109642758f2ea8367dbb504](https://github.com/DevDooly/devdooly-platform-lab/commit/0d49ab99bd1caccf8109642758f2ea8367dbb504) |
| runtime manifest SHA-256 | `c2457176d92d7892c1bc5d5c4e7f83a471b105de6a08898bb35b837f6ce2a551` |
| 원본 [summary.json](summary.json) SHA-256 | `b28349129318582cdd4ac9117fcfc5b072179f6f129e0c287158bf2a401158c8` |
| 검증한 Surefire XML SHA-256 | `6b102c50d3d87dd104ec797ab95c3b9d77dda2b7b9e0a922c0e22003de43f273` |

[run-metadata.json](run-metadata.json)은 같은 실행 URL·source·완료 시각·summary 지문에 묶여 있습니다. 원본 summary는18개 필드, 그 안의 `recoveryResult`는23개 필드입니다. 정확한 IT1개가 검증됐고 `status=PASSED`, `verifiedTests=1`, 실패 진단은 null입니다.

| 확인한 경계 | 실제 관측 |
| --- | --- |
| DB 처리 | 입력12: 성공7·실패3·중복2·pending0. 실제 DB commit이 fault보다 먼저 완료됨. |
| commit 실패와 지속 pause | `PAUSED_OPERATOR / CONSUME / OFFSET_COMMIT_FAILED` 지속. 일반 run 재시작은 journal·업무 상태를 바꾸지 못하고 거부됨. |
| 명시적 재개 | operator resume 기록 후 새 정상 실행기가 회복함. |
| unpause 직후 첫 offset | `NO_COMMIT / null`. timeout 결과를 offset reset으로 만들지 않고 실제 조회함. |
| 재전달 | 실제 완료 메시지 replay1회. 업무 행·처리 시각은 보존됨. |
| export와 슬롯 | 결과/실패 파일2개의 전체 bytes·크기·SHA 검증, EXPORTED, 슬롯 해제. |
| 최종 Kafka | READ_COMMITTED end1·committed1·lag0. |
| 종료·근거 보존 | child/client 닫힘, source/artifact/tool/staging 불변, 소유 자원 정리 확인. |

`NO_COMMIT/null`은 이번 실행의 첫 실제 조회값입니다. broker pause가 커널 TCP buffer를 비우지는 않으므로 늦은 commit이 가능한 다른 실행에서는1이 관측될 수도 있습니다. timeout만으로 broker 미처리나 재전달 횟수를 추정하지 않았습니다.

## 앞선 실패5건

| 순서·실행 | 완료 시각(UTC, 2026-10-20) | 확인한 실패와 다음 조정 |
| --- | --- | --- |
| [1: 39417413600](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39417413600) | 11:49:08 | `POST_DB_WAIT`에서 첫 checkpoint 전 JVM 종료. Java 세부 원인이 없어 유한 JVM/JUnit 진단을 추가함. |
| [2: 39418943100](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39418943100) | 12:02:00 | 실제 exit1·OOM false, JUnit failure1/error0, `KAFKA_CREATE`. 원 예외의 kind와 source line을 보존하는 진단을 추가함. |
| [3: 39420607863](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39420607863) | 12:15:28 | `KAFKA_CREATE / TIMEOUT`, 원 IT446줄의 첫 `listConsumerGroupOffsets`10초 대기. 초기 조회 한 곳에만45초의 제한된 준비 관측을 추가함. |
| [4: 39421773890](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39421773890) | 12:25:04 | 초기 조회 준비를 통과한 뒤 `STAGE_INPUT / OTHER`, 원 IT187줄의 테스트용 admission reset helper 호출에서 실패. 정확한 helper 내부 원인은 미확정. 새 schema의 불필요한 reset을 V4 기본 policy의 읽기 전용 확인으로 바꿈. |
| [5: 39422876573](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39422876573) | 12:31:52 | `PREPARATION_OR_INPUT_UNVERIFIED`, base187줄. 자원 생성·workload 전에 실패해 runtime 단계는 SKIPPED, 결과 artifact 없음. 정확한 Maven 실패 원인은 미확정이며 준비 stage·exit·고정 signature 진단을 추가함. |

1~4의 원본은 [attempt-1-summary.json](attempt-1-summary.json), [attempt-2-summary.json](attempt-2-summary.json), [attempt-3-summary.json](attempt-3-summary.json), [attempt-4-summary.json](attempt-4-summary.json)에 보존합니다. 모두 `FAILED`, `verifiedTests=0`, XML 지문 null, 소유 자원 정리 true입니다. `sourceAndArtifactsUnchanged=false`는 최종 불변 확인 미완료인 **UNVERIFIED**이며 그 자체가 변조 증거는 아닙니다.

5는 runtime 결과가 없으므로 summary나 XML을 만들어 보충하지 않습니다. 알려진 유한 준비 진단만 [attempt-5-preparation.json](attempt-5-preparation.json)에 보존합니다.

| 기록 | source | manifest SHA-256 |
| --- | --- | --- |
| 1 | `721e2f5158602a726cf10860885b77a55f08098b` | `4ca6fe3799132bab231b5d20cf1d5c3d5804df4f8b3aab28ddd4c39110530d38` |
| 2 | `20e36d045c1663380051908f121db7bfa99e903b` | `9cd9c6d43c11c0cf7e6e682ffcd5c34402485154eb92ffde0b3532484e9ceeb0` |
| 3 | `9786f47300d0fdcdea4d030537b84177eefd2ca7` | `f8426b938edfd833d8cfdea160f5afa36d27aee08730363e4091f873ec6c38ec` |
| 4 | `3c6566b0e8110e196c1f2a2d9d6215578fc2c903` | `02189145ccf86d83c7f88207e4d461b45312b4e5427cdcd66487a0d7c11c09b8` |
| 5 | `4d874926e45578df6eb766a1efde03d0f6747e45` | source workflow에 설정된 `d73472d374f61585486daf58d141fc4d3a51c6a579d61cd47a44aa8c51be37d0`; runtime artifact는 없음 |

원본 파일 지문은 다음과 같습니다. 진단을 개선한 다음 시도의 결과로 실패 기록을 덮어쓰지 않습니다.

```text
attempt-1-summary.json      8c4fdcc67503a8520e58a4c247592451040ee71a0ea223555f5e4c537981301b
attempt-2-summary.json      11d4c5b7e40a01b605479fdfc3987c6fc8ac625463fb72fb1ac89631aea2c6bc
attempt-3-summary.json      567ce35df7f1835512d8e323434869016ae4cfba897140cdffd39e7f17069a47
attempt-4-summary.json      c5d968a92405fdc7320a4d144b003bcec5170903d5c7e31ed9c50d297903ae16
attempt-5-preparation.json  7af1b56db1f92e97bda7ee4719ec601514e4fc40d3f06a81d55b2ea7d07f82f9
```

## 검증 범위

초기 group 조회의 timeout은 실제로 관측했지만 broker 내부 지연 원인까지 확정하지 않았습니다. 네 번째 reset helper와 다섯 번째 Maven 준비 실패도 외부 서비스·driver 문제를 근본 원인으로 단정하지 않습니다. 여섯 번째 통과는 검토한 새 source의 한 실행 결과이며 과거 실패의 원인을 소급해 입증하지 않습니다.

시험은 새 컨테이너4개·internal network·전용 DB/S3/Kafka fixture에서 수행한 합성 사례입니다. summary의 `operatingServicesChanged=false`, `hostOrBrokerRestartVerified=false`, `publicExecutionEnabled=false`를 유지합니다. 이 결과가 운영 현재 상태·물리 host/broker 재시작 복구·다중 broker HA·SLA·모든 장애에서의 exactly-once를 증명하지는 않습니다. 공개 근거에는 유한 집계·고정 enum·검증 bool·source/XML 지문만 남기며 raw 로그·SQL·credential·실제 resource ID는 포함하지 않습니다.
