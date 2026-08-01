#!/usr/bin/env python3
"""Alpha GWIN.SOL-only cooperative patch for Derby Stallion 97 v1.1.

This patch changes only DATA/WINNING/GWIN.SOL inside the disc image. Other overlays
that reuse the same 0x800Fxxxx RAM addresses are not changed. Within GWIN.SOL it
preserves the wrapper entry at 0x800F8344 by replacing the 44-byte call-and-return
wrapper with an equivalent 16-byte tail-call wrapper. The remaining 28 bytes at
0x800F8354..0x800F836C hold the cooperative guard.

The guard keeps the original 0xF0 threshold.  When counter < 0xF0 it checks
0x801C7678.  If no frame is pending it returns to the wait loop.  If a frame
is pending it tail-jumps to the existing service routine at 0x800F7024.  At
the wait site, $ra is 0x800F7E30 (the return address from the immediately
preceding JAL), so the service routine returns directly to the wait loop.

Post-win recovery itself is runtime-confirmed on no$psX 2.3. The public tool
remains alpha/experimental because long-term operation, existing-save
compatibility, save/reload, repeated wins, and other emulators remain
unresolved or unconfirmed.

This script never modifies the input in place, verifies the confirmed source
image and all original bytes, preserves the 0xF0 comparison, regenerates
Mode2/Form1 EDC/ECC, and checks that only the two intended sectors changed.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
import sys
from pathlib import Path

SECTOR_SIZE = 2352
USER_OFFSET = 24
USER_SIZE = 2048

EXPECTED_BIN_SIZE = 405_917_568
EXPECTED_SHA256 = "92fc3d8bae259f4167a5b72ff9e6d849b3c3790dc50140557ca965c8270b080a"

GWIN_LBA = 151_556
GWIN_SIZE = 0x3AB78
OVERLAY_HEADER_FILE_OFFSET = 0x30B50
OVERLAY_PAYLOAD_FILE_OFFSET = 0x30B60
OVERLAY_LOAD_ADDRESS = 0x800F2AB8

WAIT_LOOP_ADDRESS = 0x800F7E30
WAIT_BRANCH_ADDRESS = 0x800F7E40
WAIT_BRANCH_FILE_OFFSET = 0x35EE8
SERVICE_ROUTINE_ADDRESS = 0x800F7024
PENDING_FLAG_ADDRESS = 0x801C7678

# The live wrapper at 0x800F8344..0x800F836C is preserved semantically as a
# four-instruction tail call.  Its freed tail becomes a 28-byte dual-entry
# guard at 0x800F8354.  The adjacent wrapper at 0x800F8370 is untouched.
PATCH_REGION_ADDRESS = 0x800F8344
GUARD_ADDRESS = 0x800F8354
PATCH_REGION_FILE_OFFSET = OVERLAY_PAYLOAD_FILE_OFFSET + (
    PATCH_REGION_ADDRESS - OVERLAY_LOAD_ADDRESS
)

ORIGINAL_WAIT_BRANCH = bytes.fromhex("FB FF 40 14")
ORIGINAL_WAIT_CONTEXT = bytes.fromhex(
    "1C 80 02 3C F0 4B 42 8C 00 00 00 00 F0 00 42 28 "
    "FB FF 40 14 00 00 00 00"
)
ORIGINAL_PATCH_REGION = bytes.fromhex(
    "E8 FF BD 27 10 00 BF AF 21 28 80 00 10 80 04 3C "
    "00 C9 84 24 95 BA 01 0C 00 00 00 00 10 00 BF 8F "
    "18 00 BD 27 08 00 E0 03 00 00 00 00"
)
ORIGINAL_THRESHOLD = bytes.fromhex("F0 00 42 28")
THRESHOLD_FILE_OFFSET = 0x35EE4


# ---------------------------------------------------------------------------
# MIPS instruction encoders
# ---------------------------------------------------------------------------

def encode_branch(opcode: int, rs: int, rt: int, pc: int, target: int) -> bytes:
    delta = target - (pc + 4)
    if delta % 4:
        raise ValueError(f"Unaligned branch target: 0x{target:08X}")
    imm = delta // 4
    if not -0x8000 <= imm <= 0x7FFF:
        raise ValueError(
            f"Branch out of range: PC=0x{pc:08X}, target=0x{target:08X}"
        )
    word = (
        ((opcode & 0x3F) << 26)
        | ((rs & 0x1F) << 21)
        | ((rt & 0x1F) << 16)
        | (imm & 0xFFFF)
    )
    return struct.pack("<I", word)


def encode_jump(opcode: int, target: int) -> bytes:
    if target % 4:
        raise ValueError(f"Unaligned jump target: 0x{target:08X}")
    word = ((opcode & 0x3F) << 26) | ((target >> 2) & 0x03FFFFFF)
    return struct.pack("<I", word)


def build_patch_region() -> bytes:
    # 0x800F8344: preserve the original wrapper as a tail call.
    # Original semantics: a1=caller a0; a0=0x8010C900; call 0x8006EA54; return.
    words = [
        struct.pack("<I", 0x00802821),  # move  a1,a0
        struct.pack("<I", 0x3C048010),  # lui   a0,0x8010
        encode_jump(0x02, 0x8006EA54),  # j     0x8006EA54 (preserve caller ra)
        struct.pack("<I", 0x2484C900),  # addiu a0,a0,-0x3700 (delay slot)

        # 0x800F8354: cooperative guard.
        struct.pack("<I", 0x3C02801C),  # lui   v0,0x801C
        struct.pack("<I", 0x8C427678),  # lw    v0,0x7678(v0)
        struct.pack("<I", 0x00000000),  # nop   (load delay)
        encode_branch(0x04, 2, 0, GUARD_ADDRESS + 0x0C, WAIT_LOOP_ADDRESS),
        struct.pack("<I", 0x00000000),  # nop   (branch delay)
        encode_jump(0x02, SERVICE_ROUTINE_ADDRESS),  # j 0x800F7024
        struct.pack("<I", 0x00000000),  # nop   (jump delay)
    ]
    region = b"".join(words)
    if len(region) != 44:
        raise AssertionError(len(region))
    return region


PATCHED_WAIT_BRANCH = encode_branch(
    0x05, 2, 0, WAIT_BRANCH_ADDRESS, GUARD_ADDRESS
)
PATCH_REGION_BYTES = build_patch_region()
GUARD_BYTES = PATCH_REGION_BYTES[16:]

# Static byte-level expectations for auditability.
assert PATCHED_WAIT_BRANCH == bytes.fromhex("44 01 40 14")
assert PATCH_REGION_BYTES == bytes.fromhex(
    "21 28 80 00 10 80 04 3C 95 BA 01 08 00 C9 84 24 "
    "1C 80 02 3C 78 76 42 8C 00 00 00 00 B3 FE 40 10 "
    "00 00 00 00 09 DC 03 08 00 00 00 00"
)


# ---------------------------------------------------------------------------
# CD-ROM Mode2/Form1 EDC/ECC
# ---------------------------------------------------------------------------

EDC_LUT = [0] * 256
ECC_F_LUT = [0] * 256
ECC_B_LUT = [0] * 256

for _i in range(256):
    _edc = _i
    for _ in range(8):
        _edc = (_edc >> 1) ^ (0xD8018001 if (_edc & 1) else 0)
    EDC_LUT[_i] = _edc & 0xFFFFFFFF

    _j = ((_i << 1) ^ (0x11D if (_i & 0x80) else 0)) & 0xFF
    ECC_F_LUT[_i] = _j
    ECC_B_LUT[_i ^ _j] = _i


def edc_compute(data: bytes | bytearray) -> int:
    edc = 0
    for value in data:
        edc = (edc >> 8) ^ EDC_LUT[(edc ^ value) & 0xFF]
    return edc & 0xFFFFFFFF


def ecc_compute(
    source: bytes | bytearray,
    major_count: int,
    minor_count: int,
    major_mult: int,
    minor_inc: int,
) -> bytes:
    size = major_count * minor_count
    if len(source) < size:
        raise ValueError(f"ECC source too short: {len(source)} < {size}")

    dest = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        ecc_a = 0
        ecc_b = 0
        for _ in range(minor_count):
            temp = source[index]
            index += minor_inc
            if index >= size:
                index -= size
            ecc_a ^= temp
            ecc_b ^= temp
            ecc_a = ECC_F_LUT[ecc_a]
        ecc_a = ECC_B_LUT[ECC_F_LUT[ecc_a] ^ ecc_b]
        dest[major] = ecc_a
        dest[major + major_count] = ecc_a ^ ecc_b
    return bytes(dest)


def is_mode2_form1(sector: bytes | bytearray) -> bool:
    return (
        len(sector) == SECTOR_SIZE
        and sector[15] == 2
        and not (sector[18] & 0x20)
        and sector[16:20] == sector[20:24]
    )


def regenerate_mode2_form1(sector: bytearray) -> None:
    if not is_mode2_form1(sector):
        raise ValueError("Touched sector is not Mode2/Form1")

    sector[2072:2076] = struct.pack("<I", edc_compute(sector[16:2072]))

    # For Mode2/Form1 ECC, the four address/mode bytes are treated as zero.
    ecc_source = bytearray(sector)
    ecc_source[12:16] = b"\x00" * 4
    sector[2076:2248] = ecc_compute(ecc_source[12:2076], 86, 24, 2, 86)

    # Q parity includes the newly generated P parity.
    ecc_source[2076:2248] = sector[2076:2248]
    sector[2248:2352] = ecc_compute(ecc_source[12:2248], 52, 43, 86, 88)


def verify_mode2_form1(sector: bytes | bytearray) -> bool:
    if not is_mode2_form1(sector):
        return False
    expected = bytearray(sector)
    regenerate_mode2_form1(expected)
    return expected[2072:2352] == sector[2072:2352]


# ---------------------------------------------------------------------------
# Raw BIN helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gwin_file_offset_to_raw(file_offset: int) -> int:
    if not 0 <= file_offset < GWIN_SIZE:
        raise ValueError(f"GWIN.SOL file offset out of range: 0x{file_offset:X}")
    return (
        GWIN_LBA * SECTOR_SIZE
        + (file_offset // USER_SIZE) * SECTOR_SIZE
        + USER_OFFSET
        + (file_offset % USER_SIZE)
    )


def read_gwin_bytes(path: Path, file_offset: int, size: int) -> bytes:
    result = bytearray()
    remaining = size
    cursor = file_offset
    with path.open("rb") as handle:
        while remaining:
            within = cursor % USER_SIZE
            amount = min(remaining, USER_SIZE - within)
            handle.seek(gwin_file_offset_to_raw(cursor))
            result.extend(handle.read(amount))
            cursor += amount
            remaining -= amount
    return bytes(result)


def patch_gwin_bytes(path: Path, file_offset: int, data: bytes) -> set[int]:
    touched: set[int] = set()
    remaining = memoryview(data)
    cursor = file_offset
    with path.open("r+b") as handle:
        while remaining:
            sector_index = cursor // USER_SIZE
            within = cursor % USER_SIZE
            amount = min(len(remaining), USER_SIZE - within)
            lba = GWIN_LBA + sector_index
            raw = lba * SECTOR_SIZE + USER_OFFSET + within
            handle.seek(raw)
            handle.write(remaining[:amount])
            touched.add(lba)
            cursor += amount
            remaining = remaining[amount:]
    return touched


def regenerate_lbas(path: Path, lbas: set[int]) -> None:
    with path.open("r+b") as handle:
        for lba in sorted(lbas):
            handle.seek(lba * SECTOR_SIZE)
            sector = bytearray(handle.read(SECTOR_SIZE))
            if len(sector) != SECTOR_SIZE:
                raise ValueError(f"Short sector at LBA {lba}")
            regenerate_mode2_form1(sector)
            handle.seek(lba * SECTOR_SIZE)
            handle.write(sector)


def verify_lbas(path: Path, lbas: set[int]) -> None:
    with path.open("rb") as handle:
        for lba in sorted(lbas):
            handle.seek(lba * SECTOR_SIZE)
            sector = handle.read(SECTOR_SIZE)
            if not verify_mode2_form1(sector):
                raise ValueError(f"EDC/ECC verification failed at LBA {lba}")


def changed_lbas(original: Path, patched: Path) -> tuple[list[int], int]:
    changed: list[int] = []
    diff_bytes = 0
    with original.open("rb") as left, patched.open("rb") as right:
        lba = 0
        while True:
            a = left.read(SECTOR_SIZE)
            b = right.read(SECTOR_SIZE)
            if not a and not b:
                break
            if len(a) != len(b):
                raise ValueError("Original and patched BIN sizes differ")
            if a != b:
                changed.append(lba)
                diff_bytes += sum(x != y for x, y in zip(a, b, strict=True))
            lba += 1
    return changed, diff_bytes


def write_paired_cue(input_cue: Path, output_cue: Path, output_bin: Path) -> None:
    text = input_cue.read_text(encoding="ascii")
    lines = text.splitlines(keepends=True)
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        leading = line[: len(line) - len(stripped)]
        if stripped.upper().startswith("FILE ") and " BINARY" in stripped.upper():
            newline = (
                "\r\n"
                if line.endswith("\r\n")
                else "\n"
                if line.endswith("\n")
                else ""
            )
            lines[index] = f'{leading}FILE "{output_bin.name}" BINARY{newline}'
            replaced = True
            break
    if not replaced:
        raise ValueError(f"No FILE ... BINARY line found in {input_cue}")
    output_cue.write_text("".join(lines), encoding="ascii")


def verify_original(path: Path, allow_unverified_sha256: bool) -> str:
    if path.stat().st_size != EXPECTED_BIN_SIZE:
        raise ValueError(
            f"Unexpected BIN size: {path.stat().st_size}; expected {EXPECTED_BIN_SIZE}"
        )
    if path.stat().st_size % SECTOR_SIZE:
        raise ValueError("Input is not an exact 2352-byte-sector image")

    digest = sha256_file(path)
    if digest != EXPECTED_SHA256 and not allow_unverified_sha256:
        raise ValueError(
            "Input SHA-256 does not match the confirmed v1.1 image. "
            f"Expected {EXPECTED_SHA256}, got {digest}. "
            "Use --allow-unverified-sha256 only after independent byte-level review."
        )

    context_start = WAIT_BRANCH_FILE_OFFSET - 0x10
    actual_context = read_gwin_bytes(path, context_start, len(ORIGINAL_WAIT_CONTEXT))
    if actual_context != ORIGINAL_WAIT_CONTEXT:
        raise ValueError(
            "Original wait-loop context mismatch: "
            f"expected {ORIGINAL_WAIT_CONTEXT.hex(' ').upper()}, "
            f"got {actual_context.hex(' ').upper()}"
        )

    threshold = read_gwin_bytes(path, THRESHOLD_FILE_OFFSET, 4)
    if threshold != ORIGINAL_THRESHOLD:
        raise ValueError("Original 0xF0 threshold assertion failed")

    branch = read_gwin_bytes(path, WAIT_BRANCH_FILE_OFFSET, 4)
    if branch != ORIGINAL_WAIT_BRANCH:
        raise ValueError("Original wait branch assertion failed")

    patch_region = read_gwin_bytes(
        path, PATCH_REGION_FILE_OFFSET, len(ORIGINAL_PATCH_REGION)
    )
    if patch_region != ORIGINAL_PATCH_REGION:
        raise ValueError("Original live-wrapper byte assertion failed")

    original_lbas = {
        GWIN_LBA + WAIT_BRANCH_FILE_OFFSET // USER_SIZE,
        GWIN_LBA + PATCH_REGION_FILE_OFFSET // USER_SIZE,
    }
    verify_lbas(path, original_lbas)
    return digest


def verify_patched(path: Path, expected_lbas: set[int]) -> None:
    if read_gwin_bytes(path, THRESHOLD_FILE_OFFSET, 4) != ORIGINAL_THRESHOLD:
        raise ValueError("Patch changed the original 0xF0 threshold")
    if read_gwin_bytes(path, WAIT_BRANCH_FILE_OFFSET, 4) != PATCHED_WAIT_BRANCH:
        raise ValueError("Patched wait branch verification failed")
    if (
        read_gwin_bytes(path, PATCH_REGION_FILE_OFFSET, len(PATCH_REGION_BYTES))
        != PATCH_REGION_BYTES
    ):
        raise ValueError("Compact-wrapper/guard byte verification failed")
    verify_lbas(path, expected_lbas)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create the alpha GWIN.SOL-only cooperative DS97 v1.1 patch "
            "while preserving the original 0xF0 completion threshold."
        )
    )
    parser.add_argument("--input-bin", required=True, type=Path)
    parser.add_argument("--output-bin", required=True, type=Path)
    parser.add_argument("--input-cue", type=Path)
    parser.add_argument("--output-cue", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--allow-unverified-sha256",
        action="store_true",
        help="Allow a different SHA-256 only if all fixed byte assertions pass.",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    input_bin = args.input_bin.resolve()
    output_bin = args.output_bin.resolve()

    if not input_bin.is_file():
        raise FileNotFoundError(input_bin)
    if input_bin == output_bin:
        raise ValueError("Input and output BIN paths must differ")
    if output_bin.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite {output_bin}")
    if args.input_cue is None and args.output_cue is not None:
        raise ValueError("--output-cue requires --input-cue")
    if args.input_cue is not None and args.output_cue is None:
        raise ValueError("--input-cue requires --output-cue")
    if args.output_cue and args.output_cue.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite {args.output_cue}")

    print(f"Input BIN:  {input_bin}")
    print(f"Output BIN: {output_bin}")
    original_sha = verify_original(input_bin, args.allow_unverified_sha256)
    print(f"Original SHA256: {original_sha}")
    print("Original byte and EDC/ECC assertions: OK")

    output_bin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_bin, output_bin)

    touched = set()
    touched |= patch_gwin_bytes(output_bin, WAIT_BRANCH_FILE_OFFSET, PATCHED_WAIT_BRANCH)
    touched |= patch_gwin_bytes(
        output_bin, PATCH_REGION_FILE_OFFSET, PATCH_REGION_BYTES
    )
    regenerate_lbas(output_bin, touched)
    verify_patched(output_bin, touched)

    changed, diff_count = changed_lbas(input_bin, output_bin)
    expected = sorted(touched)
    if changed != expected:
        raise ValueError(f"Unexpected changed LBAs: expected {expected}, got {changed}")

    if args.input_cue is not None:
        input_cue = args.input_cue.resolve()
        output_cue = args.output_cue.resolve()
        if not input_cue.is_file():
            raise FileNotFoundError(input_cue)
        output_cue.parent.mkdir(parents=True, exist_ok=True)
        write_paired_cue(input_cue, output_cue, output_bin)
        print(f"Output CUE: {output_cue}")

    print(f"Preserved threshold: 0x800F7E3C = {ORIGINAL_THRESHOLD.hex(' ').upper()}")
    print(
        f"Wait branch: 0x800F7E40 -> 0x{GUARD_ADDRESS:08X} "
        f"({PATCHED_WAIT_BRANCH.hex(' ').upper()})"
    )
    print(
        f"Compact wrapper: 0x{PATCH_REGION_ADDRESS:08X}, 16 bytes; "
        f"guard: 0x{GUARD_ADDRESS:08X}, {len(GUARD_BYTES)} bytes; "
        f"service routine 0x{SERVICE_ROUTINE_ADDRESS:08X}"
    )
    print(f"Changed LBAs: {', '.join(map(str, changed))}")
    print(f"Changed bytes including regenerated EDC/ECC: {diff_count}")
    print("Patched-sector EDC/ECC verification: OK")
    print(f"Patched SHA256: {sha256_file(output_bin)}")
    print(
        "Runtime status: post-win recovery confirmed on no$psX 2.3; "
        "long-term operation, existing-save compatibility, save/reload, "
        "repeated wins, and other emulators remain unconfirmed."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
