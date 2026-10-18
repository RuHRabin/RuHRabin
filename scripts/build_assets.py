#!/usr/bin/env python3
"""Generate the animated SVGs in ../assets/ by actually solving the physics.

Pure standard library. Nothing here is hand-drawn: every curve is the output of a
numerical integrator or a closed-form solution.

    hero.svg             Lorenz attractor, two trajectories 1e-3 apart (RK4)
    double-pendulum.svg  Lagrangian double pendulum, two copies 1e-3 rad apart (RK4)
    kepler-orbit.svg     Kepler's equation solved with Newton's method, equal areas swept
    wave-divider.svg     two travelling sine waves, used as a section separator

Run:  python3 scripts/build_assets.py
"""
import math
import os
import re

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")

BG = "#0a0e1a"
PANEL = "#0f1528"
TEXT = "#d7e3ff"
MUTED = "#7f8fb5"
CYAN = "#5ce1e6"
AMBER = "#ffb454"
ROSE = "#ff6b9d"

SERIF = "'STIX Two Math','Cambria Math','DejaVu Serif','Times New Roman',serif"
MONO = "'JetBrains Mono','SFMono-Regular',Menlo,Consolas,'DejaVu Sans Mono',monospace"


# ───────────────────────────── helpers ─────────────────────────────
def f(v):
    return f"{v:.1f}"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_TOK = re.compile(r"([_^])\{([^}]*)\}")


def rich(s, size):
    """Turn  x_{0}  and  10^{-3}  into positioned <tspan>s.

    Unicode sub/superscript digits are missing from many fonts; a shifted, smaller
    tspan renders the same everywhere.
    """
    if not _TOK.search(s):
        return esc(s)
    out, state = [], {"cur": 0.0}

    def emit(txt, off, fs):
        if not txt:
            return
        dy = off - state["cur"]
        state["cur"] = off
        dy_attr = f' dy="{dy:.1f}"' if abs(dy) > 0.05 else ""
        out.append(f'<tspan{dy_attr} font-size="{fs:.1f}">{esc(txt)}</tspan>')

    pos = 0
    for m in _TOK.finditer(s):
        emit(s[pos:m.start()], 0.0, size)
        if m.group(1) == "_":
            emit(m.group(2), 0.28 * size, 0.7 * size)
        else:
            emit(m.group(2), -0.38 * size, 0.7 * size)
        pos = m.end()
    emit(s[pos:], 0.0, size)
    return "".join(out)


def text(x, y, s, size=13, fill=MUTED, anchor="start", cls="m", extra=""):
    return (f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" {extra}>{rich(s, size)}</text>')


def head(w, h, title, desc, css=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">\n'
        f'<title id="t">{esc(title)}</title>\n<desc id="d">{esc(desc)}</desc>\n'
        f'<style>.m{{font-family:{MONO}}}.s{{font-family:{SERIF}}}{css}</style>\n'
    )


GRID_DEFS = (
    '<pattern id="g" width="20" height="20" patternUnits="userSpaceOnUse">'
    '<path d="M20 0H0V20" fill="none" stroke="#141c36" stroke-width="1"/></pattern>'
    '<pattern id="G" width="100" height="100" patternUnits="userSpaceOnUse">'
    '<rect width="100" height="100" fill="url(#g)"/>'
    '<path d="M100 0H0V100" fill="none" stroke="#1b2748" stroke-width="1"/></pattern>'
)


def panel(w, h):
    return (f'<rect width="{w}" height="{h}" rx="14" fill="{BG}"/>'
            f'<rect width="{w}" height="{h}" rx="14" fill="url(#G)"/>'
            f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="14" fill="none" '
            f'stroke="#26345e" stroke-width="1"/>')


def animate(attr, vals, dur):
    return (f'<animate attributeName="{attr}" values="{";".join(vals)}" dur="{dur}s" '
            f'repeatCount="indefinite"/>')


def write(name, content):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"{name:22s} {os.path.getsize(path) / 1024:6.1f} KB")


# ───────────────────────────── 1. Lorenz attractor hero ─────────────────────────────
def lorenz_path(s, steps, dt, every, sigma=10.0, rho=28.0, beta=8.0 / 3.0):
    def deriv(p):
        x, y, z = p
        return (sigma * (y - x), x * (rho - z) - y, x * y - beta * z)

    def axpy(p, k, h):
        return (p[0] + h * k[0], p[1] + h * k[1], p[2] + h * k[2])

    out = []
    for i in range(steps):
        if i % every == 0:
            out.append(s)
        k1 = deriv(s)
        k2 = deriv(axpy(s, k1, dt / 2))
        k3 = deriv(axpy(s, k2, dt / 2))
        k4 = deriv(axpy(s, k3, dt))
        s = (s[0] + dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
             s[1] + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]),
             s[2] + dt / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]))
    return out


def build_hero():
    dt = 0.005
    # settle onto the attractor for 10 time units, then split into two trajectories 1e-3 apart
    start = lorenz_path((1.0, 1.0, 1.0), 2000, dt, 1)[-1]
    a0 = start
    b0 = (start[0] + 1e-3, start[1], start[2])
    A = lorenz_path(a0, 8000, dt, 4)
    B = lorenz_path(b0, 8000, dt, 4)

    def to_d(pts):
        return "M" + " L".join(f"{860 + x * 14.5:.1f},{385 - z * 6.8:.1f}" for x, _, z in pts)

    dA, dB = to_d(A), to_d(B)
    cycle = 18

    css = (
        ".draw{stroke-dasharray:1 1;stroke-dashoffset:1;fill:none;stroke-linecap:round;stroke-linejoin:round;"
        f"animation:draw {cycle}s linear infinite}}"
        "@keyframes draw{0%{stroke-dashoffset:1;opacity:1}88%{stroke-dashoffset:0;opacity:1}"
        "95%{stroke-dashoffset:0;opacity:1}100%{stroke-dashoffset:0;opacity:0}}"
        "@media (prefers-reduced-motion:reduce){.draw{animation:none;stroke-dashoffset:0}}"
    )
    w, h = 1200, 440
    o = [head(w, h, "Rabin: a Lorenz attractor drawn by two nearly identical trajectories",
              "A dark graph-paper panel. The name Rabin sits at left above three equations: the Schrodinger "
              "equation, gradient descent and Euler's identity. At right two trajectories of the Lorenz "
              "system, one cyan and one amber, start 0.001 apart and slowly diverge.", css)]
    o.append("<defs>" + GRID_DEFS)
    o.append(f'<linearGradient id="tg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{CYAN}"/>'
             f'<stop offset="1" stop-color="#eaf3ff"/></linearGradient>')
    o.append('<radialGradient id="glow" cx=".72" cy=".5" r=".55"><stop offset="0" stop-color="#1d3a78" '
             'stop-opacity=".45"/><stop offset="1" stop-color="#1d3a78" stop-opacity="0"/></radialGradient>')
    o.append("</defs>")
    o.append(panel(w, h))
    o.append(f'<rect width="{w}" height="{h}" rx="14" fill="url(#glow)"/>')

    # axes for the attractor plot
    o.append('<g stroke="#2a3a68" stroke-width="1">'
             '<line x1="570" y1="385" x2="1150" y2="385"/><line x1="860" y1="385" x2="860" y2="45"/></g>')
    for xv in (-10, 0, 10):
        px = 860 + xv * 14.5
        o.append(f'<line x1="{px}" y1="385" x2="{px}" y2="390" stroke="#2a3a68"/>')
        o.append(text(px, 403, str(xv), 10, MUTED, "middle"))
    for zv in (10, 20, 30, 40, 50):
        py = 385 - zv * 6.8
        o.append(f'<line x1="855" y1="{py:.1f}" x2="860" y2="{py:.1f}" stroke="#2a3a68"/>')
        o.append(text(851, f"{py + 3.5:.1f}", str(zv), 10, MUTED, "end"))
    o.append(text(1150, 378, "x", 13, MUTED, "end", "s", 'font-style="italic"'))
    o.append(text(868, 56, "z", 13, MUTED, "start", "s", 'font-style="italic"'))
    o.append(text(1156, 34, "σ = 10 · ρ = 28 · β = 8/3", 13, AMBER, "end"))

    # trajectories
    o.append(f'<path id="la" class="draw" pathLength="1" d="{dA}" stroke="{CYAN}" stroke-width="1.3" opacity=".95"/>')
    o.append(f'<path id="lb" class="draw" pathLength="1" d="{dB}" stroke="{AMBER}" stroke-width="1.3" opacity=".9" '
             f'style="animation-delay:0s"/>')
    for pid, col in (("la", CYAN), ("lb", AMBER)):
        o.append(
            f'<circle r="4.5" fill="{col}"><animateMotion dur="{cycle}s" repeatCount="indefinite" '
            f'keyPoints="0;1;1" keyTimes="0;0.88;1" calcMode="linear"><mpath xlink:href="#{pid}"/></animateMotion>'
            f'<animate attributeName="opacity" values="1;1;0" keyTimes="0;0.95;1" dur="{cycle}s" '
            f'repeatCount="indefinite"/></circle>')

    # legend
    o.append(f'<circle cx="600" cy="424" r="4" fill="{CYAN}"/>')
    o.append(text(610, 428, "x_{0}", 12, TEXT))
    o.append(f'<circle cx="650" cy="424" r="4" fill="{AMBER}"/>')
    o.append(text(660, 428, "x_{0} + 10^{−3}", 12, TEXT))
    o.append(text(1150, 428, "same law, different futures", 12, MUTED, "end"))

    # left column
    o.append(text(44, 64, "// rabin.sim — phase space of one curious mind", 13, MUTED))
    o.append(text(40, 168, "RABIN", 104, "url(#tg)", "start", "s", 'font-weight="700" letter-spacing="6"'))
    o.append(text(44, 212, "lifelong learner", 18, TEXT))
    o.append(text(44, 238, "machine learning · simulation", 18, CYAN))
    o.append(f'<line x1="44" y1="262" x2="300" y2="262" stroke="{AMBER}" stroke-width="2" opacity=".8"/>')
    o.append(text(44, 304, "iħ ∂ψ/∂t = Hψ", 30, AMBER, "start", "s", 'font-style="italic"'))
    o.append(text(44, 342, "θ ← θ − η ∇L(θ)", 26, TEXT, "start", "s", 'font-style="italic"'))
    o.append(text(44, 380, "e^{iπ} + 1 = 0", 26, CYAN, "start", "s", 'font-style="italic"'))
    o.append(text(44, 428, "c = 299 792 458 m/s · ħ ≈ 1.0546×10^{−34} J·s", 12, MUTED))
    o.append("</svg>\n")
    write("hero.svg", "\n".join(o))


# ───────────────────────────── 2. Double pendulum ─────────────────────────────
def pendulum_frames(th1, th2, total=20.0, dt=0.002, frame_dt=0.05, g=9.81):
    def deriv(s):
        t1, t2, w1, w2 = s
        d = t1 - t2
        den = 2 - math.cos(2 * d)
        a1 = (-3 * g * math.sin(t1) - g * math.sin(t1 - 2 * t2)
              - 2 * math.sin(d) * (w2 * w2 + w1 * w1 * math.cos(d))) / den
        a2 = (2 * math.sin(d) * (2 * w1 * w1 + 2 * g * math.cos(t1) + w2 * w2 * math.cos(d))) / den
        return (w1, w2, a1, a2)

    def step(s, h):
        k1 = deriv(s)
        k2 = deriv(tuple(s[i] + h / 2 * k1[i] for i in range(4)))
        k3 = deriv(tuple(s[i] + h / 2 * k2[i] for i in range(4)))
        k4 = deriv(tuple(s[i] + h * k3[i] for i in range(4)))
        return tuple(s[i] + h / 6 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) for i in range(4))

    s = (th1, th2, 0.0, 0.0)
    frames, every = [], int(round(frame_dt / dt))
    for i in range(int(round(total / dt)) + 1):
        if i % every == 0:
            frames.append(s)
        s = step(s, dt)
    return frames


def build_pendulum():
    w, h = 480, 420
    px, py, S = 240, 210, 92
    total = 20
    A = pendulum_frames(1.9, 2.4, total)
    B = pendulum_frames(1.9, 2.4 + 1e-3, total)

    def pos(fr):
        b1 = [(px + S * math.sin(t1), py + S * math.cos(t1)) for t1, _, _, _ in fr]
        b2 = [(x + S * math.sin(t2), y + S * math.cos(t2))
              for (x, y), (_, t2, _, _) in zip(b1, fr)]
        return b1, b2

    o = [head(w, h, "Two double pendulums that start 0.001 radians apart",
              "A cyan and an amber double pendulum swing together at first, then drift apart into completely "
              "different motion, a demonstration of chaos.")]
    o.append("<defs>" + GRID_DEFS + "</defs>")
    o.append(panel(w, h))
    o.append(text(20, 30, "double pendulum · chaos", 14, MUTED))
    o.append(text(460, 32, "ℒ = T − V", 20, AMBER, "end", "s", 'font-style="italic"'))

    for fr, col in ((A, CYAN), (B, AMBER)):
        b1, b2 = pos(fr)
        trace = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in b2)
        o.append(f'<path d="{trace}" fill="none" stroke="{col}" stroke-width="1" opacity=".22"/>')
    for fr, col in ((A, CYAN), (B, AMBER)):
        b1, b2 = pos(fr)
        b1x = [f(x) for x, _ in b1]
        b1y = [f(y) for _, y in b1]
        b2x = [f(x) for x, _ in b2]
        b2y = [f(y) for _, y in b2]
        o.append(f'<g stroke="{col}" stroke-width="2" stroke-linecap="round">')
        o.append(f'<line x1="{px}" y1="{py}" x2="{b1x[0]}" y2="{b1y[0]}">'
                 f'{animate("x2", b1x, total)}{animate("y2", b1y, total)}</line>')
        o.append(f'<line x1="{b1x[0]}" y1="{b1y[0]}" x2="{b2x[0]}" y2="{b2y[0]}">'
                 f'{animate("x1", b1x, total)}{animate("y1", b1y, total)}'
                 f'{animate("x2", b2x, total)}{animate("y2", b2y, total)}</line></g>')
        o.append(f'<circle r="5" fill="{col}" cx="{b1x[0]}" cy="{b1y[0]}">'
                 f'{animate("cx", b1x, total)}{animate("cy", b1y, total)}</circle>')
        o.append(f'<circle r="8" fill="{col}" fill-opacity=".85" cx="{b2x[0]}" cy="{b2y[0]}">'
                 f'{animate("cx", b2x, total)}{animate("cy", b2y, total)}</circle>')
    o.append(f'<circle cx="{px}" cy="{py}" r="4" fill="{BG}" stroke="{TEXT}" stroke-width="1.5"/>')
    o.append(f'<circle cx="24" cy="396" r="4" fill="{CYAN}"/>')
    o.append(text(34, 400, "θ_{2}(0)", 12, TEXT))
    o.append(f'<circle cx="84" cy="396" r="4" fill="{AMBER}"/>')
    o.append(text(94, 400, "θ_{2}(0) + 10^{−3} rad", 12, TEXT))
    o.append("</svg>\n")
    write("double-pendulum.svg", "\n".join(o))


# ───────────────────────────── 3. Kepler orbit ─────────────────────────────
def kepler_E(M, e):
    E = M if e < 0.8 else math.pi
    for _ in range(30):
        E -= (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
    return E


def build_kepler():
    w, h = 480, 420
    cx, cy = 250.0, 205.0
    a, e = 168.0, 0.62
    b = a * math.sqrt(1 - e * e)
    c = a * e
    fx, fy = cx + c, cy  # the star sits at the right-hand focus
    T = 12.0
    n = 120
    window = 0.1  # fraction of the period swept by the wedge
    k = 8

    def at(M):
        E = kepler_E(M % (2 * math.pi), e)
        return cx + a * math.cos(E), cy + b * math.sin(E)

    px_, py_, poly = [], [], []
    for i in range(n + 1):
        M = 2 * math.pi * i / n
        x, y = at(M)
        px_.append(f(x))
        py_.append(f(y))
        pts = [(fx, fy)]
        for j in range(k + 1):
            pts.append(at(M - 2 * math.pi * window + j * 2 * math.pi * window / k))
        poly.append(" ".join(f"{u:.1f},{v:.1f}" for u, v in pts))

    o = [head(w, h, "Kepler orbit: equal areas in equal times",
              "A planet moves on an eccentric ellipse around a glowing star, fastest near the star. A shaded "
              "wedge from the star to the planet always has the same area.")]
    o.append("<defs>" + GRID_DEFS)
    o.append(f'<radialGradient id="sun"><stop offset="0" stop-color="#fff3d1"/><stop offset=".45" '
             f'stop-color="{AMBER}"/><stop offset="1" stop-color="{AMBER}" stop-opacity="0"/></radialGradient>')
    o.append("</defs>")
    o.append(panel(w, h))
    o.append(text(20, 30, "kepler orbit · order", 14, MUTED))
    o.append(text(460, 30, "e = 0.62", 14, AMBER, "end"))
    o.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{a}" ry="{b:.1f}" fill="none" stroke="#36497e" '
             f'stroke-width="1.2" stroke-dasharray="4 5"/>')
    o.append(f'<line x1="{cx - a}" y1="{cy}" x2="{cx + a}" y2="{cy}" stroke="#1f2c52" stroke-width="1"/>')
    o.append(f'<polygon points="{poly[0]}" fill="{AMBER}" fill-opacity=".22" stroke="{AMBER}" '
             f'stroke-opacity=".7" stroke-width="1">{animate("points", poly, T)}</polygon>')
    o.append(f'<circle cx="{fx}" cy="{fy}" r="30" fill="url(#sun)" opacity=".8"/>')
    o.append(f'<circle cx="{fx}" cy="{fy}" r="9" fill="#fff3d1"><animate attributeName="r" values="9;10.5;9" '
             f'dur="3s" repeatCount="indefinite"/></circle>')
    # inner planet obeys T ∝ a^(3/2): a_inner = 38  ->  T = 12·(38/168)^1.5
    t_in = T * (38 / a) ** 1.5
    o.append(f'<circle cx="{fx}" cy="{fy}" r="38" fill="none" stroke="#26345e" stroke-width="1"/>')
    o.append(f'<circle cx="{fx + 38}" cy="{fy}" r="3.5" fill="{ROSE}"><animateTransform attributeName="transform" '
             f'type="rotate" from="0 {fx} {fy}" to="360 {fx} {fy}" dur="{t_in:.2f}s" repeatCount="indefinite"/></circle>')
    o.append(f'<circle r="7" fill="{CYAN}" cx="{px_[0]}" cy="{py_[0]}">'
             f'{animate("cx", px_, T)}{animate("cy", py_, T)}</circle>')
    o.append(text(250, 380, "r(θ) = a(1 − e^{2}) / (1 + e cos θ)", 19, AMBER, "middle", "s", 'font-style="italic"'))
    o.append(text(250, 404, "dA/dt = L / 2m = const", 13, MUTED, "middle"))
    o.append("</svg>\n")
    write("kepler-orbit.svg", "\n".join(o))


# ───────────────────────────── 5. Divider ─────────────────────────────
def build_divider():
    w, h = 1200, 40

    def wave(amp, lam):
        xs = range(-int(lam), w + int(lam) + 1, 6)
        return "M" + " L".join(f"{x},{20 - amp * math.sin(2 * math.pi * x / lam):.1f}" for x in xs)

    o = [head(w, h, "", "")]
    o[0] = o[0].replace('role="img" aria-labelledby="t d"', 'role="presentation" aria-hidden="true"')
    o.append('<defs><clipPath id="c"><rect width="1200" height="40"/></clipPath></defs>')
    o.append('<g clip-path="url(#c)">')
    o.append('<line x1="0" y1="20" x2="1200" y2="20" stroke="#7f8fb5" stroke-width="1" stroke-dasharray="2 6" opacity=".45"/>')
    o.append(f'<path d="{wave(9, 120)}" fill="none" stroke="#22b8cf" stroke-width="1.7" opacity=".9">'
             f'<animateTransform attributeName="transform" type="translate" from="0 0" to="120 0" dur="4s" '
             f'repeatCount="indefinite"/></path>')
    o.append(f'<path d="{wave(7, 200)}" fill="none" stroke="#f59f00" stroke-width="1.5" opacity=".8">'
             f'<animateTransform attributeName="transform" type="translate" from="0 0" to="-200 0" dur="8s" '
             f'repeatCount="indefinite"/></path>')
    o.append("</g></svg>\n")
    write("wave-divider.svg", "\n".join(o))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    build_hero()
    build_pendulum()
    build_kepler()
    build_divider()
