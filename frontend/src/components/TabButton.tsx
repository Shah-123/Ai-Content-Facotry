import React from 'react';
import { motion } from 'motion/react';

export function TabButton<T extends string>({
  id,
  icon,
  label,
  activeTab,
  setActiveTab,
}: {
  id: T;
  icon: React.ReactNode;
  label: string;
  activeTab: T;
  setActiveTab: (t: T) => void;
}) {
  const active = activeTab === id;
  return (
    <button
      type="button"
      role="tab"
      id={`tab-${id}`}
      aria-selected={active}
      aria-controls={`panel-${id}`}
      tabIndex={active ? 0 : -1}
      onClick={() => setActiveTab(id)}
      className={`relative inline-flex h-10 items-center gap-2 px-3 text-ui font-medium whitespace-nowrap rounded-t-lg transition-colors focus-visible:outline-offset-[-2px] ${
        active ? 'text-base-50' : 'text-base-400 hover:text-base-100'
      }`}
    >
      <span aria-hidden="true" className={`inline-flex [&_svg]:size-4 ${active ? 'text-indicator' : 'text-base-500'}`}>
        {icon}
      </span>
      {label}
      {active && (
        <motion.span
          layoutId="tab-active-underline"
          className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-indicator"
          transition={{ type: 'spring', stiffness: 500, damping: 40 }}
        />
      )}
    </button>
  );
}
