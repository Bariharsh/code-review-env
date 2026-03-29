# Stage 1: Build the frontend (Astro/Svelte)
FROM node:18-alpine AS frontend-builder
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

# Copy root requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the python backend code
COPY backend/ ./backend/

# Copy the built frontend artifacts from Stage 1 into the location expected by backend/server.py
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose the API and Web Server port
EXPOSE 8000

# Start the web server and API
CMD ["python", "backend/server.py"]
