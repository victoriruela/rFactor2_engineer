"""
generate_fixtures.py — Generates synthetic MoTeC .ld binary test fixtures.

Run from any Python 3.7+ environment:
    python scripts/generate_fixtures.py

Writes fixtures to: crates/ld_parser/tests/fixtures/
"""

import struct
import pathlib

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "crates" / "ld_parser" / "tests" / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

LD_MAGIC = 0x0045_F836
HEADER_SIZE = 0x0C00
CHANNEL_RECORD_SIZE = 0x01A8

# ────────────────────────────────────────────────────────────────────────────
# Helper: build a null-padded fixed-width byte field
# ────────────────────────────────────────────────────────────────────────────
def fixed_str(s: str, width: int) -> bytes:
    encoded = s.encode("ascii")[:width]
    return encoded + b"\x00" * (width - len(encoded))


# ────────────────────────────────────────────────────────────────────────────
# Helper: build a single channel meta record
# ────────────────────────────────────────────────────────────────────────────
def make_channel_record(
    prev_offset: int,
    next_offset: int,
    data_offset: int,
    count: int,
    type_id: int,
    sample_rate: int,
    shift: int,
    multiplier: int,
    scale: int,
    decimal_places: int,
    name: str,
    short_name: str,
    units: str,
) -> bytes:
    rec = bytearray(CHANNEL_RECORD_SIZE)
    struct.pack_into("<I", rec, 0x000, prev_offset)
    struct.pack_into("<I", rec, 0x004, next_offset)
    struct.pack_into("<I", rec, 0x008, data_offset)
    struct.pack_into("<I", rec, 0x00C, count)
    struct.pack_into("<H", rec, 0x010, type_id)
    struct.pack_into("<H", rec, 0x012, sample_rate)
    struct.pack_into("<h", rec, 0x014, shift)
    struct.pack_into("<h", rec, 0x016, multiplier)
    struct.pack_into("<h", rec, 0x018, scale)
    struct.pack_into("<h", rec, 0x01A, decimal_places)
    rec[0x01C:0x03C] = fixed_str(name, 32)
    rec[0x03C:0x044] = fixed_str(short_name, 8)
    rec[0x044:0x050] = fixed_str(units, 12)
    return bytes(rec)


# ────────────────────────────────────────────────────────────────────────────
# Fixture 1: minimal_valid_ld3.ld
#   - LD3 format (magic + version=1)
#   - 2 channels: EngineRPM (Uint16) and ThrottlePos (Float32)
#   - Data block contains predictable synthetic samples
# ────────────────────────────────────────────────────────────────────────────
def write_minimal_valid_ld3():
    META_OFFSET = HEADER_SIZE                       # 0x0C00
    RPM_COUNT = 50
    THROTTLE_COUNT = 50

    # Data layout: RPM block immediately after meta, Throttle block after RPM
    RPM_DATA_OFFSET = META_OFFSET + 2 * CHANNEL_RECORD_SIZE
    THROTTLE_DATA_OFFSET = RPM_DATA_OFFSET + RPM_COUNT * 2   # u16 = 2 bytes each

    # Channel 0: EngineRPM (Uint16, type_id=0x0002)
    chan0_offset = META_OFFSET
    chan1_offset = META_OFFSET + CHANNEL_RECORD_SIZE
    chan0 = make_channel_record(
        prev_offset=0, next_offset=chan1_offset,
        data_offset=RPM_DATA_OFFSET, count=RPM_COUNT,
        type_id=0x0002, sample_rate=100,
        shift=0, multiplier=1, scale=0, decimal_places=0,
        name="EngineRPM", short_name="RPM", units="rpm",
    )
    # Channel 1: ThrottlePos (Float32, type_id=0x0000)
    chan1 = make_channel_record(
        prev_offset=chan0_offset, next_offset=0,
        data_offset=THROTTLE_DATA_OFFSET, count=THROTTLE_COUNT,
        type_id=0x0000, sample_rate=100,
        shift=0, multiplier=1, scale=0, decimal_places=2,
        name="ThrottlePos", short_name="Thr", units="%",
    )

    # Header
    hdr = bytearray(HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x000, LD_MAGIC)
    struct.pack_into("<I", hdr, 0x004, 1)                        # version = 1 (LD3)
    struct.pack_into("<I", hdr, 0x008, META_OFFSET)              # channel_meta_offset
    struct.pack_into("<I", hdr, 0x00C, 2 * CHANNEL_RECORD_SIZE) # channel_meta_size
    struct.pack_into("<I", hdr, 0x010, RPM_DATA_OFFSET)          # data_offset (start of first data block)
    # data_size = RPM block + Throttle block
    data_size = RPM_COUNT * 2 + THROTTLE_COUNT * 4
    struct.pack_into("<I", hdr, 0x014, data_size)
    hdr[0x018:0x058] = fixed_str("Race", 64)
    hdr[0x058:0x098] = fixed_str("Silverstone", 64)
    hdr[0x098:0x0D8] = fixed_str("Formula 2000", 64)
    hdr[0x0D8:0x118] = fixed_str("Test Driver", 64)
    hdr[0x118:0x138] = fixed_str("2024-06-09 14:32:00", 32)

    # Data: RPM values (0..5000 linear, u16 little-endian)
    rpm_data = b"".join(struct.pack("<H", i * 100) for i in range(RPM_COUNT))
    # Data: Throttle (0.0..1.0 linear, f32 little-endian)
    throttle_data = b"".join(
        struct.pack("<f", i / (THROTTLE_COUNT - 1)) for i in range(THROTTLE_COUNT)
    )

    full = bytes(hdr) + chan0 + chan1 + rpm_data + throttle_data
    path = FIXTURES_DIR / "minimal_valid_ld3.ld"
    path.write_bytes(full)
    print(f"  wrote {path} ({len(full)} bytes)")


# ────────────────────────────────────────────────────────────────────────────
# Fixture 2: bad_magic.ld
#   - Wrong magic; all other fields valid
#   - Parser must return ParseError::UnknownMagic
# ────────────────────────────────────────────────────────────────────────────
def write_bad_magic():
    hdr = bytearray(HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x000, 0xDEAD_BEEF)   # bad magic
    struct.pack_into("<I", hdr, 0x004, 1)
    struct.pack_into("<I", hdr, 0x008, HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x010, HEADER_SIZE + CHANNEL_RECORD_SIZE)
    path = FIXTURES_DIR / "bad_magic.ld"
    path.write_bytes(bytes(hdr))
    print(f"  wrote {path} ({len(hdr)} bytes)")


# ────────────────────────────────────────────────────────────────────────────
# Fixture 3: unsupported_version.ld
#   - Valid magic but version = 99
#   - Parser must return ParseError::UnsupportedVersion
# ────────────────────────────────────────────────────────────────────────────
def write_unsupported_version():
    hdr = bytearray(HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x000, LD_MAGIC)
    struct.pack_into("<I", hdr, 0x004, 99)             # unsupported version
    struct.pack_into("<I", hdr, 0x008, HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x010, HEADER_SIZE + CHANNEL_RECORD_SIZE)
    path = FIXTURES_DIR / "unsupported_version.ld"
    path.write_bytes(bytes(hdr))
    print(f"  wrote {path} ({len(hdr)} bytes)")


# ────────────────────────────────────────────────────────────────────────────
# Fixture 4: channel_unknown_type.ld
#   - Valid header + 1 channel with type_id=0x0099 (unknown)
#   - Parser must emit ParseWarning::UnsupportedDataType, not crash
# ────────────────────────────────────────────────────────────────────────────
def write_channel_unknown_type():
    META_OFFSET = HEADER_SIZE
    chan = make_channel_record(
        prev_offset=0, next_offset=0,
        data_offset=META_OFFSET + CHANNEL_RECORD_SIZE, count=10,
        type_id=0x0099,   # unknown
        sample_rate=100, shift=0, multiplier=1, scale=0, decimal_places=0,
        name="Mystery", short_name="Myst", units="?",
    )
    hdr = bytearray(HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x000, LD_MAGIC)
    struct.pack_into("<I", hdr, 0x004, 1)
    struct.pack_into("<I", hdr, 0x008, META_OFFSET)
    struct.pack_into("<I", hdr, 0x00C, CHANNEL_RECORD_SIZE)
    struct.pack_into("<I", hdr, 0x010, META_OFFSET + CHANNEL_RECORD_SIZE)
    struct.pack_into("<I", hdr, 0x014, 40)  # 10 * 4 bytes placeholder data
    hdr[0x018:0x058] = fixed_str("Qualifying", 64)
    data = bytes(40)  # 10 zeros placeholder
    path = FIXTURES_DIR / "channel_unknown_type.ld"
    path.write_bytes(bytes(hdr) + chan + data)
    print(f"  wrote {path}")


if __name__ == "__main__":
    print("Generating .ld test fixtures...")
    write_minimal_valid_ld3()
    write_bad_magic()
    write_unsupported_version()
    write_channel_unknown_type()
    print("Done.")
