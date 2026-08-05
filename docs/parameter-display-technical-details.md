# Parameter Display Technical Details

## Evidence Boundary

This document records the exact deterministic output of
`patch_ds97_parameter_display.py` and the tested runtime scope.

- Byte-level patch derivation: statically verified
- Decompressed runtime code: statically verified
- Mode2/Form1 EDC, ECC P, and ECC Q: regenerated and verified
- Full output SHA-256: verified against the exact cooperative freeze-fix input
- Parameter display: runtime-confirmed on no$psX 2.3
- Native race-result preservation: runtime-confirmed on no$psX 2.3
- Post-win progression and farm return: runtime-confirmed on no$psX 2.3
- In-game save and cold-boot reload: runtime-confirmed on no$psX 2.3
- DuckStation testing of the optional display patch: unconfirmed
- Horse switching, screen reopen, stallion pedigree, and broodmare-market screens:
  not separately recorded for this final `record+0x18` build
- Long-term operation: unconfirmed

The cooperative post-win freeze patch used as input is independently
runtime-confirmed on no$psX 2.3 and DuckStation.

No game image, extracted game file, BIOS, save, savestate, RAM dump, or binary
patch payload is included.

## Authority Images

Cooperative post-win freeze-fix input:

```text
size:    405,917,568 bytes
SHA-256: f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84
```

Runtime-confirmed COMPACT2R1 development authority:

```text
SHA-256: 3f1f1d9f3016feb8f304c3b94afd3ba146296b7b83cea411d016276ab0d4d456
```

Public `record+0x18` target:

```text
SHA-256: fc66ceed0d09abbf73725321500eefc6486404d2bd01f90f5838bff9d5df484b
```

The authority hashes identify locally owned test images. The images themselves
are not distributed or tracked.

## Corrected `record+0x18` Derivation

An earlier unpublished converter assumed that COMPACT2R1 changed the native
source instruction at `FARMMAIN+0x0AC65B`. It does not. Both the freeze-fix
input and COMPACT2R1 contain:

```text
FARMMAIN+0x0AC65B = 0x30
runtime 0x800F8D3C = 30 00 B2 26
```

COMPACT2R1 changes the displayed pointer inside its post-race helper:

```text
runtime 0x8010E5F4
DA FF B5 26
addiu s5,s5,-0x26
record+0x40-0x26 = record+0x1A
```

The public target changes only that helper adjustment:

```text
runtime 0x8010E5F4
D8 FF B5 26
addiu s5,s5,-0x28
record+0x40-0x28 = record+0x18
```

The corresponding literal is in the compressed FARMMAIN stream at
`FARMMAIN+0x0B907B` and maps to runtime address `0x8010E5F4` after
decompression.

## Component Hashes

| Component | Input SHA-256 | Output SHA-256 |
|---|---|---|
| Full raw BIN | `f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84` | `fc66ceed0d09abbf73725321500eefc6486404d2bd01f90f5838bff9d5df484b` |
| `DATA/FARM/FARMMAIN.BIN` | `9c84ae7390c1d5ff3a7ed0760207dcf885f530a19b7a9ea9f7a693524268cb50` | `33fa367c86fec0035f1c1f7bb01df87f428d99df0b97649c5d9b683b34876b89` |
| FARMMAIN compressed slot | `f4bdf08df65b0a1d4b6c64ce71e6ee251c5e8c4cb623ec5d790b03181cabdc31` | `ed1467421ef478c31a317fcf8bce9a329b9eec09efe3dd3037ec2cdb7a900c60` |
| Decompressed FARM overlay | `7583da95bab0b1c69ea6243fc51f8ed544b8c35ec76bd0a750b2d7fde29e4ca5` | `2abd1c6085b72622318ad311fd7a1fcfb51a87e2eea592a360f16dd0ed2cccd8` |
| Final 140-byte helper | n/a | `6bcb6c52fb7068b335e3a8d6d9c4f8e925a67022f4d25fea482fcad7228b67ee` |

## Runtime Code Verification

| Runtime address | Final bytes | Meaning |
|---:|---|---|
| `0x800F8D3C` | `30 00 B2 26` | Native `record+0x30` source remains unchanged |
| `0x800F8E24` | `89 39 04 08` | Loop-exit hook to `0x8010E624` |
| `0x800F8EA4` | `7D 39 04 08` | Post-race hook to helper `0x8010E5F4` |
| `0x8010E5F4` | `D8 FF B5 26` | Helper selects `record+0x18` |

The native results loop runs normally. After it has produced the real race
record, the helper re-enters the native four-line numeric renderer with the
parameter pointer. This preserves the race result while replacing only the
four course-stat lines.

## Disc Difference Isolation

Freeze-fix input to public target:

```text
changed sectors:           2
changed LBAs:              38361, 38387
changed logical user data: 147 bytes
changed raw bytes:         503 bytes including regenerated EDC/ECC
```

COMPACT2R1 authority to public target:

```text
changed sectors:           1
changed LBA:               38387
changed logical user data: 1 byte
changed raw bytes:         37 bytes including regenerated EDC/ECC
```

The output retains the input size and sector count.

## Patcher Guards

- Exact input size and SHA-256 are required.
- Exact input FARMMAIN, compressed slot, and decompressed overlay hashes are
  required.
- Every compressed patch region must match its complete expected old bytes.
- Patched FARMMAIN, compressed slot, decompressed overlay, and helper hashes
  must match.
- Native `0x800F8D3C` must remain unchanged.
- Only LBAs `38361` and `38387` may differ.
- Logical and raw difference counts must be exactly `147` and `503`.
- Both touched sectors must pass Mode2/Form1 EDC, ECC P, and ECC Q verification.
- The final full-image SHA-256 must match the deterministic target hash.
- The input BIN is rehashed after output verification.
- Existing output files are not replaced unless `--force` is explicit.
- Audit JSON records filenames rather than absolute local paths.

## Automated Tests

Run from the repository root:

```powershell
py -3 -m pytest -q
```

The parameter-display suite covers fixed hashes and offsets, complete old/new
patch regions, the `-0x28` pointer adjustment, display layout, EDC/ECC,
Mode2/Form1 rebuilding, DS97 LZ decoding, output naming, CUE generation,
rejection guards, audit privacy, runtime-evidence metadata, and no-game-image
packaging.
