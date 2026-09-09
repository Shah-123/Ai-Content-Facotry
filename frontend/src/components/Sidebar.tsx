import React from 'react';
import {
  LayoutDashboard, FileEdit, History, Plus, RefreshCw, Sparkles, Trash2, RotateCcw
} from 'lucide-react';
import { motion } from 'motion/react';
import { Job } from '../api';
import { ViewState } from '../types';

interface SidebarProps {
  view: ViewState;
  navTo: (v: ViewState) => void;
  jobs: Job[];
  currentJob: Job | null;
  loadJob: (id: string) => void;
  startNewJob: () => void;
  onDeleteJob?: (id: string) => void;
  onResumeJob?: (id: string) => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export function Sidebar({
  view, navTo, jobs, currentJob, loadJob, startNewJob, onDeleteJob, onResumeJob,
  isMobileOpen, onCloseMobile
}: SidebarProps) {
  const navItems: { key: ViewState; icon: React.ReactNode; label: string }[] = [
    { key: 'chat',    icon: <LayoutDashboard className="w-[18px] h-[18px]" />, label: 'Dashboard' },
    { key: 'content', icon: <FileEdit       className="w-[18px] h-[18px]" />, label: 'Studio' },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isMobileOpen && (
        <div
          onClick={onCloseMobile}
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
        />
      )}
      <aside className={`w-[260px] h-full fixed left-0 top-0 bg-base-950/95 backdrop-blur-2xl flex flex-col z-50 overflow-y-auto border-r border-white/6 shadow-xl transition-transform duration-300 md:translate-x-0 ${isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}>
      {/* Brand Header */}
      <div className="flex items-center gap-3 px-6 pt-7 pb-5">
        <div className="w-9 h-9 rounded-xl aurora-chip flex items-center justify-center shadow-sm shrink-0">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 24, repeat: Infinity, ease: 'linear' }}
          >
            <Sparkles className="text-base-950 w-4 h-4" />
          </motion.div>
        </div>
        <div className="min-w-0">
          <h1 className="text-base font-extrabold text-gradient-amber tracking-tight leading-tight truncate">AI Content Factory</h1>
          <p className="text-[10px] text-base-400 font-semibold tracking-wider uppercase opacity-80">Multi-Agent Engine</p>
        </div>
      </div>

      {/* New Job CTA */}
      <div className="px-5 mb-5">
        <motion.button
          onClick={startNewJob}
          className="btn-primary w-full py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 text-xs font-bold tracking-wide shadow-md hover:shadow-lg transition-all"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <Plus className="w-4 h-4 stroke-[2.5]" /> New Generation Job
        </motion.button>
      </div>

      <nav className="flex flex-col gap-1 px-4 grow">
        <div className="text-[10px] font-bold text-base-500 mb-1.5 uppercase tracking-widest px-2">Navigation</div>
        {navItems.map(item => (
          <button key={item.key} onClick={() => navTo(item.key)}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl transition-all duration-200 group relative sidebar-glow text-xs font-semibold ${view === item.key ? 'bg-accent-500/10 text-accent-400 font-bold border border-accent-500/20 shadow-sm' : 'text-base-400 hover:text-base-200 hover:bg-white/4 border border-transparent'}`}>
            {view === item.key && (
              <motion.div
                layoutId="nav-active-indicator"
                className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-accent-500 shadow-[0_0_8px_var(--color-accent-500)]"
                transition={{ type: 'spring', stiffness: 350, damping: 30 }}
              />
            )}
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Recent Jobs History */}
      <div className="px-4 pb-5 pt-3">
        <div className="flex justify-between items-center mb-2.5 px-2">
          <span className="text-[10px] font-bold text-base-500 uppercase tracking-widest">Recent Jobs</span>
          <button onClick={() => window.location.reload()} className="text-base-500 hover:text-accent-400 transition-colors p-1 rounded-lg hover:bg-white/5" title="Refresh list"><RefreshCw className="w-3 h-3" /></button>
        </div>
        <div className="flex flex-col gap-1 max-h-[28vh] overflow-y-auto pr-1 custom-scrollbar">
          {jobs.slice(0, 10).map((job, i) => (
            <motion.div
              key={job.id}
              className="relative group w-full"
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03, duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
            >
              <button onClick={() => loadJob(job.id)}
                className={`w-full text-left rounded-xl pl-3 pr-8 py-2 text-xs flex justify-between items-center transition-all duration-200 sidebar-glow ${currentJob?.id === job.id ? 'bg-accent-500/10 border border-accent-500/30 text-base-100 font-semibold shadow-sm' : 'text-base-400 hover:text-base-200 border border-transparent hover:bg-white/4'}`}>
                <span className="truncate pr-2 text-[12px] font-medium">{job.topic}</span>
                <div className="shrink-0 group-hover:opacity-0 transition-opacity">
                  {job.status === 'completed'         && (
                    <span className="text-[9px] font-bold text-signal-success bg-signal-success-dim border border-signal-success/20 px-1.5 py-0.5 rounded uppercase tracking-wider inline-block">
                      Done
                    </span>
                  )}
                  {job.status === 'failed'            && (
                    <span className="text-[9px] font-bold text-signal-error bg-signal-error-dim border border-signal-error/20 px-1.5 py-0.5 rounded uppercase tracking-wider inline-block fail-pulse">
                      Fail
                    </span>
                  )}
                  {job.status === 'running'           && (
                    <span className="text-[9px] font-bold text-accent-400 bg-accent-glow border border-accent-500/20 px-1.5 py-0.5 rounded uppercase tracking-wider inline-block status-pulse">
                      Active
                    </span>
                  )}
                  {job.status === 'awaiting_approval' && (
                    <span className="text-[9px] font-bold text-signal-warning bg-signal-warning-dim border border-signal-warning/20 px-1.5 py-0.5 rounded uppercase tracking-wider inline-block status-pulse">
                      Review
                    </span>
                  )}
                  {job.status === 'pending'           && (
                    <span className="text-[9px] font-bold text-base-400 bg-white/5 border border-white/6 px-1.5 py-0.5 rounded uppercase tracking-wider inline-block">
                      Queue
                    </span>
                  )}
                </div>
              </button>
              {onDeleteJob && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteJob(job.id);
                  }}
                  className={`absolute top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 text-base-500 hover:text-signal-error transition-opacity duration-200 p-1.5 rounded-lg hover:bg-white/5 ${onResumeJob && job.status === 'failed' ? 'right-7' : 'right-1.5'}`}
                  title="Delete job"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
              {onResumeJob && job.status === 'failed' && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onResumeJob(job.id);
                  }}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 text-base-500 hover:text-amber-400 transition-all duration-200 p-1.5 rounded-lg hover:bg-amber-500/10"
                  title="Resume from checkpoint"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              )}
            </motion.div>
          ))}
          {jobs.length === 0 && <div className="text-xs text-base-500 px-2 py-3 text-center italic">No jobs in history</div>}
        </div>
      </div>
    </aside>
    </>
  );
}
