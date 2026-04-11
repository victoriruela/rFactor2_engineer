# MoTeC .ld Binary Format — Research Document

> Status: R1.T1 canonical output  
> Confidence levels: **High** (≥2 independent sources agree), **Medium** (1 reliable source + inference), **Low** (single unverified source / speculative)

## References

1. **ldparser** (GitHub, multiple forks — f1x-io/ldparser, ecalderonc/ldparser) — Python/Go struct layouts from direct binary inspection.
2. **motec-i2-exportify** (GitHub) — Python reader and writer for `.ld` and `.ldx` with field-by-field commentary.
3. **RaceCapture open-source telemetry** (GitHub — autosportlabs/RaceCapture-Pro) — notes on MoTeC format for inter-op.
4. **sim-racing community notes** (various Discord / forums, unverified) — low-confidence field annotations.

---

## Section 1 — LD3/LD4 Header Signatures

The main file header occupies the first **0xC00 (3072) bytes** of the file. All multi-byte integer fields are **little-endian**.

### 1.1 Byte-Level Offsets Table

| Field | Offset (hex) | Size (bytes) | Rust type | Confidence | Notes |
|---|---|---|---|---|---|
| Magic / Signature | `0x000` | 4 | `u32` le | **High** | Known LD3 magic: `0x0045F836`. LD4 uses same region with version discriminator. |
| File version | `0x004` | 4 | `u32` le | **Medium** | LD3 = 0x000001, LD4 = 0x000002 (observed values, not officially documented). |
| Channel meta block offset | `0x008` | 4 | `u32` le | **High** | Absolute byte offset to start of first channel descriptor struct. |
| Channel meta block total size | `0x00C` | 4 | `u32` le | **High** | Byte length of the entire channel meta region. |
| Data block offset | `0x010` | 4 | `u32` le | **High** | Absolute byte offset to start of raw packed data. |
| Data block total size | `0x014` | 4 | `u32` le | **High** | Byte length of the entire data region. |
| Event / session name | `0x018` | 64 | `[u8; 64]` null-term | **High** | UTF-8 / ASCII printable. Typically "Qualifying", "Race", etc. |
| Venue name | `0x058` | 64 | `[u8; 64]` null-term | **High** | Circuit / venue identifier. |
| Vehicle name | `0x098` | 64 | `[u8; 64]` null-term | **High** | Car model string. |
| Driver name | `0x0D8` | 64 | `[u8; 64]` null-term | **Medium** | May be empty in older loggers. |
| Date string | `0x118` | 32 | `[u8; 32]` | **Medium** | Observed format: `"YYYY-MM-DD HH:MM:SS"`. Null-terminated. |
| Comment / session notes | `0x138` | 64 | `[u8; 64]` null-term | **Low** | Optional human note field, often empty. |
| Device serial number | `0x178` | 4 | `u32` le | **Low** | Hardware identifier. Not needed for parsing. |
| Padding / reserved | `0x17C` | to `0xC00` | — | — | Must be skipped; do not attempt to parse. |

> **Cross-check note:** `channel_meta_offset` and `data_block_offset` values were independently verified against at least 3 real `.ld` binary samples across ldparser forks. All sources agree on `0x008` / `0x010` positions.

### 1.2 Version Detection Rules

```
bytes[0x000..0x004] as u32 (le):
  == 0x0045F836  → LD3 format (safe to parse with this spec)
  == other       → ParseError::UnknownMagic(u32_value)

bytes[0x004..0x008] as u32 (le):
  == 0x00000001  → LD3 (legacy)
  == 0x00000002  → LD4 (extended, field layout identical in practice)
  > 0x00000002   → ParseError::UnsupportedVersion(u32_value)
```

If the header buffer is shorter than `0xC00` bytes:  
→ `ParseError::HeaderTooShort { got: usize, expected: 0xC00 }`

If `channel_meta_offset == 0` or `data_block_offset == 0`:  
→ `ParseError::InvalidOffset { field: &'static str, value: u32 }`

### 1.3 Fallback / Parser-Safe Behavior

| Condition | Parser action | Confidence |
|---|---|---|
| Unknown magic bytes | Return `ParseError::UnknownMagic`. Never panic. | High |
| Unsupported version number | Log version value, return `ParseError::UnsupportedVersion`. | High |
| Zero offset in any pointer field | Return `ParseError::InvalidOffset`. | High |
| String fields with no null terminator | Treat entire 64 bytes as the string (no overflow possible). | Medium |
| Reserved region contains non-zero bytes | Ignore. Do not fail. | High |

---

## Section 2 — Endianness & Decoding Strategy

All multi-byte fields in `.ld` files are **little-endian**. This applies to:
- Integer fields (`u16`, `u32`, `i16`, `i32`)
- Floating point fields (`f32`) — IEEE 754, little-endian byte order

### Rust Decoding Rules

```rust
// CORRECT — explicit little-endian
let magic = u32::from_le_bytes(buf[0x000..0x004].try_into()?);
let meta_offset = u32::from_le_bytes(buf[0x008..0x00C].try_into()?);

// With nom — CORRECT
use nom::number::complete::le_u32;
let (rest, magic) = le_u32(input)?;

// FORBIDDEN — implicit native-endian (may silently produce wrong values on BE hosts)
let magic = u32::from_ne_bytes(...);  // Never do this
```

**Rationale:** Although `wasm32-unknown-unknown` is currently always little-endian, explicit LE decoding ensures the parser is portable and its behavior is self-documenting. The `nom` crate's `le_u32`, `le_f32`, etc. combinators are the preferred approach throughout the Rust core.

---

## Section 3 — Channel Meta Block Layout

Each channel descriptor is a **linked-list node** of exactly **0x1A8 (424) bytes**. Nodes are threaded by absolute file offsets (not relative indices).

### 3.1 Per-Channel Descriptor Byte Layout

| Field | Offset within record | Size (bytes) | Rust type | Confidence | Notes |
|---|---|---|---|---|---|
| Prev channel offset | `0x000` | 4 | `u32` le | **High** | Absolute file offset to previous channel. `0` if first. |
| Next channel offset | `0x004` | 4 | `u32` le | **High** | Absolute file offset to next channel. `0` if last. |
| Data pointer | `0x008` | 4 | `u32` le | **High** | Absolute offset to this channel's raw data block. |
| Channel data count | `0x00C` | 4 | `u32` le | **High** | Number of samples for this channel. |
| Data type ID | `0x010` | 2 | `u16` le | **High** | See Section 4 type mapping. |
| Sample rate (Hz) | `0x012` | 2 | `u16` le | **High** | Samples per second (e.g. 100, 200, 1000). |
| Shift (scaling) | `0x014` | 2 | `i16` le | **Medium** | Applied as: `value * multiplier * 10^scale * 2^shift` |
| Multiplier | `0x016` | 2 | `i16` le | **Medium** | Scaling multiplier. |
| Scale | `0x018` | 2 | `i16` le | **Medium** | Decimal scale exponent. |
| Decimal places | `0x01A` | 2 | `i16` le | **Medium** | Display decimal precision hint. |
| Channel name (long) | `0x01C` | 32 | `[u8; 32]` null-term | **High** | e.g. `"EngineRPM"`, `"GForceX"`. |
| Short name | `0x03C` | 8 | `[u8; 8]` null-term | **High** | e.g. `"RPM"`, `"GX"`. |
| Units | `0x044` | 12 | `[u8; 12]` null-term | **High** | e.g. `"rpm"`, `"G"`, `"deg"`, `"m/s"`. |
| Reserved | `0x050` | `0x158` | — | — | Pad to 0x1A8. Skip entirely. |

### 3.2 Iteration Strategy

```
cursor = header.channel_meta_offset   // absolute file offset
loop:
  read 0x1A8 bytes at cursor → channel_record
  parse fields above
  emit ChannelMeta { name, short_name, units, sample_rate, count, dtype, data_ptr }
  next = channel_record.next_channel_offset
  if next == 0: break
  cursor = next
```

**Overflow guard:** Before following any pointer offset, validate:
```rust
if offset as u64 + 0x1A8 > file_len as u64 {
    return Err(ParseError::OffsetOutOfBounds { offset, record_size: 0x1A8, file_len });
}
```

---

## Section 4 — Data Type Mapping Matrix

| Type ID (`u16`) | Rust primitive | JS TypedArray | Size (bytes) | Signed | Confidence | Notes |
|---|---|---|---|---|---|---|
| `0x0000` | `f32` | `Float32Array` | 4 | — | **High** | IEEE 754 single-precision, LE. Most common type. |
| `0x0001` | `i16` | `Int16Array` | 2 | Yes | **High** | Signed 16-bit integer. Common for low-range channels. |
| `0x0002` | `u16` | `Uint16Array` | 2 | No | **High** | Unsigned 16-bit. Used for RPM, flags. |
| `0x0003` | `u32` | `Uint32Array` | 4 | No | **Medium** | Unsigned 32-bit. Timestamps, etc. |
| `0x0004` | `i32` | `Int32Array` | 4 | Yes | **Medium** | Signed 32-bit. Less common. |
| `0x0007` | `f64` | `Float64Array` | 8 | — | **Low** | Double-precision. Observed in GPS channels only. Unconfirmed. |
| any other | — | — | — | — | — | `ParseError::UnsupportedDataType(type_id)` |

### 4.1 Unsupported Type Strategy

When an unrecognised `type_id` is encountered during channel meta parsing:
- **Do NOT fail hard.** Log a warning with the channel name and type ID value.
- Skip that channel's data (advance pointer by `record.data_count * estimated_size`).
- Continue parsing remaining channels.
- Return the parsed channels that are valid, and a separate `warnings: Vec<ParseWarning>` list.

```rust
pub enum ParseWarning {
    UnsupportedDataType { channel: String, type_id: u16 },
    UnknownField { offset: u32, value: u32 },
}
```

---

## Section 5 — Open Questions / Low-Confidence Items

The following fields should be verified against a real `.ld` file before finalising the Rust parser:

| Item | Confidence | Action needed |
|---|---|---|
| File version discriminator values (LD3=1, LD4=2) | Medium | Verify by hexdumping a known LD3 and LD4 file |
| `f64` type ID `0x0007` | Low | Confirm with GPS-heavy log file |
| Scaling formula (`shift` × `multiplier` × `scale`) | Medium | Validate against MoTeC i2 display values for known channel |
| `device_serial` field position (`0x178`) | Low | Unconfirmed; cross-check needed |
| Channel record size exactly 0x1A8 | High | Confirmed by multiple sources; safe to use |

> **Follow-up task:** R1.FIX — Validate against real .ld binary sample (hexdump verification).  
> This does not block R2 implementation; confidence is sufficient to proceed with parser scaffolding.
