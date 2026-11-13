import { technologies } from './technologyGuides';

export const handbookGroups = [
  { title: '시작하기', slugs: [''] },
  { title: '서비스와 데이터', slugs: ['java', 'kafka', 'storage'] },
  { title: '빌드와 운영', slugs: ['jenkins', 'kubernetes', 'web'] },
  { title: '확장과 검증', slugs: ['lakehouse', 'ai'] },
];

export const handbookChapters = [
  { slug: '', title: '전체 구성과 시작 순서' },
  ...handbookGroups.flatMap(group => group.slugs).filter(Boolean).map(slug => {
    const technology = technologies.find(guide => guide.slug === slug);
    if (!technology) throw new Error(`Handbook chapter has no technology guide: ${slug}`);
    return { slug, title: technology.title };
  }),
];

export const overviewSections = [
  { id: 'architecture', title: '전체 흐름' },
  { id: 'start-local', title: '로컬에서 시작하기' },
  { id: 'adapt', title: '다른 프로젝트에 적용하기' },
];

export const technologySections = [
  { id: 'role', title: '역할과 선택 이유' },
  { id: 'flow', title: '이 Lab의 동작 흐름' },
  { id: 'apply', title: '다른 프로젝트에 적용하기' },
  { id: 'changes', title: '어디를 어떻게 수정하나' },
  { id: 'verify', title: '변경 후 검증' },
  { id: 'evidence', title: '소스와 검증 근거' },
];

export function handbookHref(base: string, slug: string) {
  return `${base}handbook/${slug ? `${slug}/` : ''}`;
}
