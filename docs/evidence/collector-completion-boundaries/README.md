# 관측 응답 완료 시한과 강제 종료 후 잠금 복구

2026-10-23 KST에 저장소의 오프라인 수집기 경계를 검증했습니다. 이 오프라인 검사에서는 새 토큰·별도 VM·SSH·실제 GitHub/Kubernetes 요청·운영 설정 변경 없이 합성 응답과 시험 프로세스만 사용했습니다. 이후 같은 날 **20:17:53(KST)**에 [설치된 collector 한 파일의 교체](DEPLOYED.md)를 완료했습니다. 새 코드의 다음 자연 수집과 Pages 게시 연결은 아직 **PENDING**이며, 아래 오프라인 시험·파일 교체와 구분합니다.

## 시한을 넘긴 응답을 성공으로 채택하지 않기

기존 `JsonTransport`는 요청 전 공유 monotonic deadline을 확인했지만 응답 본문 완료 뒤에는 확인하지 않았습니다. 마지막 main 재확인 요청이 늦게 끝나면 다음 요청의 시한 검사가 없어 성공으로 수집될 수 있었습니다. 응답 read·close가 반환한 직후 `monotonic() >= deadline`이면 `TIMEOUT`을 전달하도록 수정했습니다.

fake clock·response로 시한 직전 성공·정확한 경계와 초과 거부·응답 context 종료·요청 전 만료의 open0회·마지막 main 응답 지연 시 이전 `lastSuccess`와 입력 보존을 검사했습니다. 수정 전 새4개 검사에서 실패3건을 재현했고 수정 후 통과했습니다. 비공개 canary는 결과에 포함되지 않았습니다.

이 수정은 **본문 read와 close가 반환한 뒤 늦은 성공을 거부**합니다. 지속 유입되는 본문을 시한 즉시 중단하거나 JSON 파싱·저장까지 hard deadline을 새로 보장하지 않습니다. 기존 host alarm·child timeout도 별도 보호 장치입니다.

## 파일 존재와 활성 writer 잠금 구분

기존 CLI는 `O_EXCL`로 잠금 파일을 만들고 정상 `finally`에서 삭제했습니다. 프로세스가 강제 종료돼 파일만 남으면 실제 writer가 없어도 후속 수집이 계속 차단될 수 있었습니다. 미점유 파일만 남긴 오프라인 반례에서 수집이 시작되지 않는 실패를 확인했습니다.

새 구현은 파일 inode를 유지하고 POSIX `flock(LOCK_EX | LOCK_NB)`으로 활성 writer만 차단합니다. 프로세스가 종료되면 OS 잠금이 해제됩니다. 파일은 unlink하지 않으며 symlink·regular file·단일 hard link·POSIX 현재 소유자와0600 검사를 수행합니다. Windows 오프라인 검증에는 `msvcrt` 잠금을 사용하며 Linux의 `flock` 결과와 구분합니다.

실제 Linux 시험 child가 수집 잠금을 획득한 뒤 fake transport 경계에서 대기하도록 했습니다. 이때 두 번째 수집은 transport0회로 거부되고 원 JSON bytes가 보존됐습니다. child를 SIGKILL로 종료한 뒤 종료 코드와 동일 lock inode를 확인했고, 다음 수집이 같은 inode를 재획득해 합성 인증 실패를 기록하면서 이전 `lastSuccess`를 보존했습니다. 실제 서버·서비스를 강제 종료한 시험이 아닙니다.

## 실제 검사 결과

검사 소스는 `fb41893aba7470273c4e3ba32ae5d0dee78fe69b`입니다. [PR #197의 Linux 실행39942926998](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39942926998)에서 전체 관측 계약173개·실패0·생략0과 POSIX SIGKILL·권한·symlink·inode 회귀 통과를 확인했습니다. Windows 전체173개는165개 통과·POSIX8개 생략이었습니다. 새 전용 워크플로는 contents 읽기만 사용하며 외부 서비스나 secret을 요구하지 않습니다.

## 운영 교체와 다음 확인

[운영 교체 근거](DEPLOYED.md)에서 기존 외부 cycle lock 아래 한 파일의 원자 교체·새 코드 pin·계약·unit 파일과 상태 보존을 확인했습니다. API 호출·서비스 제어·수동 실행은 하지 않았습니다. 교체 직후 선택한 상태 projection은 이전과 같았고 여전히 교체 전 수집 시각이었습니다. 이는 전체 상태 JSON의 바이트 동일성이나 새 코드의 실제 수집 성공을 증명하지 않습니다. 다음 자연 회차의 수집 시각과 Pages 연결을 별도로 확인해야 합니다.

## 운영 교체 전제와 한계

- 기존 O_EXCL 구현은 OS 잠금을 획득하지 않습니다. **기존 수집이 실행 중이지 않음을 확인하고 외부 cycle lock을 획득한 상태에서 교체**해야 합니다. 구·신 수집기를 동시에 실행하지 않습니다.
- lock 부모는 신뢰하는 전용 디렉터리여야 합니다. 적대적인 동일 UID나 외부 프로세스의 unlink·inode 교체를 방어하는 계약은 아닙니다. stale 판단에 mtime을 사용해 파일을 자동 삭제하지 않습니다.
- 이번 교체 대상은 collector 코드 한 파일입니다. 토큰·설정·state 본문·timer 주기를 바꾸지 않았습니다. 자연 회차의 수집·Pages 연결은 아직 대기 중이며 설치 코드 교체와 별도의 완료 조건입니다.
- 위 SIGKILL 시험은 격리 오프라인 프로세스의 검증이고, 실제 운영에서는 코드 교체·읽기 전용 사후 점검까지 확인했습니다. 운영 장애·재부팅·기동 복원·전체 wall-clock 상한·장기 가용성 완료로 확대하지 않습니다. Pages 토큰 교체·별도 기동 복원·예산 정책·PR #102 보류는 유지합니다.
