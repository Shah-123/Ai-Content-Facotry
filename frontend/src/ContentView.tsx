import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  CheckCircle2, Clock, Podcast, Film, Share2, Download,
  FileText, History, Settings, Image as ImageIcon,
  Play, Volume2, Copy, RefreshCw, LayoutTemplate, Bot, Trash2,
  GraduationCap, Sparkles
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { APIClient, Job, AgentEvent } from './api';
import { TabButton } from './components/TabButton';
import { EmptyState } from './components/EmptyState';
import { LoadingState } from './components/LoadingState';
import { DeepEvalSection } from './components/DeepEvalSection';
import { RubricDetailCard } from './components/RubricDetailCard';
import { PodcastPlayer } from './components/PodcastPlayer';

type ViewState = 'chat' | 'content';
type TabState = 'blog' | 'geval' | 'video' | 'podcast' | 'images' | 'social';

export function ContentView({ navTo, currentJob, refreshJob, events = [], reconnectWS, onDeleteJob }: { navTo: (v: ViewState) => void, currentJob: Job | null, refreshJob: () => void, events?: AgentEvent[], reconnectWS?: (jobId: string) => void, onDeleteJob?: (id: string) => void }) {
  const [activeTab, setActiveTab] = useState<TabState>('blog');
  const [hoveredMetric, setHoveredMetric] = useState<string | null>(null);
  const [triggering, setTriggering] = useState<Record<string, boolean>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTaskRunning = (startAgentName: string) => {
    const triggerKey = startAgentName === 'campaign' ? 'social' : startAgentName;
    if (triggering[triggerKey]) return true;

    let lastStartIdx = -1;
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].agent_name === startAgentName && events[i].status === 'started') {
        lastStartIdx = i;
        break;
      }
    }
    if (lastStartIdx === -1) return false;

    for (let i = lastStartIdx + 1; i < events.length; i++) {
      if (events[i].status === 'completed' || events[i].status === 'error') {
        return false;
      }
    }
    return true;
  };

  const hasTaskCompleted = (startAgentName: string) => {
    let lastStartIdx = -1;
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].agent_name === startAgentName && events[i].status === 'started') {
        lastStartIdx = i;
        break;
      }
    }
    if (lastStartIdx === -1) return false;

    for (let i = lastStartIdx + 1; i < events.length; i++) {
      if (events[i].status === 'completed') {
        return true;
      }
    }
    return false;
  };

  const getLastTaskError = (startAgentName: string) => {
    let lastStartIdx = -1;
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].agent_name === startAgentName && events[i].status === 'started') {
        lastStartIdx = i;
        break;
      }
    }
    if (lastStartIdx === -1) return null;

    for (let i = lastStartIdx + 1; i < events.length; i++) {
      if (events[i].status === 'error') {
        return events[i].message;
      }
    }
    return null;
  };

  const getCurrentRunEvents = (taskName: string) => {
    const startAgentName = taskName === 'social' ? 'campaign' : taskName;
    let lastStartIdx = -1;
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].agent_name === startAgentName && events[i].status === 'started') {
        lastStartIdx = i;
        break;
      }
    }
    const sliced = lastStartIdx === -1 ? events : events.slice(lastStartIdx);
    return sliced.filter(e => {
      if (taskName === 'video') return e.agent_name === 'video';
      if (taskName === 'podcast') return e.agent_name === 'podcast' || e.agent_name === 'podcast_generator';
      if (taskName === 'social') return e.agent_name === 'campaign' || e.agent_name === 'campaign_generator';
      if (taskName === 'images') return e.agent_name === 'images';
      return false;
    });
  };

  // Auto-clear triggering flags when generated data appears in the job
  useEffect(() => {
    if (!currentJob) return;
    setTriggering(prev => {
      const next = { ...prev };
      let changed = false;
      if (prev.social && (currentJob.social_linkedin || currentJob.social_twitter)) { next.social = false; changed = true; }
      if (prev.video && currentJob.video_file) { next.video = false; changed = true; }
      if (prev.podcast && currentJob.podcast_file) { next.podcast = false; changed = true; }
      if (prev.qa && currentJob.qa_score != null) { next.qa = false; changed = true; }
      if (prev.images && currentJob.final_content) { next.images = false; changed = true; }
      if (prev.deepeval && currentJob.deepeval_scores) { next.deepeval = false; changed = true; }
      return changed ? next : prev;
    });
  }, [currentJob]);

  // Clear triggering['images'] when backend events signal completion
  // (images task doesn't update final_content, so the general useEffect above won't catch it)
  useEffect(() => {
    if (hasTaskCompleted('images') && triggering['images']) {
      setTriggering(prev => ({ ...prev, images: false }));
    }
  }, [events]);

  // Stop polling when no tasks are active
  useEffect(() => {
    const anyActive = Object.values(triggering).some(v => v);
    if (!anyActive && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
      if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
    }
  }, [triggering]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const handleTrigger = async (task: string) => {
    if (!currentJob) return;
    setTriggering(p => ({ ...p, [task]: true }));
    try {
      // Re-connect the WebSocket so secondary-task events stream back live.
      // The main pipeline WS closes itself on system:completed, so we must re-dial.
      if (reconnectWS) {
        reconnectWS(currentJob.id);
      }
      if (task === 'qa') await APIClient.triggerQA(currentJob.id);
      if (task === 'podcast') await APIClient.triggerPodcast(currentJob.id);
      if (task === 'video') await APIClient.triggerVideo(currentJob.id);
      if (task === 'social') await APIClient.triggerSocial(currentJob.id);
      if (task === 'images') await APIClient.triggerImages(currentJob.id);
      if (task === 'deepeval') await APIClient.runDeepEval(currentJob.id);
      // Start polling to detect when the background task completes
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(() => { refreshJob(); }, 3000);
      // Safety timeout — podcast needs ~10 min (20 turns × 25s sleep + TTS time);
      // everything else is capped at 5 min.
      const safetyMs = task === 'podcast' ? 15 * 60 * 1000 : 5 * 60 * 1000;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        setTriggering(p => ({ ...p, [task]: false }));
      }, safetyMs);
    } catch (e) {
      console.error(`Failed to trigger ${task}`);
      setTriggering(p => ({ ...p, [task]: false }));
    }
  };

  // Helper helper to compute radar chart SVG points
  const getRadarPoints = () => {
    if (!currentJob?.geval_scores) return '';
    const scores = currentJob.geval_scores;
    const center = 50;
    const maxVal = 5;
    const scale = 30; // Radius size of 5 max

    // Angles for Coherence (top, 0), Relevance (right, 90), Accuracy (bottom, 180), Tone Alignment (left, 270)
    // Angles in radians: Coherence = -pi/2, Relevance = 0, Accuracy = pi/2, Tone = pi
    const metrics = [
      { score: scores.coherence?.score || 3, angle: -Math.PI / 2 },
      { score: scores.relevance?.score || 3, angle: 0 },
      { score: scores.accuracy?.score || 3, angle: Math.PI / 2 },
      { score: scores.tone_alignment?.score || 3, angle: Math.PI }
    ];

    return metrics.map(m => {
      const dist = (m.score / maxVal) * scale;
      const x = center + dist * Math.cos(m.angle);
      const y = center + dist * Math.sin(m.angle);
      return `${x},${y}`;
    }).join(' ');
  };

  if (!currentJob) {
    return (
      <main className="flex-1 p-6 md:p-10 flex flex-col items-center justify-center text-slate-500">
        <FileText className="w-12 h-12 mb-4 opacity-50" />
        <p>Select a job to view drafts.</p>
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
            <button className="text-base-400 text-sm font-medium hover:text-accent-400 transition-colors flex items-center gap-1.5 px-3 py-1.5 rounded-xl hover:bg-white/3">
              <History className="w-4 h-4" /> Versions
            </button>
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
              <article className="high-contrast-card rounded-2xl p-8 md:p-12 shadow-[0_20px_50px_rgba(0,0,0,0.3)] relative overflow-hidden bg-white text-slate-800">
                <div className="absolute top-0 left-0 w-full h-1 bg-linear-to-r from-accent-500 to-accent-600"></div>
                {currentJob.final_content ? (
                  <div className="prose prose-slate max-w-none prose-headings:text-slate-900 prose-a:text-accent-600 hover:prose-a:text-accent-500">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {currentJob.final_content}
                    </ReactMarkdown>
                  </div>
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
                          <polygon points={getRadarPoints()} fill="var(--color-accent-glow)" stroke="var(--color-accent-500)" strokeWidth="1.5" strokeLinejoin="round" />

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
                  <LoadingState title="Generating Images..." description="Our AI is crafting custom visuals to enhance your blog post." agentEvents={getCurrentRunEvents('images')} />
                ) : (
                  <EmptyState
                    icon={<ImageIcon className="w-12 h-12" />}
                    title="Generate Blog Images"
                    description="Create custom AI-generated visuals that will be embedded directly into your blog post to enhance engagement and readability."
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

