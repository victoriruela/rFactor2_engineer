use nom::{
    bytes::complete::take,
    number::complete::{le_i16, le_u16, le_u32},
    sequence::tuple,
    IResult,
};

use crate::domain::ChannelMeta;
use crate::error::{ParseError, ParseWarning};
use crate::types::LdDataType;
use crate::utils::parse_cstring;

/// Byte size of a single channel descriptor record in the linked list (LD3/LD4).
pub const CHANNEL_RECORD_SIZE: usize = 0x01A8;
/// Byte size of a single channel descriptor record for ADL v0 format.
pub const CHANNEL_RECORD_SIZE_V0: usize = 0x7C;

/// Detect which channel record format is in use by inspecting the spacing between
/// the first and second channel records.  Falls back to LD3 size if there is only
/// one channel or the next_offset is out of range.
fn detect_record_size(buf: &[u8], first_offset: u32) -> usize {
    let start = first_offset as usize;
    if start + 8 > buf.len() {
        return CHANNEL_RECORD_SIZE;
    }
    let next_off = u32::from_le_bytes(
        buf[start + 4..start + 8].try_into().unwrap_or([0; 4]),
    );
    if next_off > first_offset {
        let spacing = (next_off - first_offset) as usize;
        if spacing == CHANNEL_RECORD_SIZE_V0 {
            return CHANNEL_RECORD_SIZE_V0;
        }
    }
    CHANNEL_RECORD_SIZE
}

/// Parse all channel descriptors by traversing the linked list using nom.
///
/// `buf`: the **entire** file byte slice (must cover all meta nodes).
/// `first_offset`: absolute file offset of the first channel record (from header).
/// `file_len`: total file byte length (for bounds checking).
///
/// Returns `(Vec<ChannelMeta>, Vec<ParseWarning>)`.
/// Channels with unknown type_ids are included with a fallback Uint16 type in ADL v0
/// format; in LD3/LD4 format they are skipped (warning emitted).
pub fn parse_channels(
    buf: &[u8],
    first_offset: u32,
    file_len: usize,
) -> Result<(Vec<ChannelMeta>, Vec<ParseWarning>), ParseError> {
    let record_size = detect_record_size(buf, first_offset);
    let is_v0 = record_size == CHANNEL_RECORD_SIZE_V0;

    let mut channels = Vec::new();
    let mut warnings = Vec::new();
    let mut cursor = first_offset;

    loop {
        let start = cursor as usize;
        if start + record_size > file_len {
            return Err(ParseError::OffsetOutOfBounds {
                offset: cursor,
                record_size,
                file_len,
            });
        }

        let rec = &buf[start..start + record_size];
        let (_, mut raw) = if is_v0 {
            nom_channel_record_v0(rec).map_err(|e| ParseError::NomError(format!("{e:?}")))?
        } else {
            nom_channel_record(rec).map_err(|e| ParseError::NomError(format!("{e:?}")))?
        };

        let next_offset = raw.next_offset;

        // Handle data-type validation.
        if LdDataType::from_type_id(raw.type_id).is_none() {
            if is_v0 {
                // ADL v0 type_id is derived from dtype and should always be valid (0x0001/0x0004/0x0008).
                // Fall back to Int16 if an unexpected value slips through.
                raw.type_id = 0x0001; // Int16
            } else {
                warnings.push(ParseWarning::UnsupportedDataType {
                    channel: raw.name.clone(),
                    type_id: raw.type_id,
                });
                if next_offset == 0 { break; }
                cursor = next_offset;
                continue;
            }
        }

        channels.push(raw);

        if next_offset == 0 {
            break;
        }
        cursor = next_offset;
    }

    Ok((channels, warnings))
}

// -------------------------------------------------------------------------
// nom combinators — single channel record
// -------------------------------------------------------------------------

fn nom_channel_record(input: &[u8]) -> IResult<&[u8], ChannelMeta> {
    let (rest, (prev_offset, next_offset, data_offset, count)) =
        tuple((le_u32, le_u32, le_u32, le_u32))(input)?;
    let (rest, (type_id, sample_rate)) = tuple((le_u16, le_u16))(rest)?;
    let (rest, (shift, multiplier, scale, decimal_places)) =
        tuple((le_i16, le_i16, le_i16, le_i16))(rest)?;

    // Fixed-width null-terminated strings
    let (rest, name_bytes)       = take(32usize)(rest)?; // 0x01C..0x03C
    let (rest, short_name_bytes) = take(8usize)(rest)?;  // 0x03C..0x044
    let (rest, units_bytes)      = take(12usize)(rest)?; // 0x044..0x050

    // Skip remaining padding to CHANNEL_RECORD_SIZE (0x1A8)
    // Consumed so far: 4+4+4+4 + 2+2 + 2+2+2+2 + 32+8+12 = 80 = 0x50
    // Remaining pad: 0x1A8 - 0x50 = 0x158
    let (rest, _) = take(0x158usize)(rest)?;

    let meta = ChannelMeta {
        prev_offset,
        next_offset,
        data_offset,
        count,
        type_id,
        sample_rate,
        shift,
        multiplier,
        scale,
        decimal_places,
        name:         parse_cstring(name_bytes),
        short_name:   parse_cstring(short_name_bytes),
        units:        parse_cstring(units_bytes),
    };

    Ok((rest, meta))
}

/// ADL v0 channel record (0x7C bytes).
///
/// Corrected field layout (verified against .mat reference data):
///
/// +0x00..+0x0F : prev/next/data_offset/count (4×u32)
/// +0x10        : counter (u16) — sequential channel counter, not used for parsing
/// +0x12        : dtype_a (u16) — data class: 3=int16, 5=int32; used as type_id
/// +0x14        : dtype  (u16) — bytes per sample: 1=i8, 2=i16, 4=i32
/// +0x16        : rec_freq (u16) — ACTUAL sample rate in Hz (10, 50, 5, …)
/// +0x18        : legacy_shift (i16) — additive offset used in physical conversion
/// +0x1A        : mul   (i16) — raw multiplier
/// +0x1C        : scale (i16) — raw divisor (almost always 1)
/// +0x1E        : dec   (i16) — decimal exponent: result /= 10^dec
/// +0x20..+0x3F : name (32 bytes)
/// +0x40..+0x47 : short_name (8 bytes)
/// +0x48..+0x53 : units (12 bytes)
/// +0x54        : marker_a (i16)
/// +0x56        : marker_b (i16)
/// +0x58        : zero_offset (i16) — auxiliary coefficient (do not use as primary shift)
/// +0x5A        : marker_c (i16)
/// +0x5C..+0x7B : padding (to total 0x7C bytes)
///
/// Physical value formula:  physical = (raw + legacy_shift) * mul / (scale × 10^dec)
fn nom_channel_record_v0(input: &[u8]) -> IResult<&[u8], ChannelMeta> {
    let (rest, (prev_offset, next_offset, data_offset, count)) =
        tuple((le_u32, le_u32, le_u32, le_u32))(input)?;

    // +0x10: counter (ignored), +0x12: dtype_a → not needed since we derive type_id from dtype
    let (rest, (_counter, _dtype_a)) = tuple((le_u16, le_u16))(rest)?;

    // +0x14: dtype (bytes/sample), +0x16: rec_freq (Hz)
    // Map dtype → LD type_id: 1→Int16(treat as i8 by reading only low byte), 2→Int16, 4→Int32
    let (rest, (dtype, sample_rate)) = tuple((le_u16, le_u16))(rest)?;
    // Map ADL v0 dtype (bytes/sample) to LD-compatible type_id:
    // dtype=1 (signed byte, e.g. Gear) → 0x0008 (Int8)
    // dtype=2 (i16)                    → 0x0001 (Int16)
    // dtype=4 (i32, GPS channels)      → 0x0004 (Int32)
    // Any other value defaults to Int16 (best guess).
    let type_id: u16 = match dtype {
        1 => 0x0008, // Int8 (Gear uses 1-byte signed samples)
        2 => 0x0001, // Int16
        4 => 0x0004, // Int32 (GPS latitude/longitude)
        _ => 0x0001,
    };

    // +0x18..+0x1F: legacy_shift, mul, scale, dec
    let (rest, (legacy_shift, multiplier, scale, decimal_places)) =
        tuple((le_i16, le_i16, le_i16, le_i16))(rest)?;

    // Fixed-width null-terminated strings
    let (rest, name_bytes)       = take(32usize)(rest)?; // +0x20..+0x3F
    let (rest, short_name_bytes) = take(8usize)(rest)?;  // +0x40..+0x47
    let (rest, units_bytes)      = take(12usize)(rest)?; // +0x48..+0x53

    // +0x54..+0x5B carry extra ADL v0 coefficients that we currently preserve only for layout parity.
    let (rest, (_marker_a, _marker_b, _zero_offset, _marker_c)) =
        tuple((le_i16, le_i16, le_i16, le_i16))(rest)?;

    // Remaining pad: 0x7C - 0x5C = 0x20
    let (rest, _) = take(0x20usize)(rest)?;

    let meta = ChannelMeta {
        prev_offset,
        next_offset,
        data_offset,
        count,
        type_id,
        sample_rate,
        // For ADL v0 we expose legacy_shift through `shift` so JS can apply:
        // physical = (raw + shift) * multiplier / (scale * 10^decimal_places)
        shift: legacy_shift,
        multiplier,
        scale,
        decimal_places,
        name:       parse_cstring(name_bytes),
        short_name: parse_cstring(short_name_bytes),
        units:      parse_cstring(units_bytes),
    };

    Ok((rest, meta))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a minimal single-channel meta record (0x1A8 bytes).
    fn one_channel_record(
        next_offset: u32,
        type_id: u16,
        name: &[u8],
    ) -> Vec<u8> {
        let mut rec = vec![0u8; CHANNEL_RECORD_SIZE];
        // prev = 0 (first), next = next_offset
        rec[0x004..0x008].copy_from_slice(&next_offset.to_le_bytes());
        rec[0x008..0x00C].copy_from_slice(&0x2000u32.to_le_bytes()); // data_offset
        rec[0x00C..0x010].copy_from_slice(&100u32.to_le_bytes());    // count = 100
        rec[0x010..0x012].copy_from_slice(&type_id.to_le_bytes());
        rec[0x012..0x014].copy_from_slice(&200u16.to_le_bytes());     // sample_rate = 200 Hz
        // multiplier = 1
        rec[0x016..0x018].copy_from_slice(&1i16.to_le_bytes());
        // name
        let len = name.len().min(31);
        rec[0x01C..0x01C + len].copy_from_slice(&name[..len]);
        rec
    }

    #[test]
    fn single_float32_channel_parsed() {
        let rec = one_channel_record(0, 0x0000, b"ThrottlePos");
        let (channels, warnings) = parse_channels(&rec, 0, rec.len()).expect("should parse");
        assert_eq!(channels.len(), 1);
        assert!(warnings.is_empty());
        let ch = &channels[0];
        assert_eq!(ch.name, "ThrottlePos");
        assert_eq!(ch.type_id, 0x0000);
        assert_eq!(ch.count, 100);
        assert_eq!(ch.sample_rate, 200);
    }

    #[test]
    fn unknown_type_id_skipped_with_warning() {
        let rec = one_channel_record(0, 0x0099, b"UnknownChan");
        let (channels, warnings) = parse_channels(&rec, 0, rec.len()).expect("should parse");
        assert!(channels.is_empty());
        assert_eq!(warnings.len(), 1);
        assert!(matches!(
            &warnings[0],
            ParseWarning::UnsupportedDataType { type_id: 0x0099, .. }
        ));
    }

    #[test]
    fn offset_out_of_bounds_returns_error() {
        // first_offset > file length
        let buf = vec![0u8; 100];
        let result = parse_channels(&buf, 200, 100);
        assert!(matches!(result, Err(ParseError::OffsetOutOfBounds { .. })));
    }
}
