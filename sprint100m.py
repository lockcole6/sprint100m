# 100m SPRINT II (simple)
#
#   ONE BUTTON. Press Z (or tap anywhere) when the cursor is in the zone.
#
#   * Gun fires -> react fast: quicker reaction = stronger launch
#     (under 0.100s is an anticipation foul, just like real athletics)
#   * Then ride the rhythm: PERFECT / GOOD / EARLY judgement per sweep
#   * 3 CPU rivals, slow-motion photo finish, best time & wins saved

import json
import math
import os

import pyxel

FPS = 60
W, H = 256, 160
PPM = 8                 # pixels per meter
PLAYER_SX = 64          # player fixed screen X

TRACK_TOP = 58
LANE_H = 13
NUM_LANES = 4
TRACK_BOT = TRACK_TOP + LANE_H * NUM_LANES   # 110

# --- stride (rhythm) bar -----------------------------------------------
BAR_W, BAR_H = 140, 10
BAR_X, BAR_Y = (W - BAR_W) // 2, H - 18
GOOD_A, GOOD_B = 0.55, 1.0       # good window (cursor 0..1)
PERF_A, PERF_B = 0.72, 0.95      # perfect window (widened)
MARV_A, MARV_B = 0.795, 0.875    # marvelous: small sweet spot in the center

# --- physics -----------------------------------------------------------
BASE_MAX_SPEED = 11.4   # m/s
BASE_BOOST = 1.55       # m/s per perfect stride
GOOD_MUL = 0.92
MARV_MUL = 1.25         # marvelous boost multiplier
MARV_OVERCAP = 0.7      # marvelous may push past the normal speed cap
DECEL = 0.9935          # per-frame speed multiplier

SAVE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sprint_save.json"
)

CPU_DEFS = (
    dict(name="TSUBAME", shirt=12, top=10.65, ramp=3.2,
         fade_from=62.0, fade=0.10, spurt_from=999.0, spurt=0.0,
         react=(0.12, 0.17)),
    dict(name="YAMA", shirt=11, top=10.4, ramp=4.2,
         fade_from=999.0, fade=0.0, spurt_from=999.0, spurt=0.0,
         react=(0.14, 0.20)),
    dict(name="KAZE", shirt=10, top=10.5, ramp=5.0,
         fade_from=999.0, fade=0.0, spurt_from=66.0, spurt=1.0,
         react=(0.15, 0.24)),
)

DEFAULT_SAVE = {"best": None, "wins": 0, "races": 0}


# ======================================================================
class Runner:
    def __init__(self, name, shirt, lane, is_player=False, cfg=None):
        self.name = name
        self.shirt = shirt
        self.lane = lane
        self.is_player = is_player
        self.cfg = cfg
        self.reset()

    def reset(self):
        self.dist = -1.2
        self.speed = 0.0
        self.anim = 0.0
        self.finished = False
        self.time = None
        self.t_run = 0.0
        if self.cfg:
            self.top = self.cfg["top"] + pyxel.rndf(-0.25, 0.25)
            self.react = pyxel.rndf(*self.cfg["react"])

    def foot_y(self):
        return TRACK_TOP + (self.lane + 1) * LANE_H - 2


# ======================================================================
class Sprint:
    def __init__(self):
        pyxel.init(W, H, title="100m SPRINT II", fps=FPS)
        pyxel.mouse(True)
        self._setup_sounds()
        self.data = self._load_save()
        self.crowd = [
            (pyxel.rndi(0, 900), pyxel.rndi(TRACK_TOP - 24, TRACK_TOP - 8),
             pyxel.rndi(2, 15))
            for _ in range(230)
        ]
        self.player = Runner("YOU", 8, 3, is_player=True)
        self.cpus = [
            Runner(c["name"], c["shirt"], i, cfg=c)
            for i, c in enumerate(CPU_DEFS)
        ]
        self.runners = self.cpus + [self.player]
        self._to_title()
        pyxel.run(self.update, self.draw)

    # ------------------------------------------------------------ sounds
    def _setup_sounds(self):
        pyxel.sounds[0].set("c2", "t", "5", "n", 30)          # on your marks
        pyxel.sounds[1].set("g2", "t", "6", "n", 25)          # set
        pyxel.sounds[2].set("a3", "n", "7", "f", 4)           # gun
        pyxel.sounds[3].set("c1c1c1c1", "n", "7654", "n", 8)  # false start
        pyxel.sounds[4].set("c3e3", "t", "64", "n", 6)        # perfect
        pyxel.sounds[5].set("c3", "t", "4", "n", 6)           # good
        pyxel.sounds[6].set("f1", "n", "5", "f", 8)           # early miss
        pyxel.sounds[7].set("c4", "t", "2", "n", 4)           # metronome tick
        pyxel.sounds[8].set("c3e3g3c4", "t", "6666", "n", 10) # finish fanfare

    # ------------------------------------------------------------ save io
    def _load_save(self):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            out = dict(DEFAULT_SAVE)
            out.update({k: d[k] for k in d if k in out})
            return out
        except Exception:
            return dict(DEFAULT_SAVE)

    def _write_save(self):
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except Exception:
            pass  # e.g. web build: no filesystem

    # ------------------------------------------------------------ states
    def _to_title(self):
        self.state = "TITLE"
        self._reset_race()

    def _reset_race(self):
        for r in self.runners:
            r.reset()
        self.race_t = 0.0
        self.cursor = 0.0
        self.stride_done = False
        self.start_pending = False
        self.combo = 0
        self.max_combo = 0
        self.n_marv = 0
        self.n_perfect = 0
        self.n_good = 0
        self.n_early = 0
        self.press_marks = []  # [cursor_pos, col, life]
        self.reaction = None
        self.finish_place = None
        self.winner = None
        self.new_best = False
        self.foul_reason = ""
        self.foul_armed = True
        self.timer = 0
        self.gun_timer = 0
        self.shake = 0
        self.flash = 0
        self.bar_flash = 0
        self.popups = []     # [x, y, text, col, life]
        self.particles = []  # [x, y, vx, vy, life, col]  (world coords)

    # ------------------------------------------------------------ input
    def _read_stride(self):
        """One-shot press: Z / SPACE / tap anywhere."""
        return (pyxel.btnp(pyxel.KEY_Z) or pyxel.btnp(pyxel.KEY_SPACE)
                or pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT))

    def _any_held(self):
        return (pyxel.btn(pyxel.KEY_Z) or pyxel.btn(pyxel.KEY_SPACE)
                or pyxel.btn(pyxel.MOUSE_BUTTON_LEFT))

    # ------------------------------------------------------------ update
    def update(self):
        s = self.state
        stride = self._read_stride()

        if s == "TITLE":
            self._update_title()
        elif s == "MARKS":
            self._update_marks()
        elif s == "SET":
            self._update_set()
        elif s == "RUN":
            self._update_run(stride)
        elif s == "FALSE_START":
            self.timer -= 1
            if self.timer <= 0:
                self._to_title()
        elif s == "FINISH":
            self._update_finish(stride)

        # popups / particles tick everywhere
        for p in self.popups:
            p[1] -= 0.35
            p[4] -= 1
        self.popups = [p for p in self.popups if p[4] > 0]
        for pt in self.particles:
            pt[0] += pt[2]
            pt[1] += pt[3]
            pt[3] += 0.03
            pt[4] -= 1
        self.particles = [pt for pt in self.particles if pt[4] > 0]
        if self.shake > 0:
            self.shake -= 1
        if self.flash > 0:
            self.flash -= 1
        if self.bar_flash > 0:
            self.bar_flash -= 1
        for m in self.press_marks:
            m[2] -= 1
        self.press_marks = [m for m in self.press_marks if m[2] > 0]

    # --- title
    def _update_title(self):
        start = (pyxel.btnp(pyxel.KEY_Z) or pyxel.btnp(pyxel.KEY_SPACE)
                 or pyxel.btnp(pyxel.KEY_RETURN))
        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            cx = W // 2
            mx, my = pyxel.mouse_x, pyxel.mouse_y
            if cx - 44 <= mx <= cx + 44 and 102 <= my <= 122:
                start = True  # START button
        if start:
            self._reset_race()
            self.state = "MARKS"
            self.foul_armed = not self._any_held()
            self.timer = FPS * 2
            pyxel.play(0, 0)

    def _update_marks(self):
        held = self._any_held()
        if held and self.foul_armed:
            return self._false_start()
        if not held:
            self.foul_armed = True
        self.timer -= 1
        if self.timer <= 0:
            self.state = "SET"
            self.gun_timer = pyxel.rndi(FPS // 2, FPS * 3)
            pyxel.play(0, 1)

    def _update_set(self):
        if self._any_held():
            return self._false_start()
        self.foul_armed = True
        self.gun_timer -= 1
        if self.gun_timer <= 0:
            self.state = "RUN"
            self.start_pending = True
            self.flash = 5
            self.shake = 8
            self.bar_flash = 24
            self._popup("GO!!", 10)
            pyxel.play(0, 2)

    def _false_start(self):
        if not self.foul_reason:
            self.foul_reason = "pressed before the gun"
        self.state = "FALSE_START"
        self.timer = FPS * 3
        pyxel.play(0, 3)

    # --- main race
    def _update_run(self, stride):
        p = self.player
        ts = 1.0
        self.race_t += ts / FPS

        self._update_player(p, ts, stride)
        for c in self.cpus:
            self._update_cpu(c, ts)

        if p.dist >= 100.0 and not p.finished:
            p.finished = True
            p.time = self.race_t - (p.dist - 100.0) / max(p.speed, 0.1)
            if self.winner is None or p.time < self.winner.time:
                self.winner = p
            self._on_player_finish()

    def _update_player(self, p, ts, stride):
        if self.start_pending:
            if not stride:
                return  # still in the blocks, waiting on the gun reaction
            self.reaction = self.race_t
            if self.reaction < 0.10:
                # real athletics rule: reacting under 0.100s = anticipation
                self.foul_reason = f"reaction {self.reaction:.3f}s < 0.100s"
                return self._false_start()
            # faster reaction -> more explosive launch out of the blocks
            launch = min(4.5, max(1.2, 5.2 - self.reaction * 8.0))
            p.speed += launch
            if self.reaction < 0.16:
                self._popup("LIGHTNING!!", 10)
            elif self.reaction < 0.25:
                self._popup("GREAT START", 11)
            elif self.reaction < 0.38:
                self._popup("GOOD START", 7)
            else:
                self._popup("SLOW START", 6)
            pyxel.play(2, 4)
            fy = p.foot_y()
            for _ in range(4):
                self.particles.append(
                    [p.dist * PPM - 4, fy,
                     pyxel.rndf(-2.0, -0.8), pyxel.rndf(-1.4, -0.3), 22, 15])
            self.start_pending = False
            self.cursor = 0.0
            self.stride_done = False
            stride = False  # launch press consumed; rhythm starts next sweep

        # rhythm cursor: cadence rises with speed, one stride per sweep
        period = max(19.0, 36.0 - p.speed * 1.5)
        self.cursor += ts / period
        if self.cursor >= 1.0:
            self.cursor -= 1.0
            self.stride_done = False
            pyxel.play(1, 7)

        if stride and self.stride_done:
            # mashing inside the same sweep breaks your form
            p.speed *= 0.96
            self._popup("TOO FAST!", 8)
            pyxel.play(2, 6)
        elif stride:
            self.stride_done = True
            t = self.cursor
            # drive phase: extra power out of the blocks
            drive = 1.0 + max(0.0, 7.0 - p.speed) * 0.14
            fy = p.foot_y()
            if t < GOOD_A:
                p.speed *= 0.93
                self.combo = 0
                self.n_early += 1
                self.press_marks.append([t, 8, 50])
                self._popup("EARLY!", 8)
                pyxel.play(2, 6)
            elif MARV_A <= t <= MARV_B:
                # dead-center hit: extra power, may exceed the normal cap
                p.speed += BASE_BOOST * drive * MARV_MUL
                p.speed = min(p.speed, BASE_MAX_SPEED + MARV_OVERCAP)
                self.combo += 1
                self.max_combo = max(self.max_combo, self.combo)
                self.n_marv += 1
                self.press_marks.append([t, 14, 50])
                self._popup("MARVELOUS!", 14)
                pyxel.play(2, 4)
                for _ in range(5):
                    self.particles.append(
                        [p.dist * PPM - 4, fy - pyxel.rndi(0, 8),
                         pyxel.rndf(-2.2, -0.8), pyxel.rndf(-1.6, -0.3),
                         26, 14])
            elif PERF_A <= t <= PERF_B:
                p.speed += BASE_BOOST * drive
                p.speed = min(p.speed, BASE_MAX_SPEED)
                self.combo += 1
                self.max_combo = max(self.max_combo, self.combo)
                self.n_perfect += 1
                self.press_marks.append([t, 10, 50])
                self._popup("PERFECT", 10)
                pyxel.play(2, 4)
                for _ in range(3):
                    self.particles.append(
                        [p.dist * PPM - 4, fy,
                         pyxel.rndf(-1.8, -0.6), pyxel.rndf(-1.2, -0.3),
                         22, 15])
            else:
                p.speed += BASE_BOOST * drive * GOOD_MUL
                p.speed = min(p.speed, BASE_MAX_SPEED)
                self.combo = 0
                self.n_good += 1
                self.press_marks.append([t, 11, 50])
                self._popup("GOOD", 11)
                pyxel.play(2, 5)

        p.speed = min(p.speed, BASE_MAX_SPEED + MARV_OVERCAP)
        p.speed *= DECEL ** ts
        p.dist += p.speed * ts / FPS
        p.anim += p.speed * 0.019 * ts

    def _update_cpu(self, c, ts):
        if c.finished:
            c.speed *= 0.98 ** ts
            c.dist += c.speed * ts / FPS
            c.anim += c.speed * 0.019 * ts
            return
        if self.race_t < c.react:
            return
        c.t_run += ts / FPS
        cfg = c.cfg
        d = max(c.dist, 0.0)
        tgt = c.top * min(1.0, 0.25 + 0.75 * c.t_run / cfg["ramp"])
        if d > cfg["fade_from"]:
            tgt *= max(0.75, 1.0 - cfg["fade"] * (d - cfg["fade_from"]) / 40.0)
        if d > cfg["spurt_from"]:
            tgt += cfg["spurt"]
        tgt += pyxel.rndf(-0.12, 0.12)
        c.speed += (tgt - c.speed) * 0.045 * ts
        c.speed = max(0.0, c.speed)
        c.dist += c.speed * ts / FPS
        c.anim += c.speed * 0.019 * ts
        if c.dist >= 100.0:
            c.finished = True
            c.time = self.race_t - (c.dist - 100.0) / max(c.speed, 0.1)
            if self.winner is None or c.time < self.winner.time:
                self.winner = c

    def _on_player_finish(self):
        self.flash = 6
        self.shake = 7
        pyxel.play(0, 8)
        p = self.player
        # rank by interpolated crossing time so same-frame photo finishes
        # match what the result table (sorted by time) shows
        self.finish_place = 1 + sum(
            1 for c in self.cpus
            if c.finished and c.time is not None and c.time < p.time)
        self.new_best = self.data["best"] is None or p.time < self.data["best"]
        if self.new_best:
            self.data["best"] = p.time
        self.data["races"] += 1
        if self.finish_place == 1:
            self.data["wins"] += 1
        self._write_save()
        self.state = "FINISH"
        self.timer = FPS * 9

    def _update_finish(self, stride):
        # keep the clock running so late finishers get correct times
        self.race_t += 1.0 / FPS
        # let the rest of the field run through the line
        for c in self.cpus:
            self._update_cpu(c, 1.0)
        p = self.player
        p.speed *= 0.965
        p.dist += p.speed / FPS
        p.anim += p.speed * 0.019
        self.timer -= 1
        can_skip = self.timer <= FPS * 7
        if self.timer <= 0 or (can_skip and (stride
                                             or pyxel.btnp(pyxel.KEY_RETURN))):
            self._to_title()

    def _popup(self, text, col):
        p = self.player
        self.popups.append(
            [PLAYER_SX - len(text) * 2, p.foot_y() - 30, text, col, 36])

    # ================================================================ draw
    def draw(self):
        p = self.player
        ox = pyxel.rndi(-2, 2) if self.shake > 0 else 0
        oy = pyxel.rndi(-1, 1) if self.shake > 0 else 0
        cam = p.dist * PPM - PLAYER_SX + ox

        pyxel.cls(12)
        pyxel.circ(214, 18, 7, 10)                      # sun
        self._draw_clouds(cam)
        self._draw_stands(cam, oy)
        self._draw_track(cam, oy)
        self._draw_particles(cam, oy)

        for r in self.runners:                          # back lanes first
            self._draw_athlete(r, cam, oy)

        if p.speed > 9.3 and self.state in ("RUN", "FINISH"):
            for _ in range(3):
                y = pyxel.rndi(TRACK_TOP - 6, TRACK_BOT)
                x = pyxel.rndi(0, W - 24)
                pyxel.line(x, y, x + pyxel.rndi(10, 22), y, 7)

        for x, y, text, col, _ in self.popups:
            pyxel.text(int(x), int(y), text, col)

        self._draw_hud()
        self._draw_overlay()

        if self.flash > 0:
            pyxel.rect(0, 0, W, H, 7)

    # --- background
    def _draw_clouds(self, cam):
        cc = cam * 0.12
        for bx, by in ((50, 22), (170, 30), (250, 16)):
            sx = int((bx - cc) % (W + 60)) - 30
            pyxel.elli(sx, by, 34, 12, 7)
            pyxel.elli(sx + 14, by - 4, 22, 10, 7)

    def _draw_stands(self, cam, oy):
        top = TRACK_TOP - 28 + oy
        pyxel.rect(0, top, W, 28, 13)
        cc = cam * 0.5
        for x, y, col in self.crowd:
            sx = int((x - cc) % 900)
            if sx < W:
                pyxel.rect(sx, y + oy, 2, 2, col)
        pyxel.line(0, TRACK_TOP - 1 + oy, W - 1, TRACK_TOP - 1 + oy, 6)

    def _draw_track(self, cam, oy):
        pyxel.rect(0, TRACK_TOP + oy, W, TRACK_BOT - TRACK_TOP, 9)
        pyxel.rect(0, TRACK_BOT + oy, W, H - TRACK_BOT, 3)
        for i in range(NUM_LANES + 1):
            y = TRACK_TOP + i * LANE_H + oy
            pyxel.line(0, y, W - 1, y, 7)

        # distance ticks
        for m in range(0, 101, 10):
            sx = int(m * PPM - cam)
            if -8 <= sx <= W + 8:
                col = 7 if m % 20 else 0
                for i in range(NUM_LANES):
                    y = TRACK_TOP + i * LANE_H + oy
                    pyxel.line(sx, y + 2, sx, y + LANE_H - 2, col)
                if m % 20 == 0:
                    label = f"{m}"
                    pyxel.text(sx - len(label) * 2, TRACK_BOT + 3 + oy,
                               label, 7)

        # start blocks
        s0 = int(-cam)
        if -12 <= s0 <= W + 12:
            for i in range(NUM_LANES):
                fy = TRACK_TOP + (i + 1) * LANE_H - 2 + oy
                pyxel.rect(s0 - 10, fy - 2, 4, 2, 0)

        # finish: checker + tape
        fsx = int(100 * PPM - cam)
        if -24 <= fsx <= W + 24:
            for row in range((TRACK_BOT - TRACK_TOP) // 3):
                for col in range(2):
                    c = 0 if (row + col) % 2 == 0 else 7
                    pyxel.rect(fsx + col * 3, TRACK_TOP + row * 3 + oy, 3, 3, c)
            pyxel.line(fsx, TRACK_TOP - 34 + oy, fsx, TRACK_TOP + oy, 7)
            pyxel.rect(fsx, TRACK_TOP - 34 + oy, 22, 7, 8)
            pyxel.text(fsx + 3, TRACK_TOP - 33 + oy, "GOAL", 7)
            if not self.player.finished:
                pyxel.line(fsx + 6, TRACK_BOT - 10 + oy, fsx + 6,
                           TRACK_BOT - 2 + oy, 8)

    def _draw_particles(self, cam, oy):
        for x, y, _, _, life, col in self.particles:
            sx = int(x - cam)
            if 0 <= sx < W:
                pyxel.pset(sx, int(y) + oy, col if life > 8 else 13)

    # --- runners
    def _draw_athlete(self, r, cam, oy):
        sx = int(r.dist * PPM - cam)
        if sx < -20 or sx > W + 20:
            return
        fy = r.foot_y() + oy
        shirt, skin, dark = r.shirt, 15, 4
        pyxel.elli(sx - 6, fy, 13, 3, dark)  # shadow

        if self.state in ("TITLE", "MARKS", "FALSE_START"):
            self._pose_marks(sx, fy, shirt, skin, dark)
        elif self.state == "SET" or (not r.is_player and self.state == "RUN"
                                     and r.cfg and self.race_t < r.react):
            self._pose_set(sx, fy, shirt, skin, dark)
        elif r.is_player and self.state == "RUN" and self.start_pending:
            self._pose_set(sx, fy, shirt, skin, dark)
        else:
            self._pose_run(sx, fy, r, shirt, skin, dark)

        if r.is_player and self.state in ("RUN", "FINISH"):
            pyxel.tri(sx - 2, fy - 26, sx + 2, fy - 26, sx, fy - 23, 8)

    # ---- static start poses (data-driven skeletons) -------------------
    POSE_MARKS = dict(
        head=(8, -8),
        segs=(
            ("dark", -3, -7, -6, -4), ("dark", -6, -4, -9, 0),   # rear leg
            ("dark", 5, -6, 3, -3), ("dark", 3, -3, 3, 0),       # rear arm
            ("shirt", -3, -7, 5, -6),                             # torso
            ("skin", -3, -7, 1, -4), ("skin", 1, -4, 1, 0),      # front leg
            ("skin", 5, -6, 7, -3), ("skin", 7, -3, 7, 0),       # front arm
        ),
        shoes=((-9, 0), (1, 0)),
    )
    POSE_SET = dict(
        head=(7, -12),
        segs=(
            ("dark", -2, -11, -6, -6), ("dark", -6, -6, -8, 0),  # rear leg
            ("dark", 4, -10, 2, -5), ("dark", 2, -5, 2, 0),      # rear arm
            ("shirt", -2, -11, 4, -10),                           # torso
            ("skin", -2, -11, 2, -6), ("skin", 2, -6, 3, 0),     # front leg
            ("skin", 4, -10, 8, -5), ("skin", 8, -5, 8, 0),      # front arm
        ),
        shoes=((-8, 0), (3, 0)),
    )

    def _tline(self, x1, y1, x2, y2, col):
        """2px-thick line."""
        x1, y1 = int(round(x1)), int(round(y1))
        x2, y2 = int(round(x2)), int(round(y2))
        pyxel.line(x1, y1, x2, y2, col)
        if abs(x2 - x1) >= abs(y2 - y1):
            pyxel.line(x1, y1 + 1, x2, y2 + 1, col)
        else:
            pyxel.line(x1 + 1, y1, x2 + 1, y2, col)

    def _pose_static(self, x, fy, shirt, skin, dark, pose):
        cols = {"shirt": shirt, "skin": skin, "dark": dark}
        for key, x1, y1, x2, y2 in pose["segs"]:
            self._tline(x + x1, fy + y1, x + x2, fy + y2, cols[key])
        for sx, sy in pose["shoes"]:
            pyxel.rect(x + sx - 1, fy + sy - 1, 3, 2, 7)
        hx, hy = pose["head"]
        pyxel.circ(x + hx, fy + hy, 2, skin)
        pyxel.pset(x + hx - 1, fy + hy - 2, dark)
        pyxel.pset(x + hx - 2, fy + hy - 1, dark)

    def _pose_marks(self, x, fy, shirt, skin, dark):
        self._pose_static(x, fy, shirt, skin, dark, self.POSE_MARKS)

    def _pose_set(self, x, fy, shirt, skin, dark):
        self._pose_static(x, fy, shirt, skin, dark, self.POSE_SET)

    # ---- procedural running gait ---------------------------------------
    THIGH, SHIN = 5.0, 5.0
    UARM, FARM = 4.0, 4.0

    def _pose_run(self, x, fy, r, shirt, skin, dark):
        ph = r.anim
        # deep forward lean out of the blocks, upright at speed
        lean = min(0.55, 0.20 + max(0.0, 5.0 - r.speed) * 0.07)
        bob = 1.4 * math.cos(2 * ph)          # low at stance, high in flight
        hip_x, hip_y = x, fy - 9 + bob
        tl = 6.5
        sho_x = hip_x + tl * math.sin(lean)
        sho_y = hip_y - tl * math.cos(lean)
        victory = r.finished and self.winner is r

        def leg(phase, col, shoe_col):
            s = math.sin(phase)
            th = (0.95 if s > 0 else 0.40) * s            # big fwd, short back
            # knee flexion: heel-to-butt in recovery, near-straight at stance
            bend = 1.06 + 0.78 * math.cos(phase) - 0.10 * math.sin(phase)
            kx = hip_x + self.THIGH * math.sin(th)
            ky = hip_y + self.THIGH * math.cos(th)
            sa = th - bend                                # shin angle
            fx = kx + self.SHIN * math.sin(sa)
            fyy = min(fy, ky + self.SHIN * math.cos(sa))  # keep feet on track
            self._tline(hip_x, hip_y, kx, ky, col)
            self._tline(kx, ky, fx, fyy, col)
            pyxel.rect(int(round(fx)) - 1, int(round(fyy)) - 1, 3, 2, shoe_col)

        def arm(phase, col):
            th = 0.85 * math.sin(phase) + lean * 0.4
            ex = sho_x + self.UARM * math.sin(th)
            ey = sho_y + self.UARM * math.cos(th)
            fa = th + 1.85                                # elbow ~ 90 deg
            hx2 = ex + self.FARM * math.sin(fa)
            hy2 = ey + self.FARM * math.cos(fa)
            self._tline(sho_x, sho_y, ex, ey, col)
            self._tline(ex, ey, hx2, hy2, col)

        # far side first (dark), then body, then near side (lit)
        leg(ph + math.pi, dark, 13)
        if not victory:
            arm(ph, 4)
        self._tline(hip_x, hip_y, sho_x, sho_y, shirt)        # torso
        pyxel.rect(int(hip_x) - 1, int(hip_y) - 1, 3, 3, 1)   # shorts
        hx = sho_x + 3.0 * math.sin(lean)
        hy = sho_y - 3.0 * math.cos(lean)
        pyxel.circ(int(round(hx)), int(round(hy)), 2, skin)   # head
        pyxel.pset(int(round(hx)) - 1, int(round(hy)) - 2, dark)
        pyxel.pset(int(round(hx)) - 2, int(round(hy)) - 1, dark)
        leg(ph, skin, 7)
        if victory:                                           # arms to the sky
            self._tline(sho_x, sho_y, sho_x - 4, sho_y - 6, 4)
            self._tline(sho_x, sho_y, sho_x + 4, sho_y - 6, skin)
        else:
            arm(ph + math.pi, skin)

    # --- HUD
    def _draw_hud(self):
        if self.state in ("TITLE", "FALSE_START"):
            return
        p = self.player

        # minimap
        pyxel.line(8, 6, 248, 6, 5)
        for m in range(0, 101, 20):
            mx = 8 + m * 240 // 100
            pyxel.pset(mx, 6, 6)
        pyxel.rect(247, 3, 2, 7, 7)  # goal
        for r in self.runners:
            mx = 8 + int(max(0.0, min(r.dist, 100.0)) * 240 / 100)
            if r.is_player:
                pyxel.rect(mx - 1, 4, 3, 5, r.shirt)
            else:
                pyxel.rect(mx, 5, 2, 3, r.shirt)

        # timer / distance / reaction / speed (top-right stack)
        if self.state in ("RUN", "FINISH"):
            t = p.time if p.finished else self.race_t
            pyxel.text(W - 44, 12, f"{t:6.2f}s", 0)
        pyxel.text(W - 44, 18, f"{max(0.0, p.dist):5.1f}m", 0)
        if self.reaction is not None:
            col = 10 if self.reaction < 0.16 else 6
            pyxel.text(W - 44, 24, f"RT{self.reaction:5.3f}", col)
        pyxel.text(W - 44, 30, f"{p.speed * 3.6:3.0f}km/h", 5)

        if self.combo >= 2:
            pyxel.text(BAR_X + BAR_W // 2 - 14, BAR_Y - 9,
                       f"COMBO x{self.combo}", 10)

        self._draw_stride_bar()

    def _draw_stride_bar(self):
        s = self.state

        if s in ("MARKS", "SET"):
            # locked: any press now is a false start -> make it look forbidden
            blink = (pyxel.frame_count // 10) % 2 == 0
            hot = s == "SET"
            pyxel.rect(BAR_X - 1, BAR_Y - 1, BAR_W + 2, BAR_H + 2, 0)
            pyxel.rect(BAR_X, BAR_Y, BAR_W, BAR_H, 2 if hot else 1)
            pyxel.rectb(BAR_X - 2, BAR_Y - 2, BAR_W + 4, BAR_H + 4,
                        8 if (hot and blink) else 2)
            msg = "DON'T PRESS!" if hot else "HANDS OFF..."
            pyxel.text(BAR_X + BAR_W // 2 - len(msg) * 2, BAR_Y + 3,
                       msg, 7 if (hot and blink) else 8)
            return

        if s == "RUN" and self.start_pending:
            # gun has fired: slam the button!
            hot = (pyxel.frame_count // 4) % 2 == 0
            pyxel.rect(BAR_X - 1, BAR_Y - 1, BAR_W + 2, BAR_H + 2, 0)
            pyxel.rect(BAR_X, BAR_Y, BAR_W, BAR_H, 10 if hot else 9)
            msg = "PUSH!!!"
            pyxel.text(BAR_X + BAR_W // 2 - len(msg) * 2, BAR_Y + 3,
                       msg, 0 if hot else 7)
            pyxel.rectb(BAR_X - 2, BAR_Y - 2, BAR_W + 4, BAR_H + 4,
                        7 if hot else 10)
            return

        # active bar (RUN / FINISH)
        pyxel.rect(BAR_X - 1, BAR_Y - 1, BAR_W + 2, BAR_H + 2, 0)
        pyxel.rect(BAR_X, BAR_Y, BAR_W, BAR_H, 1)
        gx = BAR_X + int(GOOD_A * BAR_W)
        pyxel.rect(gx, BAR_Y, BAR_X + int(GOOD_B * BAR_W) - gx, BAR_H, 3)
        px = BAR_X + int(PERF_A * BAR_W)
        pyxel.rect(px, BAR_Y, max(2, BAR_X + int(PERF_B * BAR_W) - px),
                   BAR_H, 10)
        mx = BAR_X + int(MARV_A * BAR_W)
        pyxel.rect(mx, BAR_Y, max(2, BAR_X + int(MARV_B * BAR_W) - mx),
                   BAR_H, 14)
        for t, col, life in self.press_marks:
            mx = BAR_X + int(t * (BAR_W - 2))
            c = col if life > 16 else 13
            pyxel.rect(mx, BAR_Y + BAR_H + 1, 2, 3, c)   # notch below bar
            pyxel.pset(mx, BAR_Y - 1, c)
            pyxel.pset(mx + 1, BAR_Y - 1, c)
        cx = BAR_X + int(self.cursor * (BAR_W - 2))
        pyxel.rect(cx, BAR_Y - 2, 2, BAR_H + 4, 7)
        if self.bar_flash > 0:
            # the gun just fired: bar unlocks with a bright pulse
            col = 10 if (self.bar_flash // 3) % 2 == 0 else 7
            pyxel.rectb(BAR_X - 2, BAR_Y - 2, BAR_W + 4, BAR_H + 4, col)

    # --- overlays
    def _draw_overlay(self):
        s = self.state
        cx, cy = W // 2, H // 2

        if s == "TITLE":
            self._draw_title()

        elif s == "MARKS":
            pyxel.rect(cx - 64, 26, 128, 14, 1)
            pyxel.text(cx - 32, 30, "ON YOUR MARKS...", 7)

        elif s == "SET":
            pyxel.rect(cx - 24, 26, 48, 14, 1)
            pyxel.text(cx - 10, 30, "SET !", 10)
            if (pyxel.frame_count // 14) % 2 == 0:
                pyxel.text(cx - 36, 42, "Wait for the gun!", 8)

        elif s == "FALSE_START":
            pyxel.rect(cx - 66, cy - 24, 132, 52, 8)
            pyxel.text(cx - 28, cy - 18, "FALSE START!", 7)
            r = self.foul_reason
            pyxel.text(cx - len(r) * 2, cy - 7, r, 7)
            pyxel.text(cx - 24, cy + 4, "DISQUALIFIED", 7)
            pyxel.text(cx - 30, cy + 16, "back to title...", 6)

        elif s == "FINISH" and self.timer <= FPS * 8:
            self._draw_result()

    def _draw_title(self):
        cx = W // 2
        pyxel.rect(cx - 76, 30, 152, 100, 1)
        pyxel.rectb(cx - 76, 30, 152, 100, 7)
        pyxel.text(cx - 26, 38, "100m SPRINT", 10)

        best = self.data["best"]
        best_s = f"{best:.2f}s" if best is not None else "--.--"
        line = f"BEST {best_s}  WIN {self.data['wins']}/{self.data['races']}"
        pyxel.text(cx - len(line) * 2, 50, line, 7)

        pyxel.text(cx - 66, 64, "GUN: press fast!  (<0.100s=foul)", 6)
        pyxel.text(cx - 66, 74, "press Z / TAP in the YELLOW zone", 10)
        pyxel.text(cx - 66, 84, "PINK center = MARVELOUS bonus!", 14)

        blink = (pyxel.frame_count // 20) % 2 == 0
        pyxel.rectb(cx - 44, 102, 88, 20, 10 if blink else 7)
        pyxel.text(cx - 22, 109, "START RACE", 10 if blink else 7)

    def _draw_result(self):
        cx = W // 2
        pyxel.rect(cx - 78, 24, 156, 112, 1)
        pyxel.rectb(cx - 78, 24, 156, 112, 10)
        place = self.finish_place
        place_s = ("1st", "2nd", "3rd", "4th")[place - 1]
        pyxel.text(cx - 24, 30, f"FINISH {place_s}!",
                   10 if place == 1 else 7)

        order = sorted(self.runners,
                       key=lambda r: r.time if r.time is not None else 9999)
        for i, r in enumerate(order):
            y = 44 + i * 10
            t_s = f"{r.time:6.2f}" if r.time is not None else "  --  "
            col = 10 if r.is_player else 6
            pyxel.rect(cx - 70, y + 1, 3, 3, r.shirt)
            pyxel.text(cx - 62, y, f"{i + 1} {r.name:8s}{t_s}s", col)

        pyxel.text(cx - 70, 86, f"MARVELOUS {self.n_marv:2d}", 14)
        pyxel.text(cx + 6, 86, f"PERFECT {self.n_perfect:2d}", 10)
        pyxel.text(cx - 70, 94, f"GOOD {self.n_good:2d}", 11)
        pyxel.text(cx + 6, 94, f"EARLY {self.n_early:2d}", 8)
        react_s = f"{self.reaction:.3f}s" if self.reaction is not None else "-"
        pyxel.text(cx - 70, 104,
                   f"REACTION {react_s}   COMBO x{self.max_combo}", 6)
        if self.new_best and (pyxel.frame_count // 10) % 2 == 0:
            pyxel.text(cx - 70, 112, "NEW RECORD!!", 8)
        pyxel.text(cx - 70, 121, "TAP / Z : back to title", 6)


if __name__ == "__main__":
    Sprint()
