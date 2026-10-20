# 손상 export의 중지 유지와 명시 수리 후 복구

2026-10-20 13:16:39 UTC, 새 GitHub hosted Linux 환경의 [실제 시험 39428536206](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39428536206)이 통과했습니다. 손상된 결과 객체를 발견한 worker가 영속 중지되고, 수리 없이 재개하면 다시 중지되며, 시험 소유 객체를 명시적으로 수리한 뒤 재개해야 완료되는 경계를 확인했습니다.

## 확인한 동작

| 단계 | 실제 확인한 상태 |
| --- | --- |
| 준비 | 실제 raw 저장·전체 GET과 publisher ACK 뒤 DB 업무 처리를 직접 호출했습니다. 합성 입력 12건은 성공 7·실패 3·중복 2·미처리 0이며, 업무는 `COMPLETED`, export는 `PENDING`, 슬롯은 점유 상태입니다. 최초 완료는 consumer가 처리한 결과가 아닙니다. |
| 손상과 첫 중지 | 정답 bundle의 result bytes에서 한 byte만 바꿔 같은 크기의 다른 bytes·SHA를 만들고, 비어 있던 시험 소유 result key에 저장했습니다. 새 daemon의 실제 저장소 검증 예외가 `PAUSED_OPERATOR / EXPORT / EXPORT_FAILED`로 남았고, client 종료·lease 해제 뒤에도 유지됐습니다. |
| 수리 없는 재개 | 원 CLI의 일반 run은 거부됐고 journal을 바꾸지 않았습니다. resume는 journal을 `STOPPED`로 바꾸지만 객체를 수리하지 않습니다. 수리하지 않은 새 daemon은 같은 실제 검증 실패로 다시 중지됐습니다. |
| 명시 수리와 완료 | 종료한 child·해제된 lease·소유 key·손상 bytes를 다시 확인한 시험 코드가 그 객체 하나만 삭제했습니다. 실제 NoSuchKey를 확인한 뒤 별도 resume와 새 daemon이 결과/실패 파일 두 개의 전체 bytes·크기·SHA를 검증했고, `EXPORTED`·EXPORT ACK·슬롯 해제를 확인했습니다. |

수리 전에는 손상 객체와 업무 행·처리 시각·원본 source/raw, DISPATCH ACK와 슬롯이 유지됐습니다. 새 발행·consumer commit·failures 객체는 생기지 않았습니다. 마지막에는 실제로 발행했던 완료 메시지를 1회 재전달받고 broker end 1·committed 1·lag 0을 확인했습니다. 처음의 직접 DB fixture와 마지막 consumer replay는 서로 다른 관측입니다.

전체 업무 행·처리 시각, 원본 bytes, DISPATCH 전체 행, EXPORT identity, Kafka cluster/topic identity를 대조했습니다. 허용된 최종 export 상태·시각과 ACK·슬롯 변경 외의 불변 조건, source/artifact/tool 보존, 소유 자원 정리까지 통과했습니다. JUnit은 지정 IT 1개·실패 0·오류 0·skip 0입니다.

## 원문과 출처

- [유한 summary 원문](summary.json), [실행 metadata](run-metadata.json)
- 검증 소스: [`0f5c4bc2`의 실제 IT](https://github.com/DevDooly/devdooly-platform-lab/blob/0f5c4bc2b0e5296c0c29924a5487d2c62ad1cd75/infra/export-integrity-runtime-ci/ExportIntegrityRuntimeIT.java), [실행기·검증 조건](https://github.com/DevDooly/devdooly-platform-lab/blob/0f5c4bc2b0e5296c0c29924a5487d2c62ad1cd75/infra/export-integrity-runtime-ci/README.ko.md)
- summary SHA-256: `6230916acefad6770c49e941ac4699d5dca8bbaaea9b30cc041b3686313707da`
- source manifest SHA-256: `d0ac9e8389d967158102badd1c202c9954fbe5c839d7db333c50985b78e64488`
- JUnit XML SHA-256: `d6a16be1789f6518c234d3857307ab0a633dd5c6e47a4631e7e9e544506cd7b0`

PR137의 [Linux CI 39428333375](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39428333375)에서 순수 경계 검사 31개와 fresh API staging 108파일의 compile-only를 먼저 통과했습니다. 실제 시험은 병합된 main의 첫 수동 opt-in 실행 한 번입니다. 공개 원문은 실제 실행에서 생성한 유한 요약이며 `synthetic: true`는 합성 입력을 뜻합니다.

## 실행 범위와 공개 화면

새 Kafka·MariaDB·Garage·JVM 4개와 내부 네트워크만 사용했습니다. CPU·메모리·PID·단일 deadline을 제한했고, full ID·source/run/nonce·생성 시각·image·mount·network를 확인한 자원만 정리했습니다. 기존 API106개와 이전 시험·manifest, 미니 PC 운영 서비스·자료·PVC는 바꾸지 않았습니다.

명시 수리는 시험 코드가 소유한 손상 fixture 한 개의 삭제입니다. 운영 자동 수리·임의 자료 삭제·host/broker 재시작·HA·모든 장애에서의 exactly-once를 검증한 결과가 아닙니다. 토큰 교체·예산 정책·PR102는 계속 보류합니다.

[단계별 화면](https://devdooly.github.io/devdooly-platform-lab/#export-integrity-runtime)을 실제 source·run·manifest·완료 시각·JUnit SHA에 연결했습니다. 로컬 웹 테스트 160개·skip 0, 타입 검사 41파일의 오류·경고 0과 정적 빌드를 통과했습니다. 1280px·390px에서 단계 선택·End/방향키·기본 닫힌 상세 근거와 job/runtime 상태 표를 확인했습니다. 본문 17px, 페이지 가로 넘침 부재와 모바일 표의 내부 스크롤도 확인했습니다. 공개 Pages 게시와 게시 후 확인은 아직 대기 중입니다.
