FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server.py .
COPY simulate.py .
COPY node3_config.py .
COPY hardware_bridge.py .
COPY dashboard.html .
COPY index.html .

# Schematic/tech-page assets — server.py's schematic_asset() route whitelist
# expects these to exist in BASE_DIR (/app). Previously missing entirely,
# which is why the schematic page complained the files weren't present even
# though they sat right there in the project folder on the Mac.
COPY NODE3_Schematic.html .
COPY NODE3_DEFINITIVE_Schematic.svg .
COPY NODE3_LV_Wiring_Schematic.svg .
COPY NODE3_DEFINITIVE_BoxLayout.svg .
COPY NODE3_Distributed_Topology.svg .
COPY NODE3_Wall_Elevation.svg .
COPY NODE3_G99_SLD_DSL-SLD-001_RevA_preview.png .

# Create data directory for persistent state files
RUN mkdir -p /app/data

# Ensure state files are written to /app (volume-mountable)
ENV PYTHONUNBUFFERED=1

EXPOSE 8585

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8585"]
