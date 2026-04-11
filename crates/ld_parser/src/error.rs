use std::fmt;

/// All parse errors produced by the ld_parser crate.
///
/// Rule: NEVER use `.unwrap()` or `.expect()` outside of test code.
/// All fallible operations must return `Result<T, ParseError>`.
#[derive(Debug, PartialEq)]
pub enum ParseError {
    /// The file's 4-byte magic signature does not match 0x0045F836.
    UnknownMagic { found: u32 },

    /// The version discriminator is beyond the supported range.
    UnsupportedVersion { found: u32 },

    /// A required byte slice was shorter than expected.
    HeaderTooShort { got: usize, expected: usize },

    /// An absolute file offset field contains 0 or points outside the file.
    InvalidOffset { field: &'static str, value: u32 },

    /// An absolute file offset + record size extends beyond the file length.
    OffsetOutOfBounds { offset: u32, record_size: usize, file_len: usize },

    /// nom returned an error during binary parsing.
    NomError(String),
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnknownMagic { found } => {
                write!(f, "unknown .ld magic: 0x{found:08X} (expected 0x0045F836)")
            }
            Self::UnsupportedVersion { found } => {
                write!(f, "unsupported .ld version: {found} (max supported: 2)")
            }
            Self::HeaderTooShort { got, expected } => {
                write!(f, "header too short: got {got} bytes, expected {expected}")
            }
            Self::InvalidOffset { field, value } => {
                write!(f, "field '{field}' has invalid offset: {value}")
            }
            Self::OffsetOutOfBounds { offset, record_size, file_len } => {
                write!(
                    f,
                    "offset 0x{offset:08X} + {record_size} bytes exceeds file length {file_len}"
                )
            }
            Self::NomError(msg) => write!(f, "nom parse error: {msg}"),
        }
    }
}

impl std::error::Error for ParseError {}

impl<I: fmt::Debug> From<nom::Err<nom::error::Error<I>>> for ParseError {
    fn from(e: nom::Err<nom::error::Error<I>>) -> Self {
        Self::NomError(format!("{e:?}"))
    }
}

/// Non-fatal warnings emitted alongside a successful parse result.
#[derive(Debug, Clone, PartialEq)]
pub enum ParseWarning {
    /// A channel's type_id is unrecognised; that channel was skipped.
    UnsupportedDataType { channel: String, type_id: u16 },

    /// A header field outside the documented layout contained a non-zero reserved value.
    UnknownReservedField { offset: u32, value: u32 },
}

impl fmt::Display for ParseWarning {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedDataType { channel, type_id } => {
                write!(f, "channel '{channel}': unsupported type_id 0x{type_id:04X} — skipped")
            }
            Self::UnknownReservedField { offset, value } => {
                write!(f, "reserved field at 0x{offset:04X} has unexpected value 0x{value:08X}")
            }
        }
    }
}
