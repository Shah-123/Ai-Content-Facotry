import React from 'react';
import {
  LayoutDashboard, FileEdit, Plus, RefreshCw, Sparkles, Trash2, RotateCcw,
  PanelLeftClose, PanelLeftOpen
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
  /** Desktop-only icon-rail collapse. Mobile always renders the full panel. */
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  onRefreshJobs: () => void;
}

export function Sidebar({
  view, navTo, jobs, currentJob, loadJob, startNewJob, onDeleteJob, onResumeJob,
  isMobileOpen, onCloseMobile, isCollapsed = false, onToggleCollapse, onRefreshJobs
}: SidebarProps) {
  // Collapse is a desktop affordance; on mobile the drawer is either open
  // (full width) or off-screen, so ignore it there.
  const rail = isCollapsed && !isMobileOpen;
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
      <aside className={`h-full fixed left-0 top-0 bg-base-950/95 backdrop-blur-2xl flex flex-col z-50 overflow-y-auto overflow-x-hidden border-r border-white/6 shadow-xl transition-[transform,width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] md:translate-x-0 ${rail ? 'w-[260px] md:w-[72px]' : 'w-[260px]'} ${isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}>
      {/* Brand Header */}
      <div className={`flex items-center pt-7 pb-5 ${rail ? 'flex-col gap-2.5 px-3' : 'gap-2.5 px-4'}`}>
        <div className="w-9 h-9 rounded-xl aurora-chip flex items-center justify-center shadow-sm shrink-0">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 24, repeat: Infinity, ease: 'linear' }}
          >
            <Sparkles className="text-base-950 w-4 h-4" />
          </motion.div>
        </div>
        {!rail && (
          <div className="min-w-0 flex-1">
            <h1 className="text-[15px] font-extrabold text-gradient-amber tracking-tight leading-tight truncate">AI Content Factory</h1>
            <p className="text-[10px] text-base-400 font-semibold tracking-wider uppercase opacity-80 whitespace-nowrap">Multi-Agent Engine</p>
          </div>
        )}
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            className="hidden md:flex items-center justify-center p-1.5 rounded-lg text-base-500 hover:text-accent-400 hover:bg-white/5 transition-colors shrink-0"
            title={rail ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={rail ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!rail}
          >
            {rail ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        )}
      </div>

      {/* New Job CTA */}
      <div className={`mb-5 ${rail ? 'px-3' : 'px-5'}`}>
        <motion.button
          onClick={startNewJob}
          className={`btn-primary w-full rounded-xl flex items-center justify-center gap-2 text-xs font-bold tracking-wide shadow-md hover:shadow-lg transition-all ${rail ? 'py-2.5 px-0' : 'py-2.5 px-4'} whitespace-nowrap`}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          title={rail ? 'New Generation Job' : undefined}
        >
          <Plus className="w-4 h-4 stroke-[2.5]" /> {!rail && 'New Generation Job'}
        </motion.button>
      </div>

      <nav className={`flex flex-col gap-1 grow ${rail ? 'px-3' : 'px-4'}`}>
        {!rail && <div className="text-[10px] font-bold text-base-500 mb-1.5 uppercase tracking-widest px-2 whitespace-nowrap">Navigation</div>}
        {navItems.map(item => (
          <button key={item.key} onClick={() => navTo(item.key)}
            title={rail ? item.label : undefined}
            aria-label={item.label}
            className={`flex items-center py-2.5 rounded-xl transition-all duration-200 group relative sidebar-glow text-xs font-semibold ${rail ? 'justify-center px-0' : 'gap-3 px-3.5'} ${view === item.key ? 'bg-accent-500/10 text-accent-400 font-bold border border-accent-500/20 shadow-sm' : 'text-base-400 hover:text-base-200 hover:bg-white/4 border border-transparent'}`}>
            {view === item.key && (
              <motion.div
                layoutId="nav-active-indicator"
                className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-accent-500 shadow-[0_0_8px_var(--color-accent-500)]"
                transition={{ type: 'spring', stiffness: 350, damping: 30 }}
              />
            )}
            {item.icon}
            {!rail && <span className="whitespace-nowrap">{item.label}</span>}
          </button>
        ))}
      </nav>

      {/* Recent Jobs History — the list needs labels to be useful, so the
          rail hides it rather than showing a column of unreadable stubs. */}
      <div className={`px-4 pb-5 pt-3 ${rail ? 'hidden' : ''}`}>
        <div className="flex justify-between items-center mb-2.5 px-2">
          <span className="text-[10px] font-bold text-base-500 uppercase tracking-widest whitespace-nowrap">Recent Jobs</span>
          <button
            onClick={onRefreshJobs}
            className="text-base-500 hover:text-accent-400 transition-colors p-1 rounded-lg hover:bg-white/5"
            title="Refresh list"
            aria-label="Refresh job list"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
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
