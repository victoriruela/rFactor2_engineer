# Test Fixtures — MoTeC .ld Binary

Synthetic `.ld` binary files for use in `ld_parser` unit and integration tests.

All fixtures are generated deterministically by `scripts/generate_fixtures.py` (Python 3.7+, no deps).

## Files

| File | Size | Description | Expected parser result |
|---|---|---|---|
| `minimal_valid_ld3.ld` | 4220 B | Valid LD3 file with 2 channels: `EngineRPM` (Uint16, 50 samples, 100 Hz) and `ThrottlePos` (Float32, 50 samples, 100 Hz) | `Ok(LdFile)` with 2 `ChannelMeta` entries |
| `bad_magic.ld` | 3072 B | Valid structure but magic bytes = `0xDEADBEEF` | `Err(ParseError::UnknownMagic)` |
| `unsupported_version.ld` | 3072 B | Valid magic; version field = 99 | `Err(ParseError::UnsupportedVersion)` |
| `channel_unknown_type.ld` | varies | Valid header; 1 channel with `type_id = 0x0099` | `Ok(LdFile { channels: [] })` + `ParseWarning::UnsupportedDataType` |

## Regenerating

```bash
python scripts/generate_fixtures.py
```

## Data Layout — `minimal_valid_ld3.ld`

```
Offset      Size    Content
0x0000      0x0C00  File header (LD3, magic=0x0045F836, version=1)
0x0C00      0x01A8  Channel 0 descriptor (EngineRPM, Uint16)
0x0DA8      0x01A8  Channel 1 descriptor (ThrottlePos, Float32)
0x0F50      0x0064  EngineRPM data: 50 × u16 LE, values 0,100,200,...,4900
0x0FB4      0x00C8  ThrottlePos data: 50 × f32 LE, values 0.0..1.0 linear
```
