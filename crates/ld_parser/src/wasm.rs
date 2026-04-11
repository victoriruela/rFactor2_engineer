use wasm_bindgen::prelude::*;

use crate::channel::parse_channels;
use crate::domain::ChannelMeta;
use crate::error::ParseError;
use crate::header::{parse_header, validate_magic_and_version, validate_offsets};

// -------------------------------------------------------------------------
// JS-facing types
// -------------------------------------------------------------------------

/// Exported summary of a parsed channel for JS consumption.
#[wasm_bindgen]
pub struct JsChannelInfo {
    name: String,
    short_name: String,
    units: String,
    sample_rate: u16,
    count: u32,
    type_id: u16,
    data_offset: u32,
}

#[wasm_bindgen]
impl JsChannelInfo {
    #[wasm_bindgen(getter)]
    pub fn name(&self) -> String {
        self.name.clone()
    }

    #[wasm_bindgen(getter)]
    pub fn short_name(&self) -> String {
        self.short_name.clone()
    }

    #[wasm_bindgen(getter)]
    pub fn units(&self) -> String {
        self.units.clone()
    }

    #[wasm_bindgen(getter)]
    pub fn sample_rate(&self) -> u16 {
        self.sample_rate
    }

    #[wasm_bindgen(getter)]
    pub fn count(&self) -> u32 {
        self.count
    }

    #[wasm_bindgen(getter)]
    pub fn type_id(&self) -> u16 {
        self.type_id
    }

    #[wasm_bindgen(getter)]
    pub fn data_offset(&self) -> u32 {
        self.data_offset
    }

    /// Byte length of this channel's data block: count × sample_size(type_id).
    #[wasm_bindgen]
    pub fn data_byte_len(&self) -> u32 {
        let sample_size: u32 = match self.type_id {
            0x0000 | 0x0003 | 0x0004 => 4,
            0x0001 | 0x0002 => 2,
            0x0007 => 8,
            _ => 0,
        };
        self.count * sample_size
    }
}

/// Session context exported to JS after header parse.
#[wasm_bindgen]
pub struct JsSessionInfo {
    version: u32,
    channel_meta_offset: u32,
    data_offset: u32,
    session: String,
    venue: String,
    vehicle: String,
    driver: String,
    date: String,
}

#[wasm_bindgen]
impl JsSessionInfo {
    #[wasm_bindgen(getter)] pub fn version(&self) -> u32 { self.version }
    #[wasm_bindgen(getter)] pub fn channel_meta_offset(&self) -> u32 { self.channel_meta_offset }
    #[wasm_bindgen(getter)] pub fn data_offset(&self) -> u32 { self.data_offset }
    #[wasm_bindgen(getter)] pub fn session(&self) -> String { self.session.clone() }
    #[wasm_bindgen(getter)] pub fn venue(&self) -> String { self.venue.clone() }
    #[wasm_bindgen(getter)] pub fn vehicle(&self) -> String { self.vehicle.clone() }
    #[wasm_bindgen(getter)] pub fn driver(&self) -> String { self.driver.clone() }
    #[wasm_bindgen(getter)] pub fn date(&self) -> String { self.date.clone() }
}

// -------------------------------------------------------------------------
// Exported WASM functions
// -------------------------------------------------------------------------

/// Parse the file header from a byte slice.
///
/// Expects at least 0x200 bytes from the start of the file.
/// Returns a `JsSessionInfo` on success, or throws a JS Error string.
#[wasm_bindgen]
pub fn parse_ld_header(buf: &[u8]) -> Result<JsSessionInfo, JsValue> {
    validate_magic_and_version(buf).map_err(|e| JsValue::from_str(&e.to_string()))?;
    validate_offsets(buf).map_err(|e| JsValue::from_str(&e.to_string()))?;

    let header = parse_header(buf).map_err(|e| JsValue::from_str(&e.to_string()))?;
    Ok(JsSessionInfo {
        version: header.version,
        channel_meta_offset: header.channel_meta_offset,
        data_offset: header.data_offset,
        session: header.session,
        venue: header.venue,
        vehicle: header.vehicle,
        driver: header.driver,
        date: header.date,
    })
}

/// Parse all channel metadata records from a byte slice.
///
/// `buf`: complete file bytes or at minimum the region `[0 .. channel_meta_offset + meta_size]`.
/// `first_meta_offset`: absolute byte offset of the first channel record (from `JsSessionInfo.channel_meta_offset`).
///
/// Returns a JS Array of `JsChannelInfo` objects.
/// Channels with unsupported type IDs are silently skipped (warnings are not surfaced to JS in this MVP).
#[wasm_bindgen]
pub fn parse_ld_channels(buf: &[u8], first_meta_offset: u32) -> Result<js_sys::Array, JsValue> {
    let file_len = buf.len();
    let (channels, _warnings) =
        parse_channels(buf, first_meta_offset, file_len)
            .map_err(|e| JsValue::from_str(&e.to_string()))?;

    let arr = js_sys::Array::new();
    for ch in channels {
        let info = JsChannelInfo {
            name: ch.name,
            short_name: ch.short_name,
            units: ch.units,
            sample_rate: ch.sample_rate,
            count: ch.count,
            type_id: ch.type_id,
            data_offset: ch.data_offset,
        };
        arr.push(&JsValue::from(info));
    }
    Ok(arr)
}
