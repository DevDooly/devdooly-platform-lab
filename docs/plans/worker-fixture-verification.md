# 새 worker의 고정 입력 한 건 검증 계획

상태: **준비 단계 · 신규 작업 실행 전**. worker의 [이미지 교체](../evidence/worker-image-rollout/README.md)와 기존 자료 보존·새 실행·heartbeat는 확인했습니다. 다음은 배포된 새 worker가 새 합성 입력의 Kafka 수신·DB 처리·두 export까지 수행하는지 확인하는 것입니다. 이전 worker의 실측과 Linux 코드 검증은 새 운영 실행의 근거와 구분합니다.

고정 V1·seed42의 입력12개를 한 번 등록하고 기대 결과 `입력12 / 성공7 / 실패3 / 중복2 / 대기0`을 대조합니다. 임시 stage Job은 입력 등록만 수행하고, 현재 상시 worker가 처리하도록 합니다. 새 작업·DB 행·raw 객체1개·export 객체2개·Kafka 발행이 생기는 범위이며 기존 보존 읽기와 다릅니다.

실행 전에는 같은 worker의 image·source·현재 소유·Ready·fresh heartbeat, schema와 빈 슬롯·pending outbox 부재·cooldown·새 식별자 부재를 확인합니다. 실제 Secret 참조와 NetworkPolicy, stage Pod label이 기존 worker 조회와 충돌하는지도 대조해야 합니다. 확인되지 않은 조건을 재시작·강제 잠금 해제·정책 변경으로 보정하지 않습니다.

완료 조건은 새 작업의 COMPLETED·EXPORTED, 두 outbox ACK·빈 슬롯, 새 raw·두 export의 전체 GET 및 DB 기반 기대 결과 일치, 실제 Kafka 좌표·lag, 기존 작업·파일 보존입니다. 등록 응답이 불명확하면 같은 Job·작업부터 확인하며 새 ID로 자동 재시도하지 않습니다. 업무 자료는 검증 근거로 보존하고, 임시 Job 정리는 정확한 소유 UID를 확인한 범위만 다룹니다.

현재 manifest·절차 후보는 검토 준비 상태이며 이 계획만으로 작업을 실행했다고 표시하지 않습니다. 새 토큰·별도 VM은 필요하지 않으며 기동 복원·토큰 교체·예산 정책·PR102 보류는 유지합니다.
