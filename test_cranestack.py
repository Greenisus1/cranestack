import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cranestack as a

class StackTests(unittest.TestCase):
    def test_initial(self):
        s = a.Stack()
        self.assertEqual(len(s.blocks), 1); self.assertEqual(s.score, 0)
        self.assertFalse(s.over); self.assertEqual(s.level, 1)
    def test_perfect_drop(self):
        s = a.Stack()
        r, ov, off = s.drop(0.0)
        self.assertEqual(r, "perfect"); self.assertEqual(s.combo, 1)
        self.assertEqual(len(s.blocks), 2)
        self.assertAlmostEqual(s.top()["sx"], a.START_SIZE)  # no shrink
    def test_combo_grows(self):
        s = a.Stack()
        s.drop(0.0); s.drop(0.05)
        self.assertEqual(s.combo, 2)
        self.assertGreater(s.score, 2)  # combo bonus
    def test_ok_drop_shrinks(self):
        s = a.Stack()
        r, ov, off = s.drop(0.5)
        self.assertEqual(r, "ok"); self.assertEqual(s.combo, 0)
        self.assertAlmostEqual(s.top()["sx"], a.START_SIZE - 0.5)
        self.assertAlmostEqual(s.top()["cx"], 0.25)  # overlap center
    def test_negative_offset_shrinks(self):
        s = a.Stack()
        r, ov, off = s.drop(-0.5)
        self.assertEqual(r, "ok")
        self.assertAlmostEqual(s.top()["cx"], -0.25)
    def test_miss_ends_run(self):
        s = a.Stack()
        r, ov, off = s.drop(9.9)
        self.assertEqual(r, "miss"); self.assertTrue(s.over)
        self.assertEqual(len(s.blocks), 1)  # nothing added
    def test_axis_alternates(self):
        s = a.Stack()
        self.assertEqual(s.sweep_axis(), "x")
        s.drop(0.0)
        self.assertEqual(s.sweep_axis(), "z")
        s.drop(0.0)
        self.assertEqual(s.sweep_axis(), "x")
    def test_z_drop_shrinks_sz(self):
        s = a.Stack(); s.drop(0.0)
        r, ov, off = s.drop(0.4)
        self.assertEqual(r, "ok")
        self.assertAlmostEqual(s.top()["sz"], a.START_SIZE - 0.4)
        self.assertAlmostEqual(s.top()["sx"], a.START_SIZE)
    def test_speed_grows(self):
        s = a.Stack(); v1 = s.speed()
        for _ in range(5): s.drop(0.0)
        self.assertGreater(s.speed(), v1)
    def test_perfect_snaps_position(self):
        s = a.Stack()
        s.drop(0.05)  # within PERFECT_EPS
        self.assertAlmostEqual(s.top()["cx"], 0.0)  # snapped to center
    def test_shrink_to_sliver_then_miss(self):
        s = a.Stack()
        for _ in range(60):
            if s.over: break
            t0 = s.top(); ax = s.sweep_axis()
            c = t0["cx"] if ax == "x" else t0["cz"]
            s.drop(c + 0.4)
        t = s.top()
        self.assertTrue(s.over or t["sx"] <= 0.4 or t["sz"] <= 0.4)
    def test_record(self):
        with tempfile.TemporaryDirectory() as d, patch.object(a, "RECORD", str(Path(d) / "b.json")):
            self.assertTrue(a.save(7)); a.save(2); self.assertEqual(a.best(), 7)

class I18nTests(unittest.TestCase):
    def test_defaults_present(self):
        for k in ("MISSED", "PERFECT", "PERFECT_COMBO", "HUD"):
            self.assertIn(k, a.DEFAULT_STRINGS)
    def test_spanish_hud(self):
        S = dict(a.DEFAULT_STRINGS)
        S["HUD"] = "CRANESTACK  PUNTOS {score}  MEJOR {best}  N{level}  espacio soltar"
        self.assertIn("PUNTOS 41", S["HUD"].format(score=41, best=50, level=3))

class RenderTests(unittest.TestCase):
    def mk(self):
        s = a.Stack(); s.drop(0.3); s.drop(-0.2); s.drop(0.0)
        return s
    def test_frame_shape(self):
        rows = a.Scene().render(self.mk(), 60, 40, None, [], 1.0)
        self.assertEqual(len(rows), 40)
        for r in rows: self.assertEqual(len(r), 60)
    def test_tower_visible(self):
        rows = a.Scene().render(self.mk(), 78, 50, None, [], 1.0)
        distinct = len({c for row in rows for c in row})
        bright = sum(1 for row in rows for c in row if (c >> 16) + ((c >> 8) & 255) + (c & 255) > 250)
        self.assertGreater(distinct, 40); self.assertGreater(bright, 100)
    def test_moving_block_renders(self):
        s = self.mk()
        without = a.Scene().render(s, 78, 50, None, [], 1.0)
        t = s.top()
        withm = a.Scene().render(s, 78, 50, (0.5, t["cz"], t["sx"], t["sz"], s.top_y()), [], 1.0)
        self.assertNotEqual(without, withm)
    def test_fov_changes_frame(self):
        s = self.mk(); sc = a.Scene()
        f1 = sc.render(s, 60, 40, None, [], 1.0)
        sc.set_fov(95.0)
        f2 = sc.render(s, 60, 40, None, [], 1.0)
        self.assertNotEqual(f1, f2)
    def test_ground_renders_below(self):
        rows = a.Scene().render(self.mk(), 78, 50, None, [], 1.0)
        # bottom rows should be the dark ground slab, not sky-gradient top color
        bottom = rows[-2][39]
        self.assertLess((bottom >> 16) + ((bottom >> 8) & 255) + (bottom & 255), 260)

if __name__ == '__main__': unittest.main()
