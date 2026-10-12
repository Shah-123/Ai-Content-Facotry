import { useState, useEffect, useRef } from 'react';
import { motion } from 'motion/react';
import {
  ListOrdered, Network, ShieldAlert, X,
  FileText, Film, Podcast, Search, Bot, Image as ImageIcon,
  RotateCcw, AlertTriangle, Sparkles, Paperclip, Loader2, ArrowUpRight
} from 'lucide-react';
import { APIClient, Job, AgentEvent, CreateJobParams, UploadResult, SourceMode } from '../api';
import { PlanEditor } from './PlanEditor';
import { UploadChip } from './UploadChip';
import { ProgressTracker } from './ProgressTracker';

// Agent colour lives only in a small dot (light first, then dark:), never in text.
function getAgentConfig(agentName: string) {
  const name = agentName.toLowerCase();
  if (name.includes('research')) {
    return { icon: Search, dot: 'bg-sky-600 dark:bg-sky-400' };
  }
  if (name.includes('orchestrat') || name.includes('plan')) {
    return { icon: ListOrdered, dot: 'bg-violet-600 dark:bg-violet-400' };
  }
  if (name.includes('writer') || name.includes('edit')) {
    return { icon: FileText, dot: 'bg-amber-600 dark:bg-amber-400' };
  }
  if (name.includes('quality') || name.includes('control') || name.includes('validator') || name.includes('critic')
      || name.startsWith('qa') || name.includes('eval')) {
    return { icon: ShieldAlert, dot: 'bg-emerald-600 dark:bg-emerald-400' };
  }
  if (name.includes('video')) {
    return { icon: Film, dot: 'bg-rose-600 dark:bg-rose-400' };
  }
  if (name.includes('audio') || name.includes('podcast')) {
    return { icon: Podcast, dot: 'bg-indigo-600 dark:bg-indigo-400' };
  }
  if (name.includes('image')) {
    return { icon: ImageIcon, dot: 'bg-teal-600 dark:bg-teal-400' };
  }
  return { icon: Bot, dot: 'bg-base-500' };
}

/** "geval_evaluator" -> "G-Eval evaluator", "qa_agent" -> "QA agent" */
const sentenceCase = (s: string) => {
  const t = s.replace(/_/g, ' ').replace(/^geval\b/i, 'G-Eval').replace(/^qa\b/i, 'QA');
  return t.charAt(0).toUpperCase() + t.slice(1);
};

/** HH:MM:SS for feed timestamps. */
const formatClock = (epochSecs: number) =>
  new Date(epochSecs * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

/** Agent header row in the timeline: node on the rail, colour dot, name. */
function TimelineHead({ icon: Icon, dot, label }: { icon: typeof Bot; dot: string; label: string }) {
  return (
    <div className="relative flex h-8 items-center gap-2.5 mt-3">
      <span className="relative z-10 grid size-6 place-items-center rounded-full bg-base-800 ring-1 ring-line-strong">
        <Icon className="size-3.5 text-base-300" />
      </span>
      <span className={`size-1.5 rounded-full ${dot}`} />
      <span className="text-ui font-medium text-base-100">{label}</span>
    </div>
  );
}

const ACCEPTED_UPLOAD_TYPES = '.pdf,.docx,.txt,.md';

/** mm:ss for the live run clock, h:mm:ss past an hour. */
const formatElapsed = (secs: number) => {
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), ss = String(secs % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${String(m).padStart(2, '0')}:${ss}`;
};

/** Status map shared with Sidebar and ContentView (spec section 4). */
const JOB_STATUS: Record<Job['status'], { badge: string; dot: string; label: string }> = {
  completed:         { badge: 'badge',               dot: 'dot-success', label: 'Completed' },
  awaiting_approval: { badge: 'badge badge-warning', dot: 'dot-warning', label: 'Awaiting approval' },
  running:           { badge: 'badge badge-accent',  dot: 'live-dot',    label: 'Running' },
  pending:           { badge: 'badge',               dot: 'dot-pending', label: 'Queued' },
  failed:            { badge: 'badge badge-error',   dot: 'dot-error',   label: 'Failed' },
};

interface ChatViewProps {
  currentJob: Job | null;
  events: AgentEvent[];
  topicError?: { reason: string; category?: string; suggested_topic?: string } | null;
  clearTopicError?: () => void;
  handleCreateJob:    (params: CreateJobParams) => void;
  handleApprovePlan:  (jobId: string) => void;
  handleRevisePlan:   (jobId: string, feedback: string) => void;
  handleUpdatePlan:   (jobId: string, plan: any) => void;
  handleResumeJob?:   (jobId: string) => void;
  tone: string;
  setTone: (t: string) => void;
  sections: number;
  setSections: (s: number) => void;
  numImages?: number;
  keywordsInput: string;
  setKeywordsInput: (k: string) => void;
  selectedModel: string;
}

/* ---------- Hero Feature Cards ---------- */
const HERO_FEATURES = [
  {
    icon: FileText,
    title: 'Research & Write',
    desc: 'Multi-agent pipeline with web research, evidence grounding, and QA audit.',
    chip: 'Blog',
    sampleTopic: 'How LangGraph enables persistent agent loops',
    sampleTone: 'technical',
    sampleSections: 4,
  },
  {
    icon: Film,
    title: 'Video Generation',
    desc: 'Automated storyboard, AI voiceover, and Pexels B-roll compilation.',
    chip: 'Video',
    sampleTopic: 'A brief guide to stock video synthesis with Pexels',
    sampleTone: 'conversational',
    sampleSections: 2,
  },
  {
    icon: Podcast,
    title: 'Podcast Studio',
    desc: 'Two-host conversational audio voiced with OpenAI text-to-speech.',
    chip: 'Podcast',
    sampleTopic: 'The future of generative voice acting and audio design',
    sampleTone: 'educational',
    sampleSections: 3,
  },
] as const;

export function ChatView({
  currentJob, events, topicError, clearTopicError,
  handleCreateJob, handleApprovePlan, handleRevisePlan, handleUpdatePlan, handleResumeJob,
  tone, setTone, sections, setSections, numImages = 0, keywordsInput, setKeywordsInput, selectedModel
}: ChatViewProps) {
  const [topicInput, setTopicInput] = useState('');
  const [isResuming, setIsResuming] = useState(false);

  // Document upload state
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'ready' | 'error'>('idle');
  const [uploadName, setUploadName] = useState<string>('');
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string>('');
  const [sourceMode, setSourceMode] = useState<SourceMode>('hybrid');
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const topicRef = useRef<HTMLTextAreaElement | null>(null);

  // The box opens at one line and grows to fit, so an empty composer does not
  // reserve three lines of blank space. Keyed on topicInput rather than on the
  // change handler because the hero template buttons set the topic too, and a
  // fixed-height box would have hidden the tail of those longer samples.
  useEffect(() => {
    const el = topicRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [topicInput]);




  const clearUpload = () => {
    setUploadStatus('idle');
    setUploadName('');
    setUploadResult(null);
    setUploadError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFileSelected = async (file: File | undefined) => {
    if (!file) return;
    setUploadStatus('uploading');
    setUploadName(file.name);
    setUploadResult(null);
    setUploadError('');
    try {
      const result = await APIClient.uploadDocument(file);
      setUploadResult(result);
      setUploadStatus('ready');
      // If the user hasn't typed a topic yet, pre-fill the derived one.
      if (!topicInput.trim() && result.derived_topic) {
        setTopicInput(result.derived_topic);
      }
    } catch (e: any) {
      setUploadError(e?.message || 'Upload failed.');
      setUploadStatus('error');
    }
  };

  const submitJob = (overrideTopic?: string) => {
    // For auto_topic, fall back to the derived topic if the textarea is empty.
    let topic = (overrideTopic ?? topicInput).trim();
    if (!topic && sourceMode === 'auto_topic' && uploadResult?.derived_topic) {
      topic = uploadResult.derived_topic;
    }
    if (!topic) return;
    const upload_id = uploadStatus === 'ready' ? uploadResult?.upload_id : undefined;
    const keywords = keywordsInput
      .split(',')
      .map(k => k.trim())
      .filter(k => k.length > 0);
    handleCreateJob({
      topic, tone, sections, keywords,
      generate_podcast: false, generate_video: false, generate_campaign: false,
      generate_images: numImages > 0,
      num_images: numImages,
      upload_id,
      source_mode: upload_id ? sourceMode : undefined,
    });
    setTopicInput('');
    setKeywordsInput('');
    clearUpload();
  };

  const isAwaitingApproval = currentJob?.status === 'awaiting_approval';
  const showHero = !currentJob && events.length === 0;
  const isLive = !!currentJob && currentJob.status !== 'completed' && currentJob.status !== 'failed';

  // Keep the newest agent event in view — the feed scrolls on desktop, so
  // without this the live process runs off the bottom of the panel.
  // While the plan is up, land on its top instead: its sticky Approve footer keeps Approve visible.
  const feedEndRef = useRef<HTMLDivElement | null>(null);
  const planRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const toPlan = currentJob?.status === 'awaiting_approval' && planRef.current;
    const behavior: ScrollBehavior = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
    (toPlan || feedEndRef.current)?.scrollIntoView({ behavior, block: toPlan ? 'start' : 'end' });
  }, [events.length, currentJob?.status]);

  // Run clock — a long pipeline with no moving number reads as frozen.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!isLive || !currentJob) { setElapsed(0); return; }
    const startedAt = new Date(currentJob.created_at).getTime();
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [isLive, currentJob?.id, currentJob?.created_at]);

  const generateDisabled =
    uploadStatus === 'uploading'
    || (!topicInput.trim()
        && !(sourceMode === 'auto_topic' && uploadStatus === 'ready' && !!uploadResult?.derived_topic));

  const composer = (
    <>
      {topicError && (
        <div role="alert" className="mb-3 fade-in flex items-start gap-3 rounded-xl border border-signal-error/25 bg-signal-error-dim py-2.5 pl-4 pr-2">
          <ShieldAlert className="size-4 mt-0.5 shrink-0 text-signal-error" />
          <div className="flex-1 text-ui">
            <span className="font-medium text-signal-error">Topic rejected.</span>{' '}
            <span className="text-base-200">{topicError.reason}</span>
            {topicError.suggested_topic && (
              <button
                onClick={() => {
                  setTopicInput(topicError.suggested_topic!);
                  clearTopicError?.();
                }}
                className="block mt-2 text-xs text-accent-400 hover:text-accent-300 underline underline-offset-2 transition-colors"
              >
                Try this instead: "{topicError.suggested_topic}"
              </button>
            )}
          </div>
          <button
            onClick={() => clearTopicError?.()}
            className="btn btn-ghost btn-icon btn-sm shrink-0"
            aria-label="Dismiss"
            title="Dismiss"
          >
            <X />
          </button>
        </div>
      )}

      <div className="composer">
        {uploadStatus !== 'idle' && (
          <UploadChip
            status={uploadStatus}
            filename={uploadName}
            result={uploadResult}
            errorMessage={uploadError}
            sourceMode={sourceMode}
            onSourceModeChange={setSourceMode}
            onClear={clearUpload}
          />
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_UPLOAD_TYPES}
          className="hidden"
          onChange={e => { handleFileSelected(e.target.files?.[0]); }}
        />

        <textarea
          className="w-full resize-none bg-transparent px-2.5 pt-2 pb-1 text-base md:text-[15px] leading-6 text-base-50 placeholder:text-base-500 min-h-[32px] max-h-[180px] overflow-y-auto focus:outline-hidden"
          aria-label="Topic"
          placeholder={
            uploadStatus === 'ready' && sourceMode === 'auto_topic'
              ? (uploadResult?.derived_topic
                  ? `Auto-topic ready — press Send (or override: "${uploadResult.derived_topic}")`
                  : 'Auto-topic mode — enter or override the title...')
              : 'Enter a topic to generate a publication-ready blog...'
          }
          ref={topicRef}
          rows={1}
          value={topicInput}
          onChange={e => setTopicInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitJob(); } }}
        />

        <div className="mt-1 flex items-center gap-2 border-t border-line px-1 pt-1.5">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadStatus === 'uploading'}
            title="Attach a document (PDF, DOCX, TXT, MD)"
            aria-label="Attach document"
            className={`btn btn-ghost btn-sm ${uploadStatus === 'ready' ? 'text-accent-400' : ''}`}
          >
            <Paperclip />
            <span className="hidden sm:inline">Attach</span>
          </button>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden md:flex items-center gap-1 text-xs text-base-500">
              <span className="kbd">⇧</span><span className="kbd">↵</span> new line
            </span>
            <button
              type="button"
              onClick={() => submitJob()}
              disabled={generateDisabled}
              className="btn btn-primary btn-sm"
            >
              <Sparkles />
              Generate
              <span className="kbd max-md:hidden [@media(pointer:coarse)]:hidden">↵</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );

  const status = currentJob ? JOB_STATUS[currentJob.status] : null;
  const showJobBar = !!currentJob && !!status;
  const showComposer = !currentJob || currentJob.status === 'completed' || currentJob.status === 'failed';

  return (
    <main className="flex-1 min-h-0 flex flex-col relative overflow-hidden">
      {showHero ? (
        /* -------- Welcome hero (shown when no job is active) -------- */
        <motion.section
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
          className="flex-1 min-h-0 overflow-y-auto px-4 md:px-8 flex flex-col"
        >
          <div className="mx-auto w-full max-w-2xl flex-1 flex flex-col md:justify-center pt-8 md:py-8 md:pb-[8vh]">
            <div className="max-md:flex-1 flex flex-col justify-center text-center">
              <h1 className="font-serif text-display-sm md:text-display text-base-50 text-balance">
                What should the agents <em className="italic">write</em> today?
              </h1>
              <p className="mt-3 mx-auto max-w-md text-[15px] leading-6 text-base-400 line-clamp-2 text-balance">
                Research, outline, draft and audit — from a single topic.
              </p>
              {selectedModel && (
                <p className="mt-2 font-mono text-xs text-base-500">Model · {selectedModel}</p>
              )}
            </div>

            <div className="mt-8 max-md:order-3 max-md:mt-4 max-md:pb-[max(12px,env(safe-area-inset-bottom))]">{composer}</div>

            <div className="mt-4 max-md:order-2">
              {/* Template cards on roomy screens */}
              <div className="hidden roomy:grid grid-cols-3 gap-3">
                {HERO_FEATURES.map((feat) => (
                  // A real <button>, not a clickable div: Tab, Enter and Space and
                  // the focus ring all come free, and it is announced as a button.
                  // <button> only admits phrasing content, hence spans.
                  <button
                    key={feat.title}
                    type="button"
                    onClick={() => {
                      setTopicInput(feat.sampleTopic);
                      setTone(feat.sampleTone);
                      setSections(feat.sampleSections);
                    }}
                    className="group card card-interactive relative p-4 text-left"
                  >
                    <span className="grid size-8 place-items-center rounded-lg bg-hover ring-1 ring-line">
                      <feat.icon className="size-4 text-base-300" />
                    </span>
                    <ArrowUpRight className="size-4 absolute top-4 right-4 text-base-500 group-hover:text-base-200 transition-colors" />
                    <span className="block mt-3 text-ui font-medium text-base-100">{feat.title}</span>
                    <span className="block mt-1 text-ui text-base-400 line-clamp-2">{feat.desc}</span>
                  </button>
                ))}
              </div>

              {/* Compact chips on mobile and short desktop screens, so the
                  prompt never gets pushed below the fold. */}
              <div className="roomy:hidden flex gap-2 overflow-x-auto snap-x -mx-4 px-4 py-1 -my-1 md:mx-0 md:px-0 justify-center-safe [scrollbar-width:none]">
                {HERO_FEATURES.map((feat) => {
                  const Icon = feat.icon;
                  return (
                    <button
                      key={feat.title}
                      type="button"
                      onClick={() => {
                        setTopicInput(feat.sampleTopic);
                        setTone(feat.sampleTone);
                        setSections(feat.sampleSections);
                      }}
                      className="btn btn-secondary btn-sm rounded-full snap-start shrink-0"
                    >
                      <Icon className="text-base-400" />
                      {feat.chip}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </motion.section>
      ) : (
        <>
          {/* No bottom fade while the plan is up: its sticky Approve footer sits on that edge. */}
          <div className={`flex-1 min-h-0 overflow-y-auto scroll-pt-24 scroll-pb-20 px-4 md:px-8 ${isAwaitingApproval
            ? '[mask-image:linear-gradient(to_bottom,transparent,black_20px)]'
            : '[mask-image:linear-gradient(to_bottom,transparent,black_20px,black_calc(100%-28px),transparent)]'}`}>
            <div className={`mx-auto w-full max-w-3xl pb-6 flex flex-col gap-4 ${showJobBar ? '' : 'pt-6'}`}>

              {/* -------- Sticky job bar --------
                   Only this one-line bar pins; the full rail lives below it so the
                   pinned block stays short. The fill is opaque so the feed never
                   shows through it. */}
              {showJobBar && (
                <div className={`sticky top-0 z-20 -mx-4 px-4 md:mx-0 md:px-0 bg-canvas ${currentJob.status === 'completed' ? 'pt-5' : 'pt-4'} pb-2 after:pointer-events-none after:absolute after:inset-x-0 after:top-full after:h-8 after:bg-gradient-to-b after:from-canvas after:to-transparent`}>
                  <div className="flex h-11 items-center gap-3 rounded-xl bg-surface ring-1 ring-line px-3">
                    <span className={status.badge}><span className={`dot ${status.dot}`} />{status.label}</span>
                    {isAwaitingApproval
                      ? <span className="hidden sm:inline text-ui text-base-400 truncate">Review outline · {currentJob.plan?.tasks?.length ?? 0} sections</span>
                      : currentJob.status !== 'failed' && (
                          <ProgressTracker events={events} jobStatus={currentJob.status} compact className="hidden sm:flex" />
                        )}
                    <div className="ml-auto flex items-center gap-3">
                      {currentJob.id && (
                        <span className="hidden sm:inline font-mono text-xs text-base-500" title={currentJob.id}>{currentJob.id.slice(0, 8)}</span>
                      )}
                      {isLive && (
                        <span className={`font-mono text-xs tabular-nums ${isAwaitingApproval ? 'text-base-500' : 'text-base-200'}`}>{formatElapsed(elapsed)}</span>
                      )}
                      {(currentJob.status === 'failed' || currentJob.status === 'running') && handleResumeJob && (
                        <button
                          onClick={() => handleResumeJob(currentJob.id)}
                          className="btn btn-ghost btn-sm"
                          aria-label="Resume from checkpoint"
                          title="Resume pipeline execution from the last saved SQLite checkpoint"
                        >
                          <RotateCcw />
                          <span className="hidden sm:inline">Resume</span>
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Phones: the bar's compact tracker is hidden below sm, so show the full rail here. */}
              {currentJob && isLive && !isAwaitingApproval && (
                <ProgressTracker events={events} jobStatus={currentJob.status} className="sm:hidden" />
              )}

              {/* -------- Topic quote -------- */}
              {currentJob && (
                <div className="border-l-2 border-base-700 pl-4 py-1">
                  <p className="text-xs text-base-500">Topic</p>
                  <p className="mt-0.5 font-serif text-xl leading-7 text-base-50">{currentJob.topic}</p>
                  {currentJob.tone && <p className="mt-1 text-xs text-base-500">Tone · {currentJob.tone}</p>}
                </div>
              )}

              {/* -------- Timeline -------- */}
              {(events.length > 0 || isLive || currentJob?.status === 'completed') && (
                <ol className="relative [&>li:first-child>div:first-child]:mt-0 before:absolute before:left-[11px] before:top-3 before:bottom-3 before:w-px before:bg-line">
                  {isLive && events.length === 0 && (
                    <motion.li initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}>
                      <TimelineHead icon={ShieldAlert} dot="bg-base-500" label="Topic guard" />
                      <div className="flex items-baseline gap-3 rounded-lg py-1 pl-9 pr-2 bg-hover">
                        <p className="flex-1 text-ui text-base-100">
                          <Loader2 className="mr-1.5 inline size-3.5 animate-spin text-accent-400 align-[-2px]" />
                          Screening your topic and warming up the agent graph…
                        </p>
                        <span className="shrink-0 font-mono text-xs text-base-500 tabular-nums">{formatElapsed(elapsed)}</span>
                      </div>
                      <div className="mt-2 space-y-2 pl-9 pr-2">
                        <div className="skeleton-shimmer h-2 rounded w-5/6" />
                        <div className="skeleton-shimmer h-2 rounded w-3/5" />
                      </div>
                    </motion.li>
                  )}

                  {events.map((event, i) => {
                    const config = getAgentConfig(event.agent_name);
                    const head = i === 0 || events[i - 1].agent_name !== event.agent_name;
                    const isError = event.status === 'error';
                    const live = (event.status === 'working' || event.status === 'started')
                      && i === events.length - 1
                      && currentJob?.status !== 'completed'
                      && currentJob?.status !== 'failed';
                    return (
                      <motion.li
                        // Identity, not position. Resuming a job or triggering a
                        // secondary task clears the feed and refills it with different
                        // events; under index keys React reused those nodes, so the entry
                        // animation never replayed and text swapped in place. This tuple
                        // is the same one appendUniqueEvent de-dupes on, so it is unique
                        // within the list by construction.
                        key={`${event.agent_name}|${event.timestamp}|${event.message}`}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                      >
                        {head && <TimelineHead icon={config.icon} dot={config.dot} label={sentenceCase(event.agent_name)} />}
                        <div className={`flex items-baseline gap-3 rounded-lg py-1 pl-9 pr-2 ${live ? 'bg-hover' : ''}`}>
                          <p className={`flex-1 text-ui ${isError ? 'text-signal-error' : live ? 'text-base-100' : 'text-base-300'}`}>
                            {live && <Loader2 className="mr-1.5 inline size-3.5 animate-spin text-accent-400 align-[-2px]" />}
                            {isError && <><AlertTriangle className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden="true" /><span className="sr-only">Error: </span></>}
                            {event.message}
                          </p>
                          <time className="shrink-0 font-mono text-xs text-base-500 tabular-nums">{formatClock(event.timestamp)}</time>
                        </div>
                      </motion.li>
                    );
                  })}

                  {events.length === 0 && currentJob?.status === 'completed' && (
                    <li>
                      <TimelineHead icon={Network} dot="bg-base-500" label="System" />
                      <div className="flex items-baseline gap-3 rounded-lg py-1 pl-9 pr-2">
                        <p className="flex-1 text-ui text-base-300">Historical job completed successfully.</p>
                        {currentJob.completed_at && (
                          <time className="shrink-0 font-mono text-xs text-base-500 tabular-nums">
                            {formatClock(new Date(currentJob.completed_at).getTime() / 1000)}
                          </time>
                        )}
                      </div>
                    </li>
                  )}
                </ol>
              )}

              {isAwaitingApproval && currentJob?.plan && (
                <div ref={planRef}>
                  <PlanEditor
                    plan={currentJob.plan}
                    jobId={currentJob.id}
                    onApprove={() => handleApprovePlan(currentJob.id)}
                    onRevise={(fb) => handleRevisePlan(currentJob.id, fb)}
                    onUpdatePlan={(plan) => handleUpdatePlan(currentJob.id, plan)}
                  />
                </div>
              )}

              {/* -------- Failure banner -------- */}
              {currentJob?.status === 'failed' && (
                <div className="rounded-xl border border-signal-error/25 bg-signal-error-dim px-4 py-3 flex items-start gap-3">
                  <AlertTriangle className="size-4 shrink-0 text-signal-error mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-ui font-medium text-base-50">Pipeline interrupted</p>
                    <p className="text-xs text-base-400 mt-0.5">
                      This job encountered an error and was halted. Your progress is checkpointed — you can resume from exactly where it stopped.
                    </p>
                    {currentJob.error_message && (
                      <p className="mt-2 text-xs text-signal-error break-words">{currentJob.error_message}</p>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <button
                        onClick={async () => {
                          if (!handleResumeJob || isResuming) return;
                          setIsResuming(true);
                          try {
                            await handleResumeJob(currentJob.id);
                          } finally {
                            // Reset after a short delay to allow the UI to update
                            setTimeout(() => setIsResuming(false), 2000);
                          }
                        }}
                        disabled={isResuming || !handleResumeJob}
                        className="btn btn-primary btn-sm"
                      >
                        {isResuming ? (
                          <>
                            <Loader2 className="animate-spin" />
                            Resuming…
                          </>
                        ) : (
                          <>
                            <RotateCcw />
                            Resume from checkpoint
                          </>
                        )}
                      </button>
                      <span className="text-xs text-base-400">
                        Picks up from the last completed step — no work is repeated.
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Completed jobs get the full rail showing all-done; failed jobs show where it stopped. */}
              {currentJob?.status === 'completed' && (
                <ProgressTracker events={events} jobStatus={currentJob.status} />
              )}
              {currentJob?.status === 'failed' && events.length > 0 && (
                <ProgressTracker events={events} jobStatus={currentJob.status} />
              )}

              <div ref={feedEndRef} />
            </div>
          </div>

          {showComposer && (
            <div className="shrink-0 px-4 md:px-8 pt-2 pb-[max(16px,env(safe-area-inset-bottom))]">
              <div className="mx-auto w-full max-w-3xl">{composer}</div>
            </div>
          )}
        </>
      )}
    </main>
  );
}
