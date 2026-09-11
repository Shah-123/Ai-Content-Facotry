import { useState, useEffect, useRef } from 'react';
import { motion } from 'motion/react';
import {
  ListOrdered, Send, Network,
  CheckCircle2, RefreshCw, ShieldAlert, X,
  FileText, Film, Podcast, Search, Bot,
  RotateCcw, AlertTriangle, Sparkles, Paperclip
} from 'lucide-react';
import { APIClient, Job, AgentEvent, CreateJobParams, UploadResult, SourceMode } from '../api';
import { PlanEditor } from './PlanEditor';
import { UploadChip } from './UploadChip';
import { ProgressTracker } from './ProgressTracker';

function getAgentConfig(agentName: string) {
  const name = agentName.toLowerCase();
  if (name.includes('research')) {
    return {
      icon: Search,
      iconColor: 'text-sky-400',
      bgColor: 'bg-sky-500/10 border-sky-500/20',
      textColor: 'text-sky-400',
    };
  }
  if (name.includes('orchestrat') || name.includes('plan')) {
    return {
      icon: ListOrdered,
      iconColor: 'text-purple-400',
      bgColor: 'bg-purple-500/10 border-purple-500/20',
      textColor: 'text-purple-400',
    };
  }
  if (name.includes('writer') || name.includes('edit')) {
    return {
      icon: FileText,
      iconColor: 'text-amber-400',
      bgColor: 'bg-amber-500/10 border-amber-500/20',
      textColor: 'text-amber-400',
    };
  }
  if (name.includes('quality') || name.includes('control') || name.includes('validator') || name.includes('critic')) {
    return {
      icon: ShieldAlert,
      iconColor: 'text-emerald-400',
      bgColor: 'bg-emerald-500/10 border-emerald-500/20',
      textColor: 'text-emerald-400',
    };
  }
  if (name.includes('video')) {
    return {
      icon: Film,
      iconColor: 'text-pink-400',
      bgColor: 'bg-pink-500/10 border-pink-500/20',
      textColor: 'text-pink-400',
    };
  }
  if (name.includes('audio') || name.includes('podcast')) {
    return {
      icon: Podcast,
      iconColor: 'text-indigo-400',
      bgColor: 'bg-indigo-500/10 border-indigo-500/20',
      textColor: 'text-indigo-400',
    };
  }
  return {
    icon: Bot,
    iconColor: 'text-base-400',
    bgColor: 'bg-base-500/10 border-white/6',
    textColor: 'text-base-300',
  };
}


const ACCEPTED_UPLOAD_TYPES = '.pdf,.docx,.txt,.md';

/** mm:ss for the live run clock. */
const formatElapsed = (secs: number) =>
  `${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(secs % 60).padStart(2, '0')}`;

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
    gradient: 'from-amber-500/20 to-orange-600/10',
    sampleTopic: 'How LangGraph enables persistent agent loops',
    sampleTone: 'technical',
    sampleSections: 4,
  },
  {
    icon: Film,
    title: 'Video Generation',
    desc: 'Automated storyboard, AI voiceover, and Pexels B-roll compilation.',
    gradient: 'from-blue-500/20 to-indigo-600/10',
    sampleTopic: 'A brief guide to stock video synthesis with Pexels',
    sampleTone: 'conversational',
    sampleSections: 2,
  },
  {
    icon: Podcast,
    title: 'Podcast Studio',
    desc: 'Gemini-powered conversational audio with custom voice synthesis.',
    gradient: 'from-emerald-500/20 to-teal-600/10',
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
  const feedEndRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
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

  return (
    <main className="flex-1 flex flex-col p-4 md:p-8 relative overflow-y-auto md:overflow-hidden">
      <div className="md:flex-1 overflow-visible md:overflow-y-auto pr-0 md:pr-4 flex flex-col gap-5 pb-4 scroll-smooth">
        <header className="mb-2 shrink-0 fade-in">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-base-50 mb-1.5">
            {!currentJob
              ? 'Dashboard'
              : currentJob.status === 'completed'
                ? 'Generation Complete'
                : currentJob.status === 'failed'
                  ? 'Pipeline Interrupted'
                  : currentJob.status === 'awaiting_approval'
                    ? 'Review Outline'
                    : 'Generating…'}
          </h2>
          <p className="text-base-400 text-sm flex items-center gap-2.5">
            <span className="font-mono text-[11px] text-base-500">Powered by LangGraph</span>
            {currentJob && currentJob.status !== 'completed' && currentJob.status !== 'failed' && (
              <span className="px-2 py-0.5 rounded-md bg-accent-glow text-accent-400 text-[11px] font-semibold border border-accent-500/20 flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-accent-500 status-pulse" /> Processing
              </span>
            )}
            {currentJob?.status === 'completed' && (
              <span className="px-2 py-0.5 rounded-md bg-signal-success-dim text-signal-success text-[11px] font-semibold border border-signal-success/20 flex items-center gap-1.5">
                <CheckCircle2 className="w-3 h-3" /> Completed
              </span>
            )}
          </p>
        </header>
        {/* -------- Welcome Hero (shown when no job is active) -------- */}
        {showHero && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6 }}
            className="flex flex-col items-center justify-center py-3 md:py-12 relative"
          >
            {/* Ambient glow behind heading */}
            <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[400px] h-[200px] bg-accent-500/8 rounded-full blur-[80px] pointer-events-none hidden md:block" />

            {/* Version Badge & Active Model */}
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.1, duration: 0.4 }}
              className="hidden sm:flex items-center gap-2.5 mb-5 relative z-10"
            >
              <span className="glass-pill px-3 py-1 text-[10px] font-bold text-accent-400 tracking-wider uppercase border border-accent-500/20">
                Orchestration Engine v2.0
              </span>
              <span className="glass-pill px-3 py-1 text-[10px] font-medium text-base-300 border border-white/6 flex items-center gap-1.5 shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-signal-success animate-pulse"></span>
                Active LLM: <span className="font-mono text-accent-400 font-bold">{selectedModel}</span>
              </span>
            </motion.div>

            <motion.h3
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, duration: 0.5 }}
              className="text-2xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-center mb-2 md:mb-3 text-shimmer relative z-10"
            >
              Create Something Amazing
            </motion.h3>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.4 }}
              className="text-base-400 text-center max-w-lg mb-4 md:mb-8 px-2 text-[13px] md:text-sm leading-relaxed relative z-10"
            >
              Enter a topic below and our multi-agent pipeline will research, write, and polish a publication-ready blog — with optional video, podcast, and social campaigns.
            </motion.p>

            {/* Feature cards */}
            <div className="hidden roomy:grid md:grid-cols-3 gap-4 w-full max-w-3xl relative z-10">
              {HERO_FEATURES.map((feat, i) => (
                // A real <button>, not a clickable div: Tab, Enter and Space and
                // the focus ring all come free, and it is announced as a button.
                // The heading and paragraph became spans because <button> only
                // admits phrasing content; the styling is utility classes, so
                // nothing changes visually.
                <motion.button
                  key={feat.title}
                  type="button"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 + i * 0.1, duration: 0.4 }}
                  onClick={() => {
                    setTopicInput(feat.sampleTopic);
                    setTone(feat.sampleTone);
                    setSections(feat.sampleSections);
                  }}
                  className={`glass-panel rounded-2xl p-5 text-left border border-white/6 hover-lift cursor-pointer hover:border-accent-500/30 focus-visible:outline-none focus-visible:border-accent-500/60 focus-visible:ring-2 focus-visible:ring-accent-500/40 bg-gradient-to-br ${feat.gradient} flex flex-col justify-between group`}
                >
                  <span className="block">
                    <span className="w-10 h-10 rounded-xl bg-white/5 border border-white/8 flex items-center justify-center mb-3 group-hover:scale-105 group-hover:border-accent-500/20 transition-all duration-300">
                      <feat.icon className="w-5 h-5 text-accent-400" />
                    </span>
                    <span className="block font-bold text-base-100 text-sm mb-1">{feat.title}</span>
                    <span className="block text-[12px] text-base-400 leading-relaxed mb-4">{feat.desc}</span>
                  </span>
                  <span className="text-[10px] text-accent-400 font-semibold underline underline-offset-2 opacity-70 group-hover:opacity-100 group-hover:text-accent-300 transition-all duration-200">
                    Use Template
                  </span>
                </motion.button>
              ))}
            </div>

            {/* Stands in for the feature cards on mobile and on short desktop screens,
                so the prompt never gets pushed below the fold. */}
            <div className="flex roomy:hidden flex-wrap justify-center gap-2 w-full relative z-10">
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
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/8 bg-base-900/70 px-2.5 py-1.5 text-[11px] font-semibold text-base-300 transition-colors hover:border-accent-500/35 hover:text-accent-400"
                  >
                    <Icon className="h-3.5 w-3.5 text-accent-400" />
                    {feat.title}
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* -------- Job Controls Banner + Pipeline Rail (pinned) --------
             Sticky so the at-a-glance status stays on screen while the agent
             log scrolls underneath it. */}
        {currentJob && currentJob.status !== 'completed' && (
          <div className="sticky top-0 z-20 -mt-2 pt-2 pb-1 bg-base-950/85 backdrop-blur-xl">
            <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl glass-panel border border-white/8 backdrop-blur-md w-full">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${
                  currentJob.status === 'failed' ? 'bg-signal-error' :
                  currentJob.status === 'awaiting_approval' ? 'bg-amber-400 animate-ping' :
                  'bg-accent-400 animate-pulse'
                }`} />
                <span className="text-xs font-bold text-base-100 uppercase tracking-wider">
                  {currentJob.id
                    ? `Job #${currentJob.id.slice(0, 8)} — ${currentJob.status.replace('_', ' ')}`
                    : 'Starting pipeline'}
                </span>
                {isLive && (
                  <span className="text-[11px] font-mono text-base-400 tabular-nums px-2 py-0.5 rounded-md bg-white/5 border border-white/8">
                    {formatElapsed(elapsed)}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {(currentJob.status === 'failed' || currentJob.status === 'running') && handleResumeJob && (
                  <button
                    onClick={() => handleResumeJob(currentJob.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent-500/20 text-accent-400 hover:bg-accent-500/30 border border-accent-500/30 transition-all cursor-pointer shadow-sm"
                    title="Resume pipeline execution from the last saved SQLite checkpoint"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Resume Checkpoint
                  </button>
                )}
              </div>
            </div>

            {currentJob.status !== 'failed' && (
              <ProgressTracker events={events} jobStatus={currentJob.status} />
            )}
          </div>
        )}

        {currentJob && (
          <div className="self-end max-w-2xl w-full">
            <div className="aurora-bubble p-5 rounded-2xl rounded-tr-sm">
              <p className="text-base font-medium">Write a blog on: {currentJob.topic}</p>
              <p className="text-sm opacity-70 mt-1">Tone: {currentJob.tone}</p>
            </div>
            <div className="text-right mt-1.5 text-[11px] text-base-500 font-medium">You</div>
          </div>
        )}

        {isLive && events.length === 0 && (
          <motion.div
            className="self-start max-w-3xl flex gap-3.5 w-full"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border bg-accent-500/10 border-accent-500/20">
              <Sparkles className="w-4 h-4 text-accent-400 animate-pulse" />
            </div>
            <div className="glass-panel p-4.5 rounded-2xl rounded-tl-sm flex-1 border border-white/5 shadow-sm">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider bg-accent-500/10 border border-accent-500/20 text-accent-400">
                  topic guard
                </span>
                <span className="text-[10px] text-base-500 font-mono">{formatElapsed(elapsed)}</span>
              </div>
              <p className="text-base-200 text-sm flex items-center gap-2.5 leading-relaxed mt-2.5">
                <RefreshCw className="w-3.5 h-3.5 text-accent-400 animate-spin shrink-0" />
                <span className="flex-1">Screening your topic and warming up the agent graph…</span>
              </p>
              <div className="mt-3.5 space-y-2">
                <div className="skeleton-shimmer h-2.5 w-[85%]" />
                <div className="skeleton-shimmer h-2.5 w-[62%]" />
              </div>
            </div>
          </motion.div>
        )}

        {events.map((event, i) => {
          const config = getAgentConfig(event.agent_name);
          const AgentIcon = config.icon;
          return (
            <motion.div
              // Identity, not position. Resuming a job or triggering a
              // secondary task clears the feed and refills it with different
              // events; under index keys React reused those nodes, so the entry
              // animation never replayed and text swapped in place. This tuple
              // is the same one appendUniqueEvent de-dupes on, so it is unique
              // within the list by construction.
              key={`${event.agent_name}|${event.timestamp}|${event.message}`}
              className="self-start max-w-3xl flex gap-3.5 w-full"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: Math.min(i * 0.03, 0.3) }}
            >
              <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border ${config.bgColor}`}>
                <AgentIcon className={`w-4 h-4 ${config.iconColor}`} />
              </div>
              <div className="glass-panel p-4.5 rounded-2xl rounded-tl-sm flex-1 border border-white/5 shadow-sm">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider ${config.bgColor} ${config.textColor}`}>
                      {event.agent_name}
                    </span>
                  </div>
                  <span className="text-[10px] text-base-500 font-mono">{new Date(event.timestamp * 1000).toLocaleTimeString()}</span>
                </div>
                <p className="text-base-200 text-sm flex items-center gap-2.5 leading-relaxed mt-2.5">
                  {event.status === 'error'
                    ? <span className="text-signal-error font-bold text-xs shrink-0">ERR</span>
                    : (event.status === 'working' || event.status === 'started')
                         && i === events.length - 1
                         && currentJob?.status !== 'completed'
                         && currentJob?.status !== 'failed'
                      ? <RefreshCw className="w-3.5 h-3.5 text-accent-400 animate-spin shrink-0" />
                      : <CheckCircle2 className="w-4 h-4 text-signal-success shrink-0" />}
                  <span className="flex-1">{event.message}</span>
                </p>
              </div>
            </motion.div>
          );
        })}

        {events.length === 0 && currentJob?.status === 'completed' && (
          <div className="self-start max-w-3xl flex gap-3 w-full">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 bg-base-800 border border-white/6">
              <Network className="w-4 h-4 text-accent-400" />
            </div>
            <div className="glass-panel p-4 rounded-2xl rounded-tl-sm flex-1">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="font-semibold text-sm text-accent-400 capitalize">system</span>
                {currentJob.completed_at && <span className="text-[11px] text-base-500 font-mono">{new Date(currentJob.completed_at).toLocaleTimeString()}</span>}
              </div>
              <p className="text-base-200 text-sm flex items-center gap-2 leading-relaxed">
                <CheckCircle2 className="w-4 h-4 text-signal-success shrink-0" />
                Historical job completed successfully.
              </p>
            </div>
          </div>
        )}

        {/* Completed job also gets a progress tracker showing all-done */}
        {currentJob?.status === 'completed' && (
          <ProgressTracker events={events} jobStatus={currentJob.status} />
        )}

        {isAwaitingApproval && currentJob?.plan && (
          <PlanEditor
            plan={currentJob.plan}
            jobId={currentJob.id}
            onApprove={() => handleApprovePlan(currentJob.id)}
            onRevise={(fb) => handleRevisePlan(currentJob.id, fb)}
            onUpdatePlan={(plan) => handleUpdatePlan(currentJob.id, plan)}
          />
        )}

        {/* -------- Failed Job Resume Banner -------- */}
        {currentJob?.status === 'failed' && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
            className="w-full max-w-3xl self-start"
          >
            <div className="relative overflow-hidden rounded-2xl border border-signal-error/30 bg-signal-error-dim/20 backdrop-blur-xl shadow-md">
              {/* Subtle animated glow bar at top */}
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-signal-error/60 to-transparent" />

              <div className="p-5 md:p-6">
                {/* Header */}
                <div className="flex items-start gap-3.5 mb-4">
                  <div className="w-10 h-10 rounded-xl bg-signal-error-dim border border-signal-error/25 flex items-center justify-center shrink-0">
                    <AlertTriangle className="w-5 h-5 text-signal-error" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h4 className="text-base font-bold text-signal-error mb-0.5">Pipeline Interrupted</h4>
                    <p className="text-sm text-base-300 leading-relaxed">
                      This job encountered an error and was halted. Your progress is checkpointed — you can resume from exactly where it stopped.
                    </p>
                  </div>
                </div>

                {/* Error Details */}
                {currentJob.error_message && (
                  <div className="mb-4 p-3 rounded-xl bg-base-950/60 border border-signal-error/20">
                    <div className="text-[10px] font-bold text-base-400 uppercase tracking-wider mb-1.5">Error Details</div>
                    <p className="text-xs text-signal-error font-mono leading-relaxed break-all font-medium">
                      {currentJob.error_message}
                    </p>
                  </div>
                )}

                {/* Resume Action */}
                <div className="flex items-center gap-3">
                  <motion.button
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
                    className={`resume-btn flex items-center gap-2.5 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-300 ${
                      isResuming
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30 cursor-wait'
                        : 'bg-gradient-to-r from-amber-500 to-orange-500 text-amber-950 hover:from-amber-400 hover:to-orange-400 shadow-lg shadow-amber-500/20 hover:shadow-amber-500/30 hover:scale-[1.02] active:scale-[0.98]'
                    }`}
                    whileHover={!isResuming ? { scale: 1.03 } : undefined}
                    whileTap={!isResuming ? { scale: 0.97 } : undefined}
                  >
                    {isResuming ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        Resuming…
                      </>
                    ) : (
                      <>
                        <RotateCcw className="w-4 h-4" />
                        Resume from Checkpoint
                      </>
                    )}
                  </motion.button>
                  <span className="text-[11px] text-base-500">
                    Picks up from the last completed step — no work is repeated.
                  </span>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {/* Show progress tracker for failed jobs too (shows where it stopped) */}
        {currentJob?.status === 'failed' && events.length > 0 && (
          <ProgressTracker events={events} jobStatus={currentJob.status} />
        )}


        <div ref={feedEndRef} />
      </div>

      {(!currentJob || currentJob.status === 'completed' || currentJob.status === 'failed') && (
        <div className="w-full max-w-4xl mx-auto mt-4 shrink-0 z-30">
          {topicError && (
            <div className="max-w-4xl mx-auto mb-3 fade-in">
              <div className="flex items-start gap-3 p-3.5 pr-2 rounded-xl border border-signal-error/30 bg-signal-error-dim text-signal-error">
                <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
                <div className="flex-1 text-sm leading-relaxed">
                  <span className="font-semibold">Topic rejected.</span>{' '}
                  <span className="text-base-200">{topicError.reason}</span>
                  {topicError.suggested_topic && (
                    <button
                      onClick={() => {
                        setTopicInput(topicError.suggested_topic!);
                        clearTopicError?.();
                      }}
                      className="block mt-2 text-xs text-accent-300 hover:text-accent-200 underline underline-offset-2"
                    >
                      Try this instead: "{topicError.suggested_topic}"
                    </button>
                  )}
                </div>
                <button
                  onClick={() => clearTopicError?.()}
                  className="p-1.5 text-base-400 hover:text-base-100 rounded-md hover:bg-white/5 shrink-0"
                  aria-label="Dismiss"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}


          <div className="w-full max-w-4xl mx-auto rounded-3xl p-3 bg-base-900/90 dark:bg-base-950/90 backdrop-blur-2xl border border-base-750/80 hover:border-accent-500/40 focus-within:border-accent-500/60 focus-within:shadow-[0_8px_35px_rgba(245,158,11,0.14)] shadow-2xl transition-all duration-300 flex flex-col gap-2">

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

            {/* Prompt Textarea */}
            <div className="w-full px-1">
              <textarea
                className="w-full bg-transparent border-none text-base-100 placeholder-base-400/70 text-base font-medium min-h-[30px] max-h-[180px] resize-none overflow-y-auto focus:outline-none focus:ring-0 leading-relaxed font-sans"
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
            </div>

            {/* Control Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-2 border-t border-base-800/80 pt-2 px-1">
              {/* Left Side Tools: Attach Doc */}
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadStatus === 'uploading'}
                  title="Attach a document (PDF, DOCX, TXT, MD)"
                  className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-1.5 rounded-xl text-xs font-semibold transition-all shadow-sm ${
                    uploadStatus === 'ready'
                      ? 'text-accent-400 bg-accent-500/15 border border-accent-500/30'
                      : 'text-base-300 hover:text-accent-400 bg-base-800/80 hover:bg-base-750 border border-base-700/60 hover:border-accent-500/30'
                  } ${uploadStatus === 'uploading' ? 'opacity-50 cursor-wait' : ''}`}
                >
                  <Paperclip className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Attach Doc</span>
                </button>
              </div>

              {/* Right Side Tools: Shortcut Hint + Send Button */}
              <div className="ml-auto flex shrink-0 items-center gap-3">
                <span className="hidden md:flex items-center gap-1.5 text-[11px] font-mono text-base-400">
                  <span>Press <kbd className="px-1.5 py-0.5 rounded-md bg-base-800 border border-base-700 text-[10px] text-base-300 font-sans shadow-inner">Enter ↵</kbd></span>
                </span>

                <motion.button
                  onClick={() => submitJob()}
                  disabled={
                    uploadStatus === 'uploading'
                    || (!topicInput.trim()
                        && !(sourceMode === 'auto_topic' && uploadStatus === 'ready' && !!uploadResult?.derived_topic))
                  }
                  className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 shadow-lg transition-all ${
                    (uploadStatus === 'uploading'
                     || (!topicInput.trim()
                         && !(sourceMode === 'auto_topic' && uploadStatus === 'ready' && !!uploadResult?.derived_topic)))
                      ? 'bg-base-800 text-base-500 border border-base-700 cursor-not-allowed shadow-none'
                      : 'bg-gradient-to-r from-accent-400 to-accent-600 hover:from-accent-300 hover:to-accent-500 text-base-950 shadow-accent-500/25 active:scale-95'
                  }`}
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                >
                  <span>Generate</span>
                  <Send className="w-3.5 h-3.5" />
                </motion.button>
              </div>
            </div>

          </div>
        </div>
      )}
    </main>
  );
}
