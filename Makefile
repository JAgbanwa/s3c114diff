# Makefile for s3c114diff

PYTHON   := python3
GP       := gp
APP_NAME := d114

# ── Local search ───────────────────────────────────────────────────────
.PHONY: search search-open test clean

search:
	$(PYTHON) local_parallel_search_d114.py --limit 10000

search-open:
	$(PYTHON) local_parallel_search_d114.py --no_limit

# ── Work generator ─────────────────────────────────────────────────────
.PHONY: wg wg-daemon

wg:
	$(PYTHON) work_generator_d114.py --wu_dir wu_queue --count 200 --dry_run

wg-daemon:
	$(PYTHON) work_generator_d114.py --wu_dir wu_queue --daemon --dry_run

# ── Assimilator ────────────────────────────────────────────────────────
.PHONY: assimilate

assimilate:
	$(PYTHON) assimilator_d114.py --results_dir results --master output/solutions_d114.txt

# ── Quick smoke-test: search m ∈ [-20, 20] ────────────────────────────
.PHONY: test

test:
	@echo "Running smoke test (m ∈ [-20, 20])..."
	@$(PYTHON) worker_d114.py <(printf 'm_start -20\nm_end 20\nbatch 5\n') \
	        /tmp/d114_smoke.txt /tmp/d114_smoke_chk.json
	@echo "Smoke-test results:"
	@cat /tmp/d114_smoke.txt || echo "(no solutions in [-20,20])"

# Inline gp test
.PHONY: gp-test

gp-test:
	echo 'read("worker_d114.gp"); d114_search(-10,10)' | $(GP) -q --stacksize=128m

# ── Validation ─────────────────────────────────────────────────────────
.PHONY: validate

validate:
	$(PYTHON) validator_d114.py $(FILE1) $(FILE2)

# ── Docker ────────────────────────────────────────────────────────────
.PHONY: docker-build docker-run

docker-build:
	docker build -t s3c114diff .

docker-run:
	docker run --rm -v $(PWD)/output:/app/output s3c114diff

# ── Cleanup ────────────────────────────────────────────────────────────
clean:
	rm -rf wu_queue/*.txt output/checkpoints/ /tmp/d114_smoke.*
	rm -f wg_d114_state.db assimilated_d114.log

.PHONY: show-solutions

show-solutions:
	@echo "=== Solutions found so far ==="
	@sort -n output/solutions_d114.txt 2>/dev/null || echo "(none yet)"
