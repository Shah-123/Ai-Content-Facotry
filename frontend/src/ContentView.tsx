import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  CheckCircle2, Clock, Podcast, Film, Share2, Download,
  FileText, Settings, Image as ImageIcon,
  Play, Volume2, Copy, RefreshCw, LayoutTemplate, Bot, Trash2,
  GraduationCap, Sparkles, Edit3, Zap, FileCode, Check, Printer, BarChart3, Layers, ExternalLink
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { APIClient, Job, AgentEvent, API_BASE_URL, withApiKey } from './api';
import { TabButton } from './components/TabButton';
import { EmptyState } from './components/EmptyState';
import { LoadingState } from './components/LoadingState';
import { DeepEvalSection } from './components/DeepEvalSection';
import { RubricDetailCard } from './components/RubricDetailCard';
import { PodcastPlayer } from './components/PodcastPlayer';
import { useJobActions } from './hooks/useJobActions';
import { useJobAnalytics } from './hooks/useJobAnalytics';

type ViewState = 'chat' | 'content';
type TabState = 'blog' | 'geval' | 'analytics' | 'video' | 'podcast' | 'images' | 'social';

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

  useEffect(() => {
    if (currentJob?.final_content && !isEditing) {
      setEditedContent(currentJob.final_content);
    }
  }, [currentJob?.final_content, isEditing]);

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

  const { analytics, radarPoints } = useJobAnalytics(currentJob, events, isTaskRunning);

  if (!currentJob) {
    return (
      <main className="flex-1 p-6 md:p-10 flex items-center justify-center">
        <section className="w-full max-w-lg rounded-3xl border border-white/8 bg-base-900/60 p-8 text-center shadow-xl backdrop-blur-md">
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-accent-500/20 bg-accent-500/10">
            <FileText className="h-7 w-7 text-accent-400" />
          </div>
          <h1 className="text-xl font-bold text-base-100">Your studio is ready</h1>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-base-400">
            Create a generation job to review, edit, export, and extend your content here.
          </p>
          <button
            type="button"
            onClick={() => navTo('chat')}
            className="btn-primary mt-6 inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold"
          >
            <Sparkles className="h-4 w-4" />
            Create a new job
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="flex-1 p-6 md:p-10 flex flex-col relative overflow-y-auto w-full max-w-6xl mx-auto">

      {/* Header and Tabs */}
      <div className="mb-8 fade-in">
        <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 gap-4">
          <h2 className="text-2xl font-bold text-base-50 tracking-tight line-clamp-1">Studio: {currentJob.topic}</h2>
          <div className="flex items-center gap-2.5 shrink-0">
            <span className="px-2.5 py-1 rounded-lg bg-accent-glow text-accent-400 text-[11px] font-semibold uppercase tracking-wider flex items-center gap-1.5 border border-accent-500/20">
              {currentJob?.status === 'completed' ? <CheckCircle2 className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
              {currentJob?.status || 'Draft'}
            </span>
            {onDeleteJob && (
              <button
                onClick={() => onDeleteJob(currentJob.id)}
                className="text-base-400 text-sm font-medium hover:text-signal-error transition-colors flex items-center gap-1.5 px-3 py-1.5 rounded-xl hover:bg-white/3"
                title="Delete Job"
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete
              </button>
            )}
          </div>
        </div>

        <div className="flex gap-2 text-sm font-medium overflow-x-auto pb-2 border-b border-white/4">
          <TabButton<TabState> id="blog" icon={<FileText className="w-4 h-4" />} label="Blog" activeTab={activeTab} setActiveTab={setActiveTab} />
          <TabButton<TabState> id="geval" icon={<Bot className="w-4 h-4" />} label="G-Eval Audit" activeTab={activeTab} setActiveTab={setActiveTab} />
          <TabButton<TabState> id="analytics" icon={<BarChart3 className="w-4 h-4" />} label="Agent Analytics" activeTab={activeTab} setActiveTab={setActiveTab} />
          <TabButton<TabState> id="video" icon={<Film className="w-4 h-4" />} label="Video" activeTab={activeTab} setActiveTab={setActiveTab} />
          <TabButton<TabState> id="podcast" icon={<Podcast className="w-4 h-4" />} label="Podcast" activeTab={activeTab} setActiveTab={setActiveTab} />
          <TabButton<TabState> id="social" icon={<Share2 className="w-4 h-4" />} label="Social Media" activeTab={activeTab} setActiveTab={setActiveTab} />
          <TabButton<TabState> id="images" icon={<ImageIcon className="w-4 h-4" />} label="Images" activeTab={activeTab} setActiveTab={setActiveTab} />
        </div>
      </div>

      {/* Tab Content with animated transitions */}
      <div className="flex-1">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          >

            {/* BLOG TAB */}
            {activeTab === 'blog' && (
              <div className="flex flex-col gap-4">
                {/* Action Bar & Token Badge */}
                {currentJob.final_content && (
                  <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-2xl bg-base-900/80 dark:bg-base-900/90 border border-base-750/80 backdrop-blur-xl shadow-lg">
                    {/* Token Cost Badge */}
                    <div className="flex items-center gap-3 text-xs font-semibold">
                      <span className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-accent-500/10 text-accent-400 border border-accent-500/20 shadow-sm font-mono">
                        <Zap className="w-3.5 h-3.5" />
                        ~{Math.round((currentJob.final_content.split(/\s+/).length || 500) * 28 / 100) * 100} Tokens
                      </span>
                      <span className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-500/10 text-emerald-500 dark:text-emerald-400 border border-emerald-500/20 shadow-sm font-mono">
                        💰 ~${((currentJob.final_content.split(/\s+/).length || 500) * 0.00008).toFixed(3)} USD
                      </span>
                    </div>

                    {/* Action Controls */}
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => setIsEditing(!isEditing)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-sm ${
                          isEditing
                            ? 'bg-accent-500 text-base-950 shadow-md shadow-accent-500/30'
                            : 'bg-base-800/80 text-base-100 hover:text-accent-400 border border-base-700/80 hover:border-accent-500/30'
                        }`}
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                        {isEditing ? 'Preview' : 'Edit'}
                      </button>

                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(isEditing ? editedContent : (currentJob.final_content || editedContent));
                          setCopied(true);
                          setTimeout(() => setCopied(false), 2000);
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-base-800/80 text-base-100 hover:text-accent-400 border border-base-700/80 hover:border-accent-500/30 transition-all shadow-sm cursor-pointer"
                      >
                        {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        {copied ? 'Copied!' : 'Copy'}
                      </button>

                      {/* PDF Export */}
                      <a
                        href={APIClient.getExportUrl(currentJob.id, 'pdf')}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-rose-500/10 text-rose-500 dark:text-rose-400 hover:bg-rose-500/20 border border-rose-500/25 transition-all shadow-sm cursor-pointer"
                        title="Download as publication-ready PDF"
                      >
                        <Printer className="w-3.5 h-3.5" />
                        Export PDF
                      </a>

                      {/* DOCX Export */}
                      <a
                        href={APIClient.getExportUrl(currentJob.id, 'docx')}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-sky-500/10 text-sky-500 dark:text-sky-400 hover:bg-sky-500/20 border border-sky-500/25 transition-all shadow-sm cursor-pointer"
                        title="Download as Microsoft Word document (.docx)"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        Export DOCX
                      </a>

                      {/* HTML Export */}
                      <a
                        href={APIClient.getExportUrl(currentJob.id, 'html')}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-amber-500/10 text-amber-500 dark:text-amber-400 hover:bg-amber-500/20 border border-amber-500/25 transition-all shadow-sm cursor-pointer"
                        title="Download as standalone HTML document"
                      >
                        <FileCode className="w-3.5 h-3.5" />
                        Export HTML
                      </a>

                      {/* Markdown Download */}
                      <button
                        onClick={() => {
                          const rawText = isEditing ? editedContent : (currentJob.final_content || editedContent || '');
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
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-base-800/80 text-base-100 hover:text-accent-400 border border-base-700/80 hover:border-accent-500/30 transition-all shadow-sm cursor-pointer"
                        title="Download Markdown with picture URLs"
                      >
                        <Download className="w-3.5 h-3.5" />
                        Export MD
                      </button>
                    </div>
                  </div>
                )}

                <article className="high-contrast-card rounded-2xl p-8 md:p-12 shadow-[0_20px_50px_rgba(0,0,0,0.3)] relative overflow-hidden bg-white text-slate-800">
                  <div className="absolute top-0 left-0 w-full h-1 bg-linear-to-r from-accent-500 to-accent-600"></div>
                  {currentJob.final_content ? (
                    isEditing ? (
                      <div className="flex flex-col gap-3">
                        <div className="flex items-center justify-between text-xs text-slate-500 border-b pb-2">
                          <span className="font-semibold text-slate-700">WYSIWYG Markdown Editor</span>
                          <span>Live synchronization enabled</span>
                        </div>
                        <textarea
                          value={editedContent}
                          onChange={(e) => setEditedContent(e.target.value)}
                          className="w-full h-[600px] p-4 font-mono text-sm border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-accent-500 text-slate-900 bg-slate-50/50 resize-y"
                        />
                      </div>
                    ) : (
                      <div className="prose prose-slate max-w-none prose-headings:text-slate-900 prose-a:text-accent-600 hover:prose-a:text-accent-500">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {resolveContentImageUrls(isEditing ? editedContent : (currentJob.final_content || editedContent), currentJob?.id)}
                        </ReactMarkdown>
                      </div>
                    )
                  ) : currentJob.status === 'running' || currentJob.status === 'awaiting_approval' || currentJob.status === 'pending' ? (
                    <div className="flex flex-col items-center justify-center p-12 text-slate-500 space-y-4">
                      <div className="orbital-loader">
                        <div className="orbital-ring orbital-ring-1" />
                        <div className="orbital-ring orbital-ring-2" />
                        <div className="orbital-ring orbital-ring-3" />
                        <div className="absolute inset-0 flex items-center justify-center">
                          <Bot className="w-6 h-6 text-accent-500 animate-pulse" />
                        </div>
                      </div>
                      <p className="font-semibold text-slate-600 mt-4">Agents are at work...</p>
                      <p className="text-sm">Head back to the Dashboard to see live updates.</p>
                    </div>
                  ) : currentJob.status === 'failed' ? (
                    <div className="flex flex-col items-center justify-center p-12 text-red-500 space-y-4">
                      <Settings className="w-12 h-12 opacity-50" />
                      <p className="font-bold">Generation failed</p>
                      <p className="text-sm opacity-80">{currentJob.error_message || "An unknown error occurred."}</p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center p-12 text-slate-500">
                      <Clock className="w-12 h-12 mb-4 opacity-50" />
                      <p>Content not available for this job.</p>
                    </div>
                  )}
                </article>
              </div>
            )}

            {/* G-EVAL TAB */}
            {activeTab === 'geval' && (
              <div>
                {currentJob.geval_scores ? (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

                    {/* Left Side: Score card and SVG Radar Chart */}
                    <div className="lg:col-span-1 glass-panel p-6 rounded-2xl flex flex-col items-center border border-white/6 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
                      <h3 className="text-lg font-bold text-base-50 mb-1 tracking-wide uppercase text-[11px] text-base-400">Weighted Quality Grade</h3>

                      {/* Animated Score Ring */}
                      <div className="my-4">
                        <div
                          className="score-ring"
                          style={{ '--score-pct': (currentJob.geval_scores.overall_score / 5) * 100 } as React.CSSProperties}
                        >
                          <div className="score-ring-inner">
                            <motion.span
                              className="text-3xl font-extrabold text-accent-400"
                              initial={{ opacity: 0, scale: 0.5 }}
                              animate={{ opacity: 1, scale: 1 }}
                              transition={{ delay: 0.3, type: 'spring', stiffness: 200 }}
                            >
                              {currentJob.geval_scores.overall_score}
                            </motion.span>
                            <span className="text-[10px] text-base-500 uppercase tracking-widest font-semibold mt-0.5">out of 5</span>
                          </div>
                        </div>
                      </div>

                      {/* SVG Radar Chart */}
                      <div className="w-full relative px-4 py-2 border-t border-white/4 mt-4">
                        <svg viewBox="0 0 100 100" className="w-full h-auto overflow-visible select-none drop-shadow-[0_0_12px_var(--color-accent-glow)]">
                          {/* Grid concentric circles (representing 1 to 5 scores) */}
                          {[1, 2, 3, 4, 5].map((lvl) => (
                            <circle key={lvl} cx="50" cy="50" r={lvl * 6} fill="none" stroke="currentColor" className="text-slate-300/30 dark:text-white/4" strokeWidth="0.5" />
                          ))}

                          {/* Axis Lines */}
                          <line x1="50" y1="20" x2="50" y2="80" stroke="currentColor" className="text-slate-300/40 dark:text-white/6" strokeWidth="0.5" />
                          <line x1="20" y1="50" x2="80" y2="50" stroke="currentColor" className="text-slate-300/40 dark:text-white/6" strokeWidth="0.5" />

                          {/* Radar polygon shape */}
                          <polygon points={radarPoints} fill="var(--color-accent-glow)" stroke="var(--color-accent-500)" strokeWidth="1.5" strokeLinejoin="round" />

                          {/* Grid values labels */}
                          <text x="50" y="49" fill="currentColor" className="text-slate-400 dark:text-white/20" fontSize="2" textAnchor="middle">0</text>
                          {[1, 2, 3, 4, 5].map((lvl) => (
                            <text key={lvl} x="50" y={50 - lvl * 6 + 0.8} fill="currentColor" className="text-slate-400 dark:text-white/25" fontSize="2" textAnchor="middle">{lvl}</text>
                          ))}

                          {/* Axis Labels (top, right, bottom, left) */}
                          <text x="50" y="15" fill={hoveredMetric === 'coherence' ? 'var(--color-accent-500)' : 'currentColor'} fontSize="3.5" fontWeight={hoveredMetric === 'coherence' ? 'bold' : 'normal'} textAnchor="middle" className="text-slate-600 dark:text-slate-300/80 cursor-pointer transition-all" onMouseEnter={() => setHoveredMetric('coherence')} onMouseLeave={() => setHoveredMetric(null)}>Coherence</text>
                          <text x="83" y="51" fill={hoveredMetric === 'relevance' ? 'var(--color-accent-500)' : 'currentColor'} fontSize="3.5" fontWeight={hoveredMetric === 'relevance' ? 'bold' : 'normal'} textAnchor="start" className="text-slate-600 dark:text-slate-300/80 cursor-pointer transition-all" onMouseEnter={() => setHoveredMetric('relevance')} onMouseLeave={() => setHoveredMetric(null)}>Relevance</text>
                          <text x="50" y="87" fill={hoveredMetric === 'accuracy' ? 'var(--color-accent-500)' : 'currentColor'} fontSize="3.5" fontWeight={hoveredMetric === 'accuracy' ? 'bold' : 'normal'} textAnchor="middle" className="text-slate-600 dark:text-slate-300/80 cursor-pointer transition-all" onMouseEnter={() => setHoveredMetric('accuracy')} onMouseLeave={() => setHoveredMetric(null)}>Accuracy</text>
                          <text x="17" y="51" fill={hoveredMetric === 'tone_alignment' ? 'var(--color-accent-500)' : 'currentColor'} fontSize="3.5" fontWeight={hoveredMetric === 'tone_alignment' ? 'bold' : 'normal'} textAnchor="end" className="text-slate-600 dark:text-slate-300/80 cursor-pointer transition-all" onMouseEnter={() => setHoveredMetric('tone_alignment')} onMouseLeave={() => setHoveredMetric(null)}>Tone</text>

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
                                <circle key={itm.key} cx={cx} cy={cy} r={active ? 2.5 : 1.5} fill={active ? "#ffffff" : "var(--color-accent-500)"} stroke={active ? "var(--color-accent-500)" : "none"} strokeWidth="0.5" className="transition-all duration-300 cursor-pointer" onMouseEnter={() => setHoveredMetric(itm.key)} onMouseLeave={() => setHoveredMetric(null)} />
                              );
                            });
                          })()}
                        </svg>
                      </div>
                    </div>

                    {/* Right Side: Score breakdowns and justifications */}
                    <div className="lg:col-span-2 space-y-4">
                      <RubricDetailCard metricKey="coherence" title="Coherence (Structure & Flow)" evaluation={currentJob.geval_scores.coherence} hoveredKey={hoveredMetric} setHoveredKey={setHoveredMetric} />
                      <RubricDetailCard metricKey="relevance" title="Relevance (Topic & Keyword Coverage)" evaluation={currentJob.geval_scores.relevance} hoveredKey={hoveredMetric} setHoveredKey={setHoveredMetric} />
                      <RubricDetailCard metricKey="accuracy" title="Accuracy & Grounding (Entailment)" evaluation={currentJob.geval_scores.accuracy} hoveredKey={hoveredMetric} setHoveredKey={setHoveredMetric} />
                      <RubricDetailCard metricKey="tone_alignment" title="Tone & Audience Alignment" evaluation={currentJob.geval_scores.tone_alignment} hoveredKey={hoveredMetric} setHoveredKey={setHoveredMetric} />
                    </div>

                    {/* ============================================================
                    DEEPEVAL ACADEMIC AUDIT (Liu et al. 2023, deepeval library)
                    Manual run, displayed inline under the in-house G-Eval card.
                   ============================================================ */}
                    <div className="lg:col-span-3 mt-2">
                      <DeepEvalSection
                        currentJob={currentJob}
                        isRunning={!!triggering['deepeval']}
                        onRun={() => handleTrigger('deepeval')}
                      />
                    </div>

                  </div>
                ) : (
                  <div className="glass-panel p-12 rounded-2xl flex flex-col items-center justify-center text-center min-h-[400px] border border-white/4 relative overflow-hidden group max-w-3xl mx-auto">
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] bg-accent-500/5 rounded-full blur-3xl group-hover:bg-accent-500/10 transition-all duration-700"></div>
                    <div className="relative z-10 w-24 h-24 bg-base-900 rounded-full flex items-center justify-center mb-6 shadow-xl border border-white/6 text-accent-400 group-hover:scale-105 transition-transform duration-500">
                      <Bot className="w-12 h-12" />
                    </div>
                    <h3 className="text-2xl font-bold text-base-50 mb-3">No Evaluation Data</h3>
                    <p className="text-base-400 mb-8 max-w-md text-sm leading-relaxed">
                      Run the content pipeline completely to generate G-Eval scores across coherence, relevance, accuracy, and tone.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* AGENT ANALYTICS TAB */}
            {activeTab === 'analytics' && (
              <div className="space-y-8 fade-in">
                {/* Metrics Highlights Header */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="glass-panel p-5 rounded-2xl border border-white/6 flex flex-col justify-between">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Measured Tokens</span>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span className="text-2xl font-black text-amber-400">
                        {analytics.totalTokens === null ? '—' : analytics.totalTokens.toLocaleString()}
                      </span>
                      <span className="text-xs text-slate-500 font-medium">
                        {analytics.totalTokens === null ? 'not recorded' : 'tokens'}
                      </span>
                    </div>
                  </div>

                  <div className="glass-panel p-5 rounded-2xl border border-white/6 flex flex-col justify-between">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Measured Cost</span>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span className="text-2xl font-black text-emerald-400">
                        {analytics.totalCost === null ? '—' : `$${analytics.totalCost.toFixed(4)}`}
                      </span>
                      <span className="text-xs text-slate-500 font-medium">
                        {analytics.totalCost === null ? 'not recorded' : `USD · ${analytics.totalCalls} calls`}
                      </span>
                    </div>
                  </div>

                  <div className="glass-panel p-5 rounded-2xl border border-white/6 flex flex-col justify-between">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Active Graph Agents</span>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span className="text-2xl font-black text-accent-400">{analytics.activeAgentCount}</span>
                      <span className="text-xs text-slate-500 font-medium">/ {analytics.nodes.length} nodes active</span>
                    </div>
                  </div>

                  <div className="glass-panel p-5 rounded-2xl border border-white/6 flex flex-col justify-between">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Parallel Threads</span>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span className="text-2xl font-black text-purple-400">{analytics.numSections}</span>
                      <span className="text-xs text-slate-500 font-medium">fan-out workers</span>
                    </div>
                  </div>
                </div>

                {/* Multi-Agent Architecture Table */}
                <div className="glass-panel p-6 rounded-2xl border border-white/6 shadow-xl">
                  <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/6">
                    <div>
                      <h3 className="text-lg font-bold text-base-50 flex items-center gap-2">
                        <Layers className="w-5 h-5 text-accent-400" />
                        Multi-Agent Execution Matrix
                      </h3>
                      <p className="text-xs text-slate-400 mt-1">Model mapping, role descriptions and execution status per graph node. Cost is metered per RUN, not per agent — see the measured total above; a dash means the figure was not recorded.</p>
                    </div>
                    <span className="px-3 py-1 rounded-full text-xs font-semibold bg-accent-500/10 text-accent-400 border border-accent-500/20">
                      LangGraph Directed Acyclic Graph (DAG)
                    </span>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-white/10 text-slate-400 uppercase tracking-wider">
                          <th className="py-3 px-4">Agent Node</th>
                          <th className="py-3 px-4">Model / Provider</th>
                          <th className="py-3 px-4">Role & Logic</th>
                          <th className="py-3 px-4">Est. Cost</th>
                          <th className="py-3 px-4">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/4 text-slate-300">
                        {analytics.nodes.map((node) => {
                          const isSkipped = node.status === 'Skipped';
                          const isRunning = node.status === 'Running';
                          return (
                            <tr key={node.id} className={`hover:bg-white/2 transition-colors ${isSkipped ? 'opacity-50' : ''}`}>
                              <td className="py-3 px-4 font-semibold text-base-50 flex items-center gap-2">
                                <span className={`w-2 h-2 rounded-full ${isSkipped ? 'bg-slate-600' : node.color}`}></span>
                                <span className={isSkipped ? 'text-slate-400 line-through decoration-slate-600' : 'text-base-50'}>{node.name}</span>
                              </td>
                              <td className={`py-3 px-4 font-mono ${isSkipped ? 'text-slate-500' : node.textColor}`}>{node.model}</td>
                              <td className="py-3 px-4 text-slate-400">{node.role}</td>
                              <td className={`py-3 px-4 font-mono ${node.cost ? 'text-emerald-400 font-bold' : 'text-slate-500'}`}
                                  title={node.cost === null ? 'Per-agent cost is not measured; see the run total above' : undefined}>
                                {node.cost === null ? '—' : `$${node.cost.toFixed(4)}`}
                              </td>
                              <td className="py-3 px-4">
                                {isRunning ? (
                                  <span className="text-amber-400 font-semibold animate-pulse flex items-center gap-1">
                                    <RefreshCw className="w-3 h-3 animate-spin" /> Running...
                                  </span>
                                ) : isSkipped ? (
                                  <span className="text-slate-500 font-medium italic">Skipped</span>
                                ) : node.status.startsWith('Passed') || node.status === 'Approved' ? (
                                  <span className="text-emerald-400 font-semibold">{node.status}</span>
                                ) : (
                                  <span className="text-slate-400 font-medium">{node.status}</span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* VIDEO TAB */}
            {activeTab === 'video' && (
              <div>
                {currentJob.video_file ? (
                  <div className="glass-panel p-6 rounded-2xl">
                    <div className="flex justify-between items-center mb-4">
                      <h3 className="text-xl font-bold text-base-50 flex items-center gap-2"><Film className="w-5 h-5 text-accent-400" /> Synthetic Video</h3>
                      <a href={APIClient.getFileUrl(currentJob.id, currentJob.video_file)} download target="_blank" rel="noreferrer"
                        className="btn-primary px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2">
                        <Download className="w-4 h-4" /> Download MP4
                      </a>
                    </div>
                    <div className="bg-black rounded-xl overflow-hidden aspect-video border border-white/6 w-full max-w-4xl mx-auto">
                      <video src={APIClient.getFileUrl(currentJob.id, currentJob.video_file)} controls className="w-full h-full object-contain"></video>
                    </div>
                  </div>
                ) : isTaskRunning('video') ? (
                  <LoadingState title="Generating Video..." description="Our AI is crafting a storyboard, generating voiceovers, and compiling your video." agentEvents={getCurrentRunEvents('video')} />
                ) : (
                  <EmptyState
                    icon={<Film className="w-12 h-12" />}
                    title="Create a Video from your Blog"
                    description="Automatically transform this blog post into an engaging synthetic video with AI voiceover and animated visuals."
                    onGenerate={() => handleTrigger('video')}
                    error={getLastTaskError('video')}
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
                    icon={<Podcast className="w-12 h-12" />}
                    title="Generate a Podcast"
                    description="Convert your written content into an engaging conversational audio podcast."
                    onGenerate={() => handleTrigger('podcast')}
                    error={getLastTaskError('podcast')}
                  />
                )}
              </div>
            )}

            {/* SOCIAL TAB */}
            {activeTab === 'social' && (
              <div>
                {currentJob.social_linkedin ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="glass-panel p-6 rounded-2xl flex flex-col h-full hover-lift">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-base-100">
                          <svg className="w-5 h-5 fill-current text-[#0a66c2]" viewBox="0 0 24 24"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"></path></svg>
                          LinkedIn Post
                        </div>
                        <button onClick={() => navigator.clipboard.writeText(currentJob.social_linkedin!).catch(() => { })} className="text-base-400 hover:text-accent-400 transition-colors p-2 rounded-lg hover:bg-white/5" title="Copy to clipboard"><Copy className="w-4 h-4" /></button>
                      </div>
                      <div className="bg-base-900 rounded-xl p-5 border border-white/5 flex-1">
                        <p className="text-sm text-base-300 leading-relaxed whitespace-pre-wrap">{currentJob.social_linkedin}</p>
                      </div>
                    </div>

                    <div className="glass-panel p-6 rounded-2xl flex flex-col h-full hover-lift">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-base-100">
                          <svg className="w-5 h-5 fill-current text-base-200" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.008 4.09H5.078z"></path></svg>
                          X / Twitter Post
                        </div>
                        <button onClick={() => navigator.clipboard.writeText(currentJob.social_twitter!).catch(() => { })} className="text-base-400 hover:text-accent-400 transition-colors p-2 rounded-lg hover:bg-white/5" title="Copy to clipboard"><Copy className="w-4 h-4" /></button>
                      </div>
                      <div className="bg-base-900 rounded-xl p-5 border border-white/5 flex-1">
                        <p className="text-sm text-base-300 leading-relaxed whitespace-pre-wrap">{currentJob.social_twitter}</p>
                      </div>
                    </div>
                  </div>
                ) : isTaskRunning('campaign') ? (
                  <LoadingState title="Generating Campaign..." description="Drafting optimized posts for your social channels." agentEvents={getCurrentRunEvents('social')} />
                ) : (
                  <EmptyState
                    icon={<Share2 className="w-12 h-12" />}
                    title="Generate Social Media Campaign"
                    description="Automatically write engaging LinkedIn and X/Twitter posts optimized for virality and reach."
                    onGenerate={() => handleTrigger('social')}
                    error={getLastTaskError('campaign')}
                  />
                )}
              </div>
            )}

            {/* IMAGES TAB */}
            {activeTab === 'images' && (
              <div>
                {isTaskRunning('images') ? (
                  <LoadingState title="Generating Images..." description={`Our AI is crafting custom visuals for your blog post using the ${currentJob?.image_model || 'DALL-E 3'} model.`} agentEvents={getCurrentRunEvents('images')} />
                ) : currentJob?.image_files && currentJob.image_files.length > 0 ? (
                  <div className="space-y-6">
                    <div className="glass-panel p-6 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border border-white/6 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
                      <div>
                        <h3 className="text-xl font-bold text-base-50 tracking-tight flex items-center gap-2">
                          <ImageIcon className="w-5 h-5 text-accent-400" /> Generated Images Gallery
                        </h3>
                        <p className="text-xs text-base-400 mt-1">
                          {currentJob.image_files.length} custom AI visual(s) generated for <span className="text-base-200 font-medium">"{currentJob.topic}"</span>
                        </p>
                      </div>
                      <button
                        onClick={() => handleTrigger('images')}
                        className="px-4 py-2 rounded-xl text-xs font-bold bg-accent-500/10 text-accent-400 hover:bg-accent-500/20 border border-accent-500/20 transition-all flex items-center gap-2 cursor-pointer shrink-0"
                      >
                        <RefreshCw className="w-3.5 h-3.5" /> Regenerate Images
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                      {currentJob.image_files.map((imgPath, idx) => {
                        const url = APIClient.getFileUrl(currentJob.id, imgPath);
                        const filename = imgPath.split('/').pop() || `image_${idx + 1}.png`;
                        return (
                          <motion.div
                            key={imgPath}
                            initial={{ opacity: 0, y: 15 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: idx * 0.08 }}
                            className="glass-panel rounded-2xl border border-white/6 overflow-hidden flex flex-col justify-between group hover:border-accent-500/40 hover:shadow-[0_12px_40px_rgba(0,0,0,0.3)] transition-all duration-300"
                          >
                            <div className="relative aspect-video bg-base-950 overflow-hidden">
                              <img
                                src={url}
                                alt={filename}
                                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                              />
                              <div className="absolute inset-0 bg-gradient-to-t from-base-950/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end justify-between p-4">
                                <span className="text-[11px] font-mono font-semibold text-white/90 truncate max-w-[200px]">
                                  {filename}
                                </span>
                                <a
                                  href={url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="p-2 rounded-xl bg-white/10 hover:bg-white/20 text-white backdrop-blur-md transition-all cursor-pointer"
                                  title="View full image in new tab"
                                >
                                  <ExternalLink className="w-4 h-4" />
                                </a>
                              </div>
                            </div>
                            <div className="p-4 flex items-center justify-between gap-3 bg-base-900/40 border-t border-white/4">
                              <span className="text-xs font-semibold text-base-200 truncate flex-1" title={filename}>
                                {filename}
                              </span>
                              <a
                                href={url}
                                download={filename}
                                target="_blank"
                                rel="noreferrer"
                                className="px-3 py-1.5 rounded-xl text-xs font-bold bg-accent-500 text-base-950 hover:bg-accent-400 transition-all flex items-center gap-1.5 shrink-0 shadow-sm cursor-pointer"
                              >
                                <Download className="w-3.5 h-3.5" /> Download
                              </a>
                            </div>
                          </motion.div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    icon={<ImageIcon className="w-12 h-12" />}
                    title="Generate Blog Images"
                    description={`Create custom AI-generated visuals for your blog post using state-of-the-art ${currentJob?.image_model || 'DALL-E 3'} rendering.`}
                    onGenerate={() => handleTrigger('images')}
                    error={getLastTaskError('images')}
                  />
                )}
              </div>
            )}

          </motion.div>
        </AnimatePresence>
      </div>
    </main>
  );
}
