# Development image. It runs the Vite dev server on purpose: docker-compose.yml
# mounts ./frontend over /app and the backend runs uvicorn --reload, so the whole
# stack is a hot-reloading dev environment. Building a static bundle here would
# be pointless — the bind mount would shadow it — and the project README is
# explicit that this is a research and demonstration system, not a production
# deployment. For a production image, add a second stage that runs `npm run build`
# and serves dist/ from a static server, and drop the bind mount in compose.
FROM node:20-alpine

WORKDIR /app

# Copy the manifest and the lockfile together so `npm ci` can use it.
COPY package.json package-lock.json ./

# `npm ci` not `npm install`: it installs exactly what the lockfile pins and
# fails loudly when the two disagree, so the image cannot silently drift from
# the versions the app was tested against.
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
