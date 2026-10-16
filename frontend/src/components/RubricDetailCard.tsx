export function RubricDetailCard({
  metricKey,
  title,
  evaluation,
  hoveredKey,
  setHoveredKey,
}: {
  metricKey: string;
  title: string;
  evaluation: { score: number; reasoning: string };
  hoveredKey: string | null;
  setHoveredKey: (k: string | null) => void;
}) {
  const isHovered = hoveredKey === metricKey;

  return (
    <div
      onMouseEnter={() => setHoveredKey(metricKey)}
      onMouseLeave={() => setHoveredKey(null)}
      className={`card p-5 transition-colors hover:border-line-strong ${isHovered ? 'border-line-strong' : ''}`}
    >
      <div className="flex items-center gap-3">
        <h4 className="min-w-0 text-ui font-semibold text-base-50 flex-1">{title}</h4>
        <span className="font-mono text-[13px] text-base-100 tabular-nums">{evaluation.score}/5</span>
        <div className="flex gap-1" aria-hidden="true">
          {[1, 2, 3, 4, 5].map((lvl) => (
            <span
              key={lvl}
              className={`h-1.5 w-4 rounded-full ${lvl <= evaluation.score ? 'bg-indicator' : 'bg-base-700'}`}
            />
          ))}
        </div>
      </div>
      <p className="mt-3 text-ui leading-6 text-base-300">{evaluation.reasoning}</p>
    </div>
  );
}
