# Changelog

## Unreleased

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
