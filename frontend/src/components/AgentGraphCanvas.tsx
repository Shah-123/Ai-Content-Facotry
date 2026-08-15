import React, { useState, useMemo, useEffect, useRef } from 'react';
import { AgentEvent, Job } from '../api';
import { motion, AnimatePresence } from 'motion/react';
import {
  ShieldCheck,
  GitBranch,
  Search,
  FileText,
  LayoutGrid,
  UserCheck,
  Cpu,
  Merge,
  CheckCircle2,
  RotateCcw,
  Sparkles,
  Share2,
  Mic,
  Video,
  Award,
  Activity,
  Maximize2,
  Minimize2,
  X,
  Zap,
  Play,
  Pause,
  Clock,
  ChevronRight,
  ChevronLeft,
  Code,
  Terminal,
  Info,
  Database,
  ArrowLeftRight,
  ZoomIn,
  ZoomOut,
  Move
} from 'lucide-react';

export type GraphNodeStatus = 'idle' | 'active' | 'waiting_approval' | 'completed' | 'error' | 'skipped';

export interface GraphNodeDef {
  id: string;
  name: string;
  category: 'ingestion' | 'orchestration' | 'generation' | 'audit' | 'multimodal' | 'evaluation';
  stageIndex: number; // 0..4
  model: string;
  pyFile: string;
  icon: React.ComponentType<{ className?: string }>;
  shortDesc: string;
  fullDesc: string;
  systemPromptPreview: string;
  aliases: string[];
  isRAGRelated?: boolean;
}

// 14 Core LangGraph Agents Map
export const GRAPH_NODES: GraphNodeDef[] = [
  // STAGE 0: Ingestion & Safety
  {
    id: 'topic_guard',
    name: 'Topic Guard',
    category: 'ingestion',
    stageIndex: 0,
    model: 'gpt-4o-mini',
    pyFile: 'Agents_backend/Graph/agents/topic_guard.py',
    icon: ShieldCheck,
    shortDesc: 'Sanitizes input prompts and flags harmful/unsuitable requests.',
    fullDesc: 'First gate node. Evaluates input topics against safety guidelines, checks topic clarity, and suggests academic/factual refinements before graph execution begins.',
    systemPromptPreview: 'You are an input safety and topic refinement agent. Validate topics for safety, clarity, and depth...',
    aliases: ['topic_guard', 'topic_validator', 'guard']
  },
  {
    id: 'router',
    name: 'Intent Router',
    category: 'ingestion',
    stageIndex: 0,
    model: 'gpt-4o-mini',
    pyFile: 'Agents_backend/Graph/agents/routing.py',
    icon: GitBranch,
    shortDesc: 'Routes workflow between RAG Document Ingestion, Tavily Search, or Closed-Book.',
    fullDesc: 'Analyzes user prompt and uploaded context files to decide if execution path needs vector RAG retrieval, Tavily search engine scraping, or direct LLM processing.',
    systemPromptPreview: 'Analyze user prompt intent. Route to "document_ingest" if files attached, else "researcher"...',
    aliases: ['router', 'routing', 'router_agent'],
    isRAGRelated: true
  },
  {
    id: 'researcher',
    name: 'Tavily Web Researcher',
    category: 'ingestion',
    stageIndex: 0,
    model: 'gpt-4o-mini + Tavily API',
    pyFile: 'Agents_backend/Graph/agents/research.py',
    icon: Search,
    shortDesc: 'Performs multi-query web scraping to gather structured evidence.',
    fullDesc: 'Executes targeted search queries via Tavily API, parses HTML content, filters irrelevant snippets, and constructs grounded JSON evidence records.',
    systemPromptPreview: 'Generate search queries from topic keywords. Collect web results and return structured evidence chunks...',
    aliases: ['researcher', 'research', 'tavily_search']
  },
  {
    id: 'document_ingest',
    name: 'Advanced Vector RAG',
    category: 'ingestion',
    stageIndex: 0,
    model: 'text-embedding-3-small',
    pyFile: 'Agents_backend/Graph/agents/document_ingest.py',
    icon: Database,
    shortDesc: 'Parses PDFs/DOCX, generates semantic embeddings & cosine RAG search.',
    fullDesc: 'Extracts raw text from user documents, performs semantic boundary chunking, calculates cosine embeddings (`text-embedding-3-small`), and builds a vector RAG retrieval index.',
    systemPromptPreview: 'Process document streams, chunk text into ~500 token blocks with semantic overlap, compute embeddings...',
    aliases: ['document_ingest', 'rag_ingest', 'vector_store'],
    isRAGRelated: true
  },

  // STAGE 1: Orchestration & HITL
  {
    id: 'orchestrator',
    name: 'Master Orchestrator',
    category: 'orchestration',
    stageIndex: 1,
    model: 'gpt-4o-mini',
    pyFile: 'Agents_backend/Graph/agents/orchestrator.py',
    icon: LayoutGrid,
    shortDesc: 'Designs article outline structure and allocates RAG evidence to sections.',
    fullDesc: 'Constructs H2 section titles, bullet points, target word counts, and assigns specific semantic RAG evidence records to individual sections for parallel workers.',
    systemPromptPreview: 'Build a logically structured outline. For each section, specify title, target words, bullets, and evidence IDs...',
    aliases: ['orchestrator', 'planner', 'outline_generator'],
    isRAGRelated: true
  },
  {
    id: 'hitl_plan',
    name: 'HITL Plan Control',
    category: 'orchestration',
    stageIndex: 1,
    model: 'Human Steering / Checkpointer',
    pyFile: 'frontend/src/components/PlanEditor.tsx',
    icon: UserCheck,
    shortDesc: 'Pauses stateful DAG to allow human review, outline editing, & prompt steering.',
    fullDesc: 'LangGraph SqliteSaver checkpointer interrupt node. Pauses execution and opens PlanStudio UI so the user can modify section budgets or request LLM re-planning.',
    systemPromptPreview: '[INTERRUPT STATE]: Awaiting human approval or natural language outline revision request...',
    aliases: ['hitl_plan', 'hitl_plan_approval', 'awaiting_approval', 'plan_editor']
  },

  // STAGE 2: Fan-Out Generation
  {
    id: 'workers',
    name: 'Parallel Worker Fan-Out',
    category: 'generation',
    stageIndex: 2,
    model: 'gpt-4o-mini (xN Concurrent)',
    pyFile: 'Agents_backend/Graph/agents/workers.py',
    icon: Cpu,
    shortDesc: 'Concurrent agent workers writing assigned H2 sections in parallel.',
    fullDesc: 'Dispatches isolated Worker Agents for each outline section. Each worker receives strictly assigned RAG evidence records to prevent hallucination and duplicate text.',
    systemPromptPreview: 'Write assigned H2 section using provided evidence chunks only. Maintain tone, formatting, and word count target...',
    aliases: ['workers', 'worker_agent', 'worker_0', 'worker_1', 'worker_2', 'parallel_workers'],
    isRAGRelated: true
  },
  {
    id: 'reducer',
    name: 'Merger & Reducer Node',
    category: 'generation',
    stageIndex: 2,
    model: 'gpt-4o-mini',
    pyFile: 'Agents_backend/Graph/agents/workers.py',
    icon: Merge,
    shortDesc: 'Stitches worker section outputs and assigns image placements.',
    fullDesc: 'Gathers parallel worker outputs, removes transitional redundancies, formats headers, and identifies optimal paragraph locations for visual image inserts.',
    systemPromptPreview: 'Combine section text blocks into a cohesive blog draft. Insert image placement anchors near relevant concepts...',
    aliases: ['reducer', 'merger', 'content_stitcher']
  },

  // STAGE 3: Audit & Optimization
  {
    id: 'quality_control',
    name: 'Quality Control Auditor',
    category: 'audit',
    stageIndex: 3,
    model: 'gpt-4o-mini',
    pyFile: 'Agents_backend/Graph/agents/quality_control.py',
    icon: CheckCircle2,
    shortDesc: 'Performs fact-checking, RAG evidence compliance, & hallucination audits.',
    fullDesc: 'Compares draft text against original RAG evidence records. Flag unsupported claims, inaccurate numbers, or missing key facts before final approval.',
    systemPromptPreview: 'Audit the blog draft against evidence sources. Output QA pass/fail status and specific feedback comments...',
    aliases: ['quality_control', 'qc_auditor', 'fact_checker'],
    isRAGRelated: true
  },
  {
    id: 'revision',
    name: 'Revision Agent',
    category: 'audit',
    stageIndex: 3,
    model: 'gpt-4o-mini',
    pyFile: 'Agents_backend/Graph/agents/revision.py',
    icon: RotateCcw,
    shortDesc: 'Refines text based on Quality Control audit feedback.',
    fullDesc: 'Executes conditional loop back if Quality Control flags issues. Rewrites target paragraphs to eliminate factual discrepancies and improve readability.',
    systemPromptPreview: 'Apply Quality Control audit fixes to the draft text while preserving overall flow and section structure...',
    aliases: ['revision', 'revision_agent', 'refiner']
  },
  {
    id: 'seo_optimizer',
    name: 'SEO Keyword Optimizer',
    category: 'audit',
    stageIndex: 3,
    model: 'gpt-4o-mini',
    pyFile: 'Agents_backend/Graph/agents/keyword_optimizer.py',
    icon: Sparkles,
    shortDesc: 'Weaves target keywords naturally into headers, text, & meta description.',
    fullDesc: 'Analyzes keyword density, integrates primary/secondary keywords into H2/H3 headers and body copy, and generates meta descriptions for search visibility.',
    systemPromptPreview: 'Integrate specified SEO keywords into headers and body naturally without keyword stuffing...',
    aliases: ['seo_optimizer', 'seo_agent', 'keyword_optimizer']
  },

  // STAGE 4: Multimodal & Academic Evaluation
  {
    id: 'campaign',
    name: 'Campaign Generator',
    category: 'multimodal',
    stageIndex: 4,
    model: 'gpt-4o-mini',
    pyFile: 'Agents_backend/Graph/agents/campaign.py',
    icon: Share2,
    shortDesc: 'Generates LinkedIn posts, X threads, landing pages, & email copy.',
    fullDesc: 'Transforms synthesized post content into derivative marketing campaigns across social media channels, promotional emails, and summary bullet points.',
    systemPromptPreview: 'Extract key takeaways and generate tailored social media posts for LinkedIn, Twitter/X, and newsletter...',
    aliases: ['campaign', 'campaign_generator', 'social_agent']
  },
  {
    id: 'podcast_studio',
    name: 'Gemini Podcast Studio',
    category: 'multimodal',
    stageIndex: 4,
    model: 'Gemini 2.5 Flash Native Audio',
    pyFile: 'Agents_backend/Graph/podcast_studio.py',
    icon: Mic,
    shortDesc: 'Synthesizes conversational WAV podcast episodes with human pacing.',
    fullDesc: 'Converts article contents into an engaging two-person conversational audio script and calls Google GenAI Native Audio API to render high-fidelity WAV speech.',
    systemPromptPreview: 'Create a 2-minute podcast transcript between Host and Expert. Synthesize audio with natural inflection...',
    aliases: ['podcast', 'podcast_studio', 'audio_gen']
  },
  {
    id: 'video_generator',
    name: 'MoviePy Video Engine',
    category: 'multimodal',
    stageIndex: 4,
    model: 'gpt-4o-mini + MoviePy + Pexels',
    pyFile: 'Agents_backend/Graph/agents/video.py',
    icon: Video,
    shortDesc: 'Synthesizes MP4 videos with TTS voiceover, B-roll clips, & captions.',
    fullDesc: 'Fetches stock footage from Pexels API matching script keywords, generates TTS narration audio, and renders stylized captioned MP4 video clips.',
    systemPromptPreview: 'Parse post into video scenes. Fetch matching stock video clips and align TTS audio timestamps...',
    aliases: ['video', 'video_generator', 'video_engine']
  },
  {
    id: 'academic_evaluator',
    name: 'Academic LLM Judge',
    category: 'evaluation',
    stageIndex: 4,
    model: 'gpt-4o + DeepEval G-Eval',
    pyFile: 'Agents_backend/Graph/agents/evaluation.py',
    icon: Award,
    shortDesc: 'Grades content against academic rubrics using G-Eval Chain-of-Thought.',
    fullDesc: 'Evaluates Coherence, Relevance, Accuracy & Grounding, and Tone Alignment. Runs in-house rubric scoring alongside DeepEval GEval Chain-of-Thought benchmarks.',
    systemPromptPreview: 'Evaluate article across 4 academic dimensions: Coherence, Relevance, Accuracy, Tone. Provide CoT logs...',
    aliases: ['evaluation', 'academic_evaluator', 'deepeval_judge', 'geval']
  }
];

// Stage Definitions for Flow Diagram Layout
const STAGES = [
  { id: 0, title: 'Stage 1: Ingestion & RAG', subtitle: 'Safety validation, Tavily research & RAG vector store' },
  { id: 1, title: 'Stage 2: Orchestration', subtitle: 'Outline planning & HITL human approval' },
  { id: 2, title: 'Stage 3: Fan-Out Generation', subtitle: 'Parallel section workers & content merger' },
  { id: 3, title: 'Stage 4: Audit & SEO', subtitle: 'Fact checking, revision loops & keyword tuning' },
  { id: 4, title: 'Stage 5: Multimodal & Eval', subtitle: 'Gemini podcast, MP4 video, campaign & G-Eval' }
];

interface AgentGraphCanvasProps {
  events: AgentEvent[];
  currentJob: Job | null;
  onNodeSelect?: (node: GraphNodeDef, nodeStatus: GraphNodeStatus, nodeEvents: AgentEvent[]) => void;
  className?: string;
}

export const AgentGraphCanvas: React.FC<AgentGraphCanvasProps> = ({
  events = [],
  currentJob,
  onNodeSelect,
  className = ''
}) => {
  const [selectedNodeId, setSelectedNodeId] = useState<string>('document_ingest');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [showRAGOnly, setShowRAGOnly] = useState<boolean>(false);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simStep, setSimStep] = useState<number>(0);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [zoomScale, setZoomScale] = useState<number>(1);

  // Mouse Drag-to-Scroll Canvas Panning State (Figma Style)
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isMouseDown, setIsMouseDown] = useState<boolean>(false);
  const [startX, setStartX] = useState<number>(0);
  const [scrollLeftPos, setScrollLeftPos] = useState<number>(0);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!scrollRef.current) return;
    setIsMouseDown(true);
    setStartX(e.pageX - scrollRef.current.offsetLeft);
    setScrollLeftPos(scrollRef.current.scrollLeft);
  };

  const handleMouseLeave = () => {
    setIsMouseDown(false);
  };

  const handleMouseUp = () => {
    setIsMouseDown(false);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isMouseDown || !scrollRef.current) return;
    e.preventDefault();
    const x = e.pageX - scrollRef.current.offsetLeft;
    const walk = (x - startX) * 1.5; // Drag sensitivity
    scrollRef.current.scrollLeft = scrollLeftPos - walk;
  };

  const handleHorizontalScroll = (direction: 'left' | 'right') => {
    if (scrollRef.current) {
      const scrollAmount = direction === 'left' ? -400 : 400;
      scrollRef.current.scrollBy({ left: scrollAmount, behavior: 'smooth' });
    }
  };

  // Compute live node status map based on incoming job and events
  const nodeStatusMap = useMemo(() => {
    const map: Record<string, { status: GraphNodeStatus; lastMessage: string; lastTimestamp: number; eventCount: number; metrics?: any }> = {};

    GRAPH_NODES.forEach(n => {
      map[n.id] = { status: 'idle', lastMessage: 'Node awaiting execution...', lastTimestamp: 0, eventCount: 0 };
    });

    if (isSimulating) {
      GRAPH_NODES.forEach((n, idx) => {
        if (idx < simStep) {
          map[n.id] = { status: 'completed', lastMessage: 'Completed successfully [Simulated]', lastTimestamp: Date.now(), eventCount: 3 };
        } else if (idx === simStep) {
          const status = n.id === 'hitl_plan' ? 'waiting_approval' : 'active';
          map[n.id] = { status, lastMessage: `Processing active workload...`, lastTimestamp: Date.now(), eventCount: 1 };
        } else {
          map[n.id] = { status: 'idle', lastMessage: 'Pending execution', lastTimestamp: 0, eventCount: 0 };
        }
      });
      return map;
    }

    events.forEach(evt => {
      const lowerAgent = (evt.agent_name || '').toLowerCase();
      const matchNode = GRAPH_NODES.find(n =>
        n.id.toLowerCase() === lowerAgent ||
        n.aliases.some(alias => lowerAgent.includes(alias.toLowerCase()))
      );

      if (matchNode) {
        const key = matchNode.id;
        let mappedStatus: GraphNodeStatus = 'active';

        if (evt.status === 'completed' || evt.status === 'plan_approved') {
          mappedStatus = 'completed';
        } else if (evt.status === 'error') {
          mappedStatus = 'error';
        } else if (evt.status === 'plan_ready' || evt.status === 'plan_revised' || (currentJob?.status === 'awaiting_approval' && key === 'hitl_plan')) {
          mappedStatus = 'waiting_approval';
        } else if (evt.status === 'started' || evt.status === 'working') {
          mappedStatus = 'active';
        }

        map[key] = {
          status: mappedStatus,
          lastMessage: evt.message || map[key].lastMessage,
          lastTimestamp: evt.timestamp || Date.now(),
          eventCount: (map[key].eventCount || 0) + 1,
          metrics: evt.metrics || map[key].metrics
        };
      }
    });

    if (currentJob) {
      if (currentJob.status === 'awaiting_approval') {
        map['orchestrator'].status = 'completed';
        map['hitl_plan'].status = 'waiting_approval';
        map['hitl_plan'].lastMessage = 'State checkpointed: Awaiting human plan approval in PlanStudio';
      } else if (currentJob.status === 'completed') {
        GRAPH_NODES.forEach(n => {
          if (map[n.id].status === 'active' || map[n.id].status === 'waiting_approval') {
            map[n.id].status = 'completed';
          }
        });
        map['academic_evaluator'].status = 'completed';
      }
    }

    return map;
  }, [events, currentJob, isSimulating, simStep]);

  // Simulation timer loop
  useEffect(() => {
    if (!isSimulating) return;
    const interval = setInterval(() => {
      setSimStep(prev => {
        if (prev >= GRAPH_NODES.length - 1) {
          setIsSimulating(false);
          return 0;
        }
        return prev + 1;
      });
    }, 2500);
    return () => clearInterval(interval);
  }, [isSimulating]);

  const selectedNode = useMemo(() => {
    return GRAPH_NODES.find(n => n.id === selectedNodeId) || GRAPH_NODES[0];
  }, [selectedNodeId]);

  const selectedNodeEvents = useMemo(() => {
    if (!selectedNode) return [];
    return events.filter(evt => {
      const lower = (evt.agent_name || '').toLowerCase();
      return selectedNode.id.toLowerCase() === lower || selectedNode.aliases.some(a => lower.includes(a.toLowerCase()));
    });
  }, [events, selectedNode]);

  const handleNodeClick = (node: GraphNodeDef) => {
    setSelectedNodeId(node.id);
    const nodeState = nodeStatusMap[node.id];
    if (onNodeSelect) {
      onNodeSelect(node, nodeState?.status || 'idle', selectedNodeEvents);
    }
  };

  // Filter nodes by category and RAG toggle
  const filteredNodes = useMemo(() => {
    let result = GRAPH_NODES;
    if (showRAGOnly) {
      result = result.filter(n => n.isRAGRelated);
    }
    if (categoryFilter !== 'all') {
      result = result.filter(n => n.category === categoryFilter);
    }
    return result;
  }, [categoryFilter, showRAGOnly]);

  const getStatusBadgeStyle = (status: GraphNodeStatus) => {
    switch (status) {
      case 'active':
        return 'bg-amber-500/20 text-amber-500 border-amber-500/40 shadow-sm animate-pulse';
      case 'waiting_approval':
        return 'bg-indigo-500/20 text-indigo-400 border-indigo-500/40 shadow-sm animate-pulse';
      case 'completed':
        return 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30';
      case 'error':
        return 'bg-rose-500/20 text-rose-500 border-rose-500/40';
      default:
        return 'bg-base-800/50 text-base-400 border-white/10';
    }
  };

  const getStatusIcon = (status: GraphNodeStatus) => {
    switch (status) {
      case 'active': return <Zap className="w-3.5 h-3.5 text-amber-400 animate-spin" />;
      case 'waiting_approval': return <Clock className="w-3.5 h-3.5 text-indigo-400 animate-bounce" />;
      case 'completed': return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />;
      case 'error': return <X className="w-3.5 h-3.5 text-rose-400" />;
      default: return <div className="w-2 h-2 rounded-full bg-base-500" />;
    }
  };

  return (
    <div className={`relative flex flex-col h-full bg-base-950 border border-white/8 rounded-2xl overflow-hidden shadow-xl transition-colors ${isFullscreen ? 'fixed inset-4 z-50 rounded-2xl' : ''} ${className}`}>

      {/* TOP CANVAS CONTROL BAR */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 bg-base-900/90 backdrop-blur-md border-b border-white/8 z-20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-accent-500/10 border border-accent-500/20 text-accent-400">
            <Activity className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <h2 className="text-base font-extrabold text-base-100 flex items-center gap-2">
              LangGraph Multi-Agent Workflow
              <span className="px-2 py-0.5 text-xs font-mono rounded-full bg-base-800 text-accent-400 border border-white/10">
                14 Nodes
              </span>
            </h2>
            <p className="text-xs text-base-400">
              Interactive multi-agent DAG execution with Advanced RAG, Tavily Search, & Multimodal Nodes
            </p>
          </div>
        </div>

        {/* CONTROLS & RAG FEATURE TOGGLES & SIDE SCROLL BUTTONS */}
        <div className="flex items-center gap-2 flex-wrap">

          {/* EXPLICIT HORIZONTAL SLIDE SCROLL BUTTONS */}
          <div className="flex items-center gap-1 bg-base-800/90 border border-white/10 rounded-xl p-1 shadow-sm">
            <button
              onClick={() => handleHorizontalScroll('left')}
              className="p-1.5 rounded-lg text-base-300 hover:text-base-100 hover:bg-white/10 transition-colors flex items-center gap-1 text-xs font-bold"
              title="Scroll workflow left"
            >
              <ChevronLeft className="w-4 h-4 text-accent-400" />
            </button>
            <span className="text-[10px] font-mono font-bold text-base-400 px-1.5 flex items-center gap-1">
              <Move className="w-3.5 h-3.5 text-accent-400" />
              SLIDE WORKFLOW
            </span>
            <button
              onClick={() => handleHorizontalScroll('right')}
              className="p-1.5 rounded-lg text-base-300 hover:text-base-100 hover:bg-white/10 transition-colors flex items-center gap-1 text-xs font-bold"
              title="Scroll workflow right"
            >
              <ChevronRight className="w-4 h-4 text-accent-400" />
            </button>
          </div>

          {/* ZOOM SCALING CONTROLS */}
          <div className="flex items-center gap-1 bg-base-800/90 border border-white/10 rounded-xl p-1">
            <button
              onClick={() => setZoomScale(Math.max(0.7, zoomScale - 0.15))}
              className="p-1 rounded text-base-300 hover:text-base-100"
              title="Zoom out canvas"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[10px] font-mono font-bold text-accent-400 px-1">
              {Math.round(zoomScale * 100)}%
            </span>
            <button
              onClick={() => setZoomScale(Math.min(1.3, zoomScale + 0.15))}
              className="p-1 rounded text-base-300 hover:text-base-100"
              title="Zoom in canvas"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* RAG Feature Filter Toggle */}
          <button
            onClick={() => setShowRAGOnly(!showRAGOnly)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border transition-all ${
              showRAGOnly
                ? 'bg-accent-500/20 text-accent-400 border-accent-500/40 shadow-sm'
                : 'bg-base-800/80 text-base-300 border-white/10 hover:bg-base-750'
            }`}
            title="Highlight Advanced RAG Document Ingestion & Retrieval Nodes"
          >
            <Database className="w-3.5 h-3.5 text-accent-400" />
            <span>RAG Workflow {showRAGOnly ? '(Active)' : ''}</span>
          </button>

          {/* Category Filter Pills */}
          <div className="hidden xl:flex items-center gap-1 p-1 bg-base-900 rounded-xl border border-white/8 text-xs">
            {['all', 'ingestion', 'orchestration', 'generation', 'audit', 'multimodal', 'evaluation'].map((cat) => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat)}
                className={`px-2 py-1 rounded-lg transition-all capitalize font-semibold text-[11px] ${
                  categoryFilter === cat
                    ? 'bg-accent-500 text-base-950 shadow-sm'
                    : 'text-base-400 hover:text-base-100 hover:bg-white/5'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* SIMULATION TEST BUTTON */}
          <button
            onClick={() => {
              if (isSimulating) {
                setIsSimulating(false);
                setSimStep(0);
              } else {
                setIsSimulating(true);
                setSimStep(0);
              }
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border transition-all ${
              isSimulating
                ? 'bg-accent-500/20 text-accent-400 border-accent-500/40 animate-pulse'
                : 'bg-base-800/80 text-base-200 border-white/10 hover:bg-base-750'
            }`}
            title="Simulate complete agent execution graph pipeline"
          >
            {isSimulating ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 text-emerald-400" />}
            {isSimulating ? 'Stop Demo' : 'Simulate Workflow'}
          </button>

          {/* FULLSCREEN TOGGLE */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-2 rounded-xl bg-base-800/80 text-base-300 border border-white/10 hover:bg-base-750 text-xs"
            title="Toggle canvas fullscreen"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* GRAPH WORKSPACE: STAGE PIPELINE FLOW */}
      <div className="flex-1 flex overflow-hidden relative min-h-0">

        {/* LEFT/CENTER PIPELINE FLOW CANVAS WITH FIGMA-STYLE CLICK-DRAG PANNING & SCROLL */}
        <div
          ref={scrollRef}
          onMouseDown={handleMouseDown}
          onMouseLeave={handleMouseLeave}
          onMouseUp={handleMouseUp}
          onMouseMove={handleMouseMove}
          className={`flex-1 overflow-x-auto overflow-y-auto p-6 bg-base-950 scroll-smooth ${
            isMouseDown ? 'cursor-grabbing' : 'cursor-grab'
          }`}
          style={{ scrollbarWidth: 'thin' }}
        >
          <div
            className="flex gap-6 items-start min-w-max pb-6 transition-transform duration-100 origin-top-left"
            style={{ transform: `scale(${zoomScale})` }}
          >

            {STAGES.map((stage) => {
              const stageNodes = filteredNodes.filter(n => n.stageIndex === stage.id);
              if (stageNodes.length === 0) return null;

              return (
                <div
                  key={stage.id}
                  className="w-[320px] shrink-0 flex flex-col bg-base-900/80 rounded-2xl border border-white/8 p-4 relative shadow-md max-h-[calc(100vh-12rem)]"
                >
                  {/* STAGE HEADER */}
                  <div className="mb-3 pb-3 border-b border-white/8 flex items-center justify-between shrink-0">
                    <div>
                      <h3 className="text-xs font-extrabold tracking-wider uppercase text-accent-400">
                        {stage.title}
                      </h3>
                      <p className="text-[11px] text-base-400 mt-0.5">{stage.subtitle}</p>
                    </div>
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-base-800 text-base-300 border border-white/10">
                      {stageNodes.length} Nodes
                    </span>
                  </div>

                  {/* STAGE NODES STACK (VERTICAL OVERFLOW SCROLLABLE PER STAGE) */}
                  <div className="flex-1 overflow-y-auto pr-1 flex flex-col gap-3 py-1 scrollbar-thin">
                    {stageNodes.map((node) => {
                      const IconComp = node.icon;
                      const nodeState = nodeStatusMap[node.id] || { status: 'idle', lastMessage: '', eventCount: 0 };
                      const isSelected = selectedNodeId === node.id;
                      const statusStyle = getStatusBadgeStyle(nodeState.status);

                      return (
                        <motion.div
                          key={node.id}
                          whileHover={{ scale: 1.01 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleNodeClick(node);
                          }}
                          className={`group relative flex flex-col p-3.5 rounded-xl border transition-all cursor-pointer bg-base-850/90 backdrop-blur-md shrink-0 ${
                            isSelected
                              ? 'border-accent-500 shadow-lg ring-1 ring-accent-500/40'
                              : 'border-white/8 hover:border-white/20 shadow-md'
                          }`}
                        >
                          {/* RAG BADGE INDICATOR */}
                          {node.isRAGRelated && (
                            <div className="absolute top-2.5 right-2.5 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-accent-500/15 text-accent-400 border border-accent-500/30">
                              RAG NODE
                            </div>
                          )}

                          {/* NODE TOP ROW */}
                          <div className="flex items-start justify-between gap-2 mb-2 pr-12">
                            <div className="flex items-center gap-2.5">
                              <div className={`p-2 rounded-xl border ${
                                nodeState.status === 'active'
                                  ? 'bg-amber-500/20 border-amber-500/40 text-amber-400'
                                  : nodeState.status === 'completed'
                                  ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                                  : nodeState.status === 'waiting_approval'
                                  ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-400'
                                  : 'bg-base-800 border-white/10 text-base-200'
                              }`}>
                                <IconComp className="w-4 h-4" />
                              </div>
                              <div>
                                <h4 className="text-xs font-bold text-base-100 group-hover:text-accent-400 transition-colors flex items-center gap-1.5">
                                  {node.name}
                                </h4>
                                <div className="text-[10px] font-mono text-base-400 flex items-center gap-1">
                                  <span>{node.model}</span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* STATUS BADGE */}
                          <div className="mb-2 flex items-center">
                            <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold border uppercase tracking-wider ${statusStyle}`}>
                              {getStatusIcon(nodeState.status)}
                              <span>{nodeState.status.replace('_', ' ')}</span>
                            </div>
                          </div>

                          {/* NODE SHORT DESCRIPTION */}
                          <p className="text-[11px] text-base-300 line-clamp-2 leading-relaxed font-medium">
                            {node.shortDesc}
                          </p>

                          {/* NODE FOOTER TELEMETRY */}
                          <div className="mt-2.5 pt-2 border-t border-white/6 flex items-center justify-between text-[10px] text-base-400">
                            <div className="flex items-center gap-1 font-mono">
                              <Terminal className="w-3 h-3 text-base-400" />
                              <span>{node.pyFile.split('/').pop()}</span>
                            </div>
                            {nodeState.eventCount > 0 && (
                              <span className="font-mono text-accent-400 bg-accent-500/10 px-1.5 py-0.5 rounded border border-accent-500/20 font-bold">
                                {nodeState.eventCount} Events
                              </span>
                            )}
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

          </div>
        </div>

        {/* RIGHT PANEL: NODE INSPECTOR DRAWER */}
        <AnimatePresence>
          {selectedNode && (
            <motion.div
              initial={{ x: 350, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 350, opacity: 0 }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="w-96 bg-base-900 border-l border-white/8 flex flex-col h-full z-30 shadow-2xl shrink-0"
            >
              {/* INSPECTOR HEADER */}
              <div className="p-4 border-b border-white/8 flex items-center justify-between bg-base-950/60 shrink-0">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-xl bg-accent-500/10 text-accent-400 border border-accent-500/20">
                    <Info className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-extrabold text-base-100">Node Inspector</h3>
                    <p className="text-[11px] font-mono text-base-400">{selectedNode.id}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedNodeId('')}
                  className="p-1.5 text-base-400 hover:text-base-100 rounded-lg hover:bg-white/5"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* INSPECTOR CONTENT */}
              <div className="flex-1 overflow-y-auto p-4 space-y-5 scrollbar-thin scrollbar-thumb-base-750">

                {/* NODE IDENTITY CARD */}
                <div className="p-4 rounded-xl bg-base-850 border border-white/8 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-base font-extrabold text-accent-400 flex items-center gap-2">
                      {selectedNode.name}
                    </h4>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border uppercase ${getStatusBadgeStyle(nodeStatusMap[selectedNode.id]?.status || 'idle')}`}>
                      {nodeStatusMap[selectedNode.id]?.status || 'idle'}
                    </span>
                  </div>

                  <p className="text-xs text-base-200 leading-relaxed font-medium">
                    {selectedNode.fullDesc}
                  </p>

                  <div className="pt-2 border-t border-white/8 space-y-2 text-xs font-mono">
                    <div className="flex justify-between text-base-400">
                      <span>Core LLM:</span>
                      <span className="text-base-100 font-bold">{selectedNode.model}</span>
                    </div>
                    <div className="flex justify-between text-base-400">
                      <span>Category:</span>
                      <span className="text-accent-400 font-bold capitalize">{selectedNode.category}</span>
                    </div>
                    {selectedNode.isRAGRelated && (
                      <div className="flex justify-between text-base-400">
                        <span>RAG Integration:</span>
                        <span className="text-emerald-400 font-bold">Enabled (Cosine Embeddings)</span>
                      </div>
                    )}
                    <div className="flex justify-between text-base-400">
                      <span>Source File:</span>
                      <span className="text-emerald-400 text-[11px] truncate max-w-[180px]" title={selectedNode.pyFile}>
                        {selectedNode.pyFile.split('/').pop()}
                      </span>
                    </div>
                  </div>
                </div>

                {/* SYSTEM PROMPT PREVIEW */}
                <div className="space-y-2">
                  <h5 className="text-xs font-extrabold text-base-300 uppercase tracking-wider flex items-center gap-1.5">
                    <Code className="w-3.5 h-3.5 text-accent-400" />
                    System Prompt Template
                  </h5>
                  <div className="p-3 rounded-xl bg-base-950 border border-white/8 font-mono text-[11px] text-base-300 leading-relaxed overflow-x-auto">
                    {selectedNode.systemPromptPreview}
                  </div>
                </div>

                {/* RECENT NODE EVENT LOGS */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h5 className="text-xs font-extrabold text-base-300 uppercase tracking-wider flex items-center gap-1.5">
                      <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                      Live Stream Event Logs
                    </h5>
                    <span className="text-[10px] font-mono text-base-400">
                      {selectedNodeEvents.length} Captured
                    </span>
                  </div>

                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {selectedNodeEvents.length === 0 ? (
                      <div className="p-4 text-center rounded-xl bg-base-850/40 border border-white/6 text-xs text-base-400">
                        No active stream events recorded yet for this node.
                      </div>
                    ) : (
                      selectedNodeEvents.map((evt, i) => (
                        <div key={i} className="p-2.5 rounded-lg bg-base-950 border border-white/8 text-xs space-y-1">
                          <div className="flex justify-between items-center text-[10px] font-mono text-base-400">
                            <span className="text-accent-400 font-bold uppercase">{evt.status}</span>
                            <span>{new Date(evt.timestamp * 1000).toLocaleTimeString()}</span>
                          </div>
                          <p className="text-base-200 leading-normal">{evt.message}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>

              </div>
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </div>
  );
};
export default AgentGraphCanvas;
