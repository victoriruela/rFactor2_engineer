use nom::{
    bytes::complete::take,
    number::complete::le_u32,
    sequence::tuple,
    IResult,
};

use crate::domain::LdFileHeader;
use crate::error::ParseError;
use crate::utils::parse_cstring;

/// MoTeC LD3/LD4 file magic.
pub const LD_MAGIC: u32 = 0x0045_F836;
/// ADL / older MoTeC format magic (rFactor2 native .ld export).
pub const LD_MAGIC_V0: u32 = 0x0000_0040;
/// Minimum supported format version for LD3/LD4.
pub const LD_VERSION_MIN: u32 = 1;
/// Maximum supported format version.
pub const LD_VERSION_MAX: u32 = 2;
/// Expected minimum header size in bytes.
pub const HEADER_SIZE: usize = 0x0200; // conservative; actual usable region up to 0xC00

/// Returns true if the buffer starts with the ADL v0 header signature.
fn is_v0(buf: &[u8]) -> bool {
    buf.len() >= 8
        && u32::from_le_bytes(buf[0..4].try_into().unwrap_or([0; 4])) == LD_MAGIC_V0
        && u32::from_le_bytes(buf[4..8].try_into().unwrap_or([1; 4])) == 0
}

fn find_header_start(buf: &[u8]) -> Option<usize> {
    // ADL v0: magic is always at offset 0, version == 0.
    if is_v0(buf) {
        return Some(0);
    }
    // LD3/LD4: scan for magic + valid version anywhere in the prefix.
    let scan_end = buf.len().saturating_sub(8);
    for i in 0..=scan_end {
        let magic = u32::from_le_bytes(buf[i..i + 4].try_into().ok()?);
        if magic != LD_MAGIC {
            continue;
        }
        let version = u32::from_le_bytes(buf[i + 4..i + 8].try_into().ok()?);
        if (LD_VERSION_MIN..=LD_VERSION_MAX).contains(&version) {
            return Some(i);
        }
    }
    None
}

/// Parse the .ld file header from a byte slice using nom combinators.
///
/// The caller must supply at least `HEADER_SIZE` (0x200) bytes from the
/// start of the file via `File.slice(0, HEADER_SIZE)` before calling this.
///
/// Returns `Err(ParseError)` on any structural violation; never panics.
pub fn parse_header(input: &[u8]) -> Result<LdFileHeader, ParseError> {
    if input.len() < HEADER_SIZE {
        return Err(ParseError::HeaderTooShort { got: input.len(), expected: HEADER_SIZE });
    }
	let start = find_header_start(input).ok_or_else(|| {
		let found = if input.len() >= 4 {
			u32::from_le_bytes(input[0..4].try_into().unwrap_or([0u8; 4]))
		} else {
			0
		};
		ParseError::UnknownMagic { found }
	})?;
	let buf = &input[start..];

    // Pre-validate magic and version to give callers typed errors before nom runs.
    validate_magic_and_version(buf)?;
    validate_offsets(buf)?;

    let (_, mut hdr) = nom_header(buf).map_err(|e| ParseError::NomError(format!("{e:?}")))?;

    // ADL v0: data_offset is 0 in the file header.  Patch it with the first
    // channel record's data_offset so that callers can use it as a upper-bound
    // for the meta slice (readMetaSlice on the JS side).
    if hdr.data_offset == 0 {
        let ch_start = hdr.channel_meta_offset as usize;
        if ch_start + 12 <= input.len() {
            let first_data = u32::from_le_bytes(
                input[ch_start + 8..ch_start + 12].try_into().unwrap_or([0; 4]),
            );
            if first_data > 0 {
                hdr.data_offset = first_data;
            }
        }
    }

    Ok(hdr)
}

// -------------------------------------------------------------------------
// nom combinator — full header
// -------------------------------------------------------------------------

fn nom_header(input: &[u8]) -> IResult<&[u8], LdFileHeader> {
    let (rest, (magic, version, channel_meta_offset, channel_meta_size, data_offset, data_size)) =
        tuple((le_u32, le_u32, le_u32, le_u32, le_u32, le_u32))(input)?;

    let _ = magic; // already validated before calling this

    // String fields: consumed as fixed-width byte slices.
    let (rest, session_bytes)  = take(64usize)(rest)?; // 0x018..0x058
    let (rest, venue_bytes)    = take(64usize)(rest)?; // 0x058..0x098
    let (rest, vehicle_bytes)  = take(64usize)(rest)?; // 0x098..0x0D8
    let (rest, driver_bytes)   = take(64usize)(rest)?; // 0x0D8..0x118
    let (rest, date_bytes)     = take(32usize)(rest)?; // 0x118..0x138

    let hdr = LdFileHeader {
        version,
        channel_meta_offset,
        channel_meta_size,
        data_offset,
        data_size,
        session: parse_cstring(session_bytes),
        venue:   parse_cstring(venue_bytes),
        vehicle: parse_cstring(vehicle_bytes),
        driver:  parse_cstring(driver_bytes),
        date:    parse_cstring(date_bytes),
    };

    Ok((rest, hdr))
}

// -------------------------------------------------------------------------
// Typed validation helpers (used before nom, also re-exported for callers)
// -------------------------------------------------------------------------

/// Validate magic and version.
/// Accepts LD3/LD4 (magic=0x0045F836, version 1-2) and ADL v0 (magic=0x40, version=0).
/// Returns typed `ParseError` variants; use this before `parse_header` when
/// you need to distinguish magic vs version errors.
pub fn validate_magic_and_version(buf: &[u8]) -> Result<(), ParseError> {
    if buf.len() < 8 {
        return Err(ParseError::HeaderTooShort { got: buf.len(), expected: 8 });
    }
    let magic = u32::from_le_bytes(buf[0..4].try_into().expect("4 bytes"));
    // ADL v0 format: magic=0x40, version=0.
    if magic == LD_MAGIC_V0 {
        let version = u32::from_le_bytes(buf[4..8].try_into().expect("4 bytes"));
        if version == 0 {
            return Ok(());
        }
        return Err(ParseError::UnsupportedVersion { found: version });
    }
    // LD3/LD4 format.
    if magic != LD_MAGIC {
        return Err(ParseError::UnknownMagic { found: magic });
    }
    let version = u32::from_le_bytes(buf[4..8].try_into().expect("4 bytes"));
    if version < LD_VERSION_MIN || version > LD_VERSION_MAX {
        return Err(ParseError::UnsupportedVersion { found: version });
    }
    Ok(())
}

/// Validate that `channel_meta_offset` is non-zero, and `data_offset` is non-zero
/// for LD3/LD4 format (ADL v0 keeps data_offset=0 in the file header; each channel
/// record carries its own data_offset).
pub fn validate_offsets(buf: &[u8]) -> Result<(), ParseError> {
    if buf.len() < 0x18 {
        return Err(ParseError::HeaderTooShort { got: buf.len(), expected: 0x18 });
    }
    let meta_off = u32::from_le_bytes(buf[8..12].try_into().expect("4 bytes"));
    if meta_off == 0 {
        return Err(ParseError::InvalidOffset { field: "channel_meta_offset", value: 0 });
    }
    // Skip data_offset check for ADL v0 — it is always 0 in the file header.
    if !is_v0(buf) {
        let data_off = u32::from_le_bytes(buf[16..20].try_into().expect("4 bytes"));
        if data_off == 0 {
            return Err(ParseError::InvalidOffset { field: "data_offset", value: 0 });
        }
    }
    Ok(())
}

// -------------------------------------------------------------------------
// Tests
// -------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn minimal_header() -> Vec<u8> {
        let mut buf = vec![0u8; HEADER_SIZE];
        buf[0x000..0x004].copy_from_slice(&LD_MAGIC.to_le_bytes());
        buf[0x004..0x008].copy_from_slice(&1u32.to_le_bytes());          // LD3
        buf[0x008..0x00C].copy_from_slice(&0x0C00u32.to_le_bytes());
        buf[0x00C..0x010].copy_from_slice(&0x01A8u32.to_le_bytes());
        buf[0x010..0x014].copy_from_slice(&0x1000u32.to_le_bytes());
        buf[0x014..0x018].copy_from_slice(&0x0400u32.to_le_bytes());
        buf[0x018..0x021].copy_from_slice(b"TestSess\0");
        buf
    }

    #[test]
    fn valid_header_parses_correctly() {
        let buf = minimal_header();
        let hdr = parse_header(&buf).expect("should parse");
        assert_eq!(hdr.version, 1);
        assert_eq!(hdr.channel_meta_offset, 0x0C00);
        assert_eq!(hdr.data_offset, 0x1000);
        assert_eq!(hdr.session, "TestSess");
        assert_eq!(hdr.venue, "");
    }

    #[test]
    fn wrong_magic_returns_typed_error() {
        let mut buf = minimal_header();
        buf[0x000..0x004].copy_from_slice(&0xDEAD_BEEFu32.to_le_bytes());
        assert!(matches!(parse_header(&buf), Err(ParseError::UnknownMagic { .. })));
    }

    #[test]
    fn unsupported_version_returns_typed_error() {
        let mut buf = minimal_header();
        buf[0x004..0x008].copy_from_slice(&99u32.to_le_bytes());
        assert!(matches!(parse_header(&buf), Err(ParseError::UnsupportedVersion { .. })));
    }

    #[test]
    fn zero_channel_meta_offset_returns_typed_error() {
        let mut buf = minimal_header();
        buf[0x008..0x00C].copy_from_slice(&0u32.to_le_bytes());
        assert!(matches!(parse_header(&buf), Err(ParseError::InvalidOffset { .. })));
    }

    #[test]
    fn too_short_buffer_returns_header_too_short() {
        assert!(matches!(
            parse_header(&[0u8; 10]),
            Err(ParseError::HeaderTooShort { .. })
        ));
    }

    #[test]
    fn all_string_fields_parsed() {
        let mut buf = minimal_header();
        buf[0x058..0x063].copy_from_slice(b"Silverstone");
        buf[0x098..0x0A3].copy_from_slice(b"Formula2000");
        buf[0x0D8..0x0E2].copy_from_slice(b"John Smith");
        let hdr = parse_header(&buf).expect("should parse");
        assert_eq!(hdr.venue, "Silverstone");
        assert_eq!(hdr.vehicle, "Formula2000");
        assert_eq!(hdr.driver, "John Smith");
    }

    #[test]
    fn ld4_version_accepted() {
        let mut buf = minimal_header();
        buf[0x004..0x008].copy_from_slice(&2u32.to_le_bytes()); // LD4
        let hdr = parse_header(&buf).expect("LD4 should parse");
        assert_eq!(hdr.version, 2);
    }
}

