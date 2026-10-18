# 조회 gateway chart의 오프라인 보존 검사

2026-10-18의 Windows 로컬 검사에서 default-disabled chart의 렌더 보존을 확인했습니다. 이 기록은 main K(`13447fa8`)의 공개 chart·값과 검증된 Nginx 정책을 바탕으로 만든 C 전용 후보의 결과입니다. 실제 미니 PC에 설치하거나 활성화한 기록이 아닙니다.

## 실제 통과한 범위

[원본 유한 결과](local-final3-summary.json)는 Node 24.19.0·Helm 4.3.0으로 검사기 한 번을 실행한 기록입니다. Helm 호출은 version 1회와 template 14회이며, 의도한 잘못된 입력 9개는 실패해야 통과하는 조건입니다.

- 기본값과 명시적 false는 기존 12개 resource의 전체 렌더 bytes와 일치했습니다. 기준 SHA-256은 `1862ec4a796a4ec860a78e84c35bb8ebf2db483ffe432974cd62ee88a0173a32`입니다.
- true는 기존 12개 객체의 전체 내용을 보존하고 ConfigMap·Deployment·Service·NetworkPolicy 4개만 추가했습니다.
- ConfigMap에서 읽은 두 정책의 bytes, 고정 image·security·resource·volume·TCP probe와 client/API/DNS NetworkPolicy 선언을 확인했습니다.
- 다른 namespace 활성화, string/null 타입과 upstream·image·replica·resource·NodePort 추가 속성을 거부했습니다. 긴 release 이름의 gateway resource 이름도 63자 이내였습니다.
- 공개 source 40개·원 기준 파일·Helm binary는 실행 전후 동일했습니다. HOME/USERPROFILE은 유지했고 원본 저장소·서버·클러스터를 변경하지 않았습니다.

이 결과의 SHA-256은 `189459d42986b568cb0835e4bc9cbcbcbbecc1a11379e9c85a4ca2ac575e7aaf`입니다. 이후 Linux 도구 검증과 CI 연결을 추가하는 새 검사기 후보는 아직 실행하지 않았습니다. 정책 bundle·chart resource 선언은 이 로컬 통과 후보에서 변경하지 않았습니다.

## 첫 실행 실패 보존

[첫 결과](local-final2-failure.json)는 version 전제조건에서 중단됐으며 template 호출은 0회였습니다. 후속 동일 binary의 전체 환경 version은 기대값과 같았고, 원 checker의 clean env에서는 version rc1·stdout0B·stderr100B가 관측됐습니다. stderr는 폐기했고 필수 파일/실행 파일 부재 계열로만 분류했습니다.

기존 성공 baseline과 맞추기 위해 PATH 단일 디렉터리 지정과 HELM_DRIVER=memory를 함께 제거한 새 후보가 위 보존 검사를 통과했습니다. 두 설정 중 어느 것이 원인이었는지는 확정하지 않습니다. 첫 실패를 성공 결과로 교체하지 않습니다.

## 아직 확인하지 않은 범위

새 Linux CI workflow는 공개 main K의 정확한 Git blob으로 원 chart를 새 폴더에 만들고, 기존 버전 lock의 Linux Helm archive를 검증하여 기준 렌더를 생성하도록 준비했습니다. 검사기에서는 archive bytes와 그 안의 단일 Helm 실행 파일 bytes를 다시 확인합니다. 원 chart와 새 chart는 같은 main K 값으로 비교하므로 현재 운영 값의 배포 검증을 뜻하지 않습니다. Linux 실행 결과는 아직 없습니다.

Kubernetes DNS namespace identity·egress·API 연결·scheduler admission·AppProject NetworkPolicy 권한·실제 Pod 기동·외부 HTTPS는 후속입니다. [선언과 활성화 전 조건](../../runbooks/public-read-gateway-chart.md)을 따르며 home-lab의 enabled 값과 AppProject는 그대로 유지합니다.
