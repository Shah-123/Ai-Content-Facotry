# 🎨 AI Content Factory: React Frontend Application
## 🖥️ User Interface & Interactive Dashboard

This directory contains the Vite React TypeScript web application for the **AI Content Factory**. The user interface communicates with the FastAPI backend via HTTP endpoints and WebSockets to enable live monitoring, job management, interactive planning, and multimedia playback.

---

## 🚀 Key Features

* **Interactive Outline Editor ([PlanEditor.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components/PlanEditor.tsx)):** Pauses the backend graph and presents the plan structure to the user. Users can modify titles, write bullet points, set word counts, or write natural language feedback to request automated plan updates.
* **Live WebSocket Console ([ChatView.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components/ChatView.tsx)):** Streams real-time event updates from the agent coordinator, outputting log statements and status changes as they occur.
* **Rich Article Renderer ([ContentView.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/ContentView.tsx)):** Renders generated markdown content with placed inline images, lists, and tables, alongside evaluation scorecards, G-Eval reports, and SEO keyword densities.
* **Multimedia Studio ([MediaView.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/MediaView.tsx)):** Provides built-in players for synthesized WAV podcasts (from Gemini 2.5 Flash) and rendered MP4 short videos.
* **Document Uploader ([UploadChip.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components/UploadChip.tsx)):** Allows uploading PDF, Word, TXT, and Markdown source documents to ground content generation.
* **Dark Mode & Responsive UI ([App.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/App.tsx) / [index.css](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/index.css)):** Features modern dark/light mode toggles and responsive layouts using Tailwind CSS v4 and custom animations.

---

## 🛠️ Technology Stack

* **Core Framework:** [React 19](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
* **Build System:** [Vite 6](https://vite.dev/)
* **Styling System:** [Tailwind CSS v4](https://tailwindcss.com/)
* **Animations:** [Motion](https://motion.dev/)
* **Icons:** [Lucide React](https://lucide.dev/)
* **Markdown Parsing:** [React Markdown](https://github.com/remarkjs/react-markdown) + [Remark GFM](https://github.com/remarkjs/remark-gfm)

---

## 🗂️ Component Architecture

* [main.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/main.tsx) — Main entry point.
* [App.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/App.tsx) — Handles application shell layouts and sidebar page routes.
* [api.ts](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/api.ts) — Configures backend HTTP calls and manages WebSocket event listeners.
* [index.css](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/index.css) — Global styles and theme definitions.
* **Components Folder ([components/](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components)):**
  - [ChatView.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components/ChatView.tsx) — Real-time event monitor.
  - [PlanEditor.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components/PlanEditor.tsx) — The outline editor interface.
  - [Sidebar.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components/Sidebar.tsx) — Displays job navigation history.
  - [TopNav.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components/TopNav.tsx) — Header controls and theme toggler.
  - [UploadChip.tsx](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/components/UploadChip.tsx) — File upload button and progress indicators.
* **Hooks Folder ([hooks/](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/hooks)):**
  - [useTheme.ts](file:///d:/Multi_Agent_Blog_generator_FYP/frontend/src/hooks/useTheme.ts) — Controls color theme state management.

---

## ⚙️ Running Locally

### Prerequisites
* **Node.js 18+** installed on your machine.
* A running instance of the **FastAPI Backend Server** (typically on `http://localhost:8000`).

### 1. Install Dependencies
```bash
npm install
```

### 2. Configure Local Settings
Check the config in `vite.config.ts`. If running the backend on a port other than `8000`, adjust the API proxy URL configuration accordingly.

### 3. Run Development Server
```bash
npm run dev
```
Once started, open `http://localhost:3000` in your web browser.

---

## 🏗️ Production Build

To compile the application bundle for production:

```bash
npm run build
```

This generates optimized static files inside the `dist/` directory. The FastAPI backend is configured to automatically serve these files from the `/static` endpoint.
