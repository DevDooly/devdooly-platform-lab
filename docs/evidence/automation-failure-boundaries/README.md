# 관측 진단 실패와 DDNS 완료 시한

2026-10-21 KST, 기존 Python·합성 파일·fake runner/child로 검증했습니다. 새 토큰·별도 VM·SSH·실제 게시·curl·DNS 요청을 사용하지 않았습니다. 저장소 코드의 수정과 현재 미니 PC에 설치된 코드의 반영은 구분합니다.

## 선택적 진단 파일 실패의 격리

`host_cycle.py`는 작업 수집이 실패해도 유효한 플랫폼 관측을 게시하고 이전 작업 기록을 보존하는 계약입니다. 하지만 선택적 `jobs-capture.json` 쓰기가 실패하면 uploader 호출 전에 예외가 전파됐습니다. Kafka 진단과 동일하게 이 파일의 쓰기만 best effort로 처리했습니다. 플랫폼·작업 snapshot의 검증, 필수 dispatch intent와 최종 state 저장은 그대로 유지합니다.

기존 production과 새 검사3개를 조합한 첫 실행에서는 정상 작업 수집과 작업 timeout의 두 경우가 진단 쓰기 OSError로 실패했고, 필수 intent 쓰기 실패를 검사한 음성 사례는 통과했습니다. 수정 뒤 세 경우 모두 통과했습니다.

1. 작업 수집 성공·진단 저장 실패: 유효한 플랫폼과 작업 입력을 fake uploader에 한 번 전달하고 원 작업 파일 bytes를 보존했습니다.
2. 작업 timeout·진단 저장 실패: 플랫폼 입력만 fake uploader에 한 번 전달하고 이전 작업 파일 bytes를 보존했습니다.
3. 필수 dispatch intent 저장 실패: 원 오류가 전파되고 fake sender 호출은0회였습니다. 전송 전에 intent를 저장해야 하는 경계를 완화하지 않았습니다.

세 경우 모두 시험용 임시 SA token 파일 정리를 확인했습니다. 두 진단 저장 실패 사례에서는 진단 원문의 공개 보고·stdout/stderr 비노출도 확인했습니다. 합성 성공 보고는 실제 GitHub 전송 성공을 뜻하지 않습니다. 선택적 진단이 저장되지 않으면 그 회차의 private 진단 자체는 남지 않을 수 있으며, 이를 성공 기록으로 대체하지 않습니다.

## 나노초 검사의 시계 의존성

첫 전체 실행160개에서는 위 새 검사3개가 통과했지만 기존 나노초 검사가 `SNAPSHOT_INVALID`로 실패했습니다. 당시 원문에 수집 시각과 검증 상한의 실제 두 값은 없어 실패 순간의 원인을 수치로 확정하지 않습니다.

기존 fixture는 실제 microsecond 시각 뒤에298ns를 덧붙였습니다. 검증 시계가 같은 microsecond를 반환하면 그 시각은 상한보다 미래가 됩니다. 이 소스상 반례에 대응해 해당 검사만 시작04Z·고정 수집04.845617298Z·후속 상한05Z를 사용하도록 바꿨습니다. 9자리 원문 보존·기존 parser 거부와 미래1ns 음성 검사는 유지하며 production의 시간 계약을 느슨하게 바꾸지 않았습니다.

이 검사 변경 뒤 전체160개 중156개 통과·실패0·오류0·기존 Windows 생략4개를 확인했습니다. 생략은 POSIX alarm2개·credential 권한1개·0600 권한1개입니다. 첫 실패 로그와 수정 후 결과를 별개로 보존했습니다.

## DDNS의 전체 완료 시한

부모 프로세스는20초 기한을 두지만 기존 코드는 `child.wait()`가 정상 반환한 뒤 시한을 다시 확인하지 않았습니다. 이미 끝난 child를 기다리던 호출자가 늦게 재스케줄되면 시한 뒤 성공을 받아들일 수 있었습니다.

정상 wait의 join 완료를 기록한 뒤, 응답 성공 판정 전에 monotonic 시각이 기한보다 작은지 한 번 확인합니다. 기한과 같거나 늦으면 기존 `UPDATE_TIMEOUT_OUTCOME_UNKNOWN`으로 거부하며 재요청하지 않습니다. 이미 join한 child를 다시 kill·poll·wait하지 않습니다. 이는 결과 수락 시점을 제한하는 검사이며 운영체제 스케줄링이나 전체 함수 반환 시간을 정확히20초 안으로 보장하는 것은 아닙니다.

fake wait의 반환 시계만19.999초·20초·20.001초로 바꾼 새 검사1개의3개 하위 사례를 실행했습니다. 기존 코드는 뒤의2개에서 거부 기대와 달리 성공해 실패했고, 수정 뒤에는 직전만 성공·기한 이상2개 거부를 확인했습니다. 세 경우 모두 spawn1회·wait1회·kill/poll0회·stdout close1회였습니다. 기존 검사와 합친5개 모두 통과·skip0입니다.

기존 Linux workflow의 예상 검사 수도4→5로 맞췄습니다. source·test·service·timer4파일의 전후 SHA 보존 조건과 실제 curl/DNS/systemd 미검증 표시는 유지했습니다. 인증서 자연 갱신·DNS 전파·실제 DDNS 갱신·운영 배포를 이 합성 결과로 완료 처리하지 않습니다.

## 같은 main의 Linux 확인

[PR168](https://github.com/DevDooly/devdooly-platform-lab/pull/168)의 main `6f551a16a8ed536bb126403234c41b9e9b266d43`에서 [CI39476929942](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39476929942)의 관측160개 모두 통과·skip0, API240개 통과·skip0와 verify·gateway 성공을 확인했습니다. 로컬에서 생략했던 POSIX 검사를 Linux 결과로 확인한 것이며 기존 Windows 결과를 덮어쓰지 않습니다.

[DDNS39476929984](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39476929984)는5개 통과·실패/오류/생략0·대상4파일 전후 SHA 동일을 보고했습니다. 같은 main의 [Pages39476929939](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39476929939)도 build·deploy를 통과했습니다. 앞선 검색 준비상태의 공개 결과는 [별도 근거](../evidence-input-readiness/README.md)를 따릅니다.

실제 미니 PC에 이 Python 수정본을 설치하지 않았습니다. 기존 HTTPS 외부 조회는 별도 읽기 검증이며, 기동 복원·토큰 교체·예산 정책·PR102의 보류는 유지합니다.
