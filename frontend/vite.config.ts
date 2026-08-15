import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

export default defineConfig(() => {
  // NOTE: do NOT add a `define` block that injects API keys here. Anything
  // defined this way is inlined into the public JS bundle and shipped to every
  // visitor. A leftover `process.env.GEMINI_API_KEY` define was removed for
  // exactly that reason — all model keys stay server-side in Agents_backend.
  // Client config belongs in VITE_* vars (see .env.example), which are also
  // public, so never put a secret in one.
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modifyâfile watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
    },
  };
});
