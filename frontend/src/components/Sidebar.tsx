import {
  LayoutDashboard, FileEdit, Plus, RefreshCw, Sparkles, Trash2, RotateCcw,
  PanelLeftClose, PanelLeftOpen, Cpu, ChevronDown, ChevronRight, X, type LucideIcon
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
  /** Foundation LLM for the session, and the opener for its settings dialog. */
  selectedModel?: string;
  onOpenSettings?: () => void;
  /** Per-run generation parameters, edited here rather than in the composer. */
  tone: string;
  setTone: (t: string) => void;
  sections: number;
  setSections: (n: number) => void;
  numImages: number;
  setNumImages: (n: number) => void;
  keywordsInput: string;
  setKeywordsInput: (k: string) => void;
}

/** Parse a number field, holding the previous value for input the field cannot
    represent (empty, "-", "abc"). `min`/`max` attributes only gate form
    submission, so the range is enforced here instead: `sections` and
    `numImages` are sent to POST /api/jobs. */
export function clampInt(raw: string, lo: number, hi: number, fallback: number): number {
  const n = Number(raw);
  if (raw.trim() === '' || !Number.isFinite(n)) return fallback;
  return Math.min(hi, Math.max(lo, Math.round(n)));
}

/** Job status map (shared spec): a dot per status plus a word for screen readers. */
const STATUS: Record<Job['status'], { dot: string; word: string }> = {
  completed:         { dot: 'dot dot-success', word: 'Completed' },
  awaiting_approval: { dot: 'dot dot-warning', word: 'Awaiting approval' },
  running:           { dot: 'dot live-dot',    word: 'Running' },
  pending:           { dot: 'dot dot-pending', word: 'Queued' },
  failed:            { dot: 'dot dot-error',   word: 'Failed' },
};

export function Sidebar({
  view, navTo, jobs, currentJob, loadJob, startNewJob, onDeleteJob, onResumeJob,
  isMobileOpen, onCloseMobile, isCollapsed = false, onToggleCollapse, onRefreshJobs,
  selectedModel, onOpenSettings,
  tone, setTone, sections, setSections, numImages, setNumImages, keywordsInput, setKeywordsInput
}: SidebarProps) {
  // Collapse is a desktop affordance; on mobile the drawer is either open
  // (full width) or off-screen, so ignore it there.
  const rail = isCollapsed && !isMobileOpen;
  const navItems: { key: ViewState; icon: LucideIcon; label: string }[] = [
    { key: 'chat',    icon: LayoutDashboard, label: 'Dashboard' },
    { key: 'content', icon: FileEdit,        label: 'Studio' },
  ];

  // Sits in the brand row when expanded; at the bottom of the 72px rail,
  // where the brand row has no room beside the mark.
  const collapseToggle = onToggleCollapse && (
    <button
      onClick={onToggleCollapse}
      className={`btn btn-ghost btn-icon btn-sm hidden lg:inline-flex ${rail ? 'self-center' : 'ml-auto'}`}
      title={rail ? 'Expand sidebar' : 'Collapse sidebar'}
      aria-label={rail ? 'Expand sidebar' : 'Collapse sidebar'}
      aria-expanded={!rail}
    >
      {rail ? <PanelLeftOpen aria-hidden="true" /> : <PanelLeftClose aria-hidden="true" />}
    </button>
  );

  return (
    <>
      {/* Mobile Backdrop */}
      {isMobileOpen && (
        <div
          onClick={onCloseMobile}
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
        />
      )}
      <aside id="app-sidebar" className={`h-full fixed left-0 top-0 bg-canvas border-r border-line flex flex-col z-50 overflow-y-auto overflow-x-hidden transition-[transform,width,visibility] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:translate-x-0 ${rail ? 'w-[280px] lg:w-[72px]' : 'w-[280px] lg:w-[260px]'} ${isMobileOpen ? 'translate-x-0' : '-translate-x-full max-lg:invisible lg:translate-x-0'}`}>
      {/* Brand row: same h-14 hairline as TopNav */}
      <div className={`h-14 shrink-0 flex items-center gap-2.5 border-b border-line ${rail ? 'justify-center px-0' : 'px-4'}`}>
        <div className="grid size-7 shrink-0 place-items-center rounded-lg bg-accent-500 text-on-accent">
          <Sparkles className="size-4" aria-hidden="true" />
        </div>
        {!rail && (
          <h1 className="min-w-0 truncate text-ui font-semibold tracking-[-0.01em] text-base-50">AI Content Factory</h1>
        )}
        {!rail && collapseToggle}
        {isMobileOpen && (
          <button onClick={onCloseMobile} className="btn btn-ghost btn-icon btn-sm ml-auto lg:hidden" aria-label="Close menu" title="Close menu">
            <X aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="flex-1 min-h-0 flex flex-col px-3 pt-3">
        {rail ? (
          <button onClick={startNewJob} className="btn btn-secondary btn-icon self-center" title="New job" aria-label="New job">
            <Plus aria-hidden="true" />
          </button>
        ) : (
          <button onClick={startNewJob} className="btn btn-secondary w-full justify-start">
            <Plus aria-hidden="true" /> New job
          </button>
        )}

        <nav className={`mt-3 flex flex-col gap-0.5 ${rail ? 'items-center' : ''}`}>
          {navItems.map(item => {
            const active = view === item.key;
            const Icon = item.icon;
            return (
              <button key={item.key} onClick={() => navTo(item.key)}
                title={rail ? item.label : undefined}
                aria-label={item.label}
                aria-current={active ? 'page' : undefined}
                className={rail
                  ? `btn btn-ghost btn-icon relative ${active ? 'bg-selected text-base-50' : ''}`
                  : `group relative flex h-8 [@media(pointer:coarse)]:h-10 items-center gap-2.5 rounded-lg px-2.5 text-ui font-medium transition-colors ${active ? 'bg-selected text-base-50' : 'text-base-400 hover:bg-hover hover:text-base-100'}`}>
                {active && (
                  <motion.span
                    layoutId="nav-active"
                    className={`absolute top-1.5 bottom-1.5 w-0.5 rounded-full bg-indicator ${rail ? '-left-5' : '-left-3'}`}
                    transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                  />
                )}
                <Icon className={`size-4 shrink-0 ${active ? 'text-indicator' : ''}`} aria-hidden="true" />
                {!rail && <span className="whitespace-nowrap">{item.label}</span>}
              </button>
            );
          })}
        </nav>

        {/* Recent jobs. The list needs labels to be useful, so the rail hides
            it rather than showing a column of unreadable stubs. */}
        <div className={`mt-6 flex-1 min-h-0 flex flex-col ${rail ? 'hidden' : ''}`}>
          <div className="h-6 [@media(pointer:coarse)]:h-10 px-2.5 mb-1 flex items-center justify-between">
            <span className="text-xs font-medium text-base-500">Recent</span>
            <button
              onClick={onRefreshJobs}
              className="btn btn-ghost btn-icon btn-sm -mr-1.5"
              title="Refresh list"
              aria-label="Refresh job list"
            >
              <RefreshCw aria-hidden="true" />
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1 py-1 flex flex-col gap-px">
            {jobs.slice(0, 10).map(job => {
              const active = currentJob?.id === job.id;
              const status = STATUS[job.status];
              return (
                <motion.div
                  key={job.id}
                  className={`group relative flex h-8 [@media(pointer:coarse)]:h-10 shrink-0 items-center rounded-lg pr-1 text-ui transition-colors ${active ? 'bg-selected text-base-50' : 'text-base-300 hover:bg-hover hover:text-base-100'}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.15 }}
                >
                  <button onClick={() => loadJob(job.id)}
                    aria-current={active ? 'true' : undefined}
                    className="flex h-full min-w-0 flex-1 items-center gap-2.5 rounded-lg pl-2.5 text-left">
                    <span className={status.dot} title={status.word} aria-hidden="true" />
                    <span className="sr-only">{status.word}, </span>
                    <span className="flex-1 truncate">{job.topic}</span>
                  </button>
                  {(onDeleteJob || (onResumeJob && job.status === 'failed')) && (
                    <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100 transition-opacity">
                      {onResumeJob && job.status === 'failed' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onResumeJob(job.id);
                          }}
                          className="btn btn-ghost btn-icon btn-sm"
                          title="Resume from checkpoint"
                          aria-label="Resume from checkpoint"
                        >
                          <RotateCcw aria-hidden="true" />
                        </button>
                      )}
                      {onDeleteJob && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteJob(job.id);
                          }}
                          className="btn btn-danger btn-icon btn-sm"
                          title="Delete job"
                          aria-label="Delete job"
                        >
                          <Trash2 aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  )}
                </motion.div>
              );
            })}
            {jobs.length === 0 && <div className="px-2.5 py-3 text-xs text-base-500">No jobs in history</div>}
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-line p-3 flex flex-col gap-1">
        {/* Which model powers the session is a workspace setting, not something
            that describes the request being typed, so it lives here rather
            than in the composer. */}
        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            title={rail ? `Foundation LLM: ${selectedModel}` : 'Change foundation LLM'}
            aria-label="Change foundation LLM"
            className={rail ? 'btn btn-ghost btn-icon self-center' : 'btn btn-ghost w-full justify-start'}
          >
            <Cpu className="text-base-500" aria-hidden="true" />
            {!rail && (
              <>
                <span className="min-w-0 truncate font-mono font-normal text-xs text-base-200">{selectedModel}</span>
                <ChevronDown className="ml-auto size-3.5 text-base-500" aria-hidden="true" />
              </>
            )}
          </button>
        )}

        {/* The run's parameters. Their lifetime is the session, not the message
            being typed, so they sit here rather than in the composer. Open by
            default so tone and keywords stay visible; the rail hides them
            because a bare field with no label is not usable. */}
        <details open className={`group/rs ${rail ? 'hidden' : ''}`}>
          <summary className="flex h-auto min-h-8 [@media(pointer:coarse)]:min-h-10 flex-wrap cursor-pointer items-center gap-x-2 rounded-lg px-2.5 py-1.5 text-xs font-medium text-base-400 hover:bg-hover hover:text-base-100 transition-colors">
            <ChevronRight className="size-3.5 shrink-0 transition-transform group-open/rs:rotate-90" aria-hidden="true" />
            <span className="whitespace-nowrap">Run settings</span>
            <span className="basis-full truncate pl-[22px] text-base-500">{tone.charAt(0).toUpperCase() + tone.slice(1)} · {sections} sections · {numImages} images</span>
          </summary>
          <div className="grid grid-cols-2 gap-3 px-1 pt-3 pb-1">
            <div className="col-span-2">
              <label htmlFor="rs-tone" className="field-label">Tone</label>
              <div className="select-wrap">
                <select
                  id="rs-tone"
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="field"
                >
                  <option value="professional">Professional</option>
                  <option value="conversational">Conversational</option>
                  <option value="technical">Technical</option>
                  <option value="educational">Educational</option>
                  <option value="persuasive">Persuasive</option>
                  <option value="inspirational">Inspirational</option>
                </select>
                <ChevronDown aria-hidden="true" />
              </div>
            </div>

            <div className="col-span-2">
              <label htmlFor="rs-keywords" className="field-label">Target keywords</label>
              <input
                id="rs-keywords"
                value={keywordsInput}
                onChange={(e) => setKeywordsInput(e.target.value)}
                placeholder="e.g. AI agents"
                className="field"
              />
            </div>

            {/* Side by side: both are single digits. */}
            <div>
              <label htmlFor="rs-sections" className="field-label">Sections</label>
              <input
                id="rs-sections"
                type="number"
                min={2}
                max={6}
                step={1}
                value={sections}
                onChange={(e) => setSections(clampInt(e.target.value, 2, 6, sections))}
                className="field font-mono"
              />
            </div>

            <div>
              <label htmlFor="rs-images" className="field-label">Images</label>
              <input
                id="rs-images"
                type="number"
                min={0}
                max={5}
                step={1}
                value={numImages}
                onChange={(e) => setNumImages(clampInt(e.target.value, 0, 5, numImages))}
                className="field font-mono"
              />
            </div>
          </div>
        </details>

        {rail && collapseToggle}
      </div>
    </aside>
    </>
  );
}
