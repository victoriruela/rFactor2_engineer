/// Zero-copy WASM linear memory API.
///
/// This module implements the pointer-based data access pattern described in SPEC.md:
/// - JS never receives a deserialized Vec<f32> or similar JS Array for large data.
/// - Instead, JS receives a raw pointer (u32 byte offset into WASM linear memory)
///   and a length, then constructs a typed array view directly over those bytes.
///
/// # Zero-Copy Contract
///
/// ```js
/// // JS side — no copying:
/// const ptr = ld_alloc_channel_buffer(channel.count, channel.type_id);
/// // ... fill the buffer from File.slice via read_channel_data_into() ...
/// const view = new Float32Array(wasm.memory.buffer, ptr, channel.count);
/// // view is a LIVE zero-copy window into WASM linear memory
/// ```
///
/// The lifetime of the buffer is managed by Rust.
/// JS MUST call `ld_free_channel_buffer(ptr, count, type_id)` when done.
/// Failing to do so is a memory leak (not undefined behaviour in WASM, but
/// it will exhaust the 4GB linear address space over time).

use wasm_bindgen::prelude::*;

use crate::types::LdDataType;

// -------------------------------------------------------------------------
// Buffer allocation / deallocation
// -------------------------------------------------------------------------

/// Allocate `count` samples of the given `type_id` in WASM linear memory.
///
/// Returns the byte offset (pointer) into `wasm.memory.buffer`.
/// Returns 0 if `type_id` is unknown or allocation fails.
///
/// JS usage:
/// ```js
/// const ptr = ld_alloc_channel_buffer(1000, 0x0000); // Float32
/// const view = new Float32Array(wasm.memory.buffer, ptr, 1000);
/// ```
#[wasm_bindgen]
pub fn ld_alloc_channel_buffer(count: u32, type_id: u16) -> u32 {
    let Some(dtype) = LdDataType::from_type_id(type_id) else {
        return 0;
    };
    let byte_len = dtype.data_block_size(count) as usize;
    if byte_len == 0 {
        return 0;
    }

    // Allocate via Vec<u8> to ensure Rust's allocator manages the memory.
    // We leak the Vec intentionally; ld_free_channel_buffer must be called by JS.
    let mut buf: Vec<u8> = vec![0u8; byte_len];
    let ptr = buf.as_mut_ptr() as u32;
    std::mem::forget(buf); // transfer ownership to JS caller
    ptr
}

/// Free a buffer previously allocated by `ld_alloc_channel_buffer`.
///
/// JS MUST pass the same `count` and `type_id` used during allocation.
/// Calling this with wrong parameters causes undefined behaviour.
///
/// # Safety
/// This reconstructs a Vec<u8> from a raw pointer; safe only when called
/// with the exact same count + type_id used during allocation.
#[wasm_bindgen]
pub fn ld_free_channel_buffer(ptr: u32, count: u32, type_id: u16) {
    let Some(dtype) = LdDataType::from_type_id(type_id) else {
        return; // unknown type; nothing to free
    };
    let byte_len = dtype.data_block_size(count) as usize;
    if byte_len == 0 || ptr == 0 {
        return;
    }
    // Reconstruct and drop the Vec to free memory.
    // SAFETY: ptr was allocated by ld_alloc_channel_buffer with the same byte_len.
    unsafe {
        let _ = Vec::from_raw_parts(ptr as *mut u8, byte_len, byte_len);
    }
}

// -------------------------------------------------------------------------
// Data ingestion — fills a pre-allocated buffer from a file byte slice
// -------------------------------------------------------------------------

/// Copy raw channel data from the file byte slice into a pre-allocated WASM buffer.
///
/// `file_buf`:      the file region containing this channel's data (from File.slice).
/// `data_offset`:   absolute file offset of this channel's data (from `JsChannelInfo.data_offset`).
/// `count`:         number of samples.
/// `type_id`:       channel type id (from `JsChannelInfo.type_id`).
/// `dest_ptr`:      pointer returned by `ld_alloc_channel_buffer`.
///
/// Returns `true` on success, throws a JS Error string on failure.
///
/// After this call JS can construct a typed array view:
/// ```js
/// const ok = read_channel_data_into(fileBuf, ch.data_offset, ch.count, ch.type_id, ptr);
/// const samples = new Float32Array(wasm.memory.buffer, ptr, ch.count);
/// ```
#[wasm_bindgen]
pub fn read_channel_data_into(
    file_buf: &[u8],
    data_offset: u32,
    count: u32,
    type_id: u16,
    dest_ptr: u32,
) -> Result<bool, JsValue> {
    let Some(dtype) = LdDataType::from_type_id(type_id) else {
        return Err(JsValue::from_str(&format!(
            "read_channel_data_into: unsupported type_id 0x{type_id:04X}"
        )));
    };

    let byte_len = dtype.data_block_size(count) as usize;
    let src_start = data_offset as usize;
    let src_end = src_start + byte_len;

    if src_end > file_buf.len() {
        return Err(JsValue::from_str(&format!(
            "read_channel_data_into: data range [{src_start}..{src_end}] exceeds buffer len {}",
            file_buf.len()
        )));
    }
    if dest_ptr == 0 {
        return Err(JsValue::from_str("read_channel_data_into: dest_ptr is null"));
    }

    // SAFETY: dest_ptr was allocated by ld_alloc_channel_buffer with byte_len bytes.
    let dest: &mut [u8] =
        unsafe { std::slice::from_raw_parts_mut(dest_ptr as *mut u8, byte_len) };
    dest.copy_from_slice(&file_buf[src_start..src_end]);

    Ok(true)
}

// -------------------------------------------------------------------------
// Utility: typed array layout info for JS
// -------------------------------------------------------------------------

/// Returns the byte size of one sample for the given `type_id`.
/// Returns 0 for unknown types.
///
/// JS uses this to compute the typed array length from the raw byte count,
/// or to validate `File.slice` window sizes.
#[wasm_bindgen]
pub fn sample_byte_size(type_id: u16) -> u32 {
    LdDataType::from_type_id(type_id)
        .map(|dt| dt.sample_size() as u32)
        .unwrap_or(0)
}

/// Returns the JS TypedArray constructor name for the given `type_id`.
/// Returns "unknown" for unsupported types.
///
/// JS can use `eval(\`new \${typedArrayName}(buf, ptr, count)\`)` but should
/// prefer a static dispatch table for security.
#[wasm_bindgen]
pub fn typed_array_name(type_id: u16) -> String {
    LdDataType::from_type_id(type_id)
        .map(|dt| dt.js_typed_array().to_owned())
        .unwrap_or_else(|| "unknown".to_owned())
}

// -------------------------------------------------------------------------
// Tests
// -------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn alloc_free_roundtrip_float32() {
        let ptr = ld_alloc_channel_buffer(100, 0x0000);
        assert_ne!(ptr, 0);
        // Should not panic or leak when freed correctly:
        ld_free_channel_buffer(ptr, 100, 0x0000);
    }

    #[test]
    fn alloc_unknown_type_returns_zero() {
        let ptr = ld_alloc_channel_buffer(100, 0x0099);
        assert_eq!(ptr, 0);
    }

    #[test]
    fn sample_byte_size_known_types() {
        assert_eq!(sample_byte_size(0x0000), 4); // f32
        assert_eq!(sample_byte_size(0x0001), 2); // i16
        assert_eq!(sample_byte_size(0x0007), 8); // f64
    }

    #[test]
    fn sample_byte_size_unknown_returns_zero() {
        assert_eq!(sample_byte_size(0x0099), 0);
    }

    #[test]
    fn typed_array_name_float32() {
        assert_eq!(typed_array_name(0x0000), "Float32Array");
    }

    #[test]
    fn typed_array_name_unknown() {
        assert_eq!(typed_array_name(0x0099), "unknown");
    }

    #[test]
    fn read_channel_data_into_copies_correctly() {
        // Build a fake file buffer: 12 bytes of f32 = 3 samples
        let mut file = vec![0u8; 0x100];
        let data = [0x00u8, 0x00, 0x80, 0x3F]; // 1.0f32 little-endian
        file[0x050..0x054].copy_from_slice(&data);
        file[0x054..0x058].copy_from_slice(&data);
        file[0x058..0x05C].copy_from_slice(&data);

        let ptr = ld_alloc_channel_buffer(3, 0x0000);
        assert_ne!(ptr, 0);
        let ok = read_channel_data_into(&file, 0x050, 3, 0x0000, ptr).expect("should succeed");
        assert!(ok);

        // Read back and verify
        let dest: &[f32] = unsafe {
            std::slice::from_raw_parts(ptr as *const f32, 3)
        };
        assert!((dest[0] - 1.0f32).abs() < f32::EPSILON);
        assert!((dest[1] - 1.0f32).abs() < f32::EPSILON);
        assert!((dest[2] - 1.0f32).abs() < f32::EPSILON);

        ld_free_channel_buffer(ptr, 3, 0x0000);
    }
}
