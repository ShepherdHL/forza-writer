"""Parse a ForzaTech modelbin file and dump its structure."""
import struct
import sys
from pathlib import Path


def read_u8(data, off): return data[off]
def read_u16(data, off): return struct.unpack_from('<H', data, off)[0]
def read_u32(data, off): return struct.unpack_from('<I', data, off)[0]
def read_i16(data, off): return struct.unpack_from('<h', data, off)[0]
def read_f32(data, off): return struct.unpack_from('<f', data, off)[0]

def read_tag(data, off):
    return data[off:off+4][::-1].decode('ascii', errors='replace')


def parse_grub_header(data, off):
    """Parse the Grub chunk table header at offset."""
    magic = read_tag(data, off)
    assert magic == 'Grub', f"Expected Grub, got {magic!r}"
    version = read_u16(data, off+4)
    flags = read_u16(data, off+6)
    data_offset = read_u32(data, off+8)   # offset to chunk data section
    data_size = read_u32(data, off+12)    # size of data section
    chunk_count = read_u32(data, off+16)
    print(f"Grub header: version={version} flags=0x{flags:04x} data_offset=0x{data_offset:x} data_size=0x{data_size:x} chunks={chunk_count}")

    chunks = []
    pos = off + 20
    for i in range(chunk_count):
        tag = read_tag(data, pos)
        unk = read_u16(data, pos+4)
        unk2 = read_u16(data, pos+6)
        chunk_off = read_u32(data, pos+8)
        chunk_abs = read_u32(data, pos+12)  # absolute offset in file
        size_a = read_u32(data, pos+16)
        size_b = read_u32(data, pos+20)
        chunks.append({'tag': tag, 'offset': chunk_off, 'abs': chunk_abs, 'size_a': size_a, 'size_b': size_b, 'unk': unk, 'unk2': unk2})
        pos += 24
    return chunks, pos


def parse_verB(data, off, size):
    """Parse VerB (vertex buffer)."""
    # Try to find vertex data: typically float pairs for 2D vinyl
    print(f"  VerB at 0x{off:x}, size={size}")
    # Dump raw hex
    chunk = data[off:off+min(size, 128)]
    print(f"  hex: {chunk.hex(' ')}")

    # Try reading as i16 pairs (normalized coords)
    n = size // 2
    shorts = struct.unpack_from(f'<{n}h', data, off)
    print(f"  as int16[{n}]: {shorts[:20]}")

    # Try reading as f32
    nf = size // 4
    floats = struct.unpack_from(f'<{nf}f', data, off)
    print(f"  as f32[{nf}]: {[f'{v:.4f}' for v in floats[:16]]}")


def parse_indB(data, off, size):
    """Parse IndB (index buffer)."""
    print(f"  IndB at 0x{off:x}, size={size}")
    n = size // 2
    indices = struct.unpack_from(f'<{n}H', data, off)
    print(f"  as uint16[{n}] (triangles): {indices}")


def parse_VLay(data, off, size):
    """Parse VLay (vertex layout descriptor)."""
    print(f"  VLay at 0x{off:x}, size={size}")
    chunk = data[off:off+size]
    print(f"  hex: {chunk.hex(' ')}")


def parse_MatI(data, off, size):
    """Parse MatI (material info)."""
    print(f"  MatI at 0x{off:x}, size={size}")
    chunk = data[off:off+size]
    # Try to find readable strings
    text = chunk.decode('latin-1')
    printable = ''.join(c if 32 <= ord(c) < 127 else '.' for c in text)
    print(f"  text: {printable[:200]}")


def parse_Mesh(data, off, size):
    """Parse Mesh descriptor."""
    print(f"  Mesh at 0x{off:x}, size={size}")
    chunk = data[off:off+size]
    print(f"  hex: {chunk.hex(' ')}")


def main(path):
    data = Path(path).read_bytes()
    print(f"File: {path}  ({len(data)} bytes)\n")

    # Parse top-level Grub
    chunks, _ = parse_grub_header(data, 0)
    print()

    for c in chunks:
        tag = c['tag']
        off = c['abs']
        size = c['size_a']
        print(f"Chunk '{tag}': abs=0x{off:x} size={size} (unk={c['unk']},{c['unk2']})")

        if tag == 'Grub':
            # Nested Grub: recurse one level
            sub_chunks, _ = parse_grub_header(data, off)
            for sc in sub_chunks:
                stag = sc['tag']
                soff = sc['abs']
                ssize = sc['size_a']
                print(f"  Sub-chunk '{stag}': abs=0x{soff:x} size={ssize}")
                if stag == 'VerB':
                    parse_verB(data, soff, ssize)
                elif stag == 'IndB':
                    parse_indB(data, soff, ssize)
                elif stag == 'VLay':
                    parse_VLay(data, soff, ssize)
                elif stag == 'MatI':
                    parse_MatI(data, soff, ssize)
                elif stag == 'Mesh':
                    parse_Mesh(data, soff, ssize)
        elif tag == 'VerB':
            parse_verB(data, off, size)
        elif tag == 'IndB':
            parse_indB(data, off, size)
        elif tag == 'VLay':
            parse_VLay(data, off, size)
        elif tag == 'MatI':
            parse_MatI(data, off, size)
        elif tag == 'Mesh':
            parse_Mesh(data, off, size)
        print()


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'user-assets/S_01.modelbin')
