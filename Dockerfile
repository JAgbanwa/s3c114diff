# ── s3c114diff — d114 elliptic-curve search
# Equation: Y² = 36x³ + 36m²x² + 12m³x + m⁴ − 19m
#
# Build:  docker build -t s3c114diff .
# Run:    docker run --rm s3c114diff python3 worker_d114.py wu.txt result.txt

FROM ubuntu:22.04
LABEL maintainer="s3c114diff search"

ENV DEBIAN_FRONTEND=noninteractive
ENV BOINC=0
ENV GP_STACK_MB=512
ENV BAND_TIMEOUT=7200

# ── System dependencies ────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        pari-gp \
        python3 \
        python3-pip \
        python3-dev \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────
RUN pip3 install --no-cache-dir cypari2 || true   # optional fast path

# ── App files ─────────────────────────────────────────────────────────
WORKDIR /app
COPY worker_d114.gp              ./
COPY worker_d114.py              ./
COPY work_generator_d114.py      ./
COPY assimilator_d114.py         ./
COPY validator_d114.py           ./
COPY local_parallel_search_d114.py ./

RUN mkdir -p output wu_queue results logs checkpoints

# ── Default command: run local parallel search (open-ended) ───────────
CMD ["python3", "local_parallel_search_d114.py", "--no_limit", "--workers", "4"]
