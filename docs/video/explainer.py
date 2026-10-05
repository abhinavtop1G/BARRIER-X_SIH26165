"""BARRIERX — animated explainer of how the system works (~90 s)."""

from manim import *

BG = "#0B0E13"
PANEL = "#141A23"
SLATE = "#5B6676"
INK = "#ECEAE4"
MUTED = "#8E98A6"
GOLD = "#E0B04F"
BLUE = "#5DA9E9"
TEAL = "#3FC1B0"
VIOLET = "#A184E6"
GREEN_OK = "#4C9F70"

SEV_HIGH = "#E5484D"
SEV_ELEV = "#F08C3A"
SEV_BORD = "#E8C547"
SEV_LOW = "#4C9F70"

MONO = "Monospace"
FAST = 0.5
HOLD = 0.75


def T(s, size=28, color=INK, weight=NORMAL, font=None, **kw):
    if font:
        kw["font"] = font
    return Text(s, font_size=size, color=color, weight=weight, **kw)


def node(title, sub=None, color=GOLD, w=2.8, h=1.1, title_size=24, sub_size=15):
    rect = RoundedRectangle(corner_radius=0.14, width=w, height=h, stroke_color=color,
                            stroke_width=2.5, fill_color=PANEL, fill_opacity=1)
    parts = [T(title, title_size, INK, weight=BOLD)]
    if sub:
        parts.append(T(sub, sub_size, color, font=MONO))
    text = VGroup(*parts).arrange(DOWN, buff=0.1)
    if text.width > w - 0.3:
        text.scale_to_fit_width(w - 0.3)
    text.move_to(rect)
    return VGroup(rect, text)


def chip(s, color=GOLD, size=16, mono=True, pad=0.18):
    t = T(s, size, color, font=MONO if mono else None)
    r = RoundedRectangle(corner_radius=0.1, width=t.width + 2 * pad, height=t.height + 2 * pad * 0.8,
                         stroke_color=color, stroke_width=1.8, fill_color=PANEL, fill_opacity=1)
    t.move_to(r)
    return VGroup(r, t)


def edge(a, b, color=SLATE, sw=3, buff=0.08, tip=True):
    if tip:
        return Arrow(a, b, buff=buff, color=color, stroke_width=sw,
                     max_tip_length_to_length_ratio=0.12, max_stroke_width_to_length_ratio=10)
    return Line(a, b, buff=buff, color=color, stroke_width=sw)


def tag(num, label):
    return MarkupText(f'<span letter_spacing="1200">{num}  /  {label}</span>',
                      font_size=16, color=GOLD, font=MONO).to_corner(UL, buff=0.4)


def tick(color=GREEN_OK, size=26):
    return T("✓", size, color, weight=BOLD)


class RepoExplainer(Scene):
    def construct(self):
        self.camera.background_color = BG
        self.bg = self.make_grid()
        self.add(self.bg)

        self.cold_open()
        self.hook()
        self.system_map()
        self.gateway()
        self.product()
        self.scoring()
        self.api_ops()
        self.training()
        self.site_risk()
        self.agent()
        self.ci()
        self.numbers()
        self.outro()

    def make_grid(self):
        dots = VGroup(*[Dot([x * 0.6, y * 0.6, 0], radius=0.012, color=SLATE)
                        for x in range(-12, 13) for y in range(-7, 8)])
        return dots.set_opacity(0.35)

    def hold(self, t):
        self.wait(t * HOLD)

    def clear(self):
        mobs = [m for m in self.mobjects if m is not self.bg]
        for m in mobs:
            m.clear_updaters()
        if mobs:
            self.play(*[FadeOut(m, shift=UP * 0.25) for m in mobs], run_time=FAST)

    def section(self, num, label, title):
        tg = tag(num, label)
        tl = T(title, 40, INK, weight=BOLD).next_to(tg, DOWN, buff=0.18, aligned_edge=LEFT)
        self.play(FadeIn(tg, shift=RIGHT * 0.3), FadeIn(tl, shift=RIGHT * 0.3), run_time=FAST)
        return VGroup(tg, tl)

    def travel(self, mob, points, run_time=0.8):
        path = VMobject().set_points_as_corners([np.array(p) for p in points])
        self.play(MoveAlongPath(mob, path), run_time=run_time, rate_func=linear)

    def cold_open(self):
        narrative = T("“isolation valve not tagged out — residual pressure escaped”",
                      26, MUTED, font=MONO)
        narrative.scale_to_fit_width(min(narrative.width, 12.5)).move_to(UP * 0.9)
        self.play(AddTextLetterByLetter(narrative), run_time=1.8)

        q = T("Could this have killed someone?", 52, INK, weight=BOLD).move_to(DOWN * 0.4)
        self.play(FadeIn(q, scale=1.35), run_time=0.4)
        self.hold(1.3)

        logo = T("BARRIER X", 110, GOLD, weight=BOLD)
        bar = Line(LEFT, RIGHT, color=GOLD, stroke_width=4).set_width(logo.width).next_to(logo, DOWN, buff=0.15)
        sub = T("SIF intelligence for high-hazard operations", 26, INK).next_to(bar, DOWN, buff=0.3)
        tagline = T("Team GIT PUSH AND PRAY  ·  SIH 2026  ·  PS 26165", 18, MUTED, font=MONO)
        tagline.next_to(sub, DOWN, buff=0.25)
        self.play(FadeOut(narrative, shift=UP * 0.4), ReplacementTransform(q, logo), run_time=0.7)
        self.play(Create(bar), FadeIn(sub, shift=UP * 0.2), FadeIn(tagline), run_time=0.6)
        self.hold(1.6)
        self.clear()

    def hook(self):
        apex, base_y, half = 2.2, -2.2, 2.3

        def hw(y):
            return half * (apex - y) / (apex - base_y)

        cuts = [apex, 0.9, -0.5, base_y]
        cols = [SEV_HIGH, SEV_ELEV, SLATE]
        names = ["fatal", "serious", "minor"]
        layers = VGroup()
        for i in range(3):
            y0, y1 = cuts[i], cuts[i + 1]
            poly = Polygon([-hw(y0), y0, 0], [hw(y0), y0, 0], [hw(y1), y1, 0], [-hw(y1), y1, 0],
                           stroke_color=BG, stroke_width=5, fill_color=cols[i], fill_opacity=0.9)
            lab = T(names[i], 16, INK, weight=BOLD).move_to(poly.get_center() + (DOWN * 0.25 if i == 0 else 0))
            layers.add(VGroup(poly, lab))
        pyramid = layers.shift(LEFT * 3.6)
        self.play(LaggedStart(*[FadeIn(l, shift=UP * 0.3) for l in reversed(layers)], lag_ratio=0.2),
                  run_time=0.9)
        myth = T("Cutting minor incidents does not cut fatalities.", 22, MUTED).move_to(RIGHT * 2.8 + UP * 2.0)
        self.play(FadeIn(myth), run_time=FAST)

        p = ValueTracker(0)
        big = always_redraw(lambda: T(f"<{int(p.get_value())}%", 130, GOLD, weight=BOLD)
                            .move_to(RIGHT * 2.8 + UP * 0.4))
        line = T("of incidents can cause a serious injury or fatality", 24, INK).move_to(RIGHT * 2.8 + DOWN * 1.0)
        punch = T("Find those first.", 34, INK, weight=BOLD).move_to(RIGHT * 2.8 + DOWN * 1.9)
        self.add(big)
        self.play(p.animate.set_value(20), run_time=0.9, rate_func=rush_from)
        self.play(FadeIn(line, shift=UP * 0.2), layers[0].animate.scale(1.12), run_time=FAST)
        self.play(FadeIn(punch, shift=UP * 0.2), run_time=FAST)
        self.hold(1.8)
        self.clear()

    def system_map(self):
        hdr = self.section("01", "ARCHITECTURE", "Five services, one compose file")

        fe = node("React", "vite · :5173", BLUE, 2.4, 1.0).move_to([-5.2, 0, 0])
        gw = node("Go Gateway", ":9000", GOLD, 2.6, 1.0).move_to([-1.6, 0, 0])
        ml = node("ML Scoring", "fastapi · :8000", TEAL, 2.8, 1.0).move_to([2.2, 1.6, 0])
        ag = node("HSE Agent", "fastapi · :8001", VIOLET, 2.8, 1.0).move_to([2.2, -1.6, 0])
        db = node("MongoDB", "mongo:6.0", SLATE, 2.6, 1.0).move_to([-1.6, -2.6, 0])
        onnx = chip("DeBERTa-v3 · ONNX", TEAL, 14).move_to([5.6, 1.9, 0])
        sqlite = chip("SQLite site store", TEAL, 14).move_to([5.6, 1.2, 0])
        llm = chip("Gemini · Groq · OpenAI", VIOLET, 14).move_to([5.6, -1.6, 0])

        edges = VGroup(
            edge(fe.get_right(), gw.get_left(), BLUE),
            edge(gw.get_right(), ml.get_left(), TEAL),
            edge(gw.get_right(), ag.get_left(), VIOLET),
            edge(gw.get_bottom(), db.get_top(), SLATE),
            edge(ag.get_top(), ml.get_bottom(), TEAL),
        )
        links = VGroup(
            edge(ml.get_right() + UP * 0.2, onnx.get_left(), TEAL, tip=False),
            edge(ml.get_right() + DOWN * 0.2, sqlite.get_left(), TEAL, tip=False),
            edge(ag.get_right(), llm.get_left(), VIOLET, tip=False),
        )
        edge_labels = VGroup(
            T("JWT", 12, BLUE, font=MONO).next_to(edges[0], UP, buff=0.05),
            T("/score", 12, TEAL, font=MONO).next_to(edges[1].get_center(), UL, buff=0.05),
            T("/agent/chat", 12, VIOLET, font=MONO).next_to(edges[2].get_center(), DL, buff=0.05),
            T("users · reports", 12, MUTED, font=MONO).next_to(edges[3], RIGHT, buff=0.08),
        )
        nodes = [fe, gw, ml, ag, db]
        self.play(LaggedStart(*[GrowFromCenter(n) for n in nodes], lag_ratio=0.15), run_time=1.2)
        self.play(LaggedStart(*[Create(e) for e in edges], lag_ratio=0.12),
                  LaggedStart(*[FadeIn(c, shift=LEFT * 0.2) for c in (onnx, sqlite, llm)], lag_ratio=0.15),
                  *[Create(l) for l in links], run_time=1.2)
        self.play(FadeIn(edge_labels), run_time=FAST)

        cmd = chip("$ docker compose up", GOLD, 18).to_edge(DOWN, buff=0.3).set_x(3.6)
        self.play(FadeIn(cmd, shift=UP * 0.2), run_time=FAST)

        cols = [BLUE, TEAL, VIOLET, SLATE, TEAL]
        for _ in range(2):
            dots = VGroup(*[Dot(e.get_start(), radius=0.07, color=c) for e, c in zip(edges, cols)])
            self.add(dots)
            self.play(*[MoveAlongPath(d, Line(e.get_start(), e.get_end())) for d, e in zip(dots, edges)],
                      run_time=0.9, rate_func=linear)
            self.remove(dots)
        self.hold(1.0)

        self.gw_node = gw
        others = [m for m in self.mobjects if m not in (self.bg, gw)]
        self.play(*[FadeOut(m) for m in others], run_time=FAST)

    def gateway(self):
        box = RoundedRectangle(corner_radius=0.2, width=10.2, height=5.0, stroke_color=GOLD,
                               stroke_width=3, fill_color=PANEL, fill_opacity=0.6).move_to([-1.3, -0.4, 0])
        self.play(FadeOut(self.gw_node[1]), ReplacementTransform(self.gw_node[0], box), run_time=0.7)
        hdr = self.section("02", "GO GATEWAY", "Every request, three gates")
        label = T("gateway/  :9000", 16, GOLD, font=MONO).next_to(box.get_corner(DL), UR, buff=0.2)
        self.play(FadeIn(label), run_time=0.3)

        y = 0.4
        gate_x = [-5.0, -3.6, -2.2]
        gate_names = ["CORS", "Log", "Auth"]
        gates = VGroup()
        for x, n in zip(gate_x, gate_names):
            bar = Line([x, y + 0.8, 0], [x, y - 0.8, 0], color=SLATE, stroke_width=8)
            nm = T(n, 18, INK, weight=BOLD).next_to(bar, DOWN, buff=0.15)
            gates.add(VGroup(bar, nm))
        proxy = node("ReverseProxy", "ForwardRequest", GOLD, 2.6, 1.0, 20, 13).move_to([0.6, y, 0])
        mlc = node("ML :8000", "/score", TEAL, 2.2, 1.0, 20, 14).move_to([5.6, y, 0])
        mongo = node("MongoDB", "users · reports", SLATE, 2.2, 1.0, 20, 13).move_to([5.6, -2.0, 0])
        google = chip("Google OAuth · tokeninfo", BLUE, 14).move_to([3.4, 2.55, 0])
        to_ml = edge(proxy.get_right(), mlc.get_left(), TEAL)
        to_db = edge(proxy.get_bottom(), mongo.get_left(), SLATE)

        self.play(LaggedStart(*[GrowFromCenter(g) for g in gates], lag_ratio=0.15),
                  FadeIn(proxy), FadeIn(mlc), FadeIn(mongo), FadeIn(google),
                  Create(to_ml), Create(to_db), run_time=1.0)

        dot = Dot([-6.1, y, 0], radius=0.11, color=BLUE)
        lab = T("POST /auth/google", 14, BLUE, font=MONO)
        lab.add_updater(lambda m: m.next_to(dot, UP, buff=1.0, aligned_edge=LEFT))
        self.add(dot, lab)
        auth_pt = np.array([gate_x[2], y, 0])
        self.play(dot.animate.move_to(auth_pt), run_time=0.7, rate_func=linear)
        lab.clear_updaters()
        self.play(FadeOut(lab), run_time=0.2)
        self.travel(dot, [auth_pt, google.get_left()], 0.45)
        self.play(Indicate(google, color=BLUE, scale_factor=1.08), run_time=0.35)
        self.travel(dot, [google.get_left(), auth_pt], 0.45)
        upsert = DashedLine(auth_pt, mongo.get_left(), color=SLATE, dash_length=0.1)
        self.play(Create(upsert), Indicate(mongo, color=INK, scale_factor=1.06), run_time=0.5)
        sess = chip("signed session token", GREEN_OK, 14).next_to(gates[2], DOWN, buff=0.25)
        self.play(gates[2][0].animate.set_color(TEAL), FadeIn(sess, shift=UP * 0.2), FadeOut(upsert),
                  FadeOut(dot), run_time=FAST)
        self.hold(0.8)

        dot = Dot([-6.1, y, 0], radius=0.11, color=GOLD)
        lab = T("POST /api/v1/reports/analyze", 14, GOLD, font=MONO)
        lab.add_updater(lambda m: m.next_to(dot, UP, buff=1.0, aligned_edge=LEFT))
        self.add(dot, lab)
        for g in gates:
            self.play(dot.animate.move_to([g[0].get_x(), y, 0]), run_time=0.35, rate_func=linear)
            self.play(g[0].animate.set_color(TEAL), Flash(dot.get_center(), color=TEAL, line_length=0.2,
                                                          flash_radius=0.25), run_time=0.3)
        lab.clear_updaters()
        self.play(FadeOut(lab), FadeOut(sess), dot.animate.move_to(proxy.get_left()), run_time=0.35,
                  rate_func=linear)
        self.travel(dot, [proxy.get_right(), mlc.get_left()], 0.4)
        self.play(Indicate(mlc, color=TEAL, scale_factor=1.08), run_time=0.4)

        dot.set_color(SEV_ELEV)
        rep = chip("REP-… · score · band · guidance", SEV_ELEV, 14).move_to([0.6, 1.65, 0])
        self.travel(dot, [mlc.get_left(), proxy.get_right()], 0.4)
        ghost = dot.copy()
        self.play(FadeIn(rep, shift=UP * 0.2),
                  MoveAlongPath(ghost, Line(proxy.get_bottom(), mongo.get_left())), run_time=0.6)
        self.play(Indicate(mongo, color=INK, scale_factor=1.08), FadeOut(ghost), run_time=0.4)
        self.hold(1.0)

        cross = Cross(mlc, stroke_color=SEV_HIGH, stroke_width=6)
        self.play(FadeOut(rep), Create(cross), run_time=0.4)
        dot.set_color(GOLD).move_to(proxy.get_right())
        self.travel(dot, [proxy.get_right(), mlc.get_left() + LEFT * 0.4, proxy.get_right()], 0.6)
        fb = chip("fallback guidance → still 200 OK", GREEN_OK, 16).move_to([0.6, 1.65, 0])
        self.play(FadeIn(fb, scale=1.2), run_time=0.35)
        punch = T("Degrades. Never crashes.", 30, INK, weight=BOLD).move_to([-1.3, -2.3, 0])
        self.play(FadeIn(punch, shift=UP * 0.2), run_time=FAST)
        self.hold(1.6)
        self.clear()

    def product(self):
        hdr = self.section("03", "PRODUCT", "What the HSE team uses")

        win = RoundedRectangle(corner_radius=0.18, width=12.6, height=5.2, stroke_color=SLATE,
                               stroke_width=2, fill_color=PANEL, fill_opacity=1).move_to([0, -0.75, 0])
        topbar = Line(win.get_corner(UL) + DOWN * 0.45, win.get_corner(UR) + DOWN * 0.45, color=SLATE,
                      stroke_width=1.5)
        lights = VGroup(*[Dot(radius=0.06, color=c) for c in (SEV_HIGH, SEV_BORD, GREEN_OK)]).arrange(RIGHT, buff=0.1)
        lights.move_to(win.get_corner(UL) + RIGHT * 0.45 + DOWN * 0.23)
        login = chip("✓ signed in with Google", GREEN_OK, 13).move_to(win.get_corner(UR) + LEFT * 1.55 + DOWN * 0.23)

        side_x = win.get_left()[0] + 1.35
        items = ["Overview", "Reports", "SIF Analysis", "HSE Agent"]
        side = VGroup(*[T(s, 17, MUTED) for s in items]).arrange(DOWN, aligned_edge=LEFT, buff=0.32)
        side.move_to([side_x, win.get_top()[1] - 1.55, 0])
        soon = T("soon: precursors · life-saving\nrules · 3D digital twin", 12, SLATE, line_spacing=0.8)
        soon.next_to(side, DOWN, buff=0.45, aligned_edge=LEFT)
        divider = Line([win.get_left()[0] + 2.7, topbar.get_y(), 0], [win.get_left()[0] + 2.7, win.get_bottom()[1], 0],
                       color=SLATE, stroke_width=1.5)
        hl = SurroundingRectangle(side[2], color=GOLD, buff=0.1, corner_radius=0.08)

        self.play(FadeIn(win), Create(topbar), FadeIn(lights), run_time=FAST)
        self.play(FadeIn(side, shift=RIGHT * 0.2), FadeIn(soon), Create(divider), FadeIn(login), run_time=FAST)
        self.play(Create(hl), side[2].animate.set_color(INK), run_time=0.4)

        main_x = 1.4
        csv = chip("incidents.csv", BLUE, 16).move_to([main_x, 3.2, 0])
        self.play(csv.animate.move_to([main_x - 3.0, 1.0, 0]), run_time=0.6, rate_func=rate_functions.ease_out_cubic)
        cols = VGroup(*[chip(f"{c} ✓", TEAL, 13) for c in ("narrative", "site", "activity")]).arrange(RIGHT, buff=0.2)
        cols.next_to(csv, RIGHT, buff=0.4)
        self.play(LaggedStart(*[FadeIn(c, shift=DOWN * 0.15) for c in cols], lag_ratio=0.2), run_time=0.6)

        rows = VGroup()
        bands = [SEV_LOW, SEV_HIGH, SEV_BORD, SEV_LOW, SEV_ELEV, SEV_LOW]
        widths = [4.6, 5.4, 3.8, 5.0, 4.2, 4.8]
        for i, w in enumerate(widths):
            bar = RoundedRectangle(corner_radius=0.05, width=w, height=0.16, stroke_width=0,
                                   fill_color=SLATE, fill_opacity=0.6)
            bar.move_to([main_x - 3.6 + w / 2, 0.35 - i * 0.36, 0])
            rows.add(bar)
        self.play(LaggedStart(*[GrowFromEdge(r, LEFT) for r in rows], lag_ratio=0.08), run_time=0.6)

        track_w = 5.8
        track = RoundedRectangle(corner_radius=0.06, width=track_w, height=0.14, stroke_color=SLATE, stroke_width=1)
        track.move_to([main_x - 0.7, -2.1, 0])
        prog = ValueTracker(0.001)
        fill = always_redraw(lambda: Rectangle(width=track_w * prog.get_value(), height=0.14, stroke_width=0,
                                               fill_color=GOLD, fill_opacity=1).align_to(track, LEFT).set_y(track.get_y()))
        prog_l = T("scoring with /score/batch", 13, MUTED, font=MONO).next_to(track, UP, buff=0.12, aligned_edge=LEFT)
        dots = VGroup(*[Dot(radius=0.09, color=c).move_to([main_x + 2.9, r.get_y(), 0]) for r, c in zip(rows, bands)])
        self.add(track, fill)
        self.play(FadeIn(prog_l), run_time=0.2)
        self.play(prog.animate.set_value(1), LaggedStart(*[FadeIn(d, scale=2) for d in dots], lag_ratio=0.3),
                  run_time=1.6, rate_func=linear)

        export = chip("Export Scored CSV", GOLD, 15, mono=False).move_to([main_x + 3.5, -2.1, 0])
        self.play(FadeIn(export, scale=1.2), run_time=0.4)
        self.play(Indicate(export, color=GOLD), run_time=0.5)

        hl2 = SurroundingRectangle(side[3], color=VIOLET, buff=0.1, corner_radius=0.08)
        to_agent = chip("rows → agent session memory", VIOLET, 13).move_to([main_x, -2.75, 0])
        self.play(ReplacementTransform(hl, hl2), side[2].animate.set_color(MUTED), side[3].animate.set_color(INK),
                  FadeIn(to_agent, shift=LEFT * 0.2), run_time=0.6)
        self.hold(1.4)
        self.clear()

    def scoring(self):
        hdr = self.section("04", "ML SERVICE", "Inside POST /score")

        norm = chip("normalise · Hinglish → English", BLUE, 12).move_to([-5.3, 1.75, 0])
        words = ["valve", "not", "tagged", "out", "residual", "pressure"]
        tokens = VGroup(*[chip(w, BLUE, 15) for w in words]).arrange(DOWN, buff=0.12).move_to([-5.6, -0.45, 0])

        enc = RoundedRectangle(corner_radius=0.15, width=2.4, height=3.3, stroke_color=GOLD, stroke_width=3,
                               fill_color=PANEL, fill_opacity=1).move_to([-2.4, -0.3, 0])
        layers = VGroup(*[RoundedRectangle(corner_radius=0.05, width=1.8, height=0.28, stroke_width=0,
                                           fill_color=GOLD, fill_opacity=0.18 + 0.1 * i) for i in range(6)])
        layers.arrange(UP, buff=0.12).move_to(enc)
        enc_l = T("DeBERTa-v3", 20, INK, weight=BOLD).next_to(enc, UP, buff=0.12)
        enc_s = T("ONNX · 46 ms on CPU", 13, GOLD, font=MONO).next_to(enc, DOWN, buff=0.12)

        ax = Axes(x_range=[0, 1, 1], y_range=[0, 1, 1], x_length=2.2, y_length=2.0, tips=False,
                  axis_config={"color": SLATE, "include_ticks": False}).move_to([1.2, -0.3, 0])
        curve = ax.plot(lambda x: 1 / (1 + np.exp(-9 * (x - 0.5))), x_range=[0, 1], color=VIOLET, stroke_width=4)
        ax_l = T("Platt calibration", 15, VIOLET, font=MONO).next_to(ax, UP, buff=0.12)

        mx, y0, y1 = 4.4, -1.9, 1.5
        thr = 0.42
        segs_def = [(0, thr - 0.17, SEV_LOW, "LOW"), (thr - 0.17, thr, SEV_BORD, "BORDERLINE"),
                    (thr, thr + 0.17, SEV_ELEV, "ELEVATED"), (thr + 0.17, 1, SEV_HIGH, "HIGH")]

        def my(v):
            return y0 + v * (y1 - y0)

        meter = VGroup()
        for a, b, c, n in segs_def:
            meter.add(VGroup(Line([mx, my(a), 0], [mx, my(b), 0], color=c, stroke_width=16),
                             T(n, 14, c, weight=BOLD).move_to([mx + 0.35, my((a + b) / 2), 0], aligned_edge=LEFT)))
        thr_line = DashedLine([mx - 0.35, my(thr), 0], [mx + 0.25, my(thr), 0], color=INK)

        a1 = edge(tokens.get_right(), enc.get_left(), BLUE)
        a2 = edge(enc.get_right(), ax.get_left(), GOLD)
        a3 = edge(ax.get_right(), [mx - 0.6, ax.get_y(), 0], VIOLET)

        self.play(FadeIn(norm, shift=DOWN * 0.2), run_time=0.4)
        self.play(LaggedStart(*[FadeIn(t, shift=RIGHT * 0.3) for t in tokens], lag_ratio=0.08), run_time=0.7)
        self.play(GrowArrow(a1), FadeIn(enc), FadeIn(enc_l), FadeIn(enc_s), run_time=FAST)
        self.play(*[t.animate.scale(0.4).move_to(enc.get_center()).set_opacity(0) for t in tokens],
                  LaggedStart(*[l.animate.set_fill(GOLD, 0.9) for l in layers], lag_ratio=0.12),
                  run_time=1.0)
        self.play(GrowArrow(a2), Create(ax), FadeIn(ax_l), run_time=FAST)
        self.play(Create(curve), run_time=0.6)
        self.play(GrowArrow(a3), LaggedStart(*[FadeIn(m) for m in meter], lag_ratio=0.1),
                  Create(thr_line), run_time=0.7)

        p = ValueTracker(0.0)
        pointer = always_redraw(lambda: Triangle(fill_opacity=1, stroke_width=0).set_fill(INK)
                                .scale(0.13).rotate(-PI / 2).move_to([mx - 0.32, my(p.get_value()), 0]))
        self.add(pointer)
        self.play(p.animate.set_value(0.52), run_time=1.0, rate_func=rush_from)
        self.play(Indicate(meter[2], color=SEV_ELEV, scale_factor=1.1), run_time=0.45)

        side = VGroup(chip("IOGP Life-Saving Rules matched", TEAL, 14),
                      chip("audit line · text hashed", SLATE, 14),
                      chip("site_id → site history", VIOLET, 14)).arrange(RIGHT, buff=0.3)
        side.to_edge(DOWN, buff=0.35)
        self.play(LaggedStart(*[FadeIn(s, shift=UP * 0.2) for s in side], lag_ratio=0.15), run_time=0.7)
        four = T("4 bands, not yes/no", 22, INK, weight=BOLD).next_to(hdr, RIGHT, buff=0.8).align_to(hdr[1], DOWN)
        self.play(FadeIn(four), run_time=FAST)
        self.hold(1.6)
        self.clear()

    def api_ops(self):
        hdr = self.section("05", "ML API", "Built to be operated")

        core = node("api/main.py", "FastAPI", TEAL, 2.6, 1.2, 22, 15).move_to([-0.5, -0.5, 0])
        eps = VGroup(*[chip(s, TEAL, 14) for s in [
            "POST /score", "POST /score/batch  top_frac", "GET  /sites", "GET  /sites/{id}",
            "GET  /dashboard", "GET  /health"]]).arrange(DOWN, buff=0.18, aligned_edge=LEFT)
        eps.move_to([-4.8, -0.5, 0])
        ops = VGroup(*[chip(s, GOLD, 14) for s in [
            "API keys  SIF_API_KEYS", "rate limit 60/min → 429", "audit log · text hashed",
            "X-Request-ID", "model_fingerprint"]]).arrange(DOWN, buff=0.22, aligned_edge=LEFT)
        ops.move_to([3.4, -0.5, 0])
        e_in = VGroup(*[edge(e.get_right(), core.get_left(), TEAL, sw=1.5, buff=0.05) for e in eps])
        e_out = VGroup(*[edge(core.get_right(), o.get_left(), GOLD, sw=1.5, buff=0.05, tip=False) for o in ops])

        self.play(GrowFromCenter(core), run_time=FAST)
        self.play(LaggedStart(*[FadeIn(e, shift=RIGHT * 0.2) for e in eps], lag_ratio=0.1),
                  LaggedStart(*[Create(a) for a in e_in], lag_ratio=0.1), run_time=1.0)
        self.play(LaggedStart(*[FadeIn(o, shift=LEFT * 0.2) for o in ops], lag_ratio=0.1),
                  LaggedStart(*[Create(a) for a in e_out], lag_ratio=0.1), run_time=1.0)

        lim = ops[1]
        start = np.array([6.4, lim.get_y(), 0])
        burst = VGroup(*[Dot(start + UP * (0.12 * (i - 2)), radius=0.07, color=INK) for i in range(5)])
        self.add(burst)
        self.play(LaggedStart(*[d.animate.move_to(lim.get_right()) for d in burst], lag_ratio=0.15), run_time=0.7)
        self.play(*[d.animate.set_color(GREEN_OK).move_to(core.get_right()) for d in burst[:3]],
                  *[d.animate.set_color(SEV_HIGH).move_to(start + UP * 0.3 * (i - 0.5)) for i, d in enumerate(burst[3:])],
                  run_time=0.6)
        r429 = T("429  Retry-After", 14, SEV_HIGH, font=MONO).move_to([6.0, lim.get_y() - 0.75, 0])
        self.play(FadeIn(r429), FadeOut(burst[:3]), run_time=0.35)
        self.hold(1.4)
        self.clear()

    def training(self):
        hdr = self.section("06", "TRAINING", "One model, four stages")

        stages = [
            ("billions", "words", "pretrained by Microsoft", SLATE, 9.0),
            ("590K", "narratives", "MLM: learns the vocabulary", BLUE, 7.0),
            ("73K", "PHMSA rows", "STILT: learns severity", VIOLET, 5.0),
            ("231", "SIF rows", "fine-tune: learns SIF", GOLD, 3.0),
        ]
        bars = VGroup()
        for big, unit, what, c, w in stages:
            r = RoundedRectangle(corner_radius=0.12, width=w, height=0.85, stroke_color=c, stroke_width=2.5,
                                 fill_color=c, fill_opacity=0.18)
            n = T(big, 34, c, weight=BOLD)
            u = T(unit, 15, INK)
            g = VGroup(n, u).arrange(RIGHT, buff=0.15, aligned_edge=DOWN).move_to(r)
            bars.add(VGroup(r, g, T(what, 15, MUTED)))
        stack = VGroup(*[b[:2] for b in bars]).arrange(DOWN, buff=0.14, aligned_edge=LEFT)
        stack.move_to([0, 0.05, 0]).set_x(-6.3, LEFT)
        for b in bars:
            b[2].next_to(b[0], RIGHT, buff=0.3)
        for b in bars:
            self.play(FadeIn(b[0], scale=0.9), FadeIn(b[1], scale=1.3), FadeIn(b[2], shift=LEFT * 0.2),
                      run_time=0.5)
        self.hold(0.6)

        out = VGroup(chip("ONNX export · fidelity-gated", TEAL, 16),
                     chip("GitHub Release · 531 MB", TEAL, 16),
                     chip("ml.fetch_model · checksum", TEAL, 16)).arrange(RIGHT, buff=0.5)
        out.to_edge(DOWN, buff=0.35)
        arrows = VGroup(*[edge(out[i].get_right(), out[i + 1].get_left(), TEAL) for i in range(2)])
        down = edge(bars[3][0].get_bottom(), out[0].get_top(), TEAL)
        self.play(GrowArrow(down), LaggedStart(*[FadeIn(o, shift=UP * 0.2) for o in out], lag_ratio=0.2),
                  LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.2), run_time=1.0)
        self.hold(1.4)
        self.clear()

    def site_risk(self):
        hdr = self.section("07", "SITE RISK", "Dull reports compound")
        sub = T("decay · cluster · recurrence · noisy-OR", 16, MUTED, font=MONO)
        sub.next_to(hdr, DOWN, buff=0.15, aligned_edge=LEFT)
        self.play(FadeIn(sub), run_time=0.3)

        base_y, scale = -2.6, 3.6

        def y(v):
            return base_y + v * scale

        axis = Line([-6, base_y, 0], [6, base_y, 0], color=SLATE, stroke_width=2)
        thr = DashedLine([-6, y(0.5), 0], [6, y(0.5), 0], color=SEV_HIGH, dash_length=0.12)
        thr_l = T("review line 0.50", 15, SEV_HIGH, font=MONO).next_to(thr, UP, buff=0.06).to_edge(LEFT, buff=0.5)

        names = ["Working at height", "Work permit", "Hot work"]
        xs = [-3.6, -2.0, -0.4]
        bars = VGroup()
        labels = VGroup()
        for n, x in zip(names, xs):
            b = Rectangle(width=1.1, height=0.35 * scale, stroke_width=0, fill_color=SEV_BORD,
                          fill_opacity=0.9).move_to([x, y(0.175), 0])
            bars.add(b)
            labels.add(T(n, 13, MUTED).next_to(b, DOWN, buff=0.12))
        vals = VGroup(*[T("0.35", 15, INK, font=MONO).next_to(b, UP, buff=0.08) for b in bars])

        self.play(Create(axis), Create(thr), FadeIn(thr_l), run_time=FAST)
        self.play(LaggedStart(*[GrowFromEdge(b, DOWN) for b in bars], lag_ratio=0.15),
                  FadeIn(labels), FadeIn(vals), run_time=0.8)
        self.hold(0.8)

        site = Rectangle(width=1.6, height=0.725 * scale, stroke_width=0, fill_color=SEV_HIGH,
                         fill_opacity=0.95).move_to([3.0, y(0.725 / 2), 0])
        formula = T("1 − (1 − 0.35)³ = 0.725", 22, GOLD, font=MONO).next_to(site, UP, buff=0.2)
        merged = bars.copy()
        self.play(Transform(merged, site), run_time=0.9, rate_func=smooth)
        self.play(FadeIn(formula, shift=DOWN * 0.2), run_time=0.4)
        flag = chip("COMPOUNDING", SEV_HIGH, 20, mono=False).next_to(site, RIGHT, buff=0.3).set_y(y(0.25))
        self.play(FadeIn(flag, scale=1.4), Flash(site.get_top(), color=SEV_HIGH, flash_radius=0.5), run_time=0.45)
        q = T("GET /sites ranks places, not reports", 15, MUTED, font=MONO).move_to([3.0, -3.35, 0])
        self.play(FadeIn(q), run_time=0.4)
        self.hold(1.5)
        self.clear()

    def agent(self):
        hdr = self.section("08", "HSE AGENT", "Route, retrieve, answer")

        q = chip("“LOTO failures on compressor C-204?”", BLUE, 15, mono=False).move_to([-4.6, 1.2, 0])
        router = VGroup(Square(1.0, color=GOLD, fill_color=PANEL, fill_opacity=1).rotate(PI / 4),
                        T("intent", 15, GOLD, font=MONO)).move_to([-4.6, -0.8, 0])
        tools = VGroup(*[chip(n, SLATE, 14) for n in
                         ["search_safety_reports", "get_asset_risk", "get_risk_summary", "get_uploaded_reports"]])
        tools.arrange(DOWN, buff=0.22, aligned_edge=LEFT).move_to([-0.6, -0.4, 0])

        cascade_names = [("Gemini 2.5 Flash", VIOLET), ("Groq Llama-3.3-70B", VIOLET),
                         ("OpenAI", VIOLET), ("built-in HSE knowledge", SLATE)]
        cascade = VGroup(*[chip(n, c, 17, mono=False) for n, c in cascade_names])
        cascade.arrange(DOWN, buff=0.32).move_to([4.6, -0.2, 0])
        fails = VGroup(*[T("fails ↓", 13, MUTED, font=MONO)
                         .move_to((cascade[i].get_bottom() + cascade[i + 1].get_top()) / 2 + RIGHT * 1.4)
                         for i in range(3)])
        llm_l = T("LLM fallback chain", 15, VIOLET, font=MONO).next_to(cascade, UP, buff=0.2)

        self.play(FadeIn(q, shift=RIGHT * 0.3), run_time=FAST)
        self.play(GrowArrow(edge(q.get_bottom(), router.get_top(), BLUE)), FadeIn(router), run_time=0.45)
        fan = VGroup(*[edge(router.get_right(), t.get_left(), SLATE, sw=2) for t in tools])
        self.play(LaggedStart(*[Create(f) for f in fan], lag_ratio=0.1),
                  LaggedStart(*[FadeIn(t, shift=RIGHT * 0.2) for t in tools], lag_ratio=0.1), run_time=0.8)
        hit = [0, 1]
        self.play(*[tools[i][0].animate.set_stroke(TEAL, width=3) for i in hit],
                  *[tools[i][1].animate.set_color(TEAL) for i in hit],
                  *[fan[i].animate.set_color(TEAL) for i in hit], run_time=0.45)
        self.hold(0.5)

        ctx = edge(tools.get_right(), cascade[0].get_left(), TEAL)
        self.play(GrowArrow(ctx), FadeIn(llm_l),
                  LaggedStart(*[FadeIn(c, shift=DOWN * 0.15) for c in cascade], lag_ratio=0.12),
                  FadeIn(fails), run_time=0.9)
        self.play(cascade[0][0].animate.set_fill(VIOLET, 0.35), Indicate(cascade[0], color=VIOLET), run_time=0.5)

        ans = chip("answer cites report IDs + IOGP rules", GOLD, 16, mono=False).to_edge(DOWN, buff=0.35).set_x(2.0)
        keys = T("API keys stay server-side", 13, MUTED, font=MONO).next_to(ans, LEFT, buff=0.6)
        self.play(FadeIn(ans, shift=UP * 0.2), FadeIn(keys), run_time=FAST)
        self.hold(1.6)
        self.clear()

    def ci(self):
        hdr = self.section("09", "CI", "Every push, proven")

        stages = [
            ("Unit tests", "pytest", BLUE),
            ("Docker build", "torch-free image", GOLD),
            ("Container serves", "/score /sites /dashboard", TEAL),
            ("Integration", "selftest · 16 checks", VIOLET),
        ]
        nodes = VGroup(*[node(t, s, c, 2.9, 1.2, 20, 13) for t, s, c in stages]).arrange(RIGHT, buff=0.45)
        nodes.move_to([0, 0.1, 0])
        arrows = VGroup(*[edge(nodes[i].get_right(), nodes[i + 1].get_left(), SLATE, buff=0.04) for i in range(3)])
        ticks = VGroup(*[tick().next_to(n, UP, buff=0.15) for n in nodes])

        self.play(LaggedStart(*[FadeIn(n, shift=UP * 0.2) for n in nodes], lag_ratio=0.15),
                  LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.15), run_time=1.0)
        for n, t in zip(nodes, ticks):
            self.play(n[0].animate.set_stroke(GREEN_OK), FadeIn(t, scale=1.6), run_time=0.3)
        why = T("9 defects found the hard way — each now has a regression check", 18, MUTED)
        why.move_to(DOWN * 1.8)
        self.play(FadeIn(why, shift=UP * 0.2), run_time=FAST)
        self.hold(1.4)
        self.clear()

    def numbers(self):
        hdr = self.section("10", "RESULTS", "Measured on 123 held-out reports")

        specs = [("PR-AUC", 0.6667, "{:.3f}", GOLD), ("ROC-AUC", 0.7570, "{:.3f}", GOLD),
                 ("P@10", 0.80, "{:.2f}", GOLD), ("ms / report", 46, "{:.0f}", TEAL)]
        xs = [-4.8, -1.6, 1.6, 4.8]
        trackers = []
        labs = VGroup()
        for (name, val, fmt, c), x in zip(specs, xs):
            v = ValueTracker(0)
            trackers.append((v, val))
            num = always_redraw(lambda v=v, fmt=fmt, c=c, x=x: T(fmt.format(v.get_value()), 60, c, weight=BOLD)
                                .move_to([x, 0.3, 0]))
            labs.add(T(name, 20, INK).move_to([x, -0.6, 0]))
            self.add(num)
        self.play(FadeIn(labs), *[v.animate.set_value(t) for v, t in trackers], run_time=1.2, rate_func=rush_from)

        note = T("base rate 0.407  ·  1.97× lift in the top 10  ·  CPU only, no GPU", 18, MUTED,
                 font=MONO).move_to(DOWN * 1.9)
        honest = T("The ranking transfers to oil & gas; a fixed threshold does not — so it ranks.",
                   19, INK).next_to(note, DOWN, buff=0.35)
        self.play(FadeIn(note, shift=UP * 0.2), run_time=FAST)
        self.play(FadeIn(honest, shift=UP * 0.2), run_time=FAST)
        self.hold(2.2)
        self.clear()

    def outro(self):
        chain = VGroup(*[chip(s, c, 18, mono=False) for s, c in
                         [("report", BLUE), ("score", GOLD), ("band", SEV_ELEV),
                          ("site risk", SEV_HIGH), ("agent", VIOLET)]]).arrange(RIGHT, buff=0.45)
        chain.move_to(UP * 1.6)
        arrows = VGroup(*[edge(chain[i].get_right(), chain[i + 1].get_left(), GOLD, buff=0.05)
                          for i in range(4)])
        self.play(LaggedStart(*[FadeIn(c, scale=1.2) for c in chain], lag_ratio=0.12),
                  LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.12), run_time=1.0)

        logo = T("BARRIER X", 96, GOLD, weight=BOLD).move_to(DOWN * 0.2)
        sub = T("GIT PUSH AND PRAY  ·  SIH 2026  ·  PS 26165", 20, MUTED, font=MONO).next_to(logo, DOWN, buff=0.3)
        self.play(FadeIn(logo, scale=0.85), run_time=0.6)
        self.play(FadeIn(sub, shift=UP * 0.2), run_time=FAST)
        self.hold(2.2)
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.9)
