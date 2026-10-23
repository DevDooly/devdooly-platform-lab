import { firstVisitTourSteps } from '../data/first-visit-tour';
import type { FirstVisitTourStepNumber } from '../data/first-visit-tour';
import '../styles/first-visit-tour.css';

interface Props {
  step: FirstVisitTourStepNumber;
}

/** Pure markup: Astro can render this directly and the existing React sections can include it. */
export default function TourStepNavigation({ step }: Props) {
  const current = firstVisitTourSteps[step - 1];
  const next = firstVisitTourSteps.find(item => item.number === step + 1);
  return <nav className="section tour-step-navigation" aria-label={`처음 방문 관람 ${step}단계 이후 이동`}>
    <p className="tour-current-step"><span>{step} / {firstVisitTourSteps.length} 단계</span><strong>{current.title}</strong></p>
    <div className="tour-navigation-links">
      <a className="tour-next-link" href={next?.target ?? '#evidence'}>{next ? `다음 · ${next.title}` : '다음 · 더 많은 검증 근거'} <span aria-hidden="true">→</span></a>
      <a className="tour-back-link" href="#tour">관람 순서로 돌아가기 <span aria-hidden="true">↑</span></a>
    </div>
  </nav>;
}
