# Stage 1: Build the frontend (Astro/Svelte)
FROM node:22-alpine AS frontend-builder
WORKDIR /app

# Copy package.json and install dependencies
COPY frontend/package.json ./frontend/
WORKDIR /app/frontend
RUN npm install

# Copy the rest of the frontend source and build it
COPY frontend/ .
RUN npm run build

# Stage 2: Setup Python Backend and Serve Application
FROM python:3.11-slim
WORKDIR /app

# Copy backend requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the python backend code
COPY backend/ ./backend/

# Copy the built frontend artifacts from Stage 1 into the location expected by backend/server.py
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose the default port for Hugging Face Spaces (Docker SDK)
EXPOSE 7860

# Start the web server on the required port
CMD ["python", "backend/server.py", "--host", "0.0.0.0", "--port", "7860"]
