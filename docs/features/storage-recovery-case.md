# MariaDB·Garage S3 저장·검증·복구 대표 사례

## 목적과 흐름

[대표 사례](https://devdooly.github.io/devdooly-platform-lab/cases/storage-recovery/)는 취업·이직 포트폴리오에서 DB 처리 완료와 S3 파일 저장 확인의 차이, 재개할 때 남은 상태를 설명합니다. 기술 선택 → 짧은 DB 트랜잭션과 외부 GET/PUT → 결과/실패 문서 → 오류·중단 세 경계 → 손상 발견/재중지/명시 수리 → 실제 캡처 → 설정·이식 → 근거 순서입니다. 기술 목차·저장소 기술 안내·README에서 진입합니다.

## 원 근거와 구현

- 정적 Astro와 native details를 사용하며 관리 API·credential 입력·삭제·복구 실행 기능을 추가하지 않습니다.
- 2026-10-15 KST의 `docs/evidence/result-export/summary.json`에서 정상 문서 크기/hash와 세 사례의 최종 run/outcome·확인 문서·kill·완료 상태를 직접 읽습니다. 원래 6 IT 중 선택한 세 사례이며 전체 Windows child kill2회와 선택 사례1회를 구분합니다. Docker build에는 해당 공개 summary만 추가 COPY합니다.
- 2026-10-20 13:16:39 UTC의 Linux 손상 수리는 기존 generated record·검증 parser·단계 모델을 재사용합니다. 원 source0f5c4bc2/run39428536206·IT1개와 네 관측 단계를 구분합니다. 직접 DB fixture→손상→pause→resume/재pause→소유 fixture 삭제·별도resume/새daemon→검증/ACK/슬롯 해제와 마지막 consumer replay를 분리합니다.
- 코드·설정 설명은 source `a652293e70cae4fbbf4f584c16f313c6941a5a05` 기준입니다. 과거 ADR/runbook의 당시 미배포·고정12개 범위를 현재 runtime 전체 범위로 바꾸지 않습니다. 원 증거·실패를 수정하지 않습니다.
- 캡처는 기존 2026-10-26 KST의 공개 export 관측 화면을 사용하고 원 Linux 시험 시각·관리 UI와의 차이를 표시합니다.
- 설정과 새 환경 이식은 기존 계약의 endpoint·bucket/region·권한/Secret·SDK·DB/schema·영속 경로·실제 bootstrap 순서를 설명합니다. DB와 S3의 원자적 commit·ETag=SHA·자동충돌수리·완료파일 자동감시·HA/재해복구를 주장하지 않습니다.

## 검증 상태

로컬 Astro107파일 진단0·Pages base의 19페이지 빌드, 진입 3페이지173링크/앵커·원 hash/사례/실행시각 연결을 확인했습니다. 실제 브라우저에서 세 대표 사례 목차→새 페이지, 저장소 기술 안내 왕복, Space/Enter의 세 경계·SHA 펼침, 네 단계의 업무/실행기·파일/슬롯 상태, 설정6그룹·이식5단계와 캡처 로딩을 확인했습니다. 페이지 script0·390px에서 문서375px/본문17px·가로넘침0이며 console 오류·경고는 없습니다.

정적 구현 검토에서 필수 수정은 없었습니다. 다른 채팅의 사실·이식 계약 검토와 frozen head의 최종 확인을 거쳐 병합하며, 같은 main CI/Pages·실제 공개 결과는 해당 PR 완료 기록을 따릅니다. 이 페이지는 새 환경 기동이나 실제 운영 복구 시험이 아닙니다.

Pages 토큰 교체·별도 환경 K3s/Jenkins 기동 복원·예산 정책·PR #102는 계속 보류합니다. 운영 image/source pin·기존 서비스/데이터·자동 이미지 제안 PR·다른 PAUSED 자동화는 유지합니다.
