# Changelog

## Unreleased

- Clarify that post-win recovery is runtime-confirmed on no$psX 2.3
- Keep long-term operation and save compatibility explicitly unresolved
- Explain the required raw 2352-byte-sector BIN/CUE format
- Document the confirmed patched BIN SHA-256

## v0.1.0-alpha

- Initial experimental public release
- GWIN.SOL-only cooperative post-win freeze workaround
- Preserves the original 0xF0 completion threshold
- Validates input image and original instructions
- Regenerates and verifies CD-ROM EDC/ECC
- Writes a separate output BIN/CUE
- No game, BIOS, save, or binary patch data included
