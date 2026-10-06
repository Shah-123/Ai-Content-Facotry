# AI Content Factory frontend

This is the React 19, TypeScript, and Vite dashboard for AI Content Factory. It creates and monitors jobs through the FastAPI backend, lets users review outlines, and presents generated content, evaluation reports, exports, and media in one studio.

## Main areas

- `src/App.tsx` — application shell, navigation, and main views.
- `src/components/ChatView.tsx` — job creation and live event stream.
- `src/components/PlanEditor.tsx` — human review and revision of the generated outline.
- `src/ContentView.tsx` — article, evaluation, asset, campaign, and export studio.
- `src/hooks/useJobActions.ts` — task execution, WebSocket, and polling behaviour.
- `src/hooks/useGEvalRadar.ts` — radar-chart geometry for the G-Eval rubric scores.
- `src/events.ts` — agent-event list semantics (de-dupes the server's replay).
- `src/api.ts` — backend HTTP and WebSocket client.

## Run locally

```powershell
npm ci
Copy-Item .env.example .env.local
npm run dev
```

The development server runs at [http://localhost:3000](http://localhost:3000). Start the backend on port 8000 before using the app.

## Configure the backend URL

`frontend/.env.local` is optional when the backend is at its default address. It supports these settings:

```ini
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

Restart the Vite development server after changing the file.

## Check and build

```powershell
npm run lint
npm run build
```

`lint` runs the TypeScript check. `build` creates the production bundle in `dist/`.
