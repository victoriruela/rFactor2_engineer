/**
 * @file ld-parser.worker.ts
 * @description Web Worker that hosts the MoTeC .ld WASM parser.
 *
 * ## Threading Model
 * - This entire file runs on a dedicated background thread.
 * - The main thread is NEVER blocked by parsing or loading.
 * - All DOM and Canvas operations remain on the main thread.
 *
 * ## WASM Init
 * The WASM module is imported and initialised once on worker startup.
 * All subsequent calls operate on the already-loaded module.
 */

// Type-only import — wasm-pack generates the actual JS glue at build time.
// The `ld_parser_bg.wasm` and `ld_parser.js` files are emitted to pkg/
// and bundled by the app build pipeline (Metro or webpack).
//
// Adjust this import path to match your wasm-pack output directory.
import init, * as LdParser from '../../wasm/ld_parser/pkg/ld_parser';

import type {
  WorkerRequest,
  WorkerResponse,
  WorkerErrorResponse,
  ChannelInfo,
} from './worker-protocol';

// ---------------------------------------------------------------------------
// WASM initialisation (once on worker load)
// ---------------------------------------------------------------------------

let wasmReady = false;

async function initWasm(): Promise<void> {
  await init();
  wasmReady = true;
}

const wasmInitPromise = initWasm();

// ---------------------------------------------------------------------------
// Message dispatcher
// ---------------------------------------------------------------------------

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  await wasmInitPromise; // ensure WASM is loaded before handling any message

  const req = event.data;
  const id = req.id;

  try {
    switch (req.kind) {
      case 'PARSE_HEADER': {
        const info = LdParser.parse_ld_header(req.headerBytes);
        const res: WorkerResponse = {
          kind: 'PARSE_HEADER_OK',
          id,
          version: info.version,
          channelMetaOffset: info.channel_meta_offset,
          dataOffset: info.data_offset,
          session: info.session,
          venue: info.venue,
          vehicle: info.vehicle,
          driver: info.driver,
          date: info.date,
        };
        self.postMessage(res);
        break;
      }

      case 'PARSE_CHANNELS': {
        const jsArr = LdParser.parse_ld_channels(req.metaBytes, req.firstMetaOffset);
        const channels: ChannelInfo[] = [];
        for (let i = 0; i < jsArr.length; i++) {
          const ch = jsArr[i];
          channels.push({
            name: ch.name,
            shortName: ch.short_name,
            units: ch.units,
            sampleRate: ch.sample_rate,
            count: ch.count,
            typeId: ch.type_id,
            dataOffset: ch.data_offset,
            dataByteLen: ch.data_byte_len(),
          });
        }
        const res: WorkerResponse = { kind: 'PARSE_CHANNELS_OK', id, channels };
        self.postMessage(res);
        break;
      }

      case 'LOAD_CHANNEL_DATA': {
        const ptr = LdParser.ld_alloc_channel_buffer(req.count, req.typeId);
        if (ptr === 0) {
          throw new Error(`ld_alloc_channel_buffer returned null for type_id=0x${req.typeId.toString(16).padStart(4, '0')}`);
        }
        LdParser.read_channel_data_into(
          req.dataBytes,
          req.dataOffset,
          req.count,
          req.typeId,
          ptr,
        );
        const typedArrayName = LdParser.typed_array_name(req.typeId);
        const res: WorkerResponse = {
          kind: 'LOAD_CHANNEL_DATA_OK',
          id,
          ptr,
          count: req.count,
          typeId: req.typeId,
          typedArrayName,
        };
        self.postMessage(res);
        break;
      }

      case 'FREE_CHANNEL_BUFFER': {
        LdParser.ld_free_channel_buffer(req.ptr, req.count, req.typeId);
        const res: WorkerResponse = { kind: 'FREE_CHANNEL_BUFFER_OK', id };
        self.postMessage(res);
        break;
      }

      default: {
        // Exhaustive check: TypeScript will error here if a new request kind is added
        // without a corresponding case.
        const _exhaustive: never = req;
        throw new Error(`Unknown worker request kind: ${JSON.stringify(_exhaustive)}`);
      }
    }
  } catch (err) {
    const errRes: WorkerErrorResponse = {
      kind: 'ERROR',
      id,
      message: err instanceof Error ? err.message : String(err),
    };
    self.postMessage(errRes);
  }
};
