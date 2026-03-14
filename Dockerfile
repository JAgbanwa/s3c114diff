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

# ── System dependencies (PARI/GP + GMP for C worker) ──────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        pari-gp \
        python3 \
        python3-pip \
        python3-dev \
        build-essential \
        libgmp-dev \
        git \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────
RUN pip3 install --no-cache-dir cypari2 || true   # optional fast path

# ── App files ─────────────────────────────────────────────────────────
WORKDIR /app
COPY worker_d114.gp                  ./
COPY worker_d114.py                  ./
COPY worker_large_d114.c             ./
COPY work_generator_d114.py          ./
COPY work_generator_large_d114.py    ./
COPY assimilator_d114.py             ./
COPY validator_d114.py               ./
COPY local_parallel_search_d114.py   ./
COPY parametric_enum_d114.py         ./

# ── Build the GMP C worker ─────────────────────────────────────────────
RUN gcc -O3 -march=native -o worker_large_d114 worker_large_d114.c -lgmp \
    && chmod +x worker_large_d114

RUN mkdir -p output wu_queue wu_large results logs

# ── Default: run parametric enumeration then open-ended local search ───
CMD ["bash", "-c", \
     "python3 parametric_enum_d114.py --m_lo 1e20 --m_hi 1e30 \
      --output output/solutions_parametric_d114.txt && \
      python3 local_parallel_search_d114.py --no_limit --workers 4"]
