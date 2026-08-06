# Stage 1: Builder
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies to the user site-packages
COPY requirements.txt .
RUN pip install --user --no-cache-dir --no-warn-script-location -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

LABEL org.opencontainers.image.title="DevOps Incident Simulation Pipeline" \
      org.opencontainers.image.description="7-Stage CrewAI multi-agent SRE incident simulator" \
      org.opencontainers.image.source="https://github.com/minaNabil96/devops-incident-sim-pipeline"

# Copy installed packages from the builder stage
COPY --from=builder /root/.local /root/.local

# Ensure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY src/ ./src/
COPY app/ ./app/

# Create outputs directory
RUN mkdir -p outputs

# Basic dependencies for healthcheck (curl) available via python
EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]