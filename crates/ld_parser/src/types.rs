/// Data type discriminant for a single .ld channel.
///
/// Maps a raw `u16` type_id to Rust primitive and corresponding JS TypedArray.
/// Used downstream to dispatch the correct WASM memory view on the JS side.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LdDataType {
    /// type_id 0x0000 — f32 → Float32Array  
    /// Physical values pre-scaled; ignore shift/multiplier/scale fields.
    Float32,
    /// type_id 0x0001 — i16 → Int16Array
    Int16,
    /// type_id 0x0002 — u16 → Uint16Array
    Uint16,
    /// type_id 0x0003 — u32 → Uint32Array
    Uint32,
    /// type_id 0x0004 — i32 → Int32Array
    Int32,
    /// type_id 0x0007 — f64 → Float64Array (GPS channels; low confidence)
    Float64,
}

impl LdDataType {
    /// Parse a raw type_id. Returns `None` for unrecognised values (caller emits ParseWarning).
    pub fn from_type_id(id: u16) -> Option<Self> {
        match id {
            0x0000 => Some(Self::Float32),
            0x0001 => Some(Self::Int16),
            0x0002 => Some(Self::Uint16),
            0x0003 => Some(Self::Uint32),
            0x0004 => Some(Self::Int32),
            0x0007 => Some(Self::Float64),
            _ => None,
        }
    }

    /// Returns the byte size of a single sample for this type.
    pub fn sample_size(self) -> usize {
        match self {
            Self::Float32 => 4,
            Self::Int16 | Self::Uint16 => 2,
            Self::Uint32 | Self::Int32 => 4,
            Self::Float64 => 8,
        }
    }

    /// Computes the total byte length of a channel's data block.
    pub fn data_block_size(self, count: u32) -> u32 {
        self.sample_size() as u32 * count
    }

    /// The JS TypedArray constructor name for documentation / code generation.
    pub fn js_typed_array(self) -> &'static str {
        match self {
            Self::Float32 => "Float32Array",
            Self::Int16 => "Int16Array",
            Self::Uint16 => "Uint16Array",
            Self::Uint32 => "Uint32Array",
            Self::Int32 => "Int32Array",
            Self::Float64 => "Float64Array",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn from_type_id_known_types() {
        assert_eq!(LdDataType::from_type_id(0x0000), Some(LdDataType::Float32));
        assert_eq!(LdDataType::from_type_id(0x0001), Some(LdDataType::Int16));
        assert_eq!(LdDataType::from_type_id(0x0002), Some(LdDataType::Uint16));
        assert_eq!(LdDataType::from_type_id(0x0003), Some(LdDataType::Uint32));
        assert_eq!(LdDataType::from_type_id(0x0004), Some(LdDataType::Int32));
        assert_eq!(LdDataType::from_type_id(0x0007), Some(LdDataType::Float64));
    }

    #[test]
    fn from_type_id_unknown_returns_none() {
        assert_eq!(LdDataType::from_type_id(0x0005), None);
        assert_eq!(LdDataType::from_type_id(0xFFFF), None);
    }

    #[test]
    fn sample_sizes_are_correct() {
        assert_eq!(LdDataType::Float32.sample_size(), 4);
        assert_eq!(LdDataType::Int16.sample_size(), 2);
        assert_eq!(LdDataType::Uint16.sample_size(), 2);
        assert_eq!(LdDataType::Uint32.sample_size(), 4);
        assert_eq!(LdDataType::Int32.sample_size(), 4);
        assert_eq!(LdDataType::Float64.sample_size(), 8);
    }

    #[test]
    fn data_block_size_multiplies_correctly() {
        assert_eq!(LdDataType::Float32.data_block_size(100), 400);
        assert_eq!(LdDataType::Int16.data_block_size(50), 100);
        assert_eq!(LdDataType::Float64.data_block_size(10), 80);
    }
}
