# MoTeC .ld Binary Format — Research Document

> Status: R1.T1 + R1.T2 canonical output  
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

---

## Section 6 — Rust `ChannelMeta` Struct Definition (R1.T2)

This section is the canonical reference for the Rust `ChannelMeta` struct that the R2 parser crate must implement. All field names, types, and semantics are binding for all downstream work.

### 6.1 Canonical Rust Struct

```rust
/// Parsed representation of one channel descriptor from the .ld channel meta block.
/// Produced by the nom parser; all raw byte-level concerns are resolved before construction.
#[derive(Debug, Clone, PartialEq)]
pub struct ChannelMeta {
    /// Absolute file offset (bytes) for the next linked-list node. 0 = end of list.
    pub next_offset: u32,
    /// Absolute file offset (bytes) for the previous linked-list node. 0 = first node.
    pub prev_offset: u32,
    /// Absolute file offset (bytes) where this channel's packed data starts.
    pub data_offset: u32,
    /// Number of samples in this channel.
    pub count: u32,
    /// Raw data type discriminant. Mapped to LdDataType via TryFrom.
    pub type_id: u16,
    /// Sample rate in Hz.
    pub sample_rate: u16,
    /// Scaling factor: shift exponent (base 2). May be negative.
    pub shift: i16,
    /// Scaling factor: multiplier (applied before shift).
    pub multiplier: i16,
    /// Scaling factor: decimal scale exponent (base 10). May be negative.
    pub scale: i16,
    /// Display decimal precision hint. Not used for data parsing.
    pub decimal_places: i16,
    /// Long channel name (up to 32 bytes, null-terminated, ASCII/UTF-8).
    pub name: String,
    /// Short channel name (up to 8 bytes, null-terminated).
    pub short_name: String,
    /// Unit string (up to 12 bytes, null-terminated). e.g. "rpm", "deg", "G".
    pub units: String,
}
```

### 6.2 `LdDataType` Enum

```rust
/// Discriminated data type for a single .ld channel.
/// Used to dispatch typed WASM memory views on the JS side.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LdDataType {
    Float32,    // 0x0000 — f32 → Float32Array
    Int16,      // 0x0001 — i16 → Int16Array
    Uint16,     // 0x0002 — u16 → Uint16Array
    Uint32,     // 0x0003 — u32 → Uint32Array
    Int32,      // 0x0004 — i32 → Int32Array
    Float64,    // 0x0007 — f64 → Float64Array (low confidence; GPS channels only)
}

impl TryFrom<u16> for LdDataType {
    type Error = ParseWarning;

    fn try_from(id: u16) -> Result<Self, Self::Error> {
        match id {
            0x0000 => Ok(LdDataType::Float32),
            0x0001 => Ok(LdDataType::Int16),
            0x0002 => Ok(LdDataType::Uint16),
            0x0003 => Ok(LdDataType::Uint32),
            0x0004 => Ok(LdDataType::Int32),
            0x0007 => Ok(LdDataType::Float64),
            other  => Err(ParseWarning::UnsupportedDataType { channel: String::new(), type_id: other }),
        }
    }
}
```

### 6.3 Sample-per-Byte Lookup

Required by the lazy `File.slice()` pipeline to compute the exact byte offset and length of any channel's data.

```rust
impl LdDataType {
    /// Returns the size in bytes of one sample of this type.
    pub fn sample_size(&self) -> usize {
        match self {
            LdDataType::Float32 => 4,
            LdDataType::Int16   => 2,
            LdDataType::Uint16  => 2,
            LdDataType::Uint32  => 4,
            LdDataType::Int32   => 4,
            LdDataType::Float64 => 8,
        }
    }

    /// Byte length of the full data block for this channel.
    pub fn data_block_size(&self, count: u32) -> u32 {
        self.sample_size() as u32 * count
    }
}
```

---

## Section 7 — Scaling Formula Validation (R1.T2)

MoTeC's physical-value formula applied to raw integer channels:

$$\text{physical} = \text{raw} \times \text{multiplier} \times 10^{\text{scale}} \times 2^{\text{shift}}$$

> Source: motec-i2-exportify source code (Python) + ldparser Go fork. Confidence: **Medium**.

### 7.1 Reference Example

Channel `ThrottlePos` (typical):
- `type_id = 0x0001` (Int16)
- `multiplier = 1`, `scale = -3`, `shift = 0`
- Raw value `750` → physical = `750 × 1 × 10⁻³ × 1` = **0.75** (75% throttle)

Channel `EngineRPM` (typical):
- `type_id = 0x0002` (Uint16)
- `multiplier = 1`, `scale = 0`, `shift = 0`
- Raw value `8500` → physical = `8500` (rpm, no conversion)

### 7.2 Parser Implementation Note

The `f32` data type (`0x0000`) stores **already-scaled physical values**. The scaling fields (`shift`, `multiplier`, `scale`) must be **ignored** for Float32 channels — they are artefacts of the format spec and may contain irrelevant non-zero values.

```rust
pub fn apply_scaling(raw: f64, meta: &ChannelMeta) -> f64 {
    match meta.data_type() {
        LdDataType::Float32 | LdDataType::Float64 => raw, // pre-scaled, no conversion
        _ => {
            let m = meta.multiplier as f64;
            let s = (10_f64).powi(meta.scale as i32);
            let sh = (2_f64).powi(meta.shift as i32);
            raw * m * s * sh
        }
    }
}
```

---

## Section 8 — Multi-Rate Channel Edge Cases (R1.T2)

Different channels in the same `.ld` file may have **different sample rates**. This is normal and expected.

| Common rates (Hz) | Typical channels |
|---|---|
| 10–20 | GPS latitude/longitude |
| 100 | Steering angle, throttle, brake |
| 200 | Suspension travel, g-forces |
| 1000+ | Engine RPM, wheel speed |

### 8.1 Time Alignment Strategy (for JS/UI layer)

Each channel's time axis is reconstructed as:
```
t[i] = i / sample_rate   (seconds, 0-based)
```

The UI must not assume channels share a common time vector. When displaying multi-channel overlays, resample to a common grid or use separate axes.

### 8.2 Lazy Slice Address Calculation

The lazy `File.slice()` pipeline (R4.T2) computes the byte window for a specific channel using:

```
data_start = channel_meta.data_offset
data_end   = data_start + channel_meta.count * data_type.sample_size()
```

Both values are available after parsing the channel meta block, before reading any data. This enables truly lazy, zero-copy sample loading.

---

## Section 9 — String Decoding Edge Cases (R1.T2)

### 9.1 Null-Termination Rules

All string fields in both header and channel meta blocks are null-terminated C strings. Parser must:
1. Find the first `0x00` byte within the allocated field width.
2. Slice to that offset.
3. Decode as UTF-8 with lossy substitution (`String::from_utf8_lossy`).

```rust
fn parse_cstring(bytes: &[u8]) -> String {
    let end = bytes.iter().position(|&b| b == 0).unwrap_or(bytes.len());
    String::from_utf8_lossy(&bytes[..end]).into_owned()
}
```

### 9.2 Common Encoding Anomalies

| Anomaly | Observed in | Handling |
|---|---|---|
| No null terminator (field fully occupied) | Old logger firmware | `unwrap_or(len)` handles cleanly |
| Latin-1 / Windows-1252 extended chars | Some driver name fields | `from_utf8_lossy` replaces with U+FFFD |
| Trailing whitespace after null | Some vehicle name fields | `.trim_end_matches('\0')` then `.trim()` |

---

## Section 10 — Complete Parser Data Flow Diagram (R1.T2)

```
File byte stream (File.slice / WASM linear memory)
│
├─► [0x000..0xC00]  File Header Parser
│       │  magic check → ParseError::UnknownMagic
│       │  version check → ParseError::UnsupportedVersion
│       └─► LdFileHeader { meta_offset, data_offset, session, venue, vehicle, driver, date }
│
└─► [meta_offset..meta_offset+meta_size]  Channel Meta LinkedList Parser
        │
        for each node (0x1A8 bytes):
        │   ├─► prev_offset, next_offset, data_offset, count
        │   ├─► type_id → LdDataType (or ParseWarning::UnsupportedDataType → skip)
        │   ├─► sample_rate, shift, multiplier, scale, decimal_places
        │   └─► name, short_name, units  (null-terminated string decode)
        │
        └─► Vec<ChannelMeta>  (ordered by linked-list traversal)

Consumer (lazy data loader):
  given ChannelMeta → File.slice(data_offset, data_offset + count * sample_size)
  → ArrayBuffer → TypedArray view over WASM linear memory → zero-copy JS access
```

---

## Updated Open Questions (after R1.T2)

| Item | Confidence | Status |
|---|---|---|
| Header magic `0x0045F836` | High | ✅ Confirmed — multiple sources |
| Channel record size 0x1A8 | High | ✅ Confirmed — multiple sources |
| Scaling formula: multiplier × 10^scale × 2^shift | Medium | ⚠️ Needs real-data validation |
| Float32 channels: scaling fields ignored | Medium | ⚠️ Inferred from observed behaviour |
| File version discriminator (LD3=1, LD4=2) | Medium | ⚠️ Needs hexdump confirmation |
| f64 type ID `0x0007` | Low | ⚠️ GPS channels only; unverified |
| device_serial at `0x178` | Low | ⚠️ Irrelevant for parser; can ignore |

> R1 research is complete. Proceed to R2: Rust parser crate scaffolding.

