"""Offline regressions for issue 3, domain cuts, supply counts and Calibre verdicts."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

SKILLS = Path(__file__).resolve().parents[1] / "skills"
GEN = SKILLS / "t28-ioring-generator"
sys.path[:0] = [str(GEN), str(SKILLS / "t28-ioring-simulator")]
from io_ring.layout.auto_filler import AutoFillerGeneratorT28
from io_ring.layout.confirmed_config import build_confirmed_config_from_io_config
from io_ring.layout.enrichment_engine import _check_supply_plan, enrich
from io_ring.verification import cell_check
from io_ring.verification.cell_check import evaluate
from sim_io.sim.run import _upload_setup

WIRING = GEN / "io_ring/schematic/devices/device_wiring_T28.json"


def analog_ring():
    pads = []
    for side in ("left", "bottom", "right", "top"):
        for i, (name, device) in enumerate(
            [("G", "PVSS3AC"), ("P", "PVDD3AC"), ("VSS", "PVSS2AC"), ("G", "PVSS3AC")]
        ):
            pads.append(
                dict(
                    name=name,
                    position=f"{side}_{i}",
                    type="pad",
                    device=device,
                    domain="a",
                )
            )
    pads[2].update(name="VIN", device="PDB3AC")
    return dict(
        instances=pads,
        domains={"a": dict(kind="analog", vdd_provider="P", vss_provider="G")},
        ring_config=dict(width=4, height=4, placement_order="clockwise"),
        **{"global": {"vss_ground": "VSS"}},
    )


class RuleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def expand(self, semantic):
        path = self.folder / "semantic.json"
        path.write_text(json.dumps(semantic))
        result = self.folder / "graph.json"
        enrich(path, WIRING, result)
        return result

    def test_placed_ring_both_directions_and_vss_path(self):
        for direction in ("clockwise", "counterclockwise"):
            plan = analog_ring()
            plan["ring_config"].update(
                placement_order=direction,
                vss_ohm_per_um=0.002,
                bus_ohm_per_um={"a": 0.02},
            )
            graph = self.expand(plan)
            out = build_confirmed_config_from_io_config(
                str(graph), skip_editor_confirmation=True
            )
            review = json.loads(Path(out).read_text(encoding="utf-8"))["rule_review"]
            (path,) = review["vss_bus"]
            self.assertGreater(path["estimated_ohm"], 0)
            self.assertTrue(
                any(
                    "estimate exceeds" in msg
                    for msg in review["G13_supply_plan"]["pending"]
                )
            )
            self.assertTrue(review["same_domain_bus"])
            self.assertTrue(
                all(
                    row["reference"] == "10.1" and row["estimated_length_um"] > 0
                    for row in review["same_domain_bus"]
                )
            )

    def test_conflicting_bus_override_preserves_wiring(self):
        plan = analog_ring()
        plan["overrides"] = {"left_2": {"pin_overrides": {"TACVSS": "OTHER"}}}
        confirmed = build_confirmed_config_from_io_config(
            str(self.expand(plan)), skip_editor_confirmation=True
        )
        data = json.loads(Path(confirmed).read_text(encoding="utf-8"))
        self.assertIn("TACVSS connects both", " ".join(data["rule_review"]["warnings"]))

        self.assertTrue(
            any(
                p.get("pin_connection", {}).get("TACVSS", {}).get("label") == "OTHER"
                for p in data["instances"]
            )
        )

    def test_sso_factors_can_exceed_minimum_supply_counts(self):
        devices = (
            ["PVDD1DGZ"] * 3 + ["PVDD2DGZ"] * 2 + ["PVSS1DGZ", "PVSS2DGZ", "PRUW08SDGZ"]
        )
        pads = [
            dict(domain="d", name=dev, device=dev, position=f"top_{i}")
            for i, dev in enumerate(devices)
        ]
        pads[-1]["drive_factor"] = 2.3
        results = {}
        _check_supply_plan(
            {"domains": {"d": {"kind": "digital"}}, "instances": pads}, results
        )
        self.assertIn(
            "bonded 1, requires 3", " ".join(results["G13_supply_plan"]["warnings"])
        )

    def test_unbonded_supply_does_not_count(self):
        plan = analog_ring()
        for pad in plan["instances"][:8]:
            pad["bonded"] = False
        notes = json.loads(self.expand(plan).read_text(encoding="utf-8"))[
            "recommendations"
        ]
        self.assertIn(
            "bonded 2, requires 3", " ".join(notes["G13_supply_plan"]["warnings"])
        )

    def test_dedicated_supplies_need_package_and_pair(self):
        plan = analog_ring()
        plan["instances"][2]["device"] = "PVDD1AC"
        notes = json.loads(self.expand(plan).read_text(encoding="utf-8"))[
            "recommendations"
        ]
        self.assertIn(
            "macro and package_pin", " ".join(notes["G13_supply_plan"]["warnings"])
        )

    def test_corner_guidance_allows_confirmation(self):
        plan = analog_ring()
        plan["instances"][0].update(name="VIN2", device="PDB3AC")
        confirmed = build_confirmed_config_from_io_config(
            str(self.expand(plan)), skip_editor_confirmation=True
        )
        data = json.loads(Path(confirmed).read_text(encoding="utf-8"))
        self.assertIn(
            "adjacent bonded grounds", " ".join(data["rule_review"]["warnings"])
        )

    def test_supply_only_domain(self):
        plan = analog_ring()
        plan["domains"] = {
            "d": dict(
                kind="digital",
                low_vdd="DV",
                high_vdd="IO",
                low_vss="VSS",
                high_vss="VSS",
                poc_grounded=True,
            )
        }
        for i, pad in enumerate(plan["instances"]):
            device, name = [
                ("PVSS3DGZ", "VSS"),
                ("PVDD1DGZ", "DV"),
                ("PVDD2DGZ", "IO"),
                ("PVSS3DGZ", "VSS"),
            ][i % 4]
            pad.update(domain="d", device=device, name=name)
        path = self.expand(plan)
        graph = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                p["pin_connection"]["POC"]["label"]
                for p in graph["instances"]
                if p["type"] == "pad"
            },
            {"VSS"},
        )
        build_confirmed_config_from_io_config(str(path), skip_editor_confirmation=True)

    def test_inner_pad_uses_original_pitch_at_domain_cut(self):
        def pad(name, i, domain, master, terminal):
            return dict(
                name=name,
                domain=domain,
                position="top_" + i,
                device=master + "_V_G",
                type="inner_pad" if "_" in i else "pad",
                pin_connection={terminal: {"label": "P"}},
            )

        for master, source_pin, expected in (
            ("PVSS3AC", "TACVSS", "PRCUTA_G"),
            ("PVSS1DGZ", "VSS", None),
        ):
            outer = [
                pad("A", "0", "a", master, source_pin),
                pad("B", "1", "b", "PVSS1DGZ", "VSS"),
            ]
            inner = [pad("B2", "0_1", "b", "PVSS1DGZ", "VSS")]
            cells = AutoFillerGeneratorT28({}).auto_insert_fillers_with_inner_pads(
                outer, inner
            )
            widths = [20 if "20" in c["device"] or c["device"].startswith("PRCUT") else 10
                      for c in cells if "_mid_" in c["name"]]
            self.assertEqual(widths, [20, 20] if expected else [10, 10])
            self.assertEqual(
                [c["device"] for c in cells if c["device"].startswith("PRCUT")],
                [expected] if expected else [],
            )

    def test_erc_findings_preserve_correct_lvs_verdict(self):
        (self.folder / "top.lvs.summary").write_text(
            "OVERALL COMPARISON RESULTS\n# CORRECT #\n CELL SUMMARY\n"
        )
        (self.folder / "calibre_erc.sum").write_text(
            "Layout Primary Cell: top\nTOTAL ERC RuleChecks Executed: 21\nTOTAL ERC RuleCheck Results Generated: 6 (12)\n"
        )
        result, ok = evaluate("lvs", self.folder, "top")
        self.assertTrue(result["lvs_correct"])
        self.assertEqual(result["erc_results"], 6)
        self.assertFalse(ok)

    def test_drc_counts_and_identity(self):
        summary = self.folder / "top.drc.summary"
        for n in (0, 3):
            summary.write_text(
                f"Layout Primary Cell: top\nTOTAL DRC RuleChecks Executed: 40\nTOTAL DRC Results Generated: {n} ({n})\n"
            )
            self.assertEqual(evaluate("drc", self.folder, "top")[1], n == 0)
        summary.write_text(
            "Layout Primary Cell: old\nTOTAL DRC Results Generated: 0 (0)\n"
        )
        with self.assertRaises(ValueError):
            evaluate("drc", self.folder, "top")

    def test_user_vss_overrides_global_recommendation(self):
        plan = analog_ring()
        plan["global"]["ring_esd"] = "global_esd"
        plan["instances"][2]["pin_connection"] = {
            "VSS": {"label": "local_esd", "create_pin": False}
        }
        graph = json.loads(self.expand(plan).read_text(encoding="utf-8"))
        pin = next(p for p in graph["instances"] if p["position"] == "left_2")[
            "pin_connection"
        ]["VSS"]
        self.assertEqual(pin, {"label": "local_esd", "create_pin": False})
        self.assertFalse(graph["recommendations"]["G4_vss_consistency"]["pass"])

    def test_semantic_input_preserves_orientation_with_partial_domain(self):
        plan = analog_ring()
        plan["instances"][2]["orientation"] = "R90"
        plan["domains"][plan["instances"][2]["domain"]].pop("kind")
        graph = json.loads(self.expand(plan).read_text(encoding="utf-8"))
        pad = next(p for p in graph["instances"] if p["position"] == "left_2")
        self.assertEqual(pad["orientation"], "R90")
        self.assertFalse(graph["recommendations"]["G13_supply_plan"]["pass"])

    def test_mixed_corner_has_one_cut_in_a_twenty_micron_spacer(self):
        plan = json.loads(
            (
                GEN
                / "T28_Testbench/semantic_intents/IO_28nm_3x3_single_ring_mixed.json"
            ).read_text()
        )
        path = self.expand(plan)
        result = build_confirmed_config_from_io_config(
            str(path), skip_editor_confirmation=True
        )
        cells = json.loads(Path(result).read_text(encoding="utf-8"))["instances"]
        cuts = [p for p in cells if p["device"] == "PRCUTA_G"]
        self.assertEqual(len(cuts), 2)
        self.assertIn("bottom_start_0", [c["name"] for c in cuts])

    def test_completed_drc_with_findings_returns_zero(self):
        import os

        def perform(*args, **kwargs):
            out = Path(os.environ["AMS_OUTPUT_ROOT"]) / "drc"
            out.mkdir()
            (out / "top.drc.summary").write_text(
                "Layout Primary Cell: top\nTOTAL DRC RuleChecks Executed: 1\nTOTAL DRC Results Generated: 2 (2)\n"
            )
            return "Calibre DRC flow (T28) completed successfully."

        with (
            patch.dict(os.environ),
            patch.object(sys, "argv", ["run_drc.py", "lib", "top"]),
            patch.object(cell_check, "resolve_output_root", return_value=self.folder),
            patch("io_ring.bridge.execute_csh_script", side_effect=perform),
        ):
            self.assertEqual(cell_check.run("drc"), 0)
        result = json.loads(
            next(self.folder.rglob("result.json")).read_text(encoding="utf-8")
        )
        self.assertTrue(result["completed"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["drc_results"], 2)

    def test_user_deck_controls_erc_and_virtual_connect(self):
        custom = self.folder / "project.tvf"
        custom.write_text('LVS EXECUTE ERC NO\nVIRTUAL CONNECT NAME "example?"\n')
        staged = self.folder / "staged.tvf"
        staged.write_text("")
        metadata = {}
        cell_check.prepare_deck("lvs", staged, metadata, custom_deck=custom)
        self.assertEqual(staged.read_text(), custom.read_text())
        self.assertFalse(metadata["erc_required"])
        self.assertIn('VIRTUAL CONNECT NAME "example?"', metadata["directives"])

    def test_failed_upload_stops_even_if_a_remote_file_exists(self):
        tunnel = Mock()
        tunnel.upload_text.return_value = SimpleNamespace(
            returncode=1, stderr="permission denied"
        )
        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            _upload_setup(SimpleNamespace(_tunnel=tunnel), "new", "/tmp/run/setup.csh")
        tunnel.run_command.assert_not_called()
