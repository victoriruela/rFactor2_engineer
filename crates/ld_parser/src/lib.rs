//! ld_parser — Zero-copy MoTeC .ld binary parser for WebAssembly.
//!
//! # Architecture
//! - `error`   — `ParseError` and `ParseWarning` types
//! - `types`   — `LdDataType` enum with sample_size / data_block_size helpers
//! - `domain`  — Plain data structs (`LdFileHeader`, `ChannelMeta`, `LdFile`)
//! - `utils`   — `parse_cstring` and other low-level helpers
//! - `header`  — Header parser (`parse_header`)
//! - `channel` — Channel meta linked-list parser (`parse_channels`)
//!
//! # Design Constraints (SPEC.md)
//! - All multi-byte integers are little-endian.
//! - `.unwrap()` / `.expect()` are forbidden outside `#[cfg(test)]` blocks.
//! - Large data arrays are returned as raw pointer + length for zero-copy JS access.

pub mod channel;
pub mod domain;
pub mod error;
pub mod header;
pub mod memory;
pub mod types;
pub mod utils;
pub mod wasm;

pub use domain::{ChannelMeta, LdFile, LdFileHeader};
pub use error::{ParseError, ParseWarning};
pub use types::LdDataType;
