from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "patch_ds97_parameter_display.py"
README = ROOT / "README.md"
PARAMETER_GUIDE = ROOT / "docs" / "parameter-display.md"
PARAMETER_TECHNICAL = ROOT / "docs" / "parameter-display-technical-details.md"


def load_module():
    spec = importlib.util.spec_from_file_location("ds97_parameter_patch", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_mode2_form1_sector(module, fill: int = 0x33) -> bytes:
    sector = bytearray(module.SECTOR_SIZE)
    sector[:12] = b"\x00" + b"\xFF" * 10 + b"\x00"
    sector[12:15] = b"\x00\x02\x00"
    sector[15] = 2
    sector[16:20] = b"\x00\x00\x08\x00"
    sector[20:24] = sector[16:20]
    sector[module.USER_OFFSET : module.USER_OFFSET + module.USER_SIZE] = bytes(
        [fill]
    ) * module.USER_SIZE
    return module.regenerate_mode2_form1(sector)


class ParameterDisplayPatchTests(unittest.TestCase):
    def test_exact_input_output_contract(self):
        module = load_module()

        self.assertEqual(module.EXPECTED_BIN_SIZE, 405_917_568)
        self.assertEqual(
            module.EXPECTED_INPUT_SHA256,
            "f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84",
        )
        self.assertEqual(
            module.EXPECTED_OUTPUT_SHA256,
            "fc66ceed0d09abbf73725321500eefc6486404d2bd01f90f5838bff9d5df484b",
        )
        self.assertEqual(module.EXPECTED_CHANGED_LBAS, (38_361, 38_387))
        self.assertEqual(module.EXPECTED_CHANGED_USER_BYTES, 147)
        self.assertEqual(module.EXPECTED_CHANGED_RAW_BYTES, 503)

    def test_patch_regions_and_helper_adjustment_are_fixed(self):
        module = load_module()

        self.assertEqual([patch.file_offset for patch in module.PATCHES], [
            0x0AC710,
            0x0AC760,
            0x0B907B,
        ])
        self.assertEqual(module.PATCHES[0].new, bytes.fromhex("89 39 04 08"))
        self.assertEqual(module.PATCHES[1].new, bytes.fromhex("7D 39 04 08"))
        self.assertEqual(len(module.PATCHES[2].old), 141)
        self.assertEqual(len(module.PATCHES[2].new), 141)
        self.assertEqual(module.PATCHES[2].new[:4], bytes.fromhex("D8 FF B5 26"))
        self.assertEqual(
            hashlib.sha256(module.PATCHES[2].old).hexdigest(),
            "c0e7754ed255b5ec6f70dc9abe260ae0a3d4a75f7b1d54d01169a0165f866801",
        )
        self.assertEqual(
            hashlib.sha256(module.PATCHES[2].new).hexdigest(),
            "941671e9c6c6383d227897e8b410722bfd782b8b05499d2c4bc879d3359be0f9",
        )
        self.assertNotIn(0x0AC65B, [patch.file_offset for patch in module.PATCHES])
        self.assertEqual(
            module.mips_jump_target(
                module.LOOP_EXIT_HOOK_RUNTIME, module.LOOP_EXIT_HOOK_INSTRUCTION
            ),
            module.HELPER_LOOP_ENTRY_RUNTIME,
        )
        self.assertEqual(
            module.mips_jump_target(
                module.POST_RACE_HOOK_RUNTIME, module.POST_RACE_HOOK_INSTRUCTION
            ),
            module.HELPER_RUNTIME,
        )

    def test_apply_patch_regions_replaces_only_declared_bytes(self):
        module = load_module()
        size = max(patch.end_offset for patch in module.PATCHES) + 16
        source = bytearray([0xA5] * size)
        for patch in module.PATCHES:
            source[patch.file_offset : patch.end_offset] = patch.old

        patched = module.apply_patch_regions(bytes(source))

        for patch in module.PATCHES:
            self.assertEqual(
                patched[patch.file_offset : patch.end_offset], patch.new
            )
        declared = set()
        for patch in module.PATCHES:
            declared.update(range(patch.file_offset, patch.end_offset))
        self.assertEqual(
            [
                index
                for index, (old, new) in enumerate(zip(source, patched, strict=True))
                if old != new and index not in declared
            ],
            [],
        )

    def test_apply_patch_regions_rejects_wrong_source(self):
        module = load_module()
        size = max(patch.end_offset for patch in module.PATCHES) + 1
        source = bytes(size)
        with self.assertRaisesRegex(ValueError, "source bytes mismatch"):
            module.apply_patch_regions(source)

    def test_display_layout_is_record_18_through_27(self):
        module = load_module()

        self.assertEqual(
            tuple(offset for _, offset, _ in module.DISPLAY_LAYOUT),
            tuple(range(0x18, 0x28)),
        )
        fields = [field for _, _, field in module.DISPLAY_LAYOUT]
        self.assertEqual(fields[1], "best_body_weight_internal")
        self.assertEqual(fields[2:4], ["max_sp", "current_sp"])
        self.assertEqual(fields[11], "growth_decline_packed")
        self.assertEqual(fields[12:15], ["dirt", "durability", "recovery"])

    def test_edc_matches_independent_bitwise_implementation(self):
        module = load_module()
        data = bytes(range(64))
        expected = 0
        for value in data:
            expected ^= value
            for _ in range(8):
                expected = (expected >> 1) ^ (
                    0xD8018001 if expected & 1 else 0
                )
                expected &= 0xFFFFFFFF
        self.assertEqual(module.edc_compute(data), expected)

    def test_mode2_form1_regeneration_and_single_sector_patch(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "synthetic.bin"
            image.write_bytes(make_mode2_form1_sector(module, 0x22))
            source = bytes([0x22]) * module.USER_SIZE
            patched = bytearray(source)
            patched[0x123:0x127] = b"TEST"

            changed = module.patch_extent(image, 0, source, bytes(patched))

            self.assertEqual(changed, [0])
            sector = module.read_sector(image, 0)
            self.assertTrue(module.verify_mode2_form1(sector))
            self.assertEqual(
                sector[module.USER_OFFSET + 0x123 : module.USER_OFFSET + 0x127],
                b"TEST",
            )

    def test_lz_literal_and_overlapping_match(self):
        module = load_module()
        literal = b"\x04ABCD"
        self.assertEqual(module.lz_decompress(literal, 4), b"ABCD")

        # literal "ABCD", then a four-byte match from offset 0
        encoded = b"\x04ABCD\x80\x00\x00"
        self.assertEqual(module.lz_decompress(encoded, 8), b"ABCDABCD")

    def test_default_output_names_match_public_convention(self):
        module = load_module()
        input_bin = Path("DerbyStallion97_v11_fix.bin")
        output_bin = module.default_output_bin(input_bin)
        self.assertEqual(output_bin.name, "DerbyStallion97_v11_fix_display.bin")
        self.assertEqual(
            output_bin.with_suffix(".cue").name,
            "DerbyStallion97_v11_fix_display.cue",
        )

    def test_cue_is_single_track_mode2_2352(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            cue = Path(temp_dir) / "output.cue"
            module.write_cue(cue, "DerbyStallion97_v11_fix_display.bin")
            self.assertEqual(
                cue.read_bytes(),
                b'FILE "DerbyStallion97_v11_fix_display.bin" BINARY\r\n'
                b"  TRACK 01 MODE2/2352\r\n"
                b"    INDEX 01 00:00:00\r\n",
            )

    def test_verify_input_rejects_wrong_size_before_copy(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            wrong = Path(temp_dir) / "wrong.bin"
            wrong.write_bytes(b"not a disc")
            with self.assertRaisesRegex(ValueError, "Unexpected BIN size"):
                module.verify_input(wrong)

    def test_verify_input_reports_missing_path_clearly(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.bin"
            with self.assertRaisesRegex(FileNotFoundError, "Input BIN not found"):
                module.verify_input(missing)

    def test_verify_input_rejects_wrong_hash(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            wrong = Path(temp_dir) / "wrong.bin"
            wrong.write_bytes(make_mode2_form1_sector(module))
            with mock.patch.object(
                module, "EXPECTED_BIN_SIZE", module.SECTOR_SIZE
            ), mock.patch.object(module, "sha256_file", return_value="0" * 64):
                with self.assertRaisesRegex(ValueError, "Input SHA-256"):
                    module.verify_input(wrong)

    def test_audit_uses_filenames_and_runtime_confirmed_status(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_bin = root / "DerbyStallion97_v11_fix.bin"
            input_bin.write_bytes(b"input")
            output_bin = root / "DerbyStallion97_v11_fix_display.bin"
            audit = module.make_audit(
                input_bin=input_bin,
                output_bin=output_bin,
                input_sha256=module.EXPECTED_INPUT_SHA256,
                output_sha256=module.EXPECTED_OUTPUT_SHA256,
                changed_lbas=list(module.EXPECTED_CHANGED_LBAS),
                raw_count=module.EXPECTED_CHANGED_RAW_BYTES,
                user_count=module.EXPECTED_CHANGED_USER_BYTES,
            )
            serialized = json.dumps(audit, ensure_ascii=False)
            self.assertEqual(audit["status"], "runtime_confirmed")
            self.assertTrue(audit["output"]["runtime_confirmed"])
            self.assertEqual(audit["display"]["record_range"], "+0x18..+0x27")
            self.assertNotIn(str(root), serialized)
            self.assertEqual(
                audit["runtime_validation"]["environment"], "no$psX 2.3"
            )
            self.assertIn(
                "post_win_progression",
                audit["runtime_validation"]["confirmed_checks"],
            )
            self.assertIn(
                "duckstation_parameter_display",
                audit["runtime_validation"]["unconfirmed_checks"],
            )
            self.assertEqual(
                audit["runtime"]["helper"]["pointer_math"],
                "record+0x40-0x28 = record+0x18",
            )

    def test_script_contains_no_game_image(self):
        source = SCRIPT.read_bytes()
        markers = [
            b"PS-X EXE",
            bytes.fromhex("00 FF FF FF FF FF FF FF FF FF FF 00"),
        ]
        self.assertLess(len(source), 100_000)
        self.assertEqual([marker for marker in markers if marker in source], [])

    def test_public_docs_match_runtime_evidence_boundary(self):
        public_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [README, PARAMETER_GUIDE, PARAMETER_TECHNICAL]
        )

        self.assertIn("runtime-confirmed", public_text)
        self.assertIn("no$psX 2.3", public_text)
        self.assertIn("fc66ceed0d09abbf", public_text)
        self.assertIn("DuckStation", public_text)
        self.assertIn("未確認", public_text)
        self.assertNotIn("static_verified_runtime_pending", public_text)


if __name__ == "__main__":
    unittest.main()
