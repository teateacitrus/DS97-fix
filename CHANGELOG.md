# Changelog

## Unreleased

- Add `patch_ds97_parameter_display.py` as an optional second-stage patcher
- Preserve native race results while displaying `record+0x18..+0x27`
- Require the exact cooperative freeze-fix output as the parameter-patch input
- Record deterministic parameter-display output SHA-256 `fc66ceed...5df484b`
- Record no$psX 2.3 runtime confirmation for display, result preservation,
  post-win progression, save, and cold reload
- Add parameter layout, installation, technical validation, and troubleshooting
  documentation
- Clarify that post-win recovery is runtime-confirmed on no$psX 2.3
- Explain the required raw 2352-byte-sector BIN/CUE format
- Document the confirmed patched BIN SHA-256
- Record post-win recovery on DuckStation
- Record repeated-win progression
- Record successful existing-ranch load and save with the correct no$psX MCD assignment
- Document no$psX basename-specific MCD behavior
- Replace the previous save-compatibility warning with the confirmed MCD mismatch cause
- Keep long-term operation explicitly unconfirmed

## v0.1.0-alpha

- Initial experimental public release
- GWIN.SOL-only cooperative post-win freeze workaround
- Preserves the original 0xF0 completion threshold
- Validates input image and original instructions
- Regenerates and verifies CD-ROM EDC/ECC
- Writes a separate output BIN/CUE
- No game, BIOS, save, or binary patch data included
