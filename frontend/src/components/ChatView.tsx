import { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'motion/react';
import {
  ListOrdered, PlusCircle, Send, Network,
  CheckCircle2, RefreshCw, ShieldAlert, X, Hash,
  FileText, Film, Podcast
} from 'lucide-react';
import { APIClient, Job, AgentEvent, CreateJobParams, UploadResult, SourceMode } from '../api';
import { ViewState } from '../types';
import { PlanEditor } from './PlanEditor';
import { UploadChip } from './UploadChip';
import { ProgressTracker } from './ProgressTracker';


const ACCEPTED_UPLOAD_TYPES = '.pdf,.docx,.txt,.md';

interface ChatViewProps {
  navTo: (v: ViewState) => void;
  currentJob: Job | null;
  events: AgentEvent[];
  topicError?: { reason: string; category?: string; suggested_topic?: string } | null;
  clearTopicError?: () => void;
  handleCreateJob:    (params: CreateJobParams) => void;
  handleApprovePlan:  (jobId: string) => void;
  handleRevisePlan:   (jobId: string, feedback: string) => void;
  handleUpdatePlan:   (jobId: string, plan: any) => void;
  tone: string;
  setTone: (t: string) => void;
  sections: number;
  setSections: (s: number) => void;
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
  handleCreateJob, handleApprovePlan, handleRevisePlan, handleUpdatePlan,
  tone, setTone, sections, setSections, keywordsInput, setKeywordsInput, selectedModel
}: ChatViewProps) {
  const [topicInput, setTopicInput] = useState('');

  // Document upload state
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'ready' | 'error'>('idle');
  const [uploadName, setUploadName] = useState<string>('');
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string>('');
  const [sourceMode, setSourceMode] = useState<SourceMode>('hybrid');
  const fileInputRef = useRef<HTMLInputElement | null>(null);




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
      upload_id,
      source_mode: upload_id ? sourceMode : undefined,
    });
    setTopicInput('');
    setKeywordsInput('');
    clearUpload();
  };




  const isAwaitingApproval = currentJob?.status === 'awaiting_approval';
  const showHero = !currentJob && events.length === 0;

  return (
    <main className="flex-1 flex flex-col p-6 md:p-8 relative overflow-hidden">
      <div className="flex-1 overflow-y-auto pr-2 md:pr-4 flex flex-col gap-5 pb-4 scroll-smooth">
        <header className="mb-2 shrink-0 fade-in">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight text-base-50 mb-1.5">AI Content Factory</h2>
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
            className="flex flex-col items-center justify-center py-6 md:py-12 relative"
          >
            {/* Ambient glow behind heading */}
            <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[400px] h-[200px] bg-accent-500/8 rounded-full blur-[80px] pointer-events-none" />

            {/* Version Badge & Active Model */}
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.1, duration: 0.4 }}
              className="flex items-center gap-2.5 mb-5 relative z-10"
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
              className="text-4xl md:text-5xl font-extrabold tracking-tight text-center mb-3 text-shimmer relative z-10"
            >
              Create Something Amazing
            </motion.h3>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.4 }}
              className="text-base-400 text-center max-w-lg mb-8 text-sm leading-relaxed relative z-10"
            >
              Enter a topic below and our multi-agent pipeline will research, write, and polish a publication-ready blog — with optional video, podcast, and social campaigns.
            </motion.p>

            {/* Feature cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full max-w-3xl relative z-10">
              {HERO_FEATURES.map((feat, i) => (
                <motion.div
                  key={feat.title}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 + i * 0.1, duration: 0.4 }}
                  onClick={() => {
                    setTopicInput(feat.sampleTopic);
                    setTone(feat.sampleTone);
                    setSections(feat.sampleSections);
                  }}
                  className={`glass-panel rounded-2xl p-5 border border-white/6 hover-lift cursor-pointer hover:border-accent-500/30 bg-gradient-to-br ${feat.gradient} flex flex-col justify-between group`}
                >
                  <div>
                    <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/8 flex items-center justify-center mb-3 group-hover:scale-105 group-hover:border-accent-500/20 transition-all duration-300">
                      <feat.icon className="w-5 h-5 text-accent-400" />
                    </div>
                    <h4 className="font-bold text-base-100 text-sm mb-1">{feat.title}</h4>
                    <p className="text-[12px] text-base-400 leading-relaxed mb-4">{feat.desc}</p>
                  </div>
                  <span className="text-[10px] text-accent-400 font-semibold underline underline-offset-2 opacity-70 group-hover:opacity-100 group-hover:text-accent-300 transition-all duration-200">
                    Use Template
                  </span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}

        {/* -------- Progress Tracker (when a job is running) -------- */}
        {currentJob && currentJob.status !== 'completed' && currentJob.status !== 'failed' && events.length > 0 && (
          <ProgressTracker events={events} jobStatus={currentJob.status} />
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

        {events.map((event, i) => (
          <motion.div
            key={i}
            className="self-start max-w-3xl flex gap-3 w-full"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: Math.min(i * 0.03, 0.3) }}
          >
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${event.status === 'error' ? 'bg-signal-error-dim' : 'bg-base-800 border border-white/6'}`}>
              <Network className={`w-4 h-4 ${event.status === 'error' ? 'text-signal-error' : 'text-accent-400'}`} />
            </div>
            <div className="glass-panel p-4 rounded-2xl rounded-tl-sm flex-1">
              <div className="flex items-center gap-2 mb-1.5">
                <span className={`font-semibold text-sm ${event.status === 'error' ? 'text-signal-error' : 'text-accent-400'} capitalize`}>{event.agent_name}</span>
                <span className="text-[11px] text-base-500 font-mono">{new Date(event.timestamp * 1000).toLocaleTimeString()}</span>
              </div>
              <p className="text-base-200 text-sm flex items-center gap-2 leading-relaxed">
                {event.status === 'error'
                  ? <span className="text-signal-error font-bold text-xs">ERR</span>
                  : (event.status === 'working' || event.status === 'started')
                       && i === events.length - 1
                       && currentJob?.status !== 'completed'
                       && currentJob?.status !== 'failed'
                    ? <RefreshCw className="w-3.5 h-3.5 text-accent-400 animate-spin shrink-0" />
                    : <CheckCircle2 className="w-4 h-4 text-signal-success shrink-0" />}
                {event.message}
              </p>
            </div>
          </motion.div>
        ))}

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


          <div className="glass-panel rounded-2xl p-4 flex flex-col gap-3 max-w-4xl mx-auto bg-base-900/90">

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

            <div className="flex items-end gap-2 bg-base-800 rounded-xl p-2 border border-white/6 focus-within:border-accent-500/30 transition-colors">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadStatus === 'uploading'}
                title="Attach a document (PDF, DOCX, TXT, MD)"
                className={`p-2.5 transition-colors hidden sm:block rounded-lg ${
                  uploadStatus === 'ready'
                    ? 'text-accent-400 bg-accent-500/10 hover:bg-accent-500/15'
                    : 'text-base-500 hover:text-accent-400 hover:bg-white/3'
                } ${uploadStatus === 'uploading' ? 'opacity-50 cursor-wait' : ''}`}
              >
                <PlusCircle className="w-5 h-5" />
              </button>
              <textarea
                className="flex-1 bg-transparent border-none text-base-100 focus:ring-0 resize-none py-2.5 px-2 placeholder-base-500 text-sm h-[44px] focus:outline-none leading-relaxed"
                placeholder={
                  uploadStatus === 'ready' && sourceMode === 'auto_topic'
                    ? (uploadResult?.derived_topic
                        ? `Auto-topic ready — press Send (or override: "${uploadResult.derived_topic}")`
                        : 'Auto-topic mode — enter or override the title...')
                    : 'Enter a topic to generate a new blog...'
                }
                value={topicInput}
                onChange={e => setTopicInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitJob(); } }}
              />
              <motion.button
                onClick={() => submitJob()}
                disabled={
                  uploadStatus === 'uploading'
                  || (!topicInput.trim()
                      && !(sourceMode === 'auto_topic' && uploadStatus === 'ready' && !!uploadResult?.derived_topic))
                }
                className={`btn-primary w-10 h-10 rounded-xl flex items-center justify-center shrink-0 group ${
                  (uploadStatus === 'uploading'
                   || (!topicInput.trim()
                       && !(sourceMode === 'auto_topic' && uploadStatus === 'ready' && !!uploadResult?.derived_topic)))
                    ? 'opacity-40 cursor-not-allowed shadow-none! transform-none!'
                    : ''
                }`}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <Send className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </motion.button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
