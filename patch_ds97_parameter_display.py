#!/usr/bin/env python3
"""Apply the DS97 v1.1 racehorse parameter-display patch.

Input authority
---------------
This tool accepts only the output of the cooperative post-win freeze patch:

    SHA-256 f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84

The patch installs the runtime-confirmed COMPACT2R1 race-result-preserving
helper and changes its pointer adjustment from record+0x1A to record+0x18.
The native two-digit decimal renderer is retained.

No game image is embedded.  The input image is copied and only the confirmed
FARMMAIN compressed-stream regions are replaced.  Touched Mode2/Form1 sectors
have EDC, ECC P, and ECC Q regenerated and verified.  The input is never
modified in place.

The direct +0x18 variant is runtime-confirmed on no$psX 2.3 for the displayed
record layout, preservation of native race results, post-win progression,
in-game saving, and cold-boot reload.  DuckStation testing of this optional
display patch and long-term operation remain unconfirmed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys


# ---------------------------------------------------------------------------
# Exact disc and file contract
# ---------------------------------------------------------------------------

SECTOR_SIZE = 2352
USER_OFFSET = 24
USER_SIZE = 2048

EXPECTED_BIN_SIZE = 405_917_568
EXPECTED_INPUT_SHA256 = (
    "f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84"
)
EXPECTED_OUTPUT_SHA256 = (
    "fc66ceed0d09abbf73725321500eefc6486404d2bd01f90f5838bff9d5df484b"
)

FARMMAIN_PATH = "DATA/FARM/FARMMAIN.BIN"
FARMMAIN_LBA = 38_017
FARMMAIN_SIZE = 764_879
FARMMAIN_INPUT_SHA256 = (
    "9c84ae7390c1d5ff3a7ed0760207dcf885f530a19b7a9ea9f7a693524268cb50"
)
FARMMAIN_OUTPUT_SHA256 = (
    "33fa367c86fec0035f1c1f7bb01df87f428d99df0b97649c5d9b683b34876b89"
)

OVERLAY_SIZE_FIELD_OFFSET = 0x0A8200
COMPRESSED_STREAM_OFFSET = 0x0A8204
EXPECTED_OVERLAY_SIZE = 0x0202A0
COMPRESSED_SLOT_SIZE = 0x0129CB
COMPRESSED_INPUT_SHA256 = (
    "f4bdf08df65b0a1d4b6c64ce71e6ee251c5e8c4cb623ec5d790b03181cabdc31"
)
COMPRESSED_OUTPUT_SHA256 = (
    "ed1467421ef478c31a317fcf8bce9a329b9eec09efe3dd3037ec2cdb7a900c60"
)
OVERLAY_INPUT_SHA256 = (
    "7583da95bab0b1c69ea6243fc51f8ed544b8c35ec76bd0a750b2d7fde29e4ca5"
)
OVERLAY_OUTPUT_SHA256 = (
    "2abd1c6085b72622318ad311fd7a1fcfb51a87e2eea592a360f16dd0ed2cccd8"
)

COMPACT2R1_AUTHORITY_SHA256 = (
    "3f1f1d9f3016feb8f304c3b94afd3ba146296b7b83cea411d016276ab0d4d456"
)

RUNTIME_BASE = 0x800F2AB8
ABILITY_SOURCE_RUNTIME = 0x800F8D3C
LOOP_EXIT_HOOK_RUNTIME = 0x800F8E24
POST_RACE_HOOK_RUNTIME = 0x800F8EA4
HELPER_RUNTIME = 0x8010E5F4
HELPER_LOOP_ENTRY_RUNTIME = 0x8010E624
HELPER_SIZE = 140

BASELINE_SOURCE_INSTRUCTION = bytes.fromhex("30 00 B2 26")
LOOP_EXIT_HOOK_INSTRUCTION = bytes.fromhex("89 39 04 08")
POST_RACE_HOOK_INSTRUCTION = bytes.fromhex("7D 39 04 08")
HELPER_FIRST_INSTRUCTION = bytes.fromhex("D8 FF B5 26")
HELPER_SHA256 = (
    "6bcb6c52fb7068b335e3a8d6d9c4f8e925a67022f4d25fea482fcad7228b67ee"
)

EXPECTED_CHANGED_LBAS = (38_361, 38_387)
EXPECTED_CHANGED_USER_BYTES = 147
EXPECTED_CHANGED_RAW_BYTES = 503


@dataclass(frozen=True)
class FarmPatch:
    file_offset: int
    old: bytes
    new: bytes
    purpose: str

    @property
    def end_offset(self) -> int:
        return self.file_offset + len(self.old)


# These are compressed FARMMAIN stream replacements derived byte-for-byte from
# the runtime-confirmed COMPACT2R1 image.  The helper block differs from that
# authority only at the literal mapped to runtime 0x8010E5F4:
#
#     DA FF B5 26  addiu s5,s5,-0x26  -> record+0x1A
#     D8 FF B5 26  addiu s5,s5,-0x28  -> record+0x18

PATCHES = (
    FarmPatch(
        file_offset=0x0AC710,
        old=bytes.fromhex("C4 FF 40 14"),
        new=LOOP_EXIT_HOOK_INSTRUCTION,
        purpose="loop_exit_hook_to_0x8010E624",
    ),
    FarmPatch(
        file_offset=0x0AC760,
        old=bytes.fromhex("C4 00 BF 8F"),
        new=POST_RACE_HOOK_INSTRUCTION,
        purpose="post_race_hook_to_0x8010E5F4",
    ),
    FarmPatch(
        file_offset=0x0B907B,
        old=bytes.fromhex(
            """
            020213131313131f1f1f1f1f030323030307172f070727272727270b0b2b0b0b
            0f1b330f0f373737373739393939391414143f142020203b200404243d040818
            30450828282841280c0c2c430c101c34471049494949494b4b4b4b4b15151515
            4d212121214f0505250551091931095329292929550d0d392d0d57111d351159
            383838384a3a3a3a3a4c161616
            """
        ),
        new=bytes.fromhex(
            """
            d8ffb526415319241000b9af21b0000021b8000021f000006666143c67669436
            750108249800a8af4ee3030800000000c4a94014000000001000b98f41531824
            0e00381700000000c400bf8fc000be8fbc00b78fb800b68fb400b58fb000b48f
            ac00b38fa800b28fa400b18fa000b08fc800bd270800e03903000000008be303
            08000000000000000000000000
            """
        ),
        purpose="compact2r1_helper_with_record_plus_0x18_pointer_adjustment",
    ),
)


DISPLAY_LAYOUT = (
    ("right_turf_1", 0x18, "unknown_internal_value"),
    ("right_turf_2", 0x19, "best_body_weight_internal"),
    ("right_turf_3", 0x1A, "max_sp"),
    ("right_turf_4", 0x1B, "current_sp"),
    ("right_dirt_1", 0x1C, "max_st"),
    ("right_dirt_2", 0x1D, "current_st"),
    ("right_dirt_3", 0x1E, "max_guts"),
    ("right_dirt_4", 0x1F, "current_guts"),
    ("left_turf_1", 0x20, "max_temper"),
    ("left_turf_2", 0x21, "current_temper"),
    ("left_turf_3", 0x22, "popularity"),
    ("left_turf_4", 0x23, "growth_decline_packed"),
    ("left_dirt_1", 0x24, "dirt"),
    ("left_dirt_2", 0x25, "durability"),
    ("left_dirt_3", 0x26, "recovery"),
    ("left_dirt_4", 0x27, "unknown_internal_value"),
)


# ---------------------------------------------------------------------------
# Basic hashing and raw-CD access
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, block_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_extent(path: Path, lba: int, size: int) -> bytes:
    output = bytearray()
    remaining = size
    current_lba = lba
    with path.open("rb") as handle:
        while remaining:
            count = min(USER_SIZE, remaining)
            handle.seek(current_lba * SECTOR_SIZE + USER_OFFSET)
            block = handle.read(count)
            if len(block) != count:
                raise EOFError(
                    f"Short raw sector user data at LBA {current_lba}: "
                    f"expected {count}, got {len(block)}"
                )
            output.extend(block)
            remaining -= count
            current_lba += 1
    return bytes(output)


def runtime_to_overlay_offset(address: int) -> int:
    offset = address - RUNTIME_BASE
    if not 0 <= offset < EXPECTED_OVERLAY_SIZE:
        raise ValueError(f"Runtime address outside FARM overlay: 0x{address:08X}")
    return offset


def mips_jump_target(address: int, instruction: bytes) -> int:
    if len(instruction) != 4:
        raise ValueError("MIPS instruction must be four bytes")
    word = int.from_bytes(instruction, "little")
    if word >> 26 != 0x02:
        raise ValueError(f"Instruction is not J: 0x{word:08X}")
    return ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


# ---------------------------------------------------------------------------
# DS97 LZ decompression for static verification
# ---------------------------------------------------------------------------


def lz_decompress(data: bytes, expected_size: int) -> bytes:
    output = bytearray()
    index = 0
    while index < len(data) and len(output) < expected_size:
        control = data[index]
        index += 1
        if control < 0x80:
            length = control & 0x7F
            if length == 0:
                continue
            if index + length > len(data):
                raise ValueError("Truncated DS97 literal")
            output.extend(data[index : index + length])
            index += length
        else:
            if index + 2 > len(data):
                raise ValueError("Truncated DS97 match offset")
            match_offset = data[index] | (data[index + 1] << 8)
            index += 2
            if (control & 0x7C) == 0x7C:
                if index >= len(data):
                    raise ValueError("Truncated DS97 extended match length")
                length = (((control & 3) << 8) | data[index]) + 0x80
                index += 1
            else:
                length = (control & 0x7F) + 4

            window_base = max(0, len(output) - 0x10000)
            source = window_base + match_offset
            if source < 0 or source >= len(output):
                raise ValueError(
                    f"Invalid DS97 match source 0x{source:X} at output 0x{len(output):X}"
                )
            for _ in range(length):
                if len(output) >= expected_size:
                    break
                output.append(output[source])
                source += 1

    if len(output) != expected_size:
        raise ValueError(
            f"DS97 overlay size mismatch: 0x{len(output):X} != 0x{expected_size:X}"
        )
    return bytes(output)


def extract_overlay(farmmain: bytes) -> bytes:
    if len(farmmain) != FARMMAIN_SIZE:
        raise ValueError(
            f"FARMMAIN size mismatch: {len(farmmain)} != {FARMMAIN_SIZE}"
        )
    size = int.from_bytes(
        farmmain[OVERLAY_SIZE_FIELD_OFFSET : OVERLAY_SIZE_FIELD_OFFSET + 4],
        "little",
    )
    if size != EXPECTED_OVERLAY_SIZE:
        raise ValueError(
            f"FARM overlay size field mismatch: 0x{size:X} != 0x{EXPECTED_OVERLAY_SIZE:X}"
        )
    compressed = farmmain[COMPRESSED_STREAM_OFFSET:]
    if len(compressed) != COMPRESSED_SLOT_SIZE:
        raise ValueError(
            f"FARM compressed slot mismatch: 0x{len(compressed):X} "
            f"!= 0x{COMPRESSED_SLOT_SIZE:X}"
        )
    return lz_decompress(compressed, size)


# ---------------------------------------------------------------------------
# CD-ROM Mode2/Form1 EDC/ECC
# ---------------------------------------------------------------------------


EDC_LUT = [0] * 256
ECC_F_LUT = [0] * 256
ECC_B_LUT = [0] * 256

for _table_index in range(256):
    _edc = _table_index
    for _ in range(8):
        _edc = (_edc >> 1) ^ (0xD8018001 if (_edc & 1) else 0)
    EDC_LUT[_table_index] = _edc & 0xFFFFFFFF

    _ecc = (
        (_table_index << 1) ^ (0x11D if (_table_index & 0x80) else 0)
    ) & 0xFF
    ECC_F_LUT[_table_index] = _ecc
    ECC_B_LUT[_table_index ^ _ecc] = _table_index


def edc_compute(data: bytes | bytearray | memoryview) -> int:
    edc = 0
    for value in data:
        edc = (edc >> 8) ^ EDC_LUT[(edc ^ value) & 0xFF]
    return edc & 0xFFFFFFFF


def ecc_compute(
    source: bytes | bytearray | memoryview,
    major_count: int,
    minor_count: int,
    major_mult: int,
    minor_inc: int,
) -> bytes:
    size = major_count * minor_count
    if len(source) < size:
        raise ValueError(f"ECC source too short: {len(source)} < {size}")

    destination = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        ecc_a = 0
        ecc_b = 0
        for _ in range(minor_count):
            value = source[index]
            index += minor_inc
            if index >= size:
                index -= size
            ecc_a ^= value
            ecc_b ^= value
            ecc_a = ECC_F_LUT[ecc_a]
        ecc_a = ECC_B_LUT[ECC_F_LUT[ecc_a] ^ ecc_b]
        destination[major] = ecc_a
        destination[major + major_count] = ecc_a ^ ecc_b
    return bytes(destination)


def is_mode2_form1(sector: bytes | bytearray) -> bool:
    return (
        len(sector) == SECTOR_SIZE
        and sector[:12] == b"\x00" + b"\xFF" * 10 + b"\x00"
        and sector[15] == 2
        and sector[16:20] == sector[20:24]
        and bool(sector[18] & 0x08)
        and not bool(sector[18] & 0x20)
    )


def regenerate_mode2_form1(sector: bytes | bytearray) -> bytes:
    if not is_mode2_form1(sector):
        raise ValueError("Touched sector is not Mode2/Form1 data")

    output = bytearray(sector)
    output[2072:2076] = struct.pack(
        "<I", edc_compute(memoryview(output)[16:2072])
    )

    saved_address_mode = bytes(output[12:16])
    output[12:16] = b"\x00" * 4
    output[2076:2248] = ecc_compute(
        memoryview(output)[12:2076], 86, 24, 2, 86
    )
    output[2248:2352] = ecc_compute(
        memoryview(output)[12:2248], 52, 43, 86, 88
    )
    output[12:16] = saved_address_mode
    return bytes(output)


def verify_mode2_form1(sector: bytes | bytearray) -> bool:
    return is_mode2_form1(sector) and regenerate_mode2_form1(sector) == bytes(sector)


def read_sector(path: Path, lba: int) -> bytes:
    with path.open("rb") as handle:
        handle.seek(lba * SECTOR_SIZE)
        sector = handle.read(SECTOR_SIZE)
    if len(sector) != SECTOR_SIZE:
        raise EOFError(f"Short sector at LBA {lba}")
    return sector


# ---------------------------------------------------------------------------
# Input, patch, and output verification
# ---------------------------------------------------------------------------


def verify_patch_regions(farmmain: bytes, *, expect_new: bool) -> None:
    for patch in PATCHES:
        expected = patch.new if expect_new else patch.old
        actual = farmmain[patch.file_offset : patch.end_offset]
        if actual != expected:
            state = "patched" if expect_new else "source"
            raise ValueError(
                f"FARMMAIN {state} bytes mismatch for {patch.purpose} at "
                f"0x{patch.file_offset:X}"
            )


def apply_patch_regions(source: bytes) -> bytes:
    verify_patch_regions(source, expect_new=False)
    output = bytearray(source)
    for patch in PATCHES:
        output[patch.file_offset : patch.end_offset] = patch.new
    patched = bytes(output)
    verify_patch_regions(patched, expect_new=True)
    return patched


def verify_runtime_overlay(overlay: bytes, *, patched: bool) -> None:
    source_offset = runtime_to_overlay_offset(ABILITY_SOURCE_RUNTIME)
    if overlay[source_offset : source_offset + 4] != BASELINE_SOURCE_INSTRUCTION:
        raise ValueError(
            "Baseline addiu s2,s5,0x30 changed unexpectedly at runtime "
            f"0x{ABILITY_SOURCE_RUNTIME:08X}"
        )

    if not patched:
        return

    checks = (
        (
            LOOP_EXIT_HOOK_RUNTIME,
            LOOP_EXIT_HOOK_INSTRUCTION,
            "loop-exit hook",
        ),
        (
            POST_RACE_HOOK_RUNTIME,
            POST_RACE_HOOK_INSTRUCTION,
            "post-race hook",
        ),
        (HELPER_RUNTIME, HELPER_FIRST_INSTRUCTION, "helper first instruction"),
    )
    for address, expected, label in checks:
        offset = runtime_to_overlay_offset(address)
        if overlay[offset : offset + len(expected)] != expected:
            raise ValueError(f"Runtime {label} mismatch at 0x{address:08X}")

    if (
        mips_jump_target(LOOP_EXIT_HOOK_RUNTIME, LOOP_EXIT_HOOK_INSTRUCTION)
        != HELPER_LOOP_ENTRY_RUNTIME
    ):
        raise ValueError("Loop-exit hook target decode mismatch")
    if (
        mips_jump_target(POST_RACE_HOOK_RUNTIME, POST_RACE_HOOK_INSTRUCTION)
        != HELPER_RUNTIME
    ):
        raise ValueError("Post-race hook target decode mismatch")

    helper_offset = runtime_to_overlay_offset(HELPER_RUNTIME)
    helper = overlay[helper_offset : helper_offset + HELPER_SIZE]
    if len(helper) != HELPER_SIZE or sha256_bytes(helper) != HELPER_SHA256:
        raise ValueError("Final 140-byte helper hash mismatch")

    word = int.from_bytes(helper[:4], "little")
    if word != 0x26B5FFD8:
        raise ValueError(f"Unexpected helper pointer instruction: 0x{word:08X}")


def verify_input(path: Path) -> tuple[str, bytes, bytes]:
    if not path.is_file():
        raise FileNotFoundError(f"Input BIN not found: {path}")
    size = path.stat().st_size
    if size != EXPECTED_BIN_SIZE:
        raise ValueError(f"Unexpected BIN size: {size}; expected {EXPECTED_BIN_SIZE}")
    if size % SECTOR_SIZE:
        raise ValueError("Input is not an exact 2352-byte-sector image")

    digest = sha256_file(path)
    if digest != EXPECTED_INPUT_SHA256:
        raise ValueError(
            "Input SHA-256 is not the supported cooperative freeze-fix image. "
            f"Expected {EXPECTED_INPUT_SHA256}, got {digest}"
        )

    farmmain = read_extent(path, FARMMAIN_LBA, FARMMAIN_SIZE)
    if sha256_bytes(farmmain) != FARMMAIN_INPUT_SHA256:
        raise ValueError("Input FARMMAIN SHA-256 mismatch")
    if sha256_bytes(farmmain[COMPRESSED_STREAM_OFFSET:]) != COMPRESSED_INPUT_SHA256:
        raise ValueError("Input FARMMAIN compressed-slot SHA-256 mismatch")
    verify_patch_regions(farmmain, expect_new=False)

    overlay = extract_overlay(farmmain)
    if sha256_bytes(overlay) != OVERLAY_INPUT_SHA256:
        raise ValueError("Input decompressed FARM overlay SHA-256 mismatch")
    verify_runtime_overlay(overlay, patched=False)

    for lba in EXPECTED_CHANGED_LBAS:
        if not verify_mode2_form1(read_sector(path, lba)):
            raise ValueError(f"Input EDC/ECC verification failed at LBA {lba}")
    return digest, farmmain, overlay


def build_patched_farmmain(source: bytes) -> tuple[bytes, bytes]:
    patched = apply_patch_regions(source)
    if sha256_bytes(patched) != FARMMAIN_OUTPUT_SHA256:
        raise ValueError("Patched FARMMAIN SHA-256 mismatch")
    if sha256_bytes(patched[COMPRESSED_STREAM_OFFSET:]) != COMPRESSED_OUTPUT_SHA256:
        raise ValueError("Patched FARMMAIN compressed-slot SHA-256 mismatch")
    overlay = extract_overlay(patched)
    if sha256_bytes(overlay) != OVERLAY_OUTPUT_SHA256:
        raise ValueError("Patched decompressed FARM overlay SHA-256 mismatch")
    verify_runtime_overlay(overlay, patched=True)
    return patched, overlay


def patch_extent(
    output_bin: Path,
    lba: int,
    source: bytes,
    patched: bytes,
) -> list[int]:
    if len(source) != len(patched):
        raise ValueError("Extent size changed")

    changed_lbas: list[int] = []
    position = 0
    sector_index = 0
    with output_bin.open("r+b") as handle:
        while position < len(source):
            count = min(USER_SIZE, len(source) - position)
            old_block = source[position : position + count]
            new_block = patched[position : position + count]
            if old_block != new_block:
                current_lba = lba + sector_index
                handle.seek(current_lba * SECTOR_SIZE)
                sector = handle.read(SECTOR_SIZE)
                if len(sector) != SECTOR_SIZE:
                    raise EOFError(f"Short output sector at LBA {current_lba}")
                if not is_mode2_form1(sector):
                    raise ValueError(f"LBA {current_lba} is not Mode2/Form1 data")

                user = bytearray(sector[USER_OFFSET : USER_OFFSET + USER_SIZE])
                if user[:count] != old_block:
                    raise ValueError(f"Raw input mismatch at LBA {current_lba}")
                user[:count] = new_block

                rebuilt = bytearray(sector)
                rebuilt[USER_OFFSET : USER_OFFSET + USER_SIZE] = user
                rebuilt = regenerate_mode2_form1(rebuilt)
                handle.seek(current_lba * SECTOR_SIZE)
                handle.write(rebuilt)
                changed_lbas.append(current_lba)

            position += count
            sector_index += 1
    return changed_lbas


def changed_sector_summary(
    original: Path, patched: Path
) -> tuple[list[int], int, int]:
    changed_lbas: list[int] = []
    changed_raw_bytes = 0
    changed_user_bytes = 0
    with original.open("rb") as left, patched.open("rb") as right:
        lba = 0
        while True:
            source_sector = left.read(SECTOR_SIZE)
            output_sector = right.read(SECTOR_SIZE)
            if not source_sector and not output_sector:
                break
            if len(source_sector) != len(output_sector):
                raise ValueError("Input and output BIN sizes differ")
            if source_sector != output_sector:
                changed_lbas.append(lba)
                changed_raw_bytes += sum(
                    a != b
                    for a, b in zip(source_sector, output_sector, strict=True)
                )
                changed_user_bytes += sum(
                    a != b
                    for a, b in zip(
                        source_sector[USER_OFFSET : USER_OFFSET + USER_SIZE],
                        output_sector[USER_OFFSET : USER_OFFSET + USER_SIZE],
                        strict=True,
                    )
                )
            lba += 1
    return changed_lbas, changed_raw_bytes, changed_user_bytes


def verify_output(
    input_bin: Path,
    output_bin: Path,
    expected_farmmain: bytes,
) -> tuple[str, list[int], int, int]:
    if output_bin.stat().st_size != EXPECTED_BIN_SIZE:
        raise ValueError("Output BIN size changed")

    output_farmmain = read_extent(output_bin, FARMMAIN_LBA, FARMMAIN_SIZE)
    if output_farmmain != expected_farmmain:
        raise ValueError("Output FARMMAIN re-extraction mismatch")
    verify_patch_regions(output_farmmain, expect_new=True)

    for lba in EXPECTED_CHANGED_LBAS:
        if not verify_mode2_form1(read_sector(output_bin, lba)):
            raise ValueError(f"Output EDC/ECC verification failed at LBA {lba}")

    digest = sha256_file(output_bin)
    if digest != EXPECTED_OUTPUT_SHA256:
        raise ValueError(
            f"Unexpected output SHA-256: expected {EXPECTED_OUTPUT_SHA256}, got {digest}"
        )

    changed_lbas, raw_count, user_count = changed_sector_summary(
        input_bin, output_bin
    )
    if tuple(changed_lbas) != EXPECTED_CHANGED_LBAS:
        raise ValueError(
            f"Unexpected changed LBAs: {changed_lbas}; "
            f"expected {list(EXPECTED_CHANGED_LBAS)}"
        )
    if raw_count != EXPECTED_CHANGED_RAW_BYTES:
        raise ValueError(
            f"Unexpected raw byte difference count: {raw_count}; "
            f"expected {EXPECTED_CHANGED_RAW_BYTES}"
        )
    if user_count != EXPECTED_CHANGED_USER_BYTES:
        raise ValueError(
            f"Unexpected user-data difference count: {user_count}; "
            f"expected {EXPECTED_CHANGED_USER_BYTES}"
        )
    return digest, changed_lbas, raw_count, user_count


# ---------------------------------------------------------------------------
# Output naming, CUE, and audit
# ---------------------------------------------------------------------------


def default_output_bin(input_bin: Path) -> Path:
    return input_bin.with_name(input_bin.stem + "_display.bin")


def write_cue(path: Path, bin_name: str) -> None:
    data = (
        f'FILE "{bin_name}" BINARY\r\n'
        "  TRACK 01 MODE2/2352\r\n"
        "    INDEX 01 00:00:00\r\n"
    ).encode("ascii")
    path.write_bytes(data)


def patch_audit_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for patch in PATCHES:
        row: dict[str, object] = {
            "purpose": patch.purpose,
            "compressed_file_offset": f"0x{patch.file_offset:06X}",
            "length": len(patch.old),
            "old_sha256": sha256_bytes(patch.old),
            "new_sha256": sha256_bytes(patch.new),
        }
        if len(patch.old) <= 16:
            row["old_hex"] = patch.old.hex(" ").upper()
            row["new_hex"] = patch.new.hex(" ").upper()
        rows.append(row)
    return rows


def make_audit(
    *,
    input_bin: Path,
    output_bin: Path,
    input_sha256: str,
    output_sha256: str,
    changed_lbas: list[int],
    raw_count: int,
    user_count: int,
) -> dict[str, object]:
    return {
        "schema": "ds97_parameter_display_patch_v1",
        "status": "runtime_confirmed",
        "input": {
            "filename": input_bin.name,
            "size": input_bin.stat().st_size,
            "sha256": input_sha256,
            "authority": "cooperative_post_win_freeze_fix",
        },
        "output": {
            "filename": output_bin.name,
            "size": EXPECTED_BIN_SIZE,
            "sha256": output_sha256,
            "runtime_confirmed": True,
        },
        "provenance": {
            "compact2r1_runtime_confirmed_sha256": COMPACT2R1_AUTHORITY_SHA256,
            "derivation": (
                "COMPACT2R1 direct compressed-stream patch with helper pointer "
                "adjustment -0x26 changed to -0x28"
            ),
        },
        "patch": {
            "iso_path": FARMMAIN_PATH,
            "extent_lba": FARMMAIN_LBA,
            "file_size": FARMMAIN_SIZE,
            "regions": patch_audit_rows(),
            "changed_lbas": changed_lbas,
            "changed_sector_count": len(changed_lbas),
            "changed_logical_user_data_bytes": user_count,
            "changed_raw_bytes_including_edc_ecc": raw_count,
            "mode2_form1_edc_ecc_verified": True,
            "input_not_modified": True,
        },
        "runtime": {
            "overlay_base": f"0x{RUNTIME_BASE:08X}",
            "baseline_source": {
                "address": f"0x{ABILITY_SOURCE_RUNTIME:08X}",
                "instruction_hex": BASELINE_SOURCE_INSTRUCTION.hex(" ").upper(),
                "status": "unchanged",
            },
            "loop_exit_hook": {
                "address": f"0x{LOOP_EXIT_HOOK_RUNTIME:08X}",
                "target": f"0x{HELPER_LOOP_ENTRY_RUNTIME:08X}",
            },
            "post_race_hook": {
                "address": f"0x{POST_RACE_HOOK_RUNTIME:08X}",
                "target": f"0x{HELPER_RUNTIME:08X}",
            },
            "helper": {
                "address": f"0x{HELPER_RUNTIME:08X}",
                "size": HELPER_SIZE,
                "sha256": HELPER_SHA256,
                "first_instruction_hex": HELPER_FIRST_INSTRUCTION.hex(" ").upper(),
                "first_instruction": "addiu s5,s5,-0x28",
                "pointer_math": "record+0x40-0x28 = record+0x18",
            },
        },
        "display": {
            "format": "native_decimal_two_digits",
            "record_range": "+0x18..+0x27",
            "layout": [
                {
                    "slot": slot,
                    "offset": f"+0x{offset:02X}",
                    "field": field,
                }
                for slot, offset, field in DISPLAY_LAYOUT
            ],
            "values_100_or_more": "hundreds_digit_not_displayed",
            "best_body_weight_formula": "256 + internal_value * 2 kg",
            "growth_decline_decode": {
                "growth_code": "value // 8",
                "decline_code": "value % 8",
            },
        },
        "runtime_validation": {
            "status": "runtime_confirmed",
            "environment": "no$psX 2.3",
            "confirmed_checks": [
                "cold_boot_from_output_cue",
                "record_plus_0x18_through_0x27_layout",
                "native_race_results_preserved",
                "save_and_cold_reload",
                "race_transition_and_farm_return",
                "post_win_progression",
                "cooperative_post_win_freeze_fix_preserved",
            ],
            "unconfirmed_checks": [
                "horse_switch_and_screen_reopen",
                "stallion_pedigree_and_broodmare_market_screens",
                "duckstation_parameter_display",
                "long_term_operation",
            ],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the DS97 racehorse parameter-display patch to the exact "
            "cooperative post-win freeze-fix BIN."
        )
    )
    parser.add_argument("--input-bin", required=True, type=Path)
    parser.add_argument("--output-bin", type=Path)
    parser.add_argument("--output-cue", type=Path)
    parser.add_argument("--audit-json", type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace only the explicitly resolved output BIN, CUE, and audit files",
    )
    return parser


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    input_bin = args.input_bin.resolve()
    output_bin = (
        args.output_bin.resolve()
        if args.output_bin is not None
        else default_output_bin(input_bin).resolve()
    )
    output_cue = (
        args.output_cue.resolve()
        if args.output_cue is not None
        else output_bin.with_suffix(".cue")
    )
    audit_json = (
        args.audit_json.resolve()
        if args.audit_json is not None
        else output_bin.with_suffix(".audit.json")
    )

    if input_bin == output_bin:
        raise ValueError("Input and output BIN paths must differ")
    outputs = (output_bin, output_cue, audit_json)
    if len(set(outputs)) != len(outputs):
        raise ValueError("Output BIN, CUE, and audit paths must be distinct")
    if input_bin in outputs:
        raise ValueError("Refusing to overwrite the input BIN")
    return input_bin, output_bin, output_cue, audit_json


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_bin, output_bin, output_cue, audit_json = resolve_paths(args)

    final_outputs = (output_bin, output_cue, audit_json)
    for path in final_outputs:
        if path.exists() and not args.force:
            raise FileExistsError(f"Refusing to overwrite {path}; use --force")

    output_bin.parent.mkdir(parents=True, exist_ok=True)
    output_cue.parent.mkdir(parents=True, exist_ok=True)
    audit_json.parent.mkdir(parents=True, exist_ok=True)

    temp_bin = output_bin.with_name(output_bin.name + ".tmp")
    temp_cue = output_cue.with_name(output_cue.name + ".tmp")
    temp_audit = audit_json.with_name(audit_json.name + ".tmp")
    temporary = (temp_bin, temp_cue, temp_audit)
    for path in temporary:
        if path.exists():
            if not args.force:
                raise FileExistsError(f"Temporary output already exists: {path}")
            path.unlink()

    print(f"Input BIN:  {input_bin}")
    print(f"Output BIN: {output_bin}")
    print("[1/7] Verifying exact cooperative freeze-fix input")
    input_sha, source_farmmain, _ = verify_input(input_bin)
    print(f"Input SHA-256: {input_sha}")

    print("[2/7] Building and statically verifying the FARMMAIN patch")
    patched_farmmain, _ = build_patched_farmmain(source_farmmain)

    try:
        print("[3/7] Copying the input without modifying it")
        shutil.copyfile(input_bin, temp_bin)

        print("[4/7] Patching two Mode2/Form1 sectors and regenerating EDC/ECC")
        written_lbas = patch_extent(
            temp_bin,
            FARMMAIN_LBA,
            source_farmmain,
            patched_farmmain,
        )
        if tuple(written_lbas) != EXPECTED_CHANGED_LBAS:
            raise ValueError(
                f"Unexpected written LBAs: {written_lbas}; "
                f"expected {list(EXPECTED_CHANGED_LBAS)}"
            )

        print("[5/7] Verifying output hash, isolated differences, and EDC/ECC")
        output_sha, changed_lbas, raw_count, user_count = verify_output(
            input_bin,
            temp_bin,
            patched_farmmain,
        )
        if sha256_file(input_bin) != input_sha:
            raise ValueError("Input BIN changed during patching")

        print("[6/7] Writing CUE and audit JSON")
        write_cue(temp_cue, output_bin.name)
        audit = make_audit(
            input_bin=input_bin,
            output_bin=output_bin,
            input_sha256=input_sha,
            output_sha256=output_sha,
            changed_lbas=changed_lbas,
            raw_count=raw_count,
            user_count=user_count,
        )
        temp_audit.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        os.replace(temp_bin, output_bin)
        os.replace(temp_cue, output_cue)
        os.replace(temp_audit, audit_json)
    except Exception:
        for path in temporary:
            if path.exists():
                path.unlink()
        raise

    print("[7/7] Complete")
    print(f"BIN:   {output_bin}")
    print(f"CUE:   {output_cue}")
    print(f"AUDIT: {audit_json}")
    print(f"Output SHA-256: {EXPECTED_OUTPUT_SHA256}")
    print("Display: record+0x18..record+0x27, native decimal two digits")
    print("Runtime status: runtime_confirmed (no$psX 2.3 tested scope)")
    return 0


assert len(PATCHES) == 3
assert all(len(patch.old) == len(patch.new) for patch in PATCHES)
assert len(PATCHES[2].old) == 141
assert PATCHES[2].new[0] == 0xD8
assert len(DISPLAY_LAYOUT) == 16
assert tuple(offset for _, offset, _ in DISPLAY_LAYOUT) == tuple(range(0x18, 0x28))
assert COMPRESSED_STREAM_OFFSET + COMPRESSED_SLOT_SIZE == FARMMAIN_SIZE
assert runtime_to_overlay_offset(ABILITY_SOURCE_RUNTIME) == 0x6284
assert runtime_to_overlay_offset(HELPER_RUNTIME) == 0x1BB3C
assert (
    mips_jump_target(LOOP_EXIT_HOOK_RUNTIME, LOOP_EXIT_HOOK_INSTRUCTION)
    == HELPER_LOOP_ENTRY_RUNTIME
)
assert (
    mips_jump_target(POST_RACE_HOOK_RUNTIME, POST_RACE_HOOK_INSTRUCTION)
    == HELPER_RUNTIME
)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
