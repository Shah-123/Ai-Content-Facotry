import { useMemo } from 'react';
import { AgentEvent, Job } from '../api';

type TaskStatus = (agentName: string) => boolean;

export type AnalyticsNode = {
  id: string;
  name: string;
  color: string;
  textColor: string;
  model: string;
  role: string;
  cost: number;
  tokens: number;
  status: string;
  active: boolean;
};

export function useJobAnalytics(
  currentJob: Job | null,
  events: AgentEvent[],
  isTaskRunning: TaskStatus,
) {
  const radarPoints = useMemo(() => buildRadarPoints(currentJob?.geval_scores), [currentJob?.geval_scores]);

  const analytics = useMemo(() => {
    if (!currentJob) return emptyAnalytics();

    const wordCount = currentJob.final_content ? currentJob.final_content.split(/\s+/).filter(Boolean).length : 0;
    const numSections = currentJob.sections || currentJob.plan?.sections?.length || 3;
    const hasImages = Array.isArray(currentJob.image_files) && currentJob.image_files.length > 0;
    const imageCount = hasImages ? currentJob.image_files!.length : 0;
    const hasPodcast = Boolean(currentJob.podcast_file);
    const hasVideo = Boolean(currentJob.video_file);
    const hasGEval = Boolean(currentJob.deepeval_scores || currentJob.geval_scores);
    const hasRag = Boolean(currentJob.plan?.upload_id || events.some(event => event.agent_name === 'document_ingest'));
    const hasResearch = currentJob.plan?.needs_research !== false;
    const hasContent = Boolean(currentJob.final_content);

    const topicGuardMetrics = getDynamicMetrics(events, 'topic_guard', 0.001, 150);
    const routerMetrics = getDynamicMetrics(events, 'router', 0.001, 200);
    const researcherMetrics = getDynamicMetrics(events, 'researcher', hasResearch ? 0.005 : 0, 0);
    const docIngestMetrics = getDynamicMetrics(events, 'document_ingest', hasRag ? 0.002 : 0, hasRag ? 1500 : 0);
    const orchestratorMetrics = getDynamicMetrics(events, 'orchestrator', 0.004, 1200);
    const workersMetrics = getDynamicMetrics(events, 'workers', hasContent ? Number((0.005 * numSections).toFixed(3)) : 0, hasContent ? Math.round((wordCount || 600) * 1.5) : 0);
    const reducerMetrics = getDynamicMetrics(events, 'reducer', hasContent ? 0.002 : 0, hasContent ? Math.round((wordCount || 600) * 0.3) : 0);
    const imageGenMetrics = getDynamicMetrics(events, 'image_gen', hasImages ? Number((0.020 * imageCount).toFixed(3)) : 0, 0);
    const qaMetrics = getDynamicMetrics(events, 'qa', hasContent ? 0.006 : 0, hasContent ? Math.round((wordCount || 600) * 0.8) : 0);
    const seoMetrics = getDynamicMetrics(events, 'seo', hasContent ? 0.003 : 0, hasContent ? Math.round((wordCount || 600) * 0.4) : 0);
    const podcastMetrics = getDynamicMetrics(events, 'podcast', hasPodcast ? 0.012 : 0, hasPodcast ? 2500 : 0);
    const videoMetrics = getDynamicMetrics(events, 'video', hasVideo ? 0.018 : 0, 0);
    const gevalMetrics = getDynamicMetrics(events, 'geval', hasGEval ? 0.015 : 0, hasGEval ? 3000 : 0);

    const nodes: AnalyticsNode[] = [
      {
        id: 'topic_guard', name: 'Topic Guard', color: 'bg-emerald-400', textColor: 'text-accent-400', model: 'gpt-5-mini',
        role: 'Sanitizes input topic, checks prompt safety & sanity', cost: topicGuardMetrics.cost, tokens: topicGuardMetrics.tokens, status: 'Passed', active: true,
      },
      {
        id: 'router', name: 'Router Agent', color: 'bg-emerald-400', textColor: 'text-accent-400', model: 'gpt-5-mini',
        role: 'Determines web search requirement vs closed-book route', cost: routerMetrics.cost, tokens: routerMetrics.tokens, status: 'Passed', active: true,
      },
      {
        id: 'researcher', name: 'Tavily Researcher', color: 'bg-blue-400', textColor: 'text-blue-400', model: 'Tavily Scraper API',
        role: 'Generates query strings & scrapes web evidence packs', cost: researcherMetrics.cost, tokens: researcherMetrics.tokens, status: hasResearch ? 'Passed' : 'Skipped', active: hasResearch,
      },
      {
        id: 'document_ingest', name: 'Document Ingest (RAG)', color: 'bg-purple-400', textColor: 'text-purple-400', model: 'text-embedding-3-small',
        role: 'Semantic sentence chunking & NumPy cosine top-k search', cost: docIngestMetrics.cost, tokens: docIngestMetrics.tokens, status: hasRag ? 'Passed' : 'Skipped', active: hasRag,
      },
      {
        id: 'orchestrator', name: 'Orchestrator Agent', color: 'bg-amber-400', textColor: 'text-accent-400', model: 'gpt-5-mini',
        role: 'Builds H2 outline structure & assigns evidence to sections', cost: orchestratorMetrics.cost, tokens: orchestratorMetrics.tokens, status: 'Passed', active: true,
      },
      {
        id: 'hitl', name: 'HITL Approval Node', color: 'bg-indigo-400', textColor: 'text-indigo-400', model: 'PlanEditor UI / SQLite',
        role: 'Human-in-the-loop interrupt checkpoint & plan editing', cost: 0, tokens: 0, status: currentJob.status === 'awaiting_approval' ? 'Pending' : 'Approved', active: true,
      },
      {
        id: 'workers', name: `Parallel Workers (x${numSections})`, color: 'bg-emerald-400', textColor: 'text-accent-400', model: 'gpt-5-mini',
        role: 'LangGraph Send API parallel section writing', cost: workersMetrics.cost, tokens: workersMetrics.tokens, status: hasContent ? 'Passed' : 'Pending', active: hasContent,
      },
      {
        id: 'reducer', name: 'Reducer & Merger', color: 'bg-emerald-400', textColor: 'text-accent-400', model: 'gpt-5-mini',
        role: 'Combines parallel sections into single markdown article', cost: reducerMetrics.cost, tokens: reducerMetrics.tokens, status: hasContent ? 'Passed' : 'Pending', active: hasContent,
      },
      {
        id: 'image_gen', name: 'AI Image Generator', color: 'bg-cyan-400', textColor: 'text-cyan-400', model: currentJob.image_model || 'DALL-E 3',
        role: 'Visual prompt generation & multi-aspect blog illustration rendering', cost: imageGenMetrics.cost, tokens: imageGenMetrics.tokens,
        status: isTaskRunning('images') ? 'Running' : hasImages ? `Passed (${imageCount} img${imageCount > 1 ? 's' : ''})` : 'Skipped', active: hasImages || isTaskRunning('images'),
      },
      {
        id: 'qa', name: 'Quality Control Auditor', color: 'bg-red-400', textColor: 'text-accent-400', model: 'gpt-5-mini',
        role: 'Fact-checking against evidence & revision looping', cost: qaMetrics.cost, tokens: qaMetrics.tokens, status: hasContent ? 'Passed' : 'Pending', active: hasContent,
      },
      {
        id: 'seo', name: 'SEO Keyword Optimizer', color: 'bg-teal-400', textColor: 'text-accent-400', model: 'gpt-5-mini',
        role: 'Weaves target keywords into headers & body paragraphs', cost: seoMetrics.cost, tokens: seoMetrics.tokens, status: hasContent ? 'Passed' : 'Pending', active: hasContent,
      },
      {
        id: 'podcast', name: 'Gemini Podcast Studio', color: 'bg-pink-400', textColor: 'text-pink-400', model: 'Gemini 2.5 Flash / OpenAI HD',
        role: '2-Host conversational script synthesis & audio TTS', cost: podcastMetrics.cost, tokens: podcastMetrics.tokens, status: isTaskRunning('podcast') ? 'Running' : hasPodcast ? 'Passed' : 'Skipped', active: hasPodcast || isTaskRunning('podcast'),
      },
      {
        id: 'video', name: 'Shorts Video Generator', color: 'bg-rose-400', textColor: 'text-rose-400', model: 'MoviePy + Whisper + Pexels',
        role: '9:16 vertical clip search, karaoke subtitles & MP4 render', cost: videoMetrics.cost, tokens: videoMetrics.tokens, status: isTaskRunning('video') ? 'Running' : hasVideo ? 'Passed' : 'Skipped', active: hasVideo || isTaskRunning('video'),
      },
      {
        id: 'geval', name: 'Academic G-Eval Judge', color: 'bg-yellow-400', textColor: 'text-yellow-400', model: 'gpt-4o + deepeval',
        role: 'Liu et al. 2023 CoT Academic Evaluation rubrics', cost: gevalMetrics.cost, tokens: gevalMetrics.tokens, status: isTaskRunning('deepeval') ? 'Running' : hasGEval ? 'Passed' : 'Skipped', active: hasGEval || isTaskRunning('deepeval'),
      },
    ];

    const activeNodes = nodes.filter(node => node.active);
    return {
      nodes,
      totalCost: nodes.reduce((total, node) => total + node.cost, 0),
      totalTokens: nodes.reduce((total, node) => total + node.tokens, 0),
      activeAgentCount: activeNodes.length,
      numSections,
    };
  }, [currentJob, events, isTaskRunning]);

  return { analytics, radarPoints };
}

function buildRadarPoints(scores: Job['geval_scores']) {
  if (!scores) return '';

  const center = 50;
  const scale = 30;
  const metrics = [
    { score: scores.coherence?.score || 3, angle: -Math.PI / 2 },
    { score: scores.relevance?.score || 3, angle: 0 },
    { score: scores.accuracy?.score || 3, angle: Math.PI / 2 },
    { score: scores.tone_alignment?.score || 3, angle: Math.PI },
  ];

  return metrics.map(metric => {
    const distance = (metric.score / 5) * scale;
    return `${center + distance * Math.cos(metric.angle)},${center + distance * Math.sin(metric.angle)}`;
  }).join(' ');
}

function getDynamicMetrics(events: AgentEvent[], nodeId: string, defaultCost: number, defaultTokens: number) {
  const event = events.find(candidate =>
    candidate.agent_name === nodeId &&
    (candidate.metrics?.cost !== undefined || candidate.metrics?.total_cost !== undefined || candidate.metrics?.tokens !== undefined)
  );
  if (!event?.metrics) return { cost: defaultCost, tokens: defaultTokens };

  return {
    cost: Number(event.metrics.cost ?? event.metrics.total_cost ?? defaultCost),
    tokens: Number(event.metrics.tokens ?? event.metrics.total_tokens ?? defaultTokens),
  };
}

function emptyAnalytics() {
  return { nodes: [] as AnalyticsNode[], totalCost: 0, totalTokens: 0, activeAgentCount: 0, numSections: 3 };
}
