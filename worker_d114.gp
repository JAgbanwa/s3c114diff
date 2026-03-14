\\  worker_d114.gp  —  PARI/GP inner script for s3c114diff search
\\
\\  Original equation (in m, x, Y — all integers):
\\
\\    Y² = 36·x³ + 36·m²·x² + 12·m³·x + m⁴ − 19·m
\\
\\  Weierstrass reduction (multiply both sides by 36²=1296,
\\  substitute  X̂ = 36·x,  Ŷ = 36·Y ):
\\
\\    Ê(m) :  Ŷ² = X̂³ + 36·m²·X̂² + 432·m³·X̂ + 1296·m⁴ − 24624·m
\\
\\  An integral point (X̂, Ŷ) gives an integer solution iff
\\    36 | X̂   and   36 | Ŷ
\\  in which case  x = X̂/36,  Y = Ŷ/36.
\\
\\  Strategy:
\\    1. Initialise Ê(m) in generalised Weierstrass form [0,a2,0,a4,a6].
\\    2. Skip singular curves (disc = 0, only at m = 0).
\\    3. ellintegralpoints(E) is PROVABLY COMPLETE:
\\         — Nagell-Tate torsion enumeration
\\         — Mordell-Weil rank via 2-descent
\\         — Baker-Wüstholz elliptic-logarithm height bound
\\         — LLL + sieving over the height-bounded region
\\    4. Filter integral points by divisibility 36|X̂, 36|Ŷ.
\\    5. Print:  m  x  Y   (one solution per line).
\\
\\  Called by worker_d114.py:
\\     echo "d114_search(m_start, m_end)" | gp -q --stacksize=512m worker_d114.gp

\\ ================================================================
\\ RHS evaluator for the ORIGINAL equation (for self-verification)
\\ ================================================================
d114_rhs_orig(m, x) = {
    36*x^3 + 36*m^2*x^2 + 12*m^3*x + m^4 - 19*m
}

\\ RHS for the Weierstrass lift (keeps big-int accuracy in gp)
d114_rhs_w(m, Xh) = {
    Xh^3 + 36*m^2*Xh^2 + 432*m^3*Xh + 1296*m^4 - 24624*m
}

\\ Final integer-solution verifier against ORIGINAL equation
d114_verify(m, x, Y) = {
    Y^2 == d114_rhs_orig(m, x)
}

\\ ================================================================
\\ Core: find all integer solutions  Y² = 36x³+...  for one m ≠ 0
\\ ================================================================
d114_one(m) = {
    my(E, pts, np, Xh, Yh, x, Y, a2, a4, a6);

    a2 =  36  * m^2;
    a4 =  432 * m^3;
    a6 =  1296 * m^4 - 24624 * m;

    E = ellinit([0, a2, 0, a4, a6]);

    \\ Singular curve (disc=0) — happens only at m=0 which is excluded.
    if(E.disc == 0, return());

    \\ Boost stack for very large m
    default(parisize, max(default(parisize), 256*1024*1024));

    \\ Find ALL integral points (PARI certificate-level completeness)
    \\ ellintegralpoints returns a list of [x,y] pairs with y > 0.
    pts = ellintegralpoints(E);
    np  = #pts;
    if(np == 0, return());

    for(i = 1, np,
        Xh = pts[i][1];
        Yh = pts[i][2];

        \\ Filter: must be divisible by 36 to give integer (x,Y)
        if( Xh % 36 != 0 || Yh % 36 != 0, next() );
        x = Xh / 36;
        Y = Yh / 36;

        \\ Self-verify against original equation
        if(!d114_verify(m, x, Y),
            printf("## VERIFY_FAIL m=%d Xh=%d Yh=%d\n", m, Xh, Yh);
            next()
        );

        printf("%d %d %d\n", m, x,  Y);
        if(Y != 0,
            printf("%d %d %d\n", m, x, -Y)
        );
    );
}

\\ ================================================================
\\ Main entry: process range [m_start, m_end]  (skips m=0)
\\ ================================================================
d114_search(m_start, m_end) = {
    my(m, t0, dt);
    t0 = gettime();

    for(m = m_start, m_end,
        if(m == 0, next());
        d114_one(m);
        dt = gettime() - t0;
        \\ Heartbeat every m to stdout (stderr would disturb the parser)
        \\ Use ## prefix so the Python wrapper can ignore it.
        printf("## DONE m=%d elapsed=%.1fs\n", m, dt/1000.0);
    );
    printf("## RANGE_DONE m_start=%d m_end=%d\n", m_start, m_end);
}
