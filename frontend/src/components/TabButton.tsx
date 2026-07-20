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
      onClick={() => setActiveTab(id)}
      className={`px-4 py-2.5 rounded-xl transition-all flex items-center gap-2 whitespace-nowrap relative
      ${
        active
          ? 'bg-accent-500/10 text-accent-400 border border-accent-500/20 shadow-sm'
          : 'text-base-400 hover:text-base-200 hover:bg-white/3 border border-transparent'
      }`}
    >
      {icon} {label}
      {active && (
        <motion.div
          layoutId="tab-active-underline"
          className="absolute -bottom-[9px] left-2 right-2 h-[2px] bg-accent-500 rounded-full"
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
        />
      )}
    </button>
  );
}
