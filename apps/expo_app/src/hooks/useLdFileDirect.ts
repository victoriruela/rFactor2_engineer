/**
 * @file useLdFileDirect.ts
 * @description Direct (main-thread) WASM version of the .ld parser hook.
 *
 * Uses the same state machine as useLdFile but parses with the WASM module
 * directly on the main thread instead of in a Web Worker.
 *
 * ## Why not a Worker?
 * Metro (Expo SDK 52 web bundler) does not create separate Worker bundles
 * from `new Worker(new URL(...))` patterns. This direct version is the
 * Metro-compatible approach. The Worker version in useLdFile.ts is the
 * intended production path when bundled with Vite or webpack.
 *
 * ## Performance
 * Header + channel metadata parsing is < 5ms even on large files, so
 * main-thread execution has no measurable UI impact for this phase.
 */

import { useState, useCallback, useRef } from 'react';
import init, * as LdParser from '../../wasm/ld_parser/pkg/ld_parser';
import { LD_PARSER_WASM_B64 } from '../../wasm/ld_parser/pkg/ld_parser_bg_inline';
import { validateLdFileFast, readHeaderSlice, readMetaSlice } from '../worker/file-slice-pipeline';
import type { LdFileState, UseLdFileResult } from './useLdFile';
import type { ChannelInfo, ParseHeaderResponse } from '../worker/worker-protocol';

// ---------------------------------------------------------------------------
// WASM initialisation (lazy, once)
// ---------------------------------------------------------------------------

let _wasmInitPromise: Promise<void> | null = null;

function ensureWasmReady(): Promise<void> {
  if (!_wasmInitPromise) {
    _wasmInitPromise = (async () => {
      const binary = Uint8Array.from(atob(LD_PARSER_WASM_B64), (c) => c.charCodeAt(0));
      await init({ module_or_path: binary.buffer });
    })();
  }
  return _wasmInitPromise;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useLdFileDirect(): UseLdFileResult {
  const [state, setState] = useState<LdFileState>({ kind: 'idle' });
  const generationRef = useRef(0);

  const loadFile = useCallback((file: File) => {
    const generation = ++generationRef.current;
    const isStale = () => generationRef.current !== generation;

    setState({ kind: 'validating', file });

    const run = async () => {
      // ── Validate magic bytes ──────────────────────────────────────────────
      try {
        await validateLdFileFast(file);
      } catch (err) {
        if (isStale()) return;
        setState({ kind: 'error', message: String(err), file });
        return;
      }
      if (isStale()) return;

      setState({ kind: 'parsing_header', file });

      // ── Init WASM (lazy singleton) ────────────────────────────────────────
      try {
        await ensureWasmReady();
      } catch (err) {
        if (isStale()) return;
        setState({ kind: 'error', message: `WASM init failed: ${err}`, file });
        return;
      }
      if (isStale()) return;

      // ── Parse header ──────────────────────────────────────────────────────
      let session: ParseHeaderResponse;
      try {
        const headerBuf = await readHeaderSlice(file);
        if (isStale()) return;

        const info = LdParser.parse_ld_header(headerBuf);
        session = {
          kind: 'PARSE_HEADER_OK',
          id: '',
          version: info.version,
          channelMetaOffset: info.channel_meta_offset,
          dataOffset: info.data_offset,
          session: info.session,
          venue: info.venue,
          vehicle: info.vehicle,
          driver: info.driver,
          date: info.date,
        };
      } catch (err) {
        if (isStale()) return;
        setState({ kind: 'error', message: String(err), file });
        return;
      }
      if (isStale()) return;

      setState({ kind: 'parsing_channels', file, session });

      // ── Parse channels ────────────────────────────────────────────────────
      let channels: readonly ChannelInfo[];
      try {
        const metaBuf = await readMetaSlice(file, session);
        if (isStale()) return;

        const jsArr = LdParser.parse_ld_channels(metaBuf, session.channelMetaOffset);
        const result: ChannelInfo[] = [];
        for (let i = 0; i < jsArr.length; i++) {
          const ch = jsArr[i];
          result.push({
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
        channels = result;
      } catch (err) {
        if (isStale()) return;
        setState({ kind: 'error', message: String(err), file });
        return;
      }
      if (isStale()) return;

      setState({ kind: 'ready', file, session, channels });
    };

    run().catch((err) => {
      if (generationRef.current === generation) {
        setState({ kind: 'error', message: String(err), file });
      }
    });
  }, []);

  const reset = useCallback(() => {
    setState((current) => (current.kind === 'error' ? { kind: 'idle' } : current));
  }, []);

  return { state, loadFile, reset };
}
