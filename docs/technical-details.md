# Technical Details

## Evidence Boundary

This document summarizes the runtime-confirmed cooperative GWIN patch recorded in `ds97_analysis`.

- Post-win freeze workaround: runtime-confirmed on no$psX 2.3
- Post-win freeze workaround: runtime-confirmed on DuckStation
- Repeated-win progression: runtime-confirmed
- Existing-ranch load/save with the correct no$psX basename-specific MCD: runtime-confirmed for the tested procedure
- Long-term operation: unconfirmed
- Public state: alpha / experimental

No game image, extracted `GWIN.SOL`, BIOS, save, or binary patch payload is included.

## Target Image

- Game: Derby Stallion 97 v1.1 / SLPS-00777
- Original raw BIN size: `405,917,568` bytes
- Original SHA-256: `92fc3d8bae259f4167a5b72ff9e6d849b3c3790dc50140557ca965c8270b080a`
- Patched SHA-256 observed in runtime confirmation: `f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84`

## Wait Loop

The post-win wait loop reads `801C4BF0`.

```text
800F7E30  load [801C4BF0]
800F7E3C  slti v0,v0,0x00F0
800F7E40  branch while less than 0xF0
```

The original `0xF0` comparison is preserved. This matters because observed freezes occurred at more than one intermediate counter value, including `0xCC` and `0xC0`, so changing the threshold to `0xCC` is not a general fix and can skip pending update work.

## Cooperative Guard

The patch uses only `DATA/WINNING/GWIN.SOL`. It does not globally patch every overlay that may later occupy the same RAM range.

The wrapper at `800F8344..800F836C` is compacted into an equivalent tail-call wrapper:

```asm
800F8344  move  a1,a0
800F8348  lui   a0,0x8010
800F834C  j     0x8006EA54
800F8350  addiu a0,a0,0xC900
```

The freed GWIN-local region holds the guard:

```asm
800F8354  lui   v0,0x801C
800F8358  lw    v0,0x7678(v0)
800F835C  nop
800F8360  beqz  v0,0x800F7E30
800F8364  nop
800F8368  j     0x800F7024
800F836C  nop
```

`801C7678` is the pending flag checked by the guard. When pending work exists, the guard tail-jumps to the existing routine at `800F7024`. At the wait site, the live return address is `800F7E30`, so `800F7024` returns directly to the wait loop after servicing the pending frame.

## Why GWIN.SOL Only

The `0x800Fxxxx` RAM range is reused by multiple overlays. Unconditional RAM-address patching can affect unrelated scenes. The public script changes only bytes inside `DATA/WINNING/GWIN.SOL`, where the post-win wait loop and compact guard were audited.

## Static and Runtime Results

- Changed LBAs: `151663`, `151664`
- Changed bytes including regenerated EDC/ECC: `247`
- Mode2/Form1 EDC/ECC: regenerated and verified
- `800F7E3C` original `0xF0` threshold: preserved
- Runtime result: `801C4BF0` advanced to `0xF0`, and victory screen returned to the ranch without stopping
- DuckStation post-win recovery: runtime-confirmed
- Repeated-win progression: runtime-confirmed
- Existing-ranch load/save with the correct no$psX basename-specific MCD: runtime-confirmed for the tested procedure

## Memory-card Assignment Investigation

- no$psX may associate the first MCD with the CD image basename
- Renaming the patched CUE/BIN can select or create a different MCD
- The initially selected cooperative-image MCD did not match the known-good MCD
- Copying the known-good MCD to the cooperative-image basename resolved the mismatch
- Immediate save after loading succeeded
- Save after post-win recovery succeeded
- The failure was not reproduced with the correct MCD assignment
- The result does not support cooperative-patch save incompatibility
- Long-term operation remains unconfirmed

## Superseded F0 to CC Patch

The older one-byte `F0 -> CC` threshold change is superseded. It is not the method used by this repository.
