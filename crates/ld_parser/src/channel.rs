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

/// Byte size of a single channel descriptor record in the linked list.
pub const CHANNEL_RECORD_SIZE: usize = 0x01A8;

/// Parse all channel descriptors by traversing the linked list using nom.
///
/// `buf`: the **entire** file byte slice (must cover all meta nodes).
/// `first_offset`: absolute file offset of the first channel record (from header).
/// `file_len`: total file byte length (for bounds checking).
///
/// Returns `(Vec<ChannelMeta>, Vec<ParseWarning>)`.
/// Channels with unknown type_ids are skipped (warning emitted); iteration continues.
pub fn parse_channels(
    buf: &[u8],
    first_offset: u32,
    file_len: usize,
) -> Result<(Vec<ChannelMeta>, Vec<ParseWarning>), ParseError> {
    let mut channels = Vec::new();
    let mut warnings = Vec::new();
    let mut cursor = first_offset;

    loop {
        let start = cursor as usize;
        if start + CHANNEL_RECORD_SIZE > file_len {
            return Err(ParseError::OffsetOutOfBounds {
                offset: cursor,
                record_size: CHANNEL_RECORD_SIZE,
                file_len,
            });
        }

        let rec = &buf[start..start + CHANNEL_RECORD_SIZE];
        let (_, raw) = nom_channel_record(rec)
            .map_err(|e| ParseError::NomError(format!("{e:?}")))?;

        // Validate data type; skip channel with warning if unknown.
        let next_offset = raw.next_offset;
        match LdDataType::from_type_id(raw.type_id) {
            None => {
                warnings.push(ParseWarning::UnsupportedDataType {
                    channel: raw.name.clone(),
                    type_id: raw.type_id,
                });
                // Do not push to channels; continue to next.
            }
            Some(_) => {
                channels.push(raw);
            }
        }

        if next_offset == 0 {
            break;
        }
        cursor = next_offset;
    }

    Ok((channels, warnings))
}

// -------------------------------------------------------------------------
// nom combinator — single channel record
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::header::LD_MAGIC;

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
