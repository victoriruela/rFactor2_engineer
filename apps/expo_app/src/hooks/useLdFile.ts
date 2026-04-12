/**
 * @file useLdFile.ts
 * @description Async state machine hook for loading and parsing MoTeC .ld files via WASM.
 *
 * State transitions:
 *
 *   idle ──────────────────────────────────────────────── (initial state)
 *     └─ loadFile(file) ─►  validating
 *
 *   validating ──────────────────────────────────────────
 *     ├─ success ─────────► parsing_header
 *     └─ failure ─────────► error
 *
 *   parsing_header ──────────────────────────────────────
 *     ├─ success ─────────► parsing_channels
 *     └─ failure ─────────► error
 *
 *   parsing_channels ────────────────────────────────────
 *     ├─ success ─────────► ready
 *     └─ failure ─────────► error
 *
 *   ready ────────────────────────────────────────────── (channels available)
 *     └─ loadFile(file) ─►  validating  (reset cycle)
 *
 *   error ────────────────────────────────────────────── (message available)
 *     └─ loadFile(file) ─►  validating  (retry)
 *     └─ reset()        ─►  idle
 */

import { useState, useCallback, useRef, useEffect } from 'react';

import type { ChannelInfo, ParseHeaderResponse, ParseChannelsResponse } from '../worker/worker-protocol';
import { LdParserWorkerClient } from '../worker/wasm-typed-array-adapter';
import { validateLdFileFast, readHeaderSlice, readMetaSlice } from '../worker/file-slice-pipeline';
import { nextRequestId } from '../worker/worker-protocol';

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------

export type LdFileStateKind =
  | 'idle'
  | 'validating'
  | 'parsing_header'
  | 'parsing_channels'
  | 'ready'
  | 'error';

export interface LdFileStateIdle {
  kind: 'idle';
}

export interface LdFileStateValidating {
  kind: 'validating';
  file: File;
}

export interface LdFileStateParsingHeader {
  kind: 'parsing_header';
  file: File;
}

export interface LdFileStateParsingChannels {
  kind: 'parsing_channels';
  file: File;
  session: ParseHeaderResponse;
}

export interface LdFileStateReady {
  kind: 'ready';
  file: File;
  session: ParseHeaderResponse;
  channels: readonly ChannelInfo[];
}

export interface LdFileStateError {
  kind: 'error';
  message: string;
  /** The file that was being loaded when the error occurred, if known. */
  file: File | null;
}

export type LdFileState =
  | LdFileStateIdle
  | LdFileStateValidating
  | LdFileStateParsingHeader
  | LdFileStateParsingChannels
  | LdFileStateReady
  | LdFileStateError;

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export interface UseLdFileResult {
  state: LdFileState;
  /** Load a new .ld file. Resets state machine from any current state. */
  loadFile: (file: File) => void;
  /** Reset to idle from an error state. No-op in other states. */
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Worker URL (adjust to match your bundler's worker output path)
// ---------------------------------------------------------------------------

const WORKER_URL = new URL('../worker/ld-parser.worker.ts', import.meta.url);

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useLdFile(): UseLdFileResult {
  const [state, setState] = useState<LdFileState>({ kind: 'idle' });

  // Stable Worker client — created once, reused across file loads.
  const clientRef = useRef<LdParserWorkerClient | null>(null);

  // Generation counter: if a new loadFile() call arrives while a previous
  // async pipeline is still running, the stale pipeline checks this and exits.
  const generationRef = useRef(0);

  // Initialise Worker on mount, terminate on unmount.
  useEffect(() => {
    clientRef.current = new LdParserWorkerClient(WORKER_URL);
    return () => {
      clientRef.current?.terminate();
      clientRef.current = null;
    };
  }, []);

  const loadFile = useCallback((file: File) => {
    // Increment generation to cancel any in-flight pipeline.
    const generation = ++generationRef.current;

    setState({ kind: 'validating', file });

    const run = async () => {
      const client = clientRef.current;
      if (!client) return;

      // Helper to bail out if superseded.
      const isStale = () => generationRef.current !== generation;

      // ── Phase 1: Fast magic-byte validation ────────────────────────────
      try {
        await validateLdFileFast(file);
      } catch (err) {
        if (isStale()) return;
        setState({ kind: 'error', message: String(err), file });
        return;
      }
      if (isStale()) return;

      setState({ kind: 'parsing_header', file });

      // ── Phase 2: Parse header ───────────────────────────────────────────
      let session: ParseHeaderResponse;
      try {
        const headerBuf = await readHeaderSlice(file);
        if (isStale()) return;

        const req = { id: nextRequestId('ph'), kind: 'PARSE_HEADER' as const, headerBytes: headerBuf };
        const res = await client.send(req);
        if (isStale()) return;

        if (res.kind === 'ERROR') {
          setState({ kind: 'error', message: res.message, file });
          return;
        }
        session = res as ParseHeaderResponse;
      } catch (err) {
        if (isStale()) return;
        setState({ kind: 'error', message: String(err), file });
        return;
      }

      setState({ kind: 'parsing_channels', file, session });

      // ── Phase 3: Parse channels ─────────────────────────────────────────
      let channels: readonly ChannelInfo[];
      try {
        const metaBuf = await readMetaSlice(file, session);
        if (isStale()) return;

        const req = {
          id: nextRequestId('pc'),
          kind: 'PARSE_CHANNELS' as const,
          metaBytes: metaBuf,
          firstMetaOffset: session.channelMetaOffset,
        };
        const res = await client.send(req);
        if (isStale()) return;

        if (res.kind === 'ERROR') {
          setState({ kind: 'error', message: res.message, file });
          return;
        }
        channels = (res as ParseChannelsResponse).channels;
      } catch (err) {
        if (isStale()) return;
        setState({ kind: 'error', message: String(err), file });
        return;
      }

      if (isStale()) return;
      setState({ kind: 'ready', file, session, channels });
    };

    run().catch((err) => {
      // Unhandled rejection guard — should not normally be reached.
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
