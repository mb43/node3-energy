FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server.py .
COPY simulate.py .
COPY dashboard.html .
COPY index.html .

# Create data directory for persistent state files
RUN mkdir -p /app/data

# Ensure state files are written to /app (volume-mountable)
ENV PYTHONUNBUFFERED=1

EXPOSE 8585

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8585"]
