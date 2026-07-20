# AI Prompts for Mermaid Live Editor

You can copy these natural language prompts and paste them directly into the **Mermaid Chart AI** or **Mermaid Live Editor AI** chat bar to generate the diagrams automatically.

---

## 1. Use Case Diagram Prompt
> **AI Prompt to paste:**
> "Create a UML use case diagram for a stateful multi-agent system named 'AI Content Factory'. There are two actors: 'Content Creator' and 'System Admin'. The 'Content Creator' has these use cases: 'Submit Topic and Grounding Files', 'Select Research Mode (Tavily/Closed-Book)', 'Monitor Live WebSocket Logs', 'Edit and Approve Outline (HITL)', 'Play Synthesized Solo Podcast', 'Preview Rendered Video', and 'Inspect DeepEval Scorecard'. The 'System Admin' has these use cases: 'Configure API Environment Keys' and 'Clear Database Checkpoints'."

---

## 2. System Architecture / Flow Diagram Prompt
> **AI Prompt to paste:**
> "Create a vertical flowchart (graph TD) illustrating the agent routing workflow of the 'AI Content Factory'. Start with a node 'Topic Input / Document Ingestion' pointing to a 'Router Node'. The router should branch with 'Needs Research' leading to a 'Research Agent', and 'No Research / Ingest Active' leading directly to the 'Orchestrator Agent'. The Research Agent also points to the Orchestrator. The Orchestrator triggers a 'Human-in-the-Loop Interrupt: Review Plan' which loops back for 'LLM Revision'. Once approved, it points to 'Parallel Worker Dispatch'. Create a subgraph for the parallel phase containing 'Worker Agent 0', 'Worker Agent 1', and 'Worker Agent N'. All workers point to a 'Reducer Node'. The Reducer merges sections and points to a 'Quality Control Auditor'. If revisions are needed, it routes to a 'Revision Agent' and back to the QC Auditor. Once approved, it routes to a 'Keyword SEO Optimizer'. The Optimizer points to 'Asset Toggles' which branches into three parallel nodes: 'Campaign Generator', 'Video Synthesis Node', and 'Gemini Podcast Studio'. All three assets route to a final node 'G-Eval & DeepEval Evaluation', which outputs to the 'Final Output Directory'."

---

## 3. Component Diagram Prompt
> **AI Prompt to paste:**
> "Create a component diagram (graph LR) for 'AI Content Factory'. Divide it into three blocks: Frontend, Backend, and Data Tier. In the Frontend, add a component 'Vite React Dashboard'. In the Backend, add components: 'FastAPI Router', 'Event Bus / WebSockets', 'LangGraph Core Engine', 'RAG Vector Module', 'Media Synthesis Studio', and 'DeepEval Evaluator'. In the Data Tier, add a database node 'SQLite DB & Checkpoints'. Connect the React Dashboard to the FastAPI Router with a two-way arrow. Connect the FastAPI Router to the Event Bus and LangGraph Engine. Connect the LangGraph Engine to the SQLite DB, RAG Vector Module, Media Synthesis Studio, and DeepEval Evaluator."

---

## 4. Data Flow Diagram (DFD Level 0) Prompt
> **AI Prompt to paste:**
> "Create a data flow diagram (Level 0 DFD) for 'AI Content Factory'. The center process is '1.0 AI Content Factory Engine'. The user actor 'Content Creator' sends Inputs/Outlines and receives Outputs/Media from the engine. The engine reads and writes 'Checkpoints & Metrics' to a database data store named 'SQLite Database'. The engine sends 'Search Queries' to 'Tavily API' and receives 'Search Results'. The engine sends 'Prompts & Embeddings' to 'OpenAI API' and receives 'Text drafts & Vectors'. The engine sends a 'Podcast Script' to 'Gemini API' and receives 'Synthesized WAV Audio'. The engine sends 'Stock Keywords' to 'Pexels API' and receives 'Stock Video Clips'."

---

## 5. UML Class Diagram Prompt
> **AI Prompt to paste:**
> "Create a UML class diagram for the backend data structures of 'AI Content Factory'. Class 'Job' has attributes 'id', 'topic', 'status', 'content', 'metrics', and 'created_at', and methods 'save()' and 'update_status()'. Class 'File' has attributes 'id', 'filename', 'filepath', 'size', and 'uploaded_at', and method 'delete()'. Class 'Plan' has attributes 'title' and 'sections', and method 'to_json()'. Class 'Section' has attributes 'title', 'word_count', and 'bullets'. Class 'GraphState' has attributes 'topic', 'research_needed', 'plan', 'sections', 'evidence', 'final_draft', 'podcast_path', and 'video_path'. Draw associations: a Job references zero or more Files, a GraphState contains one Plan, and a Plan contains one or more Sections."

---

## 6. Deployment Diagram Prompt
> **AI Prompt to paste:**
> "Create a deployment diagram showing the physical nodes of a web deployment for 'AI Content Factory'. The node 'Client Device' contains a node 'Web Browser'. The node 'Web Server Host' contains an 'Nginx Reverse Proxy' and a 'Docker Environment'. Inside the Docker Environment, show 'FastAPI Container' and a persistent data volume 'Persistent SQLite Volume'. The FastAPI Container reads/writes from the SQLite Volume. The Web Browser connects to Nginx via HTTP/WebSockets. Nginx connects to the FastAPI Container via local port forwarding. Outside the server, draw 'Cloud APIs' containing separate nodes: 'OpenAI API', 'Gemini API', 'Tavily Search API', and 'Pexels Video API'. Connect the FastAPI Container to each of these external API nodes using outbound HTTPS requests."
