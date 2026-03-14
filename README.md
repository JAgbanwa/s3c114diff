# s3c114diff — Elliptic Curve Integer Point Search

## Equation

$$Y^2 = 36x^3 + 36m^2 x^2 + 12m^3 x + m^4 - 19m \qquad (m \neq 0)$$

Find **all** integers $(m, x, Y)$ satisfying this equation.

---

## Mathematical Background

### Weierstrass Reduction

Multiplying both sides by $36^2 = 1296$ and substituting
$\hat{X} = 36x$, $\hat{Y} = 36Y$ gives the standard Weierstrass form:

$$\hat{E}(m): \quad \hat{Y}^2 = \hat{X}^3 + 36m^2\hat{X}^2 + 432m^3\hat{X} + 1296m^4 - 24624m$$

This is a cubic elliptic curve parameterised by $m$.  
An integral point $(\hat{X}, \hat{Y})$ corresponds to an integer solution
$(x, Y) = (\hat{X}/36,\, \hat{Y}/36)$ **if and only if** $36 \mid \hat{X}$ and
$36 \mid \hat{Y}$.

### Algorithm

For each integer $m \neq 0$:

1. Initialise $\hat{E}(m)$ in PARI/GP as `ellinit([0, 36m², 0, 432m³, 1296m⁴−24624m])`.
2. Compute ALL integral points via `ellintegralpoints()` — this function is
   **provably complete** (Baker–Wüstholz height bounds + LLL lattice reduction).
3. Filter points satisfying $36 \mid \hat{X}$ and $36 \mid \hat{Y}$.
4. Verify against the original equation and record $(m, x, Y)$.

---

## File Layout

```
s3c114diff/
├── worker_d114.gp              # PARI/GP inner script (core algorithm)
├── worker_d114.py              # Python CE/BOINC wrapper
├── work_generator_d114.py      # CE/BOINC work generator (daemon mode)
├── assimilator_d114.py         # Result merger + verifier
├── validator_d114.py           # BOINC consensus validator
├── local_parallel_search_d114.py  # Multi-core local runner
├── setup_boinc_d114.sh         # One-shot BOINC project setup
├── Dockerfile                  # Container image
├── Makefile                    # Convenience targets
├── templates/
│   ├── d114_wu.xml             # BOINC WU template
│   └── d114_result.xml         # BOINC result template
└── output/
    ├── solutions_d114.txt      # Verified integer solutions (appended)
    └── search_log_d114.txt     # Timestamped progress log
```

---

## Quick Start (local)

### Requirements

```bash
# macOS
brew install pari

# Ubuntu / Debian
sudo apt-get install pari-gp python3

# Optional (fast in-process PARI)
pip install cypari2
```

### Run locally on all cores

```bash
# Search |m| ≤ 5000 using all available CPUs
python3 local_parallel_search_d114.py --limit 5000

# Open-ended search (runs until Ctrl-C, checkpointed)
python3 local_parallel_search_d114.py --no_limit

# Inspect results in real time
tail -f output/solutions_d114.txt
```

### Quick PARI/GP test

```bash
echo 'read("worker_d114.gp"); d114_search(-50,50)' | gp -q --stacksize=256m
```

---

## Charity Engine / BOINC Deployment

### 1. Set up the project

```bash
export BOINC_PROJECT_DIR=/home/boincadm/projects/s3c114diff
bash setup_boinc_d114.sh
```

### 2. Start the work generator daemon

```bash
# Standalone WU files (no BOINC submission)
python3 work_generator_d114.py --daemon --wu_dir ./wu_queue --dry_run

# With BOINC project submission
python3 work_generator_d114.py \
    --daemon \
    --boinc_project_dir $BOINC_PROJECT_DIR \
    --app_name d114
```

### 3. Start the assimilator

```bash
python3 assimilator_d114.py \
    --results_dir $BOINC_PROJECT_DIR/results_d114 \
    --master output/solutions_d114.txt
```

### 4. Worker invocation (CE hosts run automatically)

```
python3 worker_d114.py  wu.txt  result.txt  checkpoint_d114.json
```

---

## Work-Unit Format

```
m_start  <int>
m_end    <int>
batch    <int>      # m values per gp subprocess (default 20)
timeout_per_m  300  # seconds
gp_stack_mb    512
```

## Result Format

```
m  x  Y
```

One line per solution.  Lines starting with `#` are comments/diagnostics.

---

## Docker

```bash
docker build -t s3c114diff .
docker run --rm -v $(pwd)/output:/app/output s3c114diff
```

---

## Notes

* The search expands symmetrically: positive and negative $m$ bands are
  dispatched simultaneously so no bias toward either sign.
* `ellintegralpoints()` is computationally intensive for large $|m|$; the
  default batch size of 20 targets ~5–15 min per work-unit on a modern CPU.
* The assimilator deduplicates $(m, x, |Y|)$ triples and logs every new
  solution with a timestamp.
* The validator enforces consensus between two independent result copies
  (Byzantine tolerance for untrusted volunteer hosts).
