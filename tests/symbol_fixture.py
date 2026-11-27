"""Small, deterministic MSF/PE fixtures; never used by production."""
import struct

GUID = bytes(range(16))


def pe(guid=GUID, age=1):
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x86, 1)
    struct.pack_into("<H", data, 0x94, 224)
    opt = 0x98
    struct.pack_into("<H", data, opt, 0x10b)
    struct.pack_into("<I", data, opt + 92, 16)
    struct.pack_into("<II", data, opt + 96 + 48, 0x1000, 28)
    struct.pack_into("<IIII", data, opt + 224 + 8, 512, 0x1000, 512, 512)
    struct.pack_into("<IIII", data, 512 + 12, 2, 32, 0x1020, 544)
    data[544:548] = b"RSDS"
    data[548:564] = guid
    struct.pack_into("<I", data, 564, age)
    data[568:576] = b"a.pdb\0\0\0"
    return bytes(data)


def pdb(guid=GUID, age=1):
    block = 512
    data = bytearray(block * 5)
    data[:32] = b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0"
    struct.pack_into("<6I", data, 32, block, 1, 5, 16, 0, 2)
    struct.pack_into("<I", data, 2 * block, 3)
    struct.pack_into("<4I", data, 3 * block, 2, 0xffffffff, 28, 4)
    struct.pack_into("<III", data, 4 * block, 20000404, 0, age)
    data[4 * block + 12:4 * block + 28] = guid
    return bytes(data)
