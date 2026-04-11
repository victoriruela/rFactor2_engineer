/// Decode a null-terminated C string from a fixed-size byte slice.
///
/// Finds the first `0x00` byte and returns everything before it decoded
/// as UTF-8 with lossy substitution (replaces invalid sequences with U+FFFD).
/// Trailing whitespace is stripped.
pub fn parse_cstring(bytes: &[u8]) -> String {
    let end = bytes.iter().position(|&b| b == 0).unwrap_or(bytes.len());
    String::from_utf8_lossy(&bytes[..end]).trim_end().to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_cstring_stops_at_null() {
        let mut buf = [0u8; 32];
        buf[..3].copy_from_slice(b"RPM");
        assert_eq!(parse_cstring(&buf), "RPM");
    }

    #[test]
    fn parse_cstring_no_null_uses_full_slice() {
        let buf = *b"EngineRPM_12345678901234567890AB";
        assert_eq!(parse_cstring(&buf), "EngineRPM_12345678901234567890AB");
    }

    #[test]
    fn parse_cstring_trims_trailing_whitespace() {
        let input = b"RPM   \0xxx";
        assert_eq!(parse_cstring(input), "RPM");
    }

    #[test]
    fn parse_cstring_invalid_utf8_substitutes() {
        // 0xFF is not valid UTF-8; should be replaced with U+FFFD
        let input = &[0xFF, 0x00, 0x00];
        let result = parse_cstring(input);
        assert!(result.contains('\u{FFFD}'));
    }
}
