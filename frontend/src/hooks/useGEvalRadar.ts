import { useMemo } from 'react';
import { Job } from '../api';

/**
 * SVG polygon points for the G-Eval rubric radar chart.
 *
 * Replaces the former `useJobAnalytics`, which also computed a per-agent cost
 * and token table for the "Agent Analytics" tab. That tab and the agent graph
 * view were removed; the radar chart is the only part still rendered, so the
 * hook is now scoped to it.
 */
export function useGEvalRadar(currentJob: Job | null) {
  return useMemo(() => buildRadarPoints(currentJob?.geval_scores), [currentJob?.geval_scores]);
}

function buildRadarPoints(scores: Job['geval_scores']) {
  if (!scores) return '';

  const center = 50;
  const scale = 30;
  const metrics = [
    { score: scores.coherence?.score || 3, angle: -Math.PI / 2 },
    { score: scores.relevance?.score || 3, angle: 0 },
    { score: scores.accuracy?.score || 3, angle: Math.PI / 2 },
    { score: scores.tone_alignment?.score || 3, angle: Math.PI },
  ];

  return metrics.map(metric => {
    const distance = (metric.score / 5) * scale;
    return `${center + distance * Math.cos(metric.angle)},${center + distance * Math.sin(metric.angle)}`;
  }).join(' ');
}
