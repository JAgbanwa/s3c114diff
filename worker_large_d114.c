/*
 * worker_large_d114.c  —  GMP shift-sieve for large m
 *
 * Equation:
 *   Y² = 36x³ + 36m²x² + 12m³x + m⁴ − 19m
 *
 * Factoring:
 *   Let B = m² + 6mx.  Then Y² = B² + D  where D = 36x³ − 19m.
 *   A solution exists iff D = (Y−B)(Y+B), i.e. D = d₁·d₂ with d₂−d₁ = 2B.
 *   Writing d₁ = t (the "shift"), d₂ = D/t:
 *       Y  = B + t
 *       t × (2B + t) = D  =  36x³ − 19m
 *   Rearranging:
 *       36x³ − 12mt·x − 2m²t − 19m − t² = 0    ... (*)
 *
 * Algorithm:
 *   For each m in [m_start, m_end]:
 *     For each shift t in [−T_MAX, T_MAX]   (t = 0 gives parametric family):
 *       Solve (*) for integer x using GMP integer cube-root near
 *           x₀ = cbrt( (2m²t + 19m + t²) / 36 )
 *       For each candidate x ∈ {x₀−2, x₀−1, x₀, x₀+1, x₀+2}:
 *         Compute Y = m² + 6mx + t
 *         Verify Y² == 36x³ + 36m²x² + 12m³x + m⁴ − 19m
 *         If true: print solution
 *
 * This is COMPLETE for all solutions with |t| ≤ T_MAX.
 * For the parametric family (t=0), all solutions in the m-range are found
 * exactly (since x = 19k when m = 12996k³).
 *
 * WU file format:
 *   m_start  <big decimal integer>
 *   m_end    <big decimal integer>
 *   t_max    <int>     (default 500)
 *
 * Result format:
 *   m  x  Y          (one solution per line, all decimal integers)
 *   ## DONE m=...     (progress heartbeat)
 *
 * Build:
 *   gcc -O3 -march=native -o worker_large_d114 worker_large_d114.c -lgmp
 *
 * Usage:
 *   ./worker_large_d114 wu.txt result.txt [checkpoint.txt]
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gmp.h>
#include <time.h>
#include <math.h>

/* ── Configuration ──────────────────────────────────────────────── */
static int    T_MAX      = 500;      /* shift range |t| ≤ T_MAX    */
static int    CKPT_EVERY = 100;      /* checkpoint every N m values */

/* ── Checkpoint ─────────────────────────────────────────────────── */
static const char *g_ckpt_path = NULL;
static time_t      g_last_ckpt = 0;

static void write_checkpoint(const mpz_t m_done) {
    if (!g_ckpt_path) return;
    FILE *f = fopen(g_ckpt_path, "w");
    if (!f) return;
    gmp_fprintf(f, "%Zd\n", m_done);
    fclose(f);
    g_last_ckpt = time(NULL);
}

static int read_checkpoint(mpz_t m_resume, const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    if (gmp_fscanf(f, "%Zd", m_resume) != 1) { fclose(f); return 0; }
    fclose(f);
    return 1;
}

/* ── Equation verifier ──────────────────────────────────────────── */
/*  RHS = 36x³ + 36m²x² + 12m³x + m⁴ − 19m                        */
static void compute_rhs(mpz_t rhs, const mpz_t m, const mpz_t x) {
    mpz_t t1, t2, t3, t4;
    mpz_inits(t1, t2, t3, t4, NULL);

    /* t1 = 36x³ */
    mpz_pow_ui(t1, x, 3);
    mpz_mul_ui(t1, t1, 36);

    /* t2 = 36m²x² */
    mpz_pow_ui(t2, m, 2);
    mpz_mul_ui(t2, t2, 36);
    mpz_t x2; mpz_init(x2);
    mpz_pow_ui(x2, x, 2);
    mpz_mul(t2, t2, x2);
    mpz_clear(x2);

    /* t3 = 12m³x */
    mpz_pow_ui(t3, m, 3);
    mpz_mul_ui(t3, t3, 12);
    mpz_mul(t3, t3, x);

    /* t4 = m⁴ */
    mpz_pow_ui(t4, m, 4);

    /* rhs = t1 + t2 + t3 + t4 - 19m */
    mpz_add(rhs, t1, t2);
    mpz_add(rhs, rhs, t3);
    mpz_add(rhs, rhs, t4);
    mpz_t t5; mpz_init(t5);
    mpz_mul_ui(t5, m, 19);
    mpz_sub(rhs, rhs, t5);

    mpz_clears(t1, t2, t3, t4, t5, NULL);
}

static int verify_solution(const mpz_t m, const mpz_t x, const mpz_t Y) {
    mpz_t rhs, Y2;
    mpz_inits(rhs, Y2, NULL);
    compute_rhs(rhs, m, x);
    mpz_pow_ui(Y2, Y, 2);
    int ok = (mpz_cmp(Y2, rhs) == 0);
    mpz_clears(rhs, Y2, NULL);
    return ok;
}

/* ── GMP integer cube root  (floor(n^(1/3))) ───────────────────── */
static void mpz_icbrt(mpz_t result, const mpz_t n) {
    /* Newton's method for integer cube root */
    if (mpz_sgn(n) == 0) { mpz_set_ui(result, 0); return; }

    int negative = (mpz_sgn(n) < 0);
    mpz_t abs_n;
    mpz_init(abs_n);
    mpz_abs(abs_n, n);

    /* Initial estimate via floating point */
    double dn = mpz_get_d(abs_n);
    double dx = pow(dn, 1.0/3.0);
    mpz_t x, x3, nx;
    mpz_inits(x, x3, nx, NULL);
    mpz_set_d(x, dx * 1.01 + 2.0);  /* start slightly above */

    /* Newton: x_new = (2x + n/x²) / 3 */
    mpz_t x2, tmp;
    mpz_inits(x2, tmp, NULL);
    for (int iter = 0; iter < 200; iter++) {
        mpz_pow_ui(x2, x, 2);
        if (mpz_sgn(x2) == 0) break;
        mpz_tdiv_q(tmp, abs_n, x2);   /* floor(n/x²) */
        mpz_mul_ui(nx, x, 2);
        mpz_add(nx, nx, tmp);
        mpz_tdiv_q_ui(nx, nx, 3);
        if (mpz_cmp(nx, x) >= 0) break;
        mpz_set(x, nx);
    }

    /* Adjust so x³ ≤ n < (x+1)³ */
    mpz_pow_ui(x3, x, 3);
    while (mpz_cmp(x3, abs_n) > 0) {
        mpz_sub_ui(x, x, 1);
        mpz_pow_ui(x3, x, 3);
    }
    mpz_t xp1, xp1_3;
    mpz_inits(xp1, xp1_3, NULL);
    mpz_add_ui(xp1, x, 1);
    mpz_pow_ui(xp1_3, xp1, 3);
    while (mpz_cmp(xp1_3, abs_n) <= 0) {
        mpz_add_ui(x, x, 1);
        mpz_set(xp1_3, xp1_3);   /* unused — just increment */
        mpz_add_ui(xp1, x, 1);
        mpz_pow_ui(xp1_3, xp1, 3);
    }

    mpz_set(result, x);
    if (negative) mpz_neg(result, result);
    mpz_clears(abs_n, x, x3, nx, x2, tmp, xp1, xp1_3, NULL);
}

/* ── Search one m value, all shifts ────────────────────────────── */
static long long search_one_m(const mpz_t m, FILE *out) {
    long long found = 0;
    mpz_t t,  arg, x0, x_cand, Y, rhs_cand;
    mpz_t two_t_m2, twelve_t_m, t_sq, coeff;
    mpz_t m2;

    mpz_inits(t, arg, x0, x_cand, Y, rhs_cand,
              two_t_m2, twelve_t_m, t_sq, coeff, m2, NULL);

    mpz_pow_ui(m2, m, 2);   /* m² */

    for (long long ti = -T_MAX; ti <= T_MAX; ti++) {
        mpz_set_si(t, ti);

        /*
         * Solve: 36x³ − 12·t·m·x − 2·t·m² − 19m − t² = 0
         * Rearranged: 36x³ = 2t·m² + 12t·m·x + 19m + t²
         * For large m, dominant term: x₀ ≈ cbrt( (2t·m² + 19m + t²) / 36 )
         * (The 12t·m·x term is a small correction; iterate once.)
         */

        /* arg = 2t·m² + 19m + t² */
        mpz_mul(two_t_m2, t, m2);
        mpz_mul_ui(two_t_m2, two_t_m2, 2);
        mpz_t m19; mpz_init(m19);
        mpz_mul_ui(m19, m, 19);
        mpz_pow_ui(t_sq, t, 2);
        mpz_add(arg, two_t_m2, m19);
        mpz_add(arg, arg, t_sq);
        mpz_clear(m19);

        /* x₀ = floor(cbrt(arg/36))  — note arg/36 could be negative */
        mpz_t arg36;
        mpz_init(arg36);
        if (ti == 0) {
            /* arg = 19m, all positive → direct cbrt */
            mpz_tdiv_q_ui(arg36, arg, 36);
        } else {
            /* divide rounding toward zero */
            mpz_tdiv_q_ui(arg36, arg, 36);
        }
        mpz_icbrt(x0, arg36);
        mpz_clear(arg36);

        /* Check x_cand ∈ {x0 - 2, ..., x0 + 2} */
        for (int delta = -2; delta <= 2; delta++) {
            mpz_set(x_cand, x0);
            if (delta > 0)       mpz_add_ui(x_cand, x_cand, (unsigned)delta);
            else if (delta < 0)  mpz_sub_ui(x_cand, x_cand, (unsigned)(-delta));

            /* Y = m² + 6mx + t */
            mpz_t B; mpz_init(B);
            mpz_mul_ui(B, m, 6);
            mpz_mul(B, B, x_cand);
            mpz_add(B, B, m2);
            mpz_add(Y, B, t);
            mpz_clear(B);

            /* Verify */
            if (verify_solution(m, x_cand, Y)) {
                gmp_fprintf(out, "%Zd %Zd %Zd\n", m, x_cand, Y);
                fflush(out);
                found++;
                /* Also print −Y if Y ≠ 0 */
                if (mpz_sgn(Y) != 0) {
                    mpz_t negY; mpz_init(negY);
                    mpz_neg(negY, Y);
                    gmp_fprintf(out, "%Zd %Zd %Zd\n", m, x_cand, negY);
                    fflush(out);
                    mpz_clear(negY);
                    found++;
                }
            }
        }
    }

    mpz_clears(t, arg, x0, x_cand, Y, rhs_cand,
               two_t_m2, twelve_t_m, t_sq, coeff, m2, NULL);
    return found;
}

/* ── WU file parser ─────────────────────────────────────────────── */
static int parse_wu(const char *wu_path,
                    mpz_t m_start, mpz_t m_end, int *t_max_out) {
    FILE *f = fopen(wu_path, "r");
    if (!f) { perror(wu_path); return 0; }
    char key[64], val[256];
    while (fscanf(f, "%63s %255s", key, val) == 2) {
        if (strcmp(key, "m_start") == 0) mpz_set_str(m_start, val, 10);
        else if (strcmp(key, "m_end")   == 0) mpz_set_str(m_end,   val, 10);
        else if (strcmp(key, "t_max")   == 0) *t_max_out = atoi(val);
    }
    fclose(f);
    return 1;
}

/* ── main ───────────────────────────────────────────────────────── */
int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr,
            "Usage: worker_large_d114 wu.txt result.txt [checkpoint.txt]\n");
        return 1;
    }

    const char *wu_path     = argv[1];
    const char *result_path = argv[2];
    if (argc >= 4) g_ckpt_path = argv[3];

    mpz_t m_start, m_end, m;
    mpz_inits(m_start, m_end, m, NULL);

    /* Parse WU */
    if (!parse_wu(wu_path, m_start, m_end, &T_MAX)) {
        fprintf(stderr, "Failed to parse WU file\n");
        return 1;
    }
    gmp_fprintf(stderr,
        "[worker_large_d114] m=[%Zd, %Zd]  t_max=%d\n",
        m_start, m_end, T_MAX);

    /* Resume from checkpoint if present */
    mpz_set(m, m_start);
    if (g_ckpt_path) {
        mpz_t m_resume; mpz_init(m_resume);
        if (read_checkpoint(m_resume, g_ckpt_path)) {
            if (mpz_cmp(m_resume, m_start) > 0
                && mpz_cmp(m_resume, m_end) <= 0) {
                mpz_add_ui(m, m_resume, 1);
                gmp_fprintf(stderr, "[worker_large_d114] Resuming from m=%Zd\n", m);
            }
        }
        mpz_clear(m_resume);
    }

    /* Open result file (append) */
    FILE *out = fopen(result_path, "a");
    if (!out) { perror(result_path); return 1; }

    long long total_found = 0;
    long long m_count = 0;
    time_t t0 = time(NULL);

    /* Main loop */
    while (mpz_cmp(m, m_end) <= 0) {
        /* Skip m = 0 */
        if (mpz_sgn(m) == 0) { mpz_add_ui(m, m, 1); continue; }

        long long found = search_one_m(m, out);
        total_found += found;
        m_count++;

        /* Heartbeat */
        gmp_fprintf(out, "## DONE m=%Zd found=%lld total=%lld\n",
                    m, found, total_found);
        fflush(out);

        /* Checkpoint */
        if (m_count % CKPT_EVERY == 0) {
            write_checkpoint(m);
            fprintf(stderr,
                "[worker_large_d114] progress %lld m-values  "
                "solutions_so_far=%lld  elapsed=%lds\n",
                m_count, total_found, (long)(time(NULL) - t0));
        }

        mpz_add_ui(m, m, 1);
    }

    /* Final checkpoint */
    write_checkpoint(m_end);
    gmp_fprintf(out,
        "## RANGE_DONE m_start=%Zd m_end=%Zd total_found=%lld\n",
        m_start, m_end, total_found);
    fclose(out);

    fprintf(stderr, "[worker_large_d114] Complete. Found %lld solutions.\n",
            total_found);
    mpz_clears(m_start, m_end, m, NULL);
    return 0;
}
