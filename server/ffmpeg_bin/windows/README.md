# Vendored Windows ffmpeg binaries

`ffmpeg.exe` and `ffprobe.exe` are static Windows x86-64 builds bundled so the
packaged app needs no system ffmpeg on the target machine.

| | |
|---|---|
| Source | https://github.com/GyanD/codexffmpeg/releases (gyan.dev builds) |
| Release | `9.0.2`, asset `ffmpeg-9.0.2-essentials_build.zip` |
| Variant | "essentials" — static, GPL, stripped |
| Size | ~105 MB each (~210 MB for the pair) |

The "essentials" variant is deliberate: the previous vendored pair was a full
BtbN build at 211 MB per binary, roughly double the size, and carried codecs
and hardware backends this app never invokes.

What the app actually needs, all present in this build:

- `libx264` — `encoder.py` re-encodes to H.264/libx264
- mp4 muxer with `+faststart` — same path
- AV1 decode (native decoder plus `libaom`) — AV1 inputs are the main
  re-encoding case
- `ffprobe` JSON output (`-print_format json -show_streams`) — `metadata.py`

`LICENSE.txt` is the build's license text, required for redistributing a GPL
build.

## Refreshing

Download the same `essentials_build.zip` asset from a newer release, take
`bin/ffmpeg.exe` and `bin/ffprobe.exe` (skip `ffplay.exe`, unused), and confirm
`file` reports `PE32+ executable ... x86-64` rather than a Git LFS pointer.
