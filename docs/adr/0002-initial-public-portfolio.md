# 0002 첫 포트폴리오의 공개 주소

- 상태: 채택
- 결정일: 2026-10-11

## 배경

사용자가 DevDooly/devdooly-platform-lab 공개 저장소를 생성하고 push와 구축을 요청했습니다. 기존 DevDooly/DevDooly.github.io 저장소가 존재하므로 초기 구현을 확인하기 위해 그 내용을 변경할 필요는 없습니다. Ubuntu 서버 연결은 사용자의 SSH 지문 확인과 공개키 등록을 기다리고 있습니다.

## 결정

현재 Astro·React 화면을 이 저장소의 GitHub Pages 프로젝트 사이트 `https://devdooly.github.io/devdooly-platform-lab/`에 먼저 게시합니다. 같은 소스를 미니 PC의 Lab UI로 사용할 때는 base를 `/`로 빌드합니다. 초기에는 소개와 합성 샘플 결과를 한 화면으로 제공하고, 공개 홈과 실행형 Lab의 분리는 실제 운영 경로가 정해질 때 진행합니다.

GitHub Actions는 정적 사이트의 check·test·build·Pages 게시를 맡습니다. Jenkins CI와 Argo CD 기반 미니 PC 배포는 별도 구축 대상이며, Pages 배포 성공을 Jenkins·Argo CD의 완료로 표시하지 않습니다.

## 결과

미니 PC가 꺼져 있어도 소개와 샘플 화면을 읽을 수 있습니다. 공개 HTTPS API가 연결되기 전에는 합성 샘플 fallback이며, 실제 실행·배포 이력을 가장하지 않습니다. 기존 TIL과 사용자 사이트 저장소는 그대로 연결합니다.

후속 공개 API 주소는 GitHub Actions 변수 LAB_PUBLIC_API_URL로 지정합니다. 토큰을 포함하지 않는 공개 주소만 사용하며, 다른 origin에서 조회하려면 API의 CORS 허용 범위를 함께 설정합니다.

관련 문서: [Pages 운영](../runbooks/pages.md), [첫 구성 결정](0001-platform-scope.md)
