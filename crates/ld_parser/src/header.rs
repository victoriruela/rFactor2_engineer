use crate::domain::LdFileHeader;
use crate::error::ParseError;
use crate::utils::parse_cstring;

/// Expected file magic for all supported .ld files.
pub const LD_MAGIC: u32 = 0x0045_F836;
/// Minimum supported format version.
pub const LD_VERSION_MIN: u32 = 1;
/// Maximum supported format version.
pub const LD_VERSION_MAX: u32 = 2;
/// Expected minimum header size in bytes.
pub const HEADER_SIZE: usize = 0x0200; // conservative; actual usable region up to 0xC00

/// Parse the .ld file header from a byte slice.
///
/// The caller is responsible for providing at least `HEADER_SIZE` bytes
/// via `File.slice(0, HEADER_SIZE)` before calling this function.
///
/// Returns `Err(ParseError)` on any structural violation; never panics.
pub fn parse_header(buf: &[u8]) -> Result<LdFileHeader, ParseError> {
    if buf.len() < HEADER_SIZE {
        return Err(ParseError::HeaderTooShort { got: buf.len(), expected: HEADER_SIZE });
    }

    let magic = le_u32(buf, 0x000);
    if magic != LD_MAGIC {
        return Err(ParseError::UnknownMagic { found: magic });
    }

    let version = le_u32(buf, 0x004);
    if version < LD_VERSION_MIN || version > LD_VERSION_MAX {
        return Err(ParseError::UnsupportedVersion { found: version });
    }

    let channel_meta_offset = le_u32(buf, 0x008);
    if channel_meta_offset == 0 {
        return Err(ParseError::InvalidOffset {
            field: "channel_meta_offset",
            value: channel_meta_offset,
        });
    }

    let channel_meta_size = le_u32(buf, 0x00C);
    let data_offset = le_u32(buf, 0x010);
    if data_offset == 0 {
        return Err(ParseError::InvalidOffset { field: "data_offset", value: data_offset });
    }
    let data_size = le_u32(buf, 0x014);

    let session = parse_cstring(&buf[0x018..0x058]);
    let venue = parse_cstring(&buf[0x058..0x098]);
    let vehicle = parse_cstring(&buf[0x098..0x0D8]);
    let driver = parse_cstring(&buf[0x0D8..0x118]);
    let date = parse_cstring(&buf[0x118..0x138]);

    Ok(LdFileHeader {
        version,
        channel_meta_offset,
        channel_meta_size,
        data_offset,
        data_size,
        session,
        venue,
        vehicle,
        driver,
        date,
    })
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Read a little-endian u32 from `buf` at byte `offset`.
/// Panics only in debug builds if the slice is too short (programmer error).
#[inline]
fn le_u32(buf: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(buf[offset..offset + 4].try_into().expect("le_u32: slice too short"))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a minimal valid header buffer for testing.
    fn minimal_header() -> Vec<u8> {
        let mut buf = vec![0u8; HEADER_SIZE];
        buf[0x000..0x004].copy_from_slice(&LD_MAGIC.to_le_bytes());
        buf[0x004..0x008].copy_from_slice(&1u32.to_le_bytes());          // version 1 = LD3
        buf[0x008..0x00C].copy_from_slice(&0x0C00u32.to_le_bytes());     // channel_meta_offset
        buf[0x00C..0x010].copy_from_slice(&0x01A8u32.to_le_bytes());     // channel_meta_size = 1 record
        buf[0x010..0x014].copy_from_slice(&0x1000u32.to_le_bytes());     // data_offset
        buf[0x014..0x018].copy_from_slice(&0x0400u32.to_le_bytes());     // data_size
        // session name
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
    }

    #[test]
    fn wrong_magic_returns_error() {
        let mut buf = minimal_header();
        buf[0x000..0x004].copy_from_slice(&0xDEAD_BEEFu32.to_le_bytes());
        assert!(matches!(parse_header(&buf), Err(ParseError::UnknownMagic { .. })));
    }

    #[test]
    fn unsupported_version_returns_error() {
        let mut buf = minimal_header();
        buf[0x004..0x008].copy_from_slice(&99u32.to_le_bytes());
        assert!(matches!(parse_header(&buf), Err(ParseError::UnsupportedVersion { .. })));
    }

    #[test]
    fn zero_channel_meta_offset_returns_error() {
        let mut buf = minimal_header();
        buf[0x008..0x00C].copy_from_slice(&0u32.to_le_bytes());
        assert!(matches!(parse_header(&buf), Err(ParseError::InvalidOffset { .. })));
    }

    #[test]
    fn too_short_buffer_returns_error() {
        let buf = vec![0u8; 10];
        assert!(matches!(parse_header(&buf), Err(ParseError::HeaderTooShort { .. })));
    }
}
