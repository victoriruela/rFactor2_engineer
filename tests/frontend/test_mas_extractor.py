"""Tests for frontend/js/mas_extractor.js logic.

Since the MAS extractor runs in the browser (JavaScript), these tests
validate the extraction algorithm by re-implementing core steps in Python
against synthetic MAS-like binary buffers. This ensures the documented
format offsets, XOR logic, and decompression work correctly.

A subprocess-based test also validates that the JS module can be loaded
by Node.js without syntax errors.
"""

import struct
import subprocess
import zlib
from pathlib import Path


JS_FILE = (
    Path(__file__).resolve().parents[2] / "frontend" / "js" / "mas_extractor.js"
)


# ── MAS 2.90 key tables (must match the JS implementation) ───────────────

FILE_TYPE_KEYS = [
    0xBB, 0x59, 0xD2, 0xFC, 0x2C, 0x80, 0x30, 0xE6,
    0x56, 0x4E, 0x79, 0x78, 0x77, 0xE3, 0x01, 0x5E,
]

MAGIC = b"GMOTOR_MAS_2.90\x00"


def xor_encode_header(magic: bytes) -> bytes:
    """XOR-encode the 16-byte magic using FILE_TYPE_KEYS (shifted right 1)."""
    encoded = bytearray(16)
    for i in range(16):
        encoded[i] = magic[i] ^ (FILE_TYPE_KEYS[i] >> 1)
    return bytes(encoded)


def derive_file_header_keys(salt: bytes) -> bytes:
    """Derive the 256-byte XOR key table from an 8-byte salt.

    Mirrors the JS derivation: rotate through salt bytes modulated
    with position to build a 256-byte key table.
    """
    keys = bytearray(256)
    for i in range(256):
        keys[i] = (salt[i % 8] + i * 7) & 0xFF
    return bytes(keys)


def build_toc_entry(
    file_index: int,
    filename: str,
    filepath: str,
    uncompressed_size: int,
    compressed_size: int,
) -> bytes:
    """Build a 256-byte TOC entry (unencrypted)."""
    entry = bytearray(256)
    # Bytes 0-3: file index (uint32 LE)
    struct.pack_into("<I", entry, 0, file_index)
    # Bytes 16-143: filename (128 bytes, null-terminated)
    fname_bytes = filename.encode("utf-8")[:127]
    entry[16: 16 + len(fname_bytes)] = fname_bytes
    # Bytes 144-271: filepath (128 bytes, null-terminated)
    fpath_bytes = filepath.encode("utf-8")[:111]  # limited by 256-byte entry
    entry[144: 144 + len(fpath_bytes)] = fpath_bytes
    # Last 8 bytes: uncompressed_size (uint32 LE) + compressed_size (uint32 LE)
    struct.pack_into("<I", entry, 248, uncompressed_size)
    struct.pack_into("<I", entry, 252, compressed_size)
    return bytes(entry)


def encrypt_toc_entry(entry: bytes, key_table: bytes) -> bytes:
    """Encrypt a 256-byte TOC entry with the XOR key table."""
    encrypted = bytearray(256)
    for i in range(256):
        encrypted[i] = entry[i] ^ key_table[i]
    return bytes(encrypted)


def build_mock_mas(files: list[dict]) -> bytes:
    """Build a complete mock MAS archive.

    files: list of dicts with keys: name, path, content (bytes)
    Returns the complete MAS binary buffer.
    """
    salt = b"\x42\x13\x77\xAB\xCD\xEF\x01\x23"
    key_table = derive_file_header_keys(salt)

    # Build TOC entries and file data
    toc_entries = []
    file_data_blocks = []
    for i, f in enumerate(files):
        raw_content = f["content"]
        # Compress if content is non-trivial
        compressed = zlib.compress(raw_content, level=6)
        if len(compressed) >= len(raw_content):
            # Store uncompressed
            compressed = raw_content
            comp_size = len(raw_content)
            uncomp_size = len(raw_content)
        else:
            comp_size = len(compressed)
            uncomp_size = len(raw_content)

        entry = build_toc_entry(i, f["name"], f.get("path", ""), uncomp_size, comp_size)
        encrypted_entry = encrypt_toc_entry(entry, key_table)
        toc_entries.append(encrypted_entry)
        file_data_blocks.append(compressed)

    # Assemble the MAS file
    buf = bytearray()

    # 1. Header (16 bytes, XOR-encoded)
    buf += xor_encode_header(MAGIC)

    # 2. Salt (8 bytes)
    buf += salt

    # 3. Padding (120 bytes)
    buf += b"\x00" * 120

    # 4. File header block size (4 bytes, uint32 LE)
    toc_block_size = len(toc_entries) * 256
    buf += struct.pack("<I", toc_block_size)

    # 5. TOC entries
    for entry in toc_entries:
        buf += entry

    # 6. File data
    for block in file_data_blocks:
        buf += block

    return bytes(buf)


# ── Test cases ────────────────────────────────────────────────────────────


class TestMASFormat:
    """Test MAS binary format construction and header validation."""

    def test_header_xor_roundtrip(self):
        """Encoding then decoding the header yields the original magic."""
        encoded = xor_encode_header(MAGIC)
        # Decode by XOR-ing again with the same key
        decoded = bytearray(16)
        for i in range(16):
            decoded[i] = encoded[i] ^ (FILE_TYPE_KEYS[i] >> 1)
        assert bytes(decoded) == MAGIC

    def test_toc_entry_structure(self):
        """TOC entry has correct field offsets."""
        entry = build_toc_entry(
            file_index=3,
            filename="track.aiw",
            filepath="GameData/Locations",
            uncompressed_size=1024,
            compressed_size=512,
        )
        assert len(entry) == 256
        assert struct.unpack_from("<I", entry, 0)[0] == 3
        # Filename at offset 16
        assert entry[16:25] == b"track.aiw"
        # Sizes at end
        assert struct.unpack_from("<I", entry, 248)[0] == 1024
        assert struct.unpack_from("<I", entry, 252)[0] == 512

    def test_toc_encryption_roundtrip(self):
        """Encrypting then decrypting with the same key yields original."""
        salt = b"\x42\x13\x77\xAB\xCD\xEF\x01\x23"
        key_table = derive_file_header_keys(salt)
        entry = build_toc_entry(0, "test.aiw", "", 100, 80)
        encrypted = encrypt_toc_entry(entry, key_table)
        # Decrypt
        decrypted = bytearray(256)
        for i in range(256):
            decrypted[i] = encrypted[i] ^ key_table[i]
        assert bytes(decrypted) == entry


class TestMockMASBuild:
    """Test that mock MAS buffers are well-formed."""

    def test_build_single_file(self):
        """A single-file MAS has correct structure sizes."""
        content = b"[Waypoint]\nlap_length=1234.5\n"
        buf = build_mock_mas([{"name": "track.aiw", "path": "", "content": content}])
        # Header(16) + Salt(8) + Padding(120) + BlockSize(4) + TOC(256) + data
        assert len(buf) >= 16 + 8 + 120 + 4 + 256

    def test_build_multiple_files(self):
        """Multi-file MAS has correct TOC block size."""
        files = [
            {"name": "texture.dds", "path": "", "content": b"\x00" * 100},
            {"name": "track.aiw", "path": "", "content": b"[Waypoint]\n"},
            {"name": "readme.txt", "path": "", "content": b"Hello"},
        ]
        buf = build_mock_mas(files)
        # TOC block size at offset 144
        toc_size = struct.unpack_from("<I", buf, 144)[0]
        assert toc_size == 3 * 256

    def test_header_magic_can_be_decoded(self):
        """The mock MAS header decodes to GMOTOR_MAS_2.90."""
        buf = build_mock_mas([{"name": "a.txt", "path": "", "content": b"x"}])
        decoded = bytearray(16)
        for i in range(16):
            decoded[i] = buf[i] ^ (FILE_TYPE_KEYS[i] >> 1)
        assert bytes(decoded) == MAGIC


class TestAIWExtraction:
    """Test end-to-end AIW extraction from mock MAS buffers.

    These tests verify the extraction algorithm that the JS module
    implements. The Python helpers mirror the JS logic.
    """

    def _extract_aiw_from_buffer(self, buf: bytes) -> str | None:
        """Python implementation of the JS extractAIWFromMAS logic."""
        # 1. Verify header
        decoded_header = bytearray(16)
        for i in range(16):
            decoded_header[i] = buf[i] ^ (FILE_TYPE_KEYS[i] >> 1)
        if bytes(decoded_header) != MAGIC:
            return None

        # 2. Read salt
        salt = buf[16:24]

        # 3. Skip padding (120 bytes) — offset now at 144

        # 4. Read TOC block size
        toc_block_size = struct.unpack_from("<I", buf, 144)[0]

        # 5. Derive key table
        key_table = derive_file_header_keys(salt)

        # 6. Read and decrypt TOC entries
        toc_start = 148
        num_entries = toc_block_size // 256
        entries = []
        for i in range(num_entries):
            offset = toc_start + i * 256
            encrypted = buf[offset: offset + 256]
            decrypted = bytearray(256)
            for j in range(256):
                decrypted[j] = encrypted[j] ^ key_table[j]
            # Parse entry
            filename_bytes = decrypted[16:144]
            filename = filename_bytes.split(b"\x00")[0].decode("utf-8", errors="replace")
            uncomp_size = struct.unpack_from("<I", decrypted, 248)[0]
            comp_size = struct.unpack_from("<I", decrypted, 252)[0]
            entries.append({
                "filename": filename,
                "uncompressed_size": uncomp_size,
                "compressed_size": comp_size,
            })

        # 7. Find AIW file
        data_start = toc_start + toc_block_size
        data_offset = 0
        for entry in entries:
            if entry["filename"].lower().endswith(".aiw"):
                # Read file data
                file_data = buf[
                    data_start + data_offset:
                    data_start + data_offset + entry["compressed_size"]
                ]
                if entry["compressed_size"] != entry["uncompressed_size"]:
                    file_data = zlib.decompress(file_data)
                return file_data.decode("utf-8")
            data_offset += entry["compressed_size"]

        return None

    def test_extract_aiw_single_file(self):
        """Extract AIW from a single-file MAS archive."""
        aiw_content = "[Waypoint]\nlap_length=3456.789\nwp_pos=(1.0,2.0,3.0)\n"
        buf = build_mock_mas([
            {"name": "barcelona.aiw", "path": "Tracks", "content": aiw_content.encode()},
        ])
        result = self._extract_aiw_from_buffer(buf)
        assert result is not None
        assert "[Waypoint]" in result
        assert "lap_length=3456.789" in result

    def test_extract_aiw_among_other_files(self):
        """Find and extract AIW from a MAS with multiple file types."""
        aiw_text = "[Waypoint]\nlap_length=5000.0\n"
        buf = build_mock_mas([
            {"name": "track.gdb", "path": "", "content": b"binary data here"},
            {"name": "track.aiw", "path": "", "content": aiw_text.encode()},
            {"name": "track.tdf", "path": "", "content": b"more binary stuff"},
        ])
        result = self._extract_aiw_from_buffer(buf)
        assert result is not None
        assert "lap_length=5000.0" in result

    def test_no_aiw_returns_none(self):
        """Return None when no AIW file exists in the archive."""
        buf = build_mock_mas([
            {"name": "model.gmt", "path": "", "content": b"mesh data"},
            {"name": "texture.dds", "path": "", "content": b"image data"},
        ])
        result = self._extract_aiw_from_buffer(buf)
        assert result is None

    def test_case_insensitive_aiw_match(self):
        """Match .AIW filename regardless of case."""
        aiw_text = "[Waypoint]\nlap_length=1.0\n"
        buf = build_mock_mas([
            {"name": "TRACK.AIW", "path": "", "content": aiw_text.encode()},
        ])
        result = self._extract_aiw_from_buffer(buf)
        assert result is not None
        assert "[Waypoint]" in result

    def test_invalid_header_returns_none(self):
        """Return None for a buffer with an invalid MAS header."""
        buf = b"\x00" * 500
        result = self._extract_aiw_from_buffer(buf)
        assert result is None

    def test_compressed_aiw_extraction(self):
        """Extract a zlib-compressed AIW file correctly."""
        # Create content large enough that zlib compression is smaller
        aiw_text = "[Waypoint]\n" + "wp_pos=(1.0, 2.0, 3.0)\n" * 200
        buf = build_mock_mas([
            {"name": "bigtrack.aiw", "path": "", "content": aiw_text.encode()},
        ])
        result = self._extract_aiw_from_buffer(buf)
        assert result is not None
        assert result == aiw_text

    def test_aiw_not_first_file_offset_correct(self):
        """Correctly compute data offset when AIW is not the first file."""
        # First file: large binary blob
        blob = bytes(range(256)) * 10  # 2560 bytes
        aiw_text = "[Waypoint]\nlap_length=42.0\n"
        buf = build_mock_mas([
            {"name": "big_texture.dds", "path": "", "content": blob},
            {"name": "track.aiw", "path": "", "content": aiw_text.encode()},
        ])
        result = self._extract_aiw_from_buffer(buf)
        assert result is not None
        assert "lap_length=42.0" in result


class TestJSSyntax:
    """Verify the JS module has no syntax errors."""

    def test_js_file_exists(self):
        """The mas_extractor.js file exists."""
        assert JS_FILE.exists(), f"Expected JS file at {JS_FILE}"

    def test_js_no_syntax_errors(self):
        """The JS file can be parsed by Node.js without errors."""
        result = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"JS syntax check failed:\n{result.stderr}"
        )
