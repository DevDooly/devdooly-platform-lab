# 내부 작업 접수 간격 운영

현재 이 기능은 별도 MariaDB·Garage에서 검증한 후보 코드입니다. 인증된 외부 SQL 사본의 복원본에서 V4 migration과 실제 이전 5a JAR의 API startup/read·idle worker 호환을 확인했습니다. 운영은 source 6c·schema V3이며 운영 migration·실제 새 image 확인은 별도 배포 근거가 생긴 뒤 완료로 표시합니다. [ADR 0011](../adr/0011-durable-admission-cooldown.md), [격리 검증](../evidence/admission-cooldown/README.md)을 연결합니다.

## 동작 판단

| 상황 | 처리 |
| --- | --- |
| 같은 run·같은 원본 재시도 | 기존 작업 반환, gate 시각 유지 |
| 잘못된 원본·충돌·다른 작업의 slot 점유 | 기존 거부 규칙, gate 시각 유지 |
| slot은 비었지만 다음 승인 시각 전 | ADMISSION_COOLDOWN, 새 행·outbox·S3 I/O 없음 |
| 적격 시각 이후 새 작업 | DB transaction으로 gate·STAGING·slot 저장 후 S3 확인 |
| 승인 뒤 S3 실패 | 동일 작업 보존, 같은 ID로 원인 확인 후 재시도 |
| 정상 export·명시적 terminate | slot 해제, 다음 승인 시각 보존 |

운영자가 DB에서 `cooldown_seconds`를 변경하는 경우 1~3,600초 범위를 지킵니다. 적용 전후 행·시각을 비공개 기록으로 남기며 마지막/다음 승인 시각을 임의 초기화해 제한을 해제하지 않습니다. 이미 저장된 다음 승인 시각은 설정 변경만으로 다시 계산되지 않습니다. 앱에는 비활성화용 환경변수가 없습니다.

## 운영 전환과 복구

1. 현재 7개 작업의 논리 DB dump·원본 7개/export 14개를 새 checkpoint로 확보하고 외부 암호화 사본을 검증합니다. 과거 6개/18개 백업을 새 기록으로 덮지 않습니다.
2. 별도 schema에 V3 자료를 복원해 새 API의 V4 migration과 기존 행·bytes·시각·이력을 비교합니다. 이전 실제 binary의 V4 startup/read는 따로 확인하며 설정 문서만으로 호환 완료를 표시하지 않습니다.
3. 같은 source SHA의 CI와 실제 immutable image를 확인합니다. API가 먼저 V4를 적용하고 worker를 그 뒤 교체합니다. 기존 job observation 필드 계약은 유지합니다.
4. source/schema/실행 이미지·기존 자료 보존을 확인한 뒤 새 binary의 내부 stage만 사용합니다. 구형 stage와 혼용하지 않습니다.
5. 거부 시 자동 새 ID 제출·policy reset을 하지 않습니다. slot과 next_admission_at, 기존 작업·outbox 상태를 확인합니다.
6. 이미지 원복이 필요하면 새 접수를 동결하고 V4 policy를 유지합니다. 구형 stage를 사용하지 않습니다. V4 DROP·Flyway repair·기존 PVC 덮어쓰기는 rollback 절차가 아닙니다.

위 1~2단계의 이번 격리 실행에서는 새 7작업/21객체 checkpoint와 외부 AES-256-GCM 인증을 확인한 뒤 SQL member만 새 schema에 복원했습니다. 새 candidate API가 복원본을 V4로 migrate했고 이전 5a JAR의 API 조회·idle worker·정상 종료를 포함한 8개 검사가 통과했습니다. 5a와 운영 6c의 main source/POM 동등성과 실제 6c OCI 실행 시험은 구분합니다. 이전 stage는 여전히 policy를 우회하므로 위 4~6단계의 혼용 금지는 유지합니다. 운영의 V4 적용은 아직 실행하지 않았습니다.

`src/test`의 AdmissionTestFixtures는 메모리 H2 또는 지정 숫자 loopback disposable schema에서만 시험 날짜를 초기화합니다. 운영 코드와 운영 절차에 이 helper를 적용하지 않습니다.

## 선택 검사

비공개 연결값은 환경변수로 전달합니다. 아래 검사는 `platform_lab_admission_it` 전용 schema와 합성 시험 bucket만 허용하며 운영 주소·관리자 credentials를 넣지 않습니다.

```sh
./mvnw -B -ntp -Dlab.admission.tests=true -Dtest=AdmissionCooldownIT \
  -DargLine=-Duser.timezone=Asia/Seoul test
```

실패 case는 자료를 보존하고 후속 case를 skip합니다. 실패 영수증을 먼저 확인하며 DB를 지우고 같은 시험을 무조건 재실행하지 않습니다. 성공한 case만 자신이 만든 행·객체를 정리합니다.
