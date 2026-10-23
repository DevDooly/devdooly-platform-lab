# 합성 정책 선택 입력의 준비 상태와 공개 확인

기준: 2026-10-24 KST. 저장된 합성 보존 계획의 선택 화면을 검증했습니다.
[PR233](https://github.com/DevDooly/devdooly-platform-lab/pull/233)의 source `d7dfb06c67d45c58e8e6576c5fef7cea971f2550`을 main `110046b9d69a80160cd5ce1a60c3b73e56180fa3`에 반영했습니다. [검증한 컴포넌트](https://github.com/DevDooly/devdooly-platform-lab/blob/110046b9d69a80160cd5ce1a60c3b73e56180fa3/apps/lab-web/src/components/IcebergPolicyScenarios.tsx)와 [합성 입력](../../../examples/iceberg-retention-scenarios/README.md)을 구분합니다.

## 재현과 변경

수정 전 로컬 정적 HTML 사본에서는 detached 조건의 선택 표시만 바뀌고 이전 KEEP9·후보0 계획이 남았습니다. 이벤트가 연결된 정상 앱의 같은 조건은 KEEP8·후보1이었습니다. 정적 사본은 이벤트 연결 전 상태를 재현한 것으로, 실제 공개 회선 지연 시간이나 운영 장애 발생을 측정한 결과가 아닙니다.

선택 입력 한 곳을 SSR·첫 client render에서 disabled/busy로 표시하고 mount 뒤 활성화했습니다. 기존 계획은 계속 읽을 수 있습니다. 저장된 합성 계획·parser·Python 계산·운영 정책·삭제 기능은 변경하지 않았습니다.

## 확인한 결과

- 기존 SSR 회귀를 보완해 수정 전6개 중1개 실패, 수정 후6개 통과를 확인했습니다. 전체 웹278개 통과·실패/생략0, Astro51파일 진단0, 정적2페이지 빌드와 독립 검토 CLEAR를 확인했습니다.
- 같은 main의 [CI39975714578](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39975714578)은 verify·public-read-gateway 성공, [Pages39975714597](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39975714597)은 build·deploy 성공입니다. 격리 실증4개 job은 생략입니다.
- 공개 정적 HTML의 disabled/busy·설명 연결과 policy JS11,536B 전체가 로컬 빌드와 일치했습니다. JS SHA-256은 `af92d4f1eb6230252670502d8a400e6cdc7b1d8681676e9d3c4496bc6f06c1b5`입니다. 전달 검사 첫 시도의 한글 literal assertion 실패를 UTF-8 파일로 교정했으며 전체 GET3회입니다. 이 전달 검사에서 runtime API는 요청하지 않았습니다.
- 전달 검사와 별도로 [공개 화면](https://devdooly.github.io/devdooly-platform-lab/#iceberg-policy-scenarios)의 브라우저1280에서 세 조건9/0·8/1·판정 보류의 선택·계획·사유 일치, 준비 후 활성화와 기본 details 닫힘을 확인했습니다. 모바일390에서도 판정 보류와 가로 넘침 없음(clientWidth=scrollWidth375)을 확인했습니다.
- 공개 화면의 추가 키보드 확인에서 Home·아래 방향키·End가 각각 세 조건과 결과를 함께 바꿨습니다. Tab으로 전체 근거 summary에 이동한 뒤 Enter로 snapshot9개·파일9개를 펼치고 다시 닫았습니다. 다음 두 Tab은 공개 입력과 고정 Python planner 링크에 차례로 도달했습니다. 링크를 실행해 새 계산이나 서버 작업을 시작한 시험은 아닙니다.

이 기록은 합성 UI·정적 전달·명시한 브라우저 조작의 범위이며 운영 삭제·자원 예산 확정·장기 가용성 검증이 아닙니다. [현재 안내](../../AUTONOMOUS_WORK.md)의 Pages 토큰 교체·별도 기동 복원·예산 정책·PR102 보류와 기존 운영 image/source pin을 유지합니다.