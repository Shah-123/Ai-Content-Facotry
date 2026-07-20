# Use official Node.js Alpine runtime
FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy dependency files
COPY package*.json ./

# Install packages
RUN npm install

# Copy frontend source code
COPY . .

# Expose Vite development server port
EXPOSE 3000

# Start Vite dev server on 0.0.0.0:3000
CMD ["npm", "run", "dev"]
