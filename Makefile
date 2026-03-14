# Makefile for s3c114diff

PYTHON   := python3
GP       := gp
CC       := gcc
APP_NAME := d114

# Detect Homebrew GMP on Apple Silicon macOS
UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)
ifeq ($(UNAME_S),Darwin)
  ifeq ($(UNAME_M),arm64)
    GMP_INC := -I/opt/homebrew/include
    GMP_LIB := -L/opt/homebrew/lib
  else
    GMP_INC := -I/usr/local/include
    GMP_LIB := -L/usr/local/lib
  endif
else
  GMP_INC :=
  GMP_LIB :=
endif

# ─────────────────────────────────────────────────────────────────────
# Build GMP C workers
# ─────────────────────────────────────────────────────────────────────
.PHONY: build
build: worker_large_d114

worker_large_d114: worker_large_d114.c
	$(CC) -O3 -march=native -o $@ $< $(GMP_INC) $(GMP_LIB) -lgmp
	@echo "Built $@"

# ─────────────────────────────────────────────────────────────────────
# Local small-m search  (PARI/GP, all |m| ≤ limit)
# ─────────────────────────────────────────────────────────────────────
.PHONY: search search-open

search:
	$(PYTHON) local_parallel_search_d114.py --limit 10000

search-open:
	$(PYTHON) local_parallel_search_d114.py --no_limit

# ─────────────────────────────────────────────────────────────────────
# Large-m search  (GMP C worker, |m| in [10^20, 10^30])
# ─────────────────────────────────────────────────────────────────────
.PHONY: parametric-enum large-wg large-wg-daemon

# Step 1: enumerate the infinite parametric family instantly
parametric-enum:
	$(PYTHON) parametric_enum_d114.py \
	    --m_lo 1e20 --m_hi 1e30 \
	    --output output/solutions_parametric_d114.txt

# Step 2: generate CE work units for anomalous solution sieve
large-wg:
	$(PYTHON) work_generator_large_d114.py \
	    --m_lo 1e20 --m_hi 1e30 \
	    --wu_dir wu_large --count 500000 --dry_run

large-wg-daemon:
	$(PYTHON) work_generator_large_d114.py \
	    --m_lo 1e20 --m_hi 1e30 \
	    --wu_dir wu_large --daemon \
	    --boinc_project_dir $(BOINC_PROJECT_DIR)

# Quick local test of the GMP worker (m ∈ [12996, 12996×8])
large-test: worker_large_d114
	@printf 'm_start 12996\nm_end 103968\nt_max 5\n' > /tmp/d114_large_wu.txt
	./worker_large_d114 /tmp/d114_large_wu.txt /tmp/d114_large_result.txt
	@echo "=== Solutions found ==="
	@grep -v '^##' /tmp/d114_large_result.txt || echo "(none)"

# ─────────────────────────────────────────────────────────────────────
# Work generator (small m)
# ─────────────────────────────────────────────────────────────────────
.PHONY: wg wg-daemon assimilate

wg:
	$(PYTHON) work_generator_d114.py --wu_dir wu_queue --count 200 --dry_run

wg-daemon:
	$(PYTHON) work_generator_d114.py --wu_dir wu_queue --daemon --dry_run

assimilate:
	$(PYTHON) assimilator_d114.py \
	    --results_dir results \
	    --master output/solutions_d114.txt

# ─────────────────────────────────────────────────────────────────────
# Smoke tests
# ─────────────────────────────────────────────────────────────────────
.PHONY: test gp-test validate

test: worker_large_d114
	@echo "--- GP smoke test (m ∈ [-20,20]) ---"
	echo 'read("worker_d114.gp"); d114_search(-20,20)' | $(GP) -q --stacksize=128m 2>/dev/null
	@echo "--- GMP smoke test (m ∈ [12996, 103968]) ---"
	$(MAKE) large-test

gp-test:
	echo 'read("worker_d114.gp"); d114_search(-50,50)' | $(GP) -q --stacksize=256m

validate:
	$(PYTHON) validator_d114.py $(FILE1) $(FILE2)

# ─────────────────────────────────────────────────────────────────────
# Docker
# ─────────────────────────────────────────────────────────────────────
.PHONY: docker-build docker-run

docker-build:
	docker build -t s3c114diff .

docker-run:
	docker run --rm -v $(PWD)/output:/app/output s3c114diff

# ─────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────
.PHONY: clean show-solutions

clean:
	rm -rf wu_queue/ wu_large/ output/checkpoints/ /tmp/d114_*.txt
	rm -f wg_d114_state.db wg_large_d114_state.db assimilated_d114.log
	rm -f worker_large_d114

show-solutions:
	@echo "=== Small-m solutions (PARI/GP search) ==="
	@sort -n output/solutions_d114.txt 2>/dev/null | head -20 || echo "(none yet)"
	@echo "=== Parametric-family solutions (large m) ==="
	@wc -l output/solutions_parametric_d114.txt 2>/dev/null || echo "(not yet run)"
