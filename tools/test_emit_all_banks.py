"""Dispatch-priority regression tests. No recompiler invocation or build."""
import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import emit_all_banks as emit


class EmissionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "title"
        self.framework = self.root / "framework"
        self.output.mkdir()
        self.framework.mkdir()
        for name in ("arm9_bios", "arm7_bios", "freebios_arm9", "freebios_arm7",
                     "fw_arm9_early"):
            (self.framework / f"{name}_dispatch.c").write_text("/* fixture */")
        self.specs = copy.deepcopy(emit.banks)
        for bank in self.specs:
            (self.output / f"{bank['bank']}_dispatch.c").write_text("/* fixture */")

    def command(self, name="nsmb_arm9_runtime", coalesce=True):
        bank = next(b for b in self.specs if b["bank"] == name)
        return emit.bank_command("recompiler.exe", bank, self.specs, self.output,
                                 self.framework, coalesce)

    def predecessors(self, name):
        cmd = self.command(name)
        return [Path(cmd[i + 1]) for i, arg in enumerate(cmd)
                if arg == "--preceding-dispatch"]

    def test_order_matches_runner_full_dispatch_filename_sort(self):
        actual = [b["bank"] for b in emit.emission_order(reversed(self.specs))]
        expected = [p.name.removesuffix("_dispatch.c") for p in
                    sorted(self.output.glob("*_dispatch.c"))]
        self.assertEqual(actual, expected)
        self.assertLess(actual.index("nsmb_arm9"), actual.index("nsmb_arm9_itcm"))
        self.assertEqual(actual[-1], "nsmb_arm9_runtime")

    def test_itcm_keeps_main_bank_priority_without_later_overlays(self):
        paths = self.predecessors("nsmb_arm9_itcm")
        self.assertIn(self.output / "nsmb_arm9_dispatch.c", paths)
        self.assertNotIn(self.output / "nsmb_arm9_ov009_dispatch.c", paths)
        self.assertNotIn(self.output / "nsmb_arm9_itcm_dispatch.c", paths)

    def test_runtime_protects_itcm_and_all_earlier_overlays(self):
        paths = self.predecessors("nsmb_arm9_runtime")
        for name in ("nsmb_arm9", "nsmb_arm9_itcm", "nsmb_arm9_ov009", "nsmb_arm9_ov054"):
            self.assertIn(self.output / f"{name}_dispatch.c", paths)
        self.assertNotIn(self.output / "nsmb_arm9_runtime_dispatch.c", paths)

    def test_all_external_banks_and_extra_earlier_title_are_protected(self):
        extra = self.output / "extra_arm9_dispatch.c"
        extra.touch()
        paths = self.predecessors("nsmb_arm9_itcm")
        self.assertIn(extra, paths)
        self.assertTrue(set(self.framework.glob("*_dispatch.c")).issubset(paths))

    def test_missing_expected_predecessor_stops_emission(self):
        (self.output / "nsmb_arm9_dispatch.c").unlink()
        with self.assertRaises(FileNotFoundError):
            self.command()

    def test_missing_framework_directory_or_bios_stops_emission(self):
        (self.framework / "arm9_bios_dispatch.c").unlink()
        with self.assertRaises(FileNotFoundError):
            self.command()
        with self.assertRaises(FileNotFoundError):
            emit.preceding_dispatches("nsmb_arm9_itcm", self.specs, self.output,
                                      self.root / "missing")

    def test_validation_required_and_direct_call_optimization_not_enabled(self):
        cmd = self.command()
        self.assertIn("--validate-live-bytes", cmd)
        self.assertIn("--coalesce-fallthroughs", cmd)
        self.assertNotIn("--validated-live-direct-calls", cmd)
        bank = next(b for b in self.specs if b["bank"] == "nsmb_arm9_runtime")
        bank["flags"].remove("--validate-live-bytes")
        with self.assertRaises(ValueError):
            self.command()

    def test_scope_and_control_mode_preserve_original_flags(self):
        for bank in self.specs:
            cmd = self.command(bank["bank"])
            self.assertEqual("--coalesce-fallthroughs" in cmd,
                             bank["bank"] in emit.COALESCED_BANKS)
            control = self.command(bank["bank"], coalesce=False)
            self.assertNotIn("--coalesce-fallthroughs", control)
            self.assertNotIn("--preceding-dispatch", control)
            for flag in bank["flags"]:
                self.assertIn(flag, control)

    def test_fresh_emission_creates_predecessors_before_using_them(self):
        for path in self.output.glob("*.c"):
            path.unlink()
        fake_tool = self.root / "recompiler.exe"
        fake_tool.touch()
        calls = []

        def fake_run(cmd, **kwargs):
            name = cmd[cmd.index("--bank") + 1]
            for index, arg in enumerate(cmd):
                if arg == "--preceding-dispatch":
                    self.assertTrue(Path(cmd[index + 1]).is_file())
            calls.append(name)
            (self.output / f"{name}_dispatch.c").touch()
            return SimpleNamespace(returncode=0, stdout="[emit] fixture", stderr="")

        with patch.object(emit, "RECOMP_DIR", self.output), \
             patch.object(emit.subprocess, "run", side_effect=fake_run), \
             contextlib.redirect_stdout(io.StringIO()):
            result = emit.main(["--recompiler", str(fake_tool),
                                "--preceding-dispatch-dir", str(self.framework)])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [b["bank"] for b in emit.emission_order(self.specs)])

    def test_failed_bank_stops_before_later_banks(self):
        fake_tool = self.root / "recompiler.exe"
        fake_tool.touch()
        with patch.object(emit, "RECOMP_DIR", self.output), \
             patch.object(emit.subprocess, "run", return_value=SimpleNamespace(
                 returncode=7, stdout="", stderr="fixture failure")) as run, \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            result = emit.main(["--recompiler", str(fake_tool)])
        self.assertEqual(result, 7)
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
