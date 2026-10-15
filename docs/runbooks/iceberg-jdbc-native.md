# Trino·JDBC 합성 실증의 현재 실행 경계

이 문서는 [실제 native7 기록](../evidence/iceberg-jdbc/README.md)의 범위와 후속 실행 조건을 정리합니다. 마지막 기록은 **2026-10-15T19:05:20.198054Z**, 실험 PostgreSQL·Trino는 중지됐으며 PVC 두 개와 warehouse는 보관됐습니다. 기존 운영 애플리케이션을 변경하거나 자동으로 재실행하는 명령은 제공하지 않습니다.

## 다음 실행 전 확인

1. 새 실행이 필요한 목적과 변경 범위를 먼저 정합니다. 보관된 결과를 읽는 일에는 새 INSERT나 새 baseline clock이 필요하지 않습니다.
2. 기존 업무 SQL·8개 작업·객체 24개와 서비스·PVC/PV·Docker 식별자를 읽어 기준을 고정합니다. Host 여유와 무거운 CI 비활성을 실제 관측하고, 실행 시간·자원 예산을 별도로 명시합니다. 이전 snapshot을 새 시점의 baseline이라고 표시하지 않습니다.
3. 이미 완료한 DDL·INSERT나 결과가 미확인인 요청을 재접수하지 않습니다. 이번 native7의 두 INSERT는 성공했으므로 같은 창을 다시 실행할 수 없습니다. 후속 쓰기 실험은 새 대상과 명확히 정한 별도 작업 범위로 진행합니다.
4. 실제 image index→amd64→config, Java/Trino/PostgreSQL 버전, UID·cgroup limits, 신규 저장소와 원본 저장소의 분리, 전용 bucket/key ACL을 확인합니다. 비밀 값은 Git·공개 출력에 넣지 않습니다.
5. Kubernetes 정책 존재만으로 네트워크 격리를 통과 처리하지 않습니다. 같은 대상의 실제 허용/거부 control과 Service→실제 Pod 연결을 확인합니다. 원래 namespace의 정책을 변경하지 않습니다.
6. 작업은 검토된 단발 도우미로 실행하며 immutable intent·query identity·결과를 보존합니다. Detached 실행 여부와 실제 PID/start identity를 확인하고 SSH 연결 성공을 작업 성공으로 간주하지 않습니다. Unknown outcome은 재시도하지 않습니다.
7. 실패 후에는 실제 소유 namespace/controller UID·전체 spec을 검증한 신규 workload만 중지합니다. 로그는 가능하면 중지 전에 bounded private 파일로 확보하고, 수집 실패가 정확한 own 중지를 막지 않게 합니다. 원본 객체·DDL·PVC를 지우거나 native 실패를 성공으로 다시 표시하지 않습니다.
8. 최종 SQL·객체 전체 bytes·정상 종료·원본 보존과 own workload 0을 확인합니다. 기록 조회는 현재 가용성 검사와 구분합니다. Retain PVC·bucket/key·warehouse의 정리는 별도 정책과 명시적인 범위 확인 뒤 진행합니다.

## 미게시 초기 준비본과의 차이

초기 `infra/iceberg-lab` 경로로 준비한 packet은 Git에 게시하지 않은 실행 전 계획입니다. PR46에도 해당 디렉터리는 없습니다. 이 경로를 현재 repository에 있는 실행 소스로 안내하지 않습니다. Private native7 소스와도 다른 준비본이며, 후속 공개 runnable 계획을 만들 때 다음 차이를 반영해야 합니다.

| 미게시 초기 계획 | 실제 native7에서 적용한 조건 | 후속 공개 실행 소스 제안 |
| --- | --- | --- |
| `s3.max-error-retries=0` | Trino 설정의 최소 허용 값에 맞춘 `1`로 별도 own ConfigMap만 교정·seal | render_plan과 stopped JSON을 함께 재생성하고 최소 값 회귀 추가 |
| snapshot 두 개, 처음부터 데이터 6·12행 | 초기 CREATE의 빈 snapshot 1개 + 데이터 append 2개, 시점 0·6·12행 | SQL plan·validation 계약과 테스트를 세 snapshot/명시적 초기 상태로 수정 |
| `summary['added-records']` | 누락 key를 `element_at`으로 읽어 초기 NULL 보존 | inspection SQL을 안전한 map 조회로 교정하고 누락 key 회귀 추가 |
| CLI용 끝 세미콜론을 HTTP SQL에 그대로 전달 | 원문·wire SHA를 기록하고 전송 끝의 세미콜론 하나만 제거 | HTTP transport를 계획과 분리하고 원문/전송·단발 요청 회귀 추가 |
| 임시 positive control에 API Service IP를 egress 대상으로 사용 | 같은 API Service 대상으로 실제 namespace·선택된 Pod를 함께 묶은 destination control을 실측 | 네트워크 계획과 실제 positive/negative control 계약을 함께 보완 |

위 공개 실행 소스는 **후속 제안**입니다. Private native7 소스를 Git에 커밋했다고 주장하지 않습니다. 기존 frozen 계획·여섯 번째 실패·collector 두 실패를 수정해 이력을 없애지 않습니다. 새 공개 runnable 계획을 제공하려면 별도 source diff·offline 회귀·실제 실행 전 검토가 필요합니다.

## 기록의 검증 기준

Snapshot ID는 문자열이며 첫 parent는 null, 다음 parent는 바로 앞 ID여야 합니다. 초기 `added-records`의 key 부재는 NULL로 유지합니다. 실제 0행 SELECT와 동일한 의미라고 바꾸어 기록하지 않습니다. Native 결과의 행 해시는 저장 JSON dict의 알파벳 key 순서로 다시 만들지 않고, 저장된 Trino `columns`·`data`와 원래 query identity를 연결해 검증합니다.

Query receipt가 serialize하지 않은 필드는 가정하지 않습니다. 초기 상태는 실제 catalog record와 query의 다섯 preinsert SELECT·별도 warehouse 전체 파일로 확인합니다. 새 projection은 전체 phase/supervisor 원본 SHA와 생산 코드·출력 필드 계약을 검증한 뒤에만 생성하며, 브라우저는 그 정적 JSON을 읽을 뿐 SQL·관리 API를 실행하지 않습니다.
