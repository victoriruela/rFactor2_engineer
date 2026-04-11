/// Parsed .ld file header.
///
/// All string fields are decoded as UTF-8 with lossy substitution.
/// All integer fields are little-endian (as per MoTeC .ld format).
#[derive(Debug, Clone, PartialEq)]
pub struct LdFileHeader {
    /// LD version: 1 = LD3, 2 = LD4.
    pub version: u32,
    /// Absolute byte offset to the start of the channel meta linked list.
    pub channel_meta_offset: u32,
    /// Byte length of the entire channel meta region.
    pub channel_meta_size: u32,
    /// Absolute byte offset to the start of the raw packed data block.
    pub data_offset: u32,
    /// Byte length of the entire data region.
    pub data_size: u32,
    /// Event / session name (e.g. "Race", "Qualifying").
    pub session: String,
    /// Venue / circuit name.
    pub venue: String,
    /// Vehicle / car model name.
    pub vehicle: String,
    /// Driver name. May be empty.
    pub driver: String,
    /// Session date-time string (ISO-like, e.g. "2024-06-09 14:32:00").
    pub date: String,
}

/// Parsed channel descriptor (one node in the linked list).
#[derive(Debug, Clone, PartialEq)]
pub struct ChannelMeta {
    /// Absolute file offset to previous channel node. 0 = first.
    pub prev_offset: u32,
    /// Absolute file offset to next channel node. 0 = last (end of list).
    pub next_offset: u32,
    /// Absolute file offset to this channel's packed data.
    pub data_offset: u32,
    /// Number of samples.
    pub count: u32,
    /// Raw data type id (see LdDataType::from_type_id).
    pub type_id: u16,
    /// Sample rate in Hz.
    pub sample_rate: u16,
    /// Scaling: base-2 shift exponent (may be negative).
    pub shift: i16,
    /// Scaling: multiplier.
    pub multiplier: i16,
    /// Scaling: base-10 decimal exponent (may be negative).
    pub scale: i16,
    /// Display decimal precision hint (not used for parsing).
    pub decimal_places: i16,
    /// Long channel name (up to 32 bytes, null-terminated).
    pub name: String,
    /// Short channel name (up to 8 bytes, null-terminated).
    pub short_name: String,
    /// Unit string (up to 12 bytes, null-terminated).
    pub units: String,
}

/// Top-level parsed result: header + all successfully decoded channel descriptors.
/// Channels with unrecognised type_ids are excluded and reported in `warnings`.
#[derive(Debug, Clone)]
pub struct LdFile {
    pub header: LdFileHeader,
    pub channels: Vec<ChannelMeta>,
}
