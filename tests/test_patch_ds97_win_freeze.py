from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "patch_ds97_win_freeze.py"
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
TECHNICAL_DETAILS = ROOT / "docs" / "technical-details.md"
TROUBLESHOOTING = ROOT / "docs" / "troubleshooting.md"
VALIDATION_CHECKLIST = ROOT / "docs" / "validation-checklist.md"


def load_patch_module():
    spec = importlib.util.spec_from_file_location("patch_ds97_win_freeze", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def independent_edc(data: bytes) -> int:
    edc = 0
    for value in data:
        edc ^= value
        for _ in range(8):
            edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
            edc &= 0xFFFFFFFF
    return edc


def configure_small_layout(monkeypatch, module, *, expected_size: int = 2352) -> None:
    monkeypatch.setattr(module, "EXPECTED_BIN_SIZE", expected_size)
    monkeypatch.setattr(module, "EXPECTED_SHA256", "not-the-test-digest")
    monkeypatch.setattr(module, "GWIN_LBA", 0)
    monkeypatch.setattr(module, "GWIN_SIZE", 2048)
    monkeypatch.setattr(module, "WAIT_BRANCH_FILE_OFFSET", 0x20)
    monkeypatch.setattr(module, "THRESHOLD_FILE_OFFSET", 0x1C)
    monkeypatch.setattr(module, "PATCH_REGION_FILE_OFFSET", 0x40)


def make_mode2_form1_sector(module) -> bytearray:
    sector = bytearray(module.SECTOR_SIZE)
    sector[15] = 2
    sector[16:20] = b"\x00\x00\x00\x00"
    sector[20:24] = sector[16:20]
    return sector


def make_small_original(module) -> bytearray:
    sector = make_mode2_form1_sector(module)
    user = memoryview(sector)[module.USER_OFFSET : module.USER_OFFSET + module.USER_SIZE]
    for index in range(len(user)):
        user[index] = index & 0xFF
    user[0x10 : 0x10 + len(module.ORIGINAL_WAIT_CONTEXT)] = module.ORIGINAL_WAIT_CONTEXT
    user[0x40 : 0x40 + len(module.ORIGINAL_PATCH_REGION)] = module.ORIGINAL_PATCH_REGION
    module.regenerate_mode2_form1(sector)
    return sector


def test_rejects_same_input_and_output_bin(tmp_path):
    module = load_patch_module()
    image = tmp_path / "same.bin"
    image.write_bytes(b"x")

    with pytest.raises(ValueError, match="must differ"):
        module.main(["--input-bin", str(image), "--output-bin", str(image)])


def test_rejects_non_2352_sector_size(tmp_path, monkeypatch):
    module = load_patch_module()
    configure_small_layout(monkeypatch, module, expected_size=2353)
    image = tmp_path / "bad-size.bin"
    image.write_bytes(b"\x00" * 2353)

    with pytest.raises(ValueError, match="2352-byte-sector"):
        module.verify_original(image, allow_unverified_sha256=True)


def test_rejects_sha256_mismatch_by_default(tmp_path, monkeypatch):
    module = load_patch_module()
    configure_small_layout(monkeypatch, module)
    image = tmp_path / "image.bin"
    image.write_bytes(make_small_original(module))

    with pytest.raises(ValueError, match="SHA-256"):
        module.verify_original(image, allow_unverified_sha256=False)


def test_rejects_original_instruction_mismatch(tmp_path, monkeypatch):
    module = load_patch_module()
    configure_small_layout(monkeypatch, module)
    image = tmp_path / "image.bin"
    sector = make_small_original(module)
    sector[module.USER_OFFSET + 0x1C] ^= 0x01
    module.regenerate_mode2_form1(sector)
    image.write_bytes(sector)

    with pytest.raises(ValueError, match="context mismatch|threshold"):
        module.verify_original(image, allow_unverified_sha256=True)


def test_cue_file_line_points_to_output_bin(tmp_path):
    module = load_patch_module()
    input_cue = tmp_path / "input.cue"
    output_cue = tmp_path / "output.cue"
    output_bin = tmp_path / "patched.bin"
    input_cue.write_text('FILE "original.bin" BINARY\r\n  TRACK 01 MODE2/2352\r\n', encoding="ascii")

    module.write_paired_cue(input_cue, output_cue, output_bin)

    assert output_cue.read_text(encoding="ascii").splitlines()[0] == 'FILE "patched.bin" BINARY'


def test_edc_calculation_matches_independent_implementation():
    module = load_patch_module()
    data = bytes(range(64))

    assert module.edc_compute(data) == independent_edc(data)


def test_ecc_calculation_for_zero_source_is_zero():
    module = load_patch_module()
    result = module.ecc_compute(bytes(86 * 24), 86, 24, 2, 86)

    assert result == bytes(172)


def test_regenerated_sector_verifies():
    module = load_patch_module()
    sector = make_mode2_form1_sector(module)
    sector[module.USER_OFFSET : module.USER_OFFSET + 32] = bytes(range(32))

    module.regenerate_mode2_form1(sector)

    assert module.verify_mode2_form1(sector)


def test_non_target_user_data_is_preserved(tmp_path, monkeypatch):
    module = load_patch_module()
    configure_small_layout(monkeypatch, module)
    input_bin = tmp_path / "input.bin"
    output_bin = tmp_path / "output.bin"
    sector = make_small_original(module)
    input_bin.write_bytes(sector)
    output_bin.write_bytes(sector)

    touched = set()
    touched |= module.patch_gwin_bytes(output_bin, module.WAIT_BRANCH_FILE_OFFSET, module.PATCHED_WAIT_BRANCH)
    touched |= module.patch_gwin_bytes(output_bin, module.PATCH_REGION_FILE_OFFSET, module.PATCH_REGION_BYTES)
    module.regenerate_lbas(output_bin, touched)

    original_user = input_bin.read_bytes()[module.USER_OFFSET : module.USER_OFFSET + module.USER_SIZE]
    patched_user = output_bin.read_bytes()[module.USER_OFFSET : module.USER_OFFSET + module.USER_SIZE]
    changed_ranges = set(range(0x20, 0x24)) | set(range(0x40, 0x40 + len(module.PATCH_REGION_BYTES)))
    for index, (left, right) in enumerate(zip(original_user, patched_user, strict=True)):
        if index not in changed_ranges:
            assert left == right


def test_existing_output_is_not_overwritten_by_default(tmp_path):
    module = load_patch_module()
    input_bin = tmp_path / "input.bin"
    output_bin = tmp_path / "output.bin"
    input_bin.write_bytes(b"input")
    output_bin.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        module.main(["--input-bin", str(input_bin), "--output-bin", str(output_bin)])


def test_runtime_status_wording_matches_evidence_boundary():
    module = load_patch_module()
    source = SCRIPT.read_text(encoding="utf-8")

    assert ("validated end-to-end in no" + "$psx") not in module.__doc__
    assert ("Runtime status: " + "experimental") not in source
    assert ("before " + "release") not in source
    assert "alpha GWIN.SOL-only" in module.build_parser().description
    assert "confirmed on no$psX 2.3" in source
    assert "DuckStation" in source
    assert "basename-specific MCD" in source
    assert "repeated-win progression" in source
    assert "Long-term operation remains unconfirmed" in source
    assert ("existing-" + "save " + "compatibility remains " + "unresolved") not in source
    assert ("repeated wins remain " + "unconfirmed") not in source


def test_public_docs_match_mcd_evidence_boundary():
    readme = README.read_text(encoding="utf-8")
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [CHANGELOG, TECHNICAL_DETAILS, TROUBLESHOOTING, VALIDATION_CHECKLIST]
    )
    public_text = readme + "\n" + docs

    assert "DuckStation" in public_text
    assert "basename" in readme
    assert "MCD" in readme
    assert "複数回の勝利後も正常に進行する" in readme
    assert "Long-term operation remains unconfirmed" in public_text
    assert "長期運用は未確認" in public_text
    assert "協調型パッチによる旧セーブ非互換を示す結果ではありません" in readme
    assert "古いsavestateが保存失敗の原因だったとは断定していません" in readme
    assert ("existing-" + "save " + "compatibility remains " + "unresolved") not in public_text
    assert ("repeated wins remain " + "unconfirmed") not in public_text
    assert "DuckStationでは未確認" not in public_text
    assert "古いsavestateが保存失敗の原因です" not in public_text
    assert "古いsavestateが保存失敗の原因でした" not in public_text


def test_patch_constants_remain_unchanged():
    module = load_patch_module()

    assert module.SECTOR_SIZE == 2352
    assert module.EXPECTED_BIN_SIZE == 405_917_568
    assert module.EXPECTED_SHA256 == "92fc3d8bae259f4167a5b72ff9e6d849b3c3790dc50140557ca965c8270b080a"
    assert module.GWIN_LBA == 151_556
    assert module.GWIN_SIZE == 0x3AB78
    assert module.OVERLAY_HEADER_FILE_OFFSET == 0x30B50
    assert module.OVERLAY_PAYLOAD_FILE_OFFSET == 0x30B60
    assert module.OVERLAY_LOAD_ADDRESS == 0x800F2AB8
    assert module.WAIT_LOOP_ADDRESS == 0x800F7E30
    assert module.WAIT_BRANCH_ADDRESS == 0x800F7E40
    assert module.WAIT_BRANCH_FILE_OFFSET == 0x35EE8
    assert module.SERVICE_ROUTINE_ADDRESS == 0x800F7024
    assert module.PENDING_FLAG_ADDRESS == 0x801C7678
    assert module.PATCH_REGION_ADDRESS == 0x800F8344
    assert module.GUARD_ADDRESS == 0x800F8354
    assert module.ORIGINAL_THRESHOLD == bytes.fromhex("F0 00 42 28")
    assert module.PATCHED_WAIT_BRANCH == bytes.fromhex("44 01 40 14")
    assert module.PATCH_REGION_BYTES == bytes.fromhex(
        "21 28 80 00 10 80 04 3C 95 BA 01 08 00 C9 84 24 "
        "1C 80 02 3C 78 76 42 8C 00 00 00 00 B3 FE 40 10 "
        "00 00 00 00 09 DC 03 08 00 00 00 00"
    )
