import React, { useState, useEffect, useMemo } from 'react';
import { motion } from 'motion/react';
import {
  Clock, Podcast, Film, Share2, Download,
  FileText, Image as ImageIcon, Gauge, Loader2, AlertTriangle, ChevronDown,
  Copy, RefreshCw, Trash2,
  Edit3, FileCode, Check, Printer, ExternalLink, Save
} from 'lucide-react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { APIClient, Job, AgentEvent, API_BASE_URL, withApiKey } from './api';
import { TabButton } from './components/TabButton';
import { EmptyState } from './components/EmptyState';
import { LoadingState } from './components/LoadingState';
import { DeepEvalSection } from './components/DeepEvalSection';
import { QAAuditSection } from './components/QAAuditSection';
import { RubricDetailCard } from './components/RubricDetailCard';
import { PodcastPlayer } from './components/PodcastPlayer';
import { useJobActions } from './hooks/useJobActions';
import { useGEvalRadar } from './hooks/useGEvalRadar';

type ViewState = 'chat' | 'content';
type TabState = 'blog' | 'geval' | 'video' | 'podcast' | 'images' | 'social';

const generatedFigureHtmlToMarkdown = (content: string) => content.replace(
  /<figure\b[^>]*>[\s\S]*?<\/figure>/gi,
  (figureHtml) => {
    const imageTag = figureHtml.match(/<img\b[^>]*>/i)?.[0];
    const src = imageTag?.match(/\bsrc=["']([^"']+)["']/i)?.[1]?.trim();
    if (!src) return '';

    const alt = imageTag?.match(/\balt=["']([^"']*)["']/i)?.[1]
      ?.replace(/([\[\]\\])/g, '\\$1') || 'Blog image';
    const caption = figureHtml.match(/<figcaption\b[^>]*>([\s\S]*?)<\/figcaption>/i)?.[1]
      ?.replace(/<[^>]+>/g, '')
      .trim();

    return `\n\n![${alt}](<${src}>)${caption ? `\n\n*${caption}*` : ''}\n\n`;
  }
);

const REMARK_PLUGINS = [remarkGfm];

// Wide tables scroll inside their own frame instead of the article column.
const MARKDOWN_COMPONENTS: Components = {
  table: ({ node: _node, ...p }) => (
    <div className="my-7 overflow-x-auto rounded-lg ring-1 ring-line"><table {...p} /></div>
  ),
};

const TABS: { id: TabState; label: string; icon: React.ReactNode }[] = [
  { id: 'blog', label: 'Blog', icon: <FileText /> },
  { id: 'geval', label: 'G-Eval audit', icon: <Gauge /> },
  { id: 'video', label: 'Video', icon: <Film /> },
  { id: 'podcast', label: 'Podcast', icon: <Podcast /> },
  { id: 'social', label: 'Social', icon: <Share2 /> },
  { id: 'images', label: 'Images', icon: <ImageIcon /> },
];

// Status map (spec section 4): dot + badge + copy per job status.
const STATUS_BADGE: Record<Job['status'], { badge: string; dot: string; label: string }> = {
  completed: { badge: 'badge', dot: 'dot dot-success', label: 'Completed' },
  awaiting_approval: { badge: 'badge badge-warning', dot: 'dot dot-warning', label: 'Awaiting approval' },
  running: { badge: 'badge badge-accent', dot: 'dot live-dot', label: 'Running' },
  pending: { badge: 'badge', dot: 'dot dot-pending', label: 'Queued' },
  failed: { badge: 'badge badge-error', dot: 'dot dot-error', label: 'Failed' },
};

// Close the native <details> menu an item lives in.
const closeMenu = (el: HTMLElement) => el.closest('details')?.removeAttribute('open');

// Render hashtags in a quieter tone; split() with a capture group puts the
// matches at odd indices.
const withHashtags = (text: string) =>
  text.split(/(#[\p{L}\p{N}_]+)/u).map((part, i) =>
    i % 2 ? <span key={i} className="text-base-400">{part}</span> : part
  );

const humaniseFilename = (name: string) => name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ');

const resolveContentImageUrls = (content: string, jobId?: string) => {
  if (!content) return '';
  if (!jobId) return generatedFigureHtmlToMarkdown(content);
  const baseUrl = API_BASE_URL || `http://${window.location.hostname}:8000`;
  // withApiKey is a no-op unless VITE_API_KEY is set; <img src> can't send headers.
  let resolved = content.replace(
    /src=["'](?:\.\/)?(assets\/images\/[^"']+)["']/g,
    (_m, p1) => `src="${withApiKey(`${baseUrl}/api/files/${jobId}/${p1}`)}"`
  );
  resolved = resolved.replace(
    /\((?:\.\/)?(assets\/images\/[^\)]+)\)/g,
    (_m, p1) => `(${withApiKey(`${baseUrl}/api/files/${jobId}/${p1}`)})`
  );
  return generatedFigureHtmlToMarkdown(resolved);
};

export function ContentView({ navTo, currentJob, refreshJob, events = [], reconnectWS, onDeleteJob }: { navTo: (v: ViewState) => void, currentJob: Job | null, refreshJob: () => void, events?: AgentEvent[], reconnectWS?: (jobId: string) => void, onDeleteJob?: (id: string) => void }) {
  const [activeTab, setActiveTab] = useState<TabState>('blog');
  const [hoveredMetric, setHoveredMetric] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editedContent, setEditedContent] = useState<string>('');
  const [copied, setCopied] = useState<boolean>(false);
  const [copiedChannel, setCopiedChannel] = useState<'linkedin' | 'x' | null>(null);

  // Seed the editor from the server copy whenever the job (or its content)
  // changes. Deliberately NOT keyed on isEditing: re-running on every
  // Edit -> Preview toggle silently overwrote whatever the user had typed.
  // `editedContent` is the single source of truth for the article from here on,
  // so preview, copy, and the Markdown export all show the edited text.
  useEffect(() => {
    setEditedContent(currentJob?.final_content ?? '');
  }, [currentJob?.id, currentJob?.final_content]);

  // PDF/DOCX/HTML exports and the media re-runs read the server copy, so an
  // edit only reaches them once saved.
  const [saving, setSaving] = useState<boolean>(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const isDirty = editedContent !== (currentJob?.final_content ?? '');
  useEffect(() => setSaveError(null), [currentJob?.id]);

  const { triggering, getCurrentRunEvents, getLastTaskError, handleTrigger, isTaskRunning } = useJobActions({
    currentJob,
    events,
    refreshJob,
    reconnectWS,
  });
  // Reset active tab to blog when switching jobs
  useEffect(() => {
    if (currentJob?.id) {
      setActiveTab('blog');
    }
  }, [currentJob?.id]);

  const radarPoints = useGEvalRadar(currentJob);

  // Parsing a 2-3k word article is the heaviest thing this view renders, and it
  // re-renders on every agent event and every 3 s poll while a manual task runs.
  // Re-parse only when the text (or the job its image URLs point at) changes.
  const articleBody = useMemo(() => (
    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={MARKDOWN_COMPONENTS}>
      {resolveContentImageUrls(editedContent, currentJob?.id)}
    </ReactMarkdown>
  ), [editedContent, currentJob?.id]);

  // ffmpeg keeps muxing for minutes after the last frame, so the backend's
  // render ticks end on "Exporting video..." (Graph/agents/video.py). Echo the
  // stage in the headline: a frozen "Generating Video..." reads as a stall.
  const videoEvents = getCurrentRunEvents('video');
  const videoTitle = videoEvents[videoEvents.length - 1]?.message.startsWith('Exporting')
    ? 'Exporting Video...'
    : 'Generating Video...';

  if (!currentJob) {
    return (
      <main className="flex-1 relative overflow-y-auto w-full">
        <div className="mx-auto w-full max-w-5xl px-4 md:px-10 pt-6 md:pt-8 pb-16">
          <EmptyState
            icon={<FileText />}
            title="Your studio is ready"
            description="Create a generation job to review, edit, export, and extend your content here."
            onGenerate={() => navTo('chat')}
            actionLabel="Create a new job"
          />
        </div>
      </main>
    );
  }

  const saveEdits = async (): Promise<boolean> => {
    setSaving(true);
    setSaveError(null);
    try {
      await APIClient.saveBlog(currentJob.id, editedContent);
      refreshJob();
      return true;
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save article');
      return false;
    } finally {
      setSaving(false);
    }
  };

  // Server-side exports render the saved copy: save unsaved edits first, then
  // start the download. With nothing unsaved the link behaves as before.
  const exportSaved = (format: 'pdf' | 'docx' | 'html') => async (e: React.MouseEvent) => {
    if (!isDirty) return;
    e.preventDefault();
    if (await saveEdits()) window.location.assign(APIClient.getExportUrl(currentJob.id, format));
  };


  // Show the Check only once the clipboard write actually succeeded.
  const copyPost = (channel: 'linkedin' | 'x', text: string) =>
    navigator.clipboard.writeText(text).then(() => {
      setCopiedChannel(channel);
      setTimeout(() => setCopiedChannel(null), 2000);
    }).catch(() => { });

  // Roving focus for the tablist: arrows wrap, Home/End jump to the ends.
  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const i = TABS.findIndex((t) => t.id === activeTab);
    const last = TABS.length - 1;
    const next = e.key === 'ArrowRight' ? (i + 1) % TABS.length
      : e.key === 'ArrowLeft' ? (i - 1 + TABS.length) % TABS.length
        : e.key === 'Home' ? 0
          : e.key === 'End' ? last
            : -1;
    if (next < 0) return;
    e.preventDefault();
    setActiveTab(TABS[next].id);
    e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus();
  };

  const status = STATUS_BADGE[currentJob.status] ?? STATUS_BADGE.pending;
  const createdAt = currentJob.created_at ? new Date(currentJob.created_at) : null;
  const imageFiles = currentJob.image_files ?? [];
  const canAudit = currentJob.status === 'completed';
  const radarAxes = [
    { key: 'coherence', label: 'Coherence', x: 50, y: 15, anchor: 'middle' },
    { key: 'relevance', label: 'Relevance', x: 83, y: 51.5, anchor: 'start' },
    { key: 'accuracy', label: 'Accuracy', x: 50, y: 88, anchor: 'middle' },
    { key: 'tone_alignment', label: 'Tone', x: 17, y: 51.5, anchor: 'end' },
  ] as const;

  const imageTile = (imgPath: string, idx: number, single = false) => {
    const url = APIClient.getFileUrl(currentJob.id, imgPath);
    const filename = imgPath.split('/').pop() || `image_${idx + 1}.png`;
    const name = humaniseFilename(filename);
    return (
      <div key={imgPath} className={`group relative overflow-hidden rounded-xl ring-1 ring-line bg-surface ${single ? '' : 'aspect-[16/10]'}`}>
        <img
          src={url}
          alt={name}
          className={`transition-transform duration-[400ms] group-hover:scale-[1.02] ${single ? 'block h-auto w-full object-contain' : 'size-full object-cover'}`}
        />
        <div className={`absolute inset-0 bg-linear-to-t from-black/60 via-transparent transition-opacity ${single ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100'}`}>
          <div className="absolute right-2 top-2 flex gap-1.5">
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="grid size-8 [@media(pointer:coarse)]:size-10 place-items-center rounded-lg bg-black/50 text-white backdrop-blur hover:bg-black/70 transition-colors"
              aria-label={`Open ${name} in a new tab`}
              title="View full image in new tab"
            >
              <ExternalLink className="size-4" />
            </a>
            <a
              href={url}
              download={filename}
              target="_blank"
              rel="noreferrer"
              className="grid size-8 [@media(pointer:coarse)]:size-10 place-items-center rounded-lg bg-black/50 text-white backdrop-blur hover:bg-black/70 transition-colors"
              aria-label={`Download ${name}`}
              title="Download"
            >
              <Download className="size-4" />
            </a>
          </div>
          <span className="absolute bottom-2 left-3 right-3 font-mono text-xs text-white/85 truncate">{name}</span>
        </div>
      </div>
    );
  };

  return (
    <main className="flex-1 relative overflow-y-auto w-full scroll-pt-16">
      <div className="@container mx-auto w-full max-w-5xl px-4 md:px-10 pt-6 pb-16">

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="font-mono text-xs text-base-400">Job {currentJob.id.slice(0, 8)}</p>
            <h1 className="mt-1 font-serif text-title-sm md:text-title text-base-50 text-balance line-clamp-2">{currentJob.topic}</h1>
            <div className="mt-2 flex items-center gap-3 text-xs text-base-400">
              <span className={status.badge}><span className={status.dot} />{status.label}</span>
              {createdAt && !isNaN(createdAt.getTime()) && (
                <time dateTime={currentJob.created_at} className="font-mono tabular-nums">
                  {createdAt.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                </time>
              )}
            </div>
          </div>
          {onDeleteJob && (
            <button
              type="button"
              onClick={() => onDeleteJob(currentJob.id)}
              className="btn btn-danger btn-icon btn-sm shrink-0"
              aria-label="Delete job"
              title="Delete job"
            >
              <Trash2 />
            </button>
          )}
        </div>

        {/* Tabs */}
        <div
          role="tablist"
          aria-label="Studio sections"
          onKeyDown={handleTabKeyDown}
          className="mt-6 flex gap-1 overflow-x-auto -mx-4 px-4 md:-mx-1 md:px-1 scroll-px-4 shadow-[inset_0_-1px_0_var(--color-line)] [scrollbar-width:none]"
        >
          {TABS.map((t) => (
            <TabButton<TabState> key={t.id} id={t.id} icon={t.icon} label={t.label} activeTab={activeTab} setActiveTab={setActiveTab} />
          ))}
        </div>

        {/* Tab panel: opacity only, no exit, so no stacking or height jump */}
        <motion.div
          key={activeTab}
          role="tabpanel"
          id={`panel-${activeTab}`}
          aria-labelledby={`tab-${activeTab}`}
          className="mt-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
        >

          {/* BLOG TAB */}
          {activeTab === 'blog' && (
            <div>
              {currentJob.final_content && (
                <div className="sticky top-0 z-10 -mx-1 px-1 mb-6 flex flex-wrap items-center justify-between gap-2 py-2 bg-canvas/85 backdrop-blur-md border-b border-line">
                  {/* Measured token usage and cost, recorded per run by
                      Agents_backend/usage.py and read off the job row. Never
                      estimated client-side: the previous badge multiplied the
                      word count by a magic constant and was 2x out on cost.
                      Absent usage means "not measured", so it renders as such
                      rather than as a zero or a guess. */}
                  <p className="font-mono text-xs text-base-400 tabular-nums">
                    {currentJob.usage ? (
                      <>
                        <span title={`${currentJob.usage.total.calls} model calls · ${currentJob.usage.total.input_tokens.toLocaleString()} in / ${currentJob.usage.total.output_tokens.toLocaleString()} out`}>
                          {currentJob.usage.total.total_tokens.toLocaleString()} tokens
                        </span>
                        {' · '}
                        <span
                          title={currentJob.usage.priced
                            ? 'Estimated from published list prices for the models actually called'
                            : 'Partial: at least one model called has no published price, so the real cost is higher'}
                        >
                          {/* A trailing + when usage.priced is false — that flag
                              means a called model had no known price, so this
                              is a floor, not the total. */}
                          ${currentJob.usage.total.cost_usd.toFixed(4)}{currentJob.usage.priced ? '' : '+'}
                        </span>
                      </>
                    ) : (
                      <span title="This job finished before usage metering existed, or never completed.">
                        Usage not recorded
                      </span>
                    )}
                  </p>

                  <div className="ml-auto flex items-center gap-1.5">
                    {saveError && !isEditing && (
                      <span role="alert" className="text-xs text-signal-error">{saveError}</span>
                    )}

                    <button
                      type="button"
                      onClick={() => setIsEditing(!isEditing)}
                      aria-pressed={isEditing}
                      className="btn btn-secondary btn-sm"
                    >
                      <Edit3 />
                      {isEditing ? 'Preview' : 'Edit'}
                    </button>

                    {(isDirty || saving) && (
                      <button
                        type="button"
                        onClick={saveEdits}
                        disabled={saving}
                        className="btn btn-primary btn-sm"
                        title="Save your edits so exports and media re-runs use them"
                      >
                        {saving ? <Loader2 className="animate-spin" /> : <Save />}
                        {saving ? 'Saving…' : 'Save'}
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(editedContent);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 2000);
                      }}
                      className="btn btn-ghost btn-icon btn-sm"
                      aria-label={copied ? 'Copied' : 'Copy Markdown'}
                      title={copied ? 'Copied' : 'Copy Markdown'}
                    >
                      {copied ? <Check className="text-signal-success" /> : <Copy />}
                    </button>

                    <details
                      className="relative group/menu"
                      // A null relatedTarget (click that does not focus, alt-tab) must not close the menu.
                      onBlur={(e) => { const n = e.relatedTarget as Node | null; if (n && !e.currentTarget.contains(n)) e.currentTarget.removeAttribute('open'); }}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') {
                          e.currentTarget.removeAttribute('open');
                          e.currentTarget.querySelector('summary')?.focus();
                        }
                      }}
                    >
                      <summary className="btn btn-secondary btn-sm">
                        <Download />
                        Export
                        <ChevronDown className="transition-transform group-open/menu:rotate-180" />
                      </summary>
                      <div className="surface-raised menu">
                        <a
                          className="menu-item"
                          href={APIClient.getExportUrl(currentJob.id, 'pdf')}
                          onClick={(e) => { const el = e.currentTarget; exportSaved('pdf')(e); closeMenu(el); }}
                          target="_blank"
                          rel="noreferrer"
                          title="Download as publication-ready PDF"
                        >
                          <Printer />PDF<span className="ml-auto font-mono text-xs text-base-500">.pdf</span>
                        </a>
                        <a
                          className="menu-item"
                          href={APIClient.getExportUrl(currentJob.id, 'docx')}
                          onClick={(e) => { const el = e.currentTarget; exportSaved('docx')(e); closeMenu(el); }}
                          target="_blank"
                          rel="noreferrer"
                          title="Download as Microsoft Word document (.docx)"
                        >
                          <FileText />Word<span className="ml-auto font-mono text-xs text-base-500">.docx</span>
                        </a>
                        <a
                          className="menu-item"
                          href={APIClient.getExportUrl(currentJob.id, 'html')}
                          onClick={(e) => { const el = e.currentTarget; exportSaved('html')(e); closeMenu(el); }}
                          target="_blank"
                          rel="noreferrer"
                          title="Download as standalone HTML document"
                        >
                          <FileCode />HTML<span className="ml-auto font-mono text-xs text-base-500">.html</span>
                        </a>
                        <button
                          type="button"
                          className="menu-item"
                          onClick={(e) => {
                            const rawText = editedContent;
                            const resolvedText = resolveContentImageUrls(rawText, currentJob.id);
                            const filename = `${(currentJob.topic || 'blog').replace(/[^a-z0-9]/gi, '_')}.md`;
                            const blob = new Blob([resolvedText], { type: 'text/markdown;charset=utf-8' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            URL.revokeObjectURL(url);
                            closeMenu(e.currentTarget);
                          }}
                          title="Download Markdown with picture URLs"
                        >
                          <Download />Markdown<span className="ml-auto font-mono text-xs text-base-500">.md</span>
                        </button>
                      </div>
                    </details>
                  </div>
                </div>
              )}

              {currentJob.final_content && isEditing ? (
                <div>
                  <div className="mb-2 flex items-center justify-between gap-4 text-xs text-base-500">
                    <span className="font-medium text-base-300">Markdown editor</span>
                    <span className={saveError ? 'text-signal-error' : undefined}>
                      {saveError
                        ? saveError
                        : isDirty
                          ? 'Unsaved changes — preview, copy and Markdown export use them now; Save for PDF/DOCX/HTML and media re-runs'
                          : 'All changes saved'}
                    </span>
                  </div>
                  <textarea
                    value={editedContent}
                    onChange={(e) => setEditedContent(e.target.value)}
                    aria-label="Article Markdown"
                    className="field font-mono text-base md:text-[13px] leading-6 min-h-[60vh] p-6 rounded-2xl"
                  />
                </div>
              ) : (
                <article className="rounded-2xl bg-surface ring-1 ring-line shadow-[var(--elev-1)] px-5 py-10 @2xl:px-16 @2xl:pt-12 @2xl:pb-16 max-sm:bg-transparent max-sm:ring-0 max-sm:shadow-none max-sm:px-0 max-sm:py-2">
                  {currentJob.final_content ? (
                    <div className="prose prose-editorial">
                      {articleBody}
                    </div>
                  ) : currentJob.status === 'running' || currentJob.status === 'awaiting_approval' || currentJob.status === 'pending' ? (
                    <div className="flex flex-col items-center text-center">
                      <div className="mb-4 grid size-10 place-items-center rounded-lg bg-hover ring-1 ring-line [&_svg]:size-5">
                        <Loader2 className="animate-spin text-accent-400" />
                      </div>
                      <h3 className="text-heading text-base-50">Agents are at work…</h3>
                      <p className="mt-1.5 max-w-sm text-ui text-base-400">Head back to the Dashboard to see live updates.</p>
                    </div>
                  ) : currentJob.status === 'failed' ? (
                    <div className="flex flex-col items-center text-center">
                      <div className="mb-4 grid size-10 place-items-center rounded-lg bg-hover ring-1 ring-line text-signal-error [&_svg]:size-5">
                        <AlertTriangle />
                      </div>
                      <h3 className="text-heading text-base-50">Generation failed</h3>
                      <p role="alert" className="mt-4 rounded-lg bg-signal-error-dim px-3 py-2 text-left text-ui text-signal-error">
                        {currentJob.error_message || 'An unknown error occurred.'}
                      </p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center text-center">
                      <div className="mb-4 grid size-10 place-items-center rounded-lg bg-hover ring-1 ring-line text-base-300 [&_svg]:size-5">
                        <Clock />
                      </div>
                      <p className="text-ui text-base-400">Content not available for this job.</p>
                    </div>
                  )}
                </article>
              )}
            </div>
          )}

          {/* G-EVAL TAB */}
          {activeTab === 'geval' && (
            <div className="grid gap-4 @xl:grid-cols-2">
              {/* KPI strip. QA is always mounted: it can be re-run on a
                  finished blog even when the G-Eval pass never produced scores. */}
              <QAAuditSection
                currentJob={currentJob}
                isRunning={!!triggering['qa'] || isTaskRunning('qa_agent')}
                onRun={() => handleTrigger('qa')}
              />
              {/* DEEPEVAL ACADEMIC AUDIT (Liu et al. 2023, deepeval library).
                  Renders its KPI tile here and its rubric grid at the end
                  of this grid (order-last). */}
              {canAudit && (
                <DeepEvalSection
                  currentJob={currentJob}
                  isRunning={!!triggering['deepeval']}
                  onRun={() => handleTrigger('deepeval')}
                />
              )}

              {currentJob.geval_scores ? (
                <>
                  {/* Overall grade + radar */}
                  <section className="@xl:col-span-2 card p-6 grid gap-8 @2xl:grid-cols-[200px_1fr] @4xl:grid-cols-[160px_minmax(0,320px)_1fr] items-center">
                    <div className="flex flex-col items-center gap-4">
                      <h3 className="text-xs font-medium text-base-500">Weighted grade</h3>
                      <div
                        className="score-ring"
                        style={{ '--score-pct': (currentJob.geval_scores.overall_score / 5) * 100 } as React.CSSProperties}
                      >
                        <div className="score-ring-inner">
                          <span className="text-kpi text-base-50 tabular-nums">{currentJob.geval_scores.overall_score}</span>
                          <span className="text-xs text-base-500">of 5</span>
                        </div>
                      </div>
                    </div>

                    {/* SVG radar chart */}
                    <svg viewBox="4 9 102 83" className="mx-auto w-full max-w-xs h-auto overflow-visible select-none" role="img" aria-label="G-Eval scores radar chart">
                      {[1, 2, 3, 4, 5].map((lvl) => (
                        <circle key={lvl} cx="50" cy="50" r={lvl * 6} fill="none" stroke="var(--color-line-strong)" strokeWidth="0.5" />
                      ))}
                      <line x1="50" y1="20" x2="50" y2="80" stroke="var(--color-line-strong)" strokeWidth="0.5" />
                      <line x1="20" y1="50" x2="80" y2="50" stroke="var(--color-line-strong)" strokeWidth="0.5" />

                      <polygon points={radarPoints} fill="rgba(var(--accent-rgb),0.14)" stroke="var(--color-indicator)" strokeWidth={0.75} strokeLinejoin="round" />

                      {/* Axis labels (top, right, bottom, left) */}
                      {radarAxes.map((a) => (
                        <text
                          key={a.key}
                          x={a.x}
                          y={a.y}
                          fontSize="3.8"
                          textAnchor={a.anchor}
                          className={`cursor-pointer transition-colors ${hoveredMetric === a.key ? 'fill-base-50 font-medium' : 'fill-base-400'}`}
                          onMouseEnter={() => setHoveredMetric(a.key)}
                          onMouseLeave={() => setHoveredMetric(null)}
                        >
                          {a.label}
                        </text>
                      ))}

                      {/* Active points */}
                      {(() => {
                        const scores = currentJob.geval_scores;
                        const center = 50;
                        const scale = 30;
                        const maxVal = 5;
                        const items = [
                          { key: 'coherence', score: scores.coherence.score, angle: -Math.PI / 2 },
                          { key: 'relevance', score: scores.relevance.score, angle: 0 },
                          { key: 'accuracy', score: scores.accuracy.score, angle: Math.PI / 2 },
                          { key: 'tone_alignment', score: scores.tone_alignment.score, angle: Math.PI }
                        ];

                        return items.map((itm) => {
                          const dist = (itm.score / maxVal) * scale;
                          const cx = center + dist * Math.cos(itm.angle);
                          const cy = center + dist * Math.sin(itm.angle);
                          const active = hoveredMetric === itm.key;
                          return (
                            <circle key={itm.key} cx={cx} cy={cy} r={active ? 2.5 : 1.5} fill="var(--color-indicator)" stroke={active ? 'var(--color-surface)' : 'none'} strokeWidth="0.75" className="cursor-pointer" onMouseEnter={() => setHoveredMetric(itm.key)} onMouseLeave={() => setHoveredMetric(null)} />
                          );
                        });
                      })()}
                    </svg>

                    <dl className="hidden @4xl:grid gap-1">
                      {radarAxes.map((a) => (
                        <div
                          key={a.key}
                          onMouseEnter={() => setHoveredMetric(a.key)}
                          onMouseLeave={() => setHoveredMetric(null)}
                          className={`flex items-baseline justify-between gap-4 rounded-md px-3 py-2 transition-colors ${hoveredMetric === a.key ? 'bg-selected' : ''}`}
                        >
                          <dt className="text-ui text-base-300">{a.label}</dt>
                          <dd className="font-mono text-[13px] text-base-100 tabular-nums">{currentJob.geval_scores![a.key].score}/5</dd>
                        </div>
                      ))}
                    </dl>
                  </section>

                  {/* Rubric breakdowns and justifications */}
                  <div className="@xl:col-span-2 grid gap-3 @2xl:grid-cols-2">
                    <RubricDetailCard metricKey="coherence" title="Coherence (Structure & Flow)" evaluation={currentJob.geval_scores.coherence} hoveredKey={hoveredMetric} setHoveredKey={setHoveredMetric} />
                    <RubricDetailCard metricKey="relevance" title="Relevance (Topic & Keyword Coverage)" evaluation={currentJob.geval_scores.relevance} hoveredKey={hoveredMetric} setHoveredKey={setHoveredMetric} />
                    <RubricDetailCard metricKey="accuracy" title="Accuracy & Grounding (Entailment)" evaluation={currentJob.geval_scores.accuracy} hoveredKey={hoveredMetric} setHoveredKey={setHoveredMetric} />
                    <RubricDetailCard metricKey="tone_alignment" title="Tone & Audience Alignment" evaluation={currentJob.geval_scores.tone_alignment} hoveredKey={hoveredMetric} setHoveredKey={setHoveredMetric} />
                  </div>
                </>
              ) : !currentJob.deepeval_scores && !triggering['deepeval'] ? (
                <div className="@xl:col-span-2">
                  <EmptyState
                    icon={<Gauge />}
                    title="No evaluation yet"
                    description="The in-house G-Eval scores appear when the content pipeline completes."
                  />
                </div>
              ) : null}
            </div>
          )}

          {/* VIDEO TAB */}
          {activeTab === 'video' && (
            <div>
              {currentJob.video_file ? (
                <div className="grid gap-8 @3xl:grid-cols-[auto_1fr] items-start">
                  <video
                    src={APIClient.getFileUrl(currentJob.id, currentJob.video_file)}
                    controls
                    playsInline
                    preload="metadata"
                    className="mx-auto block aspect-[9/16] h-[min(72vh,720px)] w-auto max-w-full rounded-xl bg-black ring-1 ring-line"
                  />
                  <div>
                    <h3 className="text-heading text-base-50">Short video</h3>
                    <p className="mt-1 font-mono text-xs text-base-500">9:16 · MP4</p>
                    <div className="mt-4 flex gap-2">
                      <a href={APIClient.getFileUrl(currentJob.id, currentJob.video_file)} download target="_blank" rel="noreferrer" className="btn btn-secondary">
                        <Download /> Download MP4
                      </a>
                    </div>
                  </div>
                </div>
              ) : isTaskRunning('video') ? (
                <LoadingState title={videoTitle} description="Our AI is crafting a storyboard, generating voiceovers, and compiling your video." agentEvents={videoEvents} />
              ) : (
                <EmptyState
                  icon={<Film />}
                  title="Create a video from your blog"
                  description="Automatically transform this blog post into an engaging synthetic video with AI voiceover and animated visuals."
                  onGenerate={() => handleTrigger('video')}
                  error={getLastTaskError('video')}
                  actionLabel="Render video"
                  hint="About 2–3 min · uses the saved article"
                />
              )}
            </div>
          )}

          {/* PODCAST TAB */}
          {activeTab === 'podcast' && (
            <div>
              {currentJob.podcast_file ? (
                <PodcastPlayer currentJob={currentJob} />
              ) : isTaskRunning('podcast') ? (
                <LoadingState title="Generating Podcast..." description="Our AI hosts are warming up their mics and preparing the script." agentEvents={getCurrentRunEvents('podcast')} />
              ) : (
                <EmptyState
                  icon={<Podcast />}
                  title="Generate a podcast"
                  description="Convert your written content into an engaging conversational audio podcast."
                  onGenerate={() => handleTrigger('podcast')}
                  error={getLastTaskError('podcast')}
                  actionLabel="Generate podcast"
                  hint="About 1–2 min · 2 hosts · MP3"
                />
              )}
            </div>
          )}

          {/* SOCIAL TAB */}
          {activeTab === 'social' && (
            <div>
              {currentJob.social_linkedin ? (
                <div className="grid gap-4 @2xl:grid-cols-2">
                  <div className="card p-5 flex flex-col">
                    <div className="flex items-center gap-2.5">
                      <svg aria-hidden="true" className="size-4 fill-current text-[#0a66c2]" viewBox="0 0 24 24"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"></path></svg>
                      <span className="text-ui font-medium text-base-100">LinkedIn</span>
                      <button type="button" onClick={() => copyPost('linkedin', currentJob.social_linkedin!)} className="ml-auto btn btn-ghost btn-icon btn-sm" aria-label={copiedChannel === 'linkedin' ? 'Copied' : 'Copy LinkedIn post'} title={copiedChannel === 'linkedin' ? 'Copied' : 'Copy to clipboard'}>{copiedChannel === 'linkedin' ? <Check className="text-signal-success" /> : <Copy />}</button>
                    </div>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-base-200">{withHashtags(currentJob.social_linkedin)}</p>
                  </div>

                  <div className="card p-5 flex flex-col">
                    <div className="flex items-center gap-2.5">
                      <svg aria-hidden="true" className="size-4 fill-current text-base-200" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.008 4.09H5.078z"></path></svg>
                      <span className="text-ui font-medium text-base-100">X / Twitter</span>
                      <button type="button" onClick={() => copyPost('x', currentJob.social_twitter!)} className="ml-auto btn btn-ghost btn-icon btn-sm" aria-label={copiedChannel === 'x' ? 'Copied' : 'Copy X post'} title={copiedChannel === 'x' ? 'Copied' : 'Copy to clipboard'}>{copiedChannel === 'x' ? <Check className="text-signal-success" /> : <Copy />}</button>
                    </div>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-base-200">{withHashtags(currentJob.social_twitter ?? '')}</p>
                  </div>
                </div>
              ) : isTaskRunning('campaign') ? (
                <LoadingState title="Generating Campaign..." description="Drafting optimized posts for your social channels." agentEvents={getCurrentRunEvents('social')} />
              ) : (
                <EmptyState
                  icon={<Share2 />}
                  title="Generate a social media campaign"
                  description="Automatically write engaging LinkedIn and X/Twitter posts optimized for virality and reach."
                  onGenerate={() => handleTrigger('social')}
                  error={getLastTaskError('campaign')}
                  actionLabel="Write social posts"
                  hint="LinkedIn and X · uses the saved article"
                />
              )}
            </div>
          )}

          {/* IMAGES TAB */}
          {activeTab === 'images' && (
            <div>
              {isTaskRunning('images') ? (
                <LoadingState title="Generating Images..." description={`Our AI is crafting custom visuals for your blog post using the ${currentJob?.image_model || 'DALL-E 3'} model.`} agentEvents={getCurrentRunEvents('images')} />
              ) : imageFiles.length > 0 ? (
                <div className={imageFiles.length === 1 ? 'max-w-3xl' : undefined}>
                  <div className="flex items-end justify-between gap-4 mb-4">
                    <div>
                      <h3 className="text-heading text-base-50">Images</h3>
                      <p className="text-ui text-base-500">{imageFiles.length} image{imageFiles.length === 1 ? '' : 's'}</p>
                    </div>
                    <button type="button" onClick={() => handleTrigger('images')} className="btn btn-secondary btn-sm">
                      <RefreshCw /> Regenerate
                    </button>
                  </div>

                  {imageFiles.length === 1 ? (
                    imageTile(imageFiles[0], 0, true)
                  ) : (
                    <div className="grid gap-4 grid-cols-[repeat(auto-fill,minmax(280px,1fr))]">
                      {imageFiles.map((p, i) => imageTile(p, i))}
                    </div>
                  )}
                </div>
              ) : (
                <EmptyState
                  icon={<ImageIcon />}
                  title="Generate blog images"
                  description={`Create custom AI-generated visuals for your blog post using state-of-the-art ${currentJob?.image_model || 'DALL-E 3'} rendering.`}
                  onGenerate={() => handleTrigger('images')}
                  error={getLastTaskError('images')}
                  actionLabel="Generate images"
                  hint="Uses the saved article"
                />
              )}
            </div>
          )}

        </motion.div>
      </div>
    </main>
  );
}
