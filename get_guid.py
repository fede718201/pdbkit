import pefile, struct, sys

pe = pefile.PE(sys.argv[1] if len(sys.argv) > 1 else './dlls/ntdll.dll')
for dbg in pe.DIRECTORY_ENTRY_DEBUG:
    if dbg.struct.Type == 2:
        data = pe.__data__[dbg.struct.PointerToRawData:dbg.struct.PointerToRawData + dbg.struct.SizeOfData]
        if data[:4] == b'RSDS':
            d1, d2, d3 = struct.unpack('<IHH', data[4:12])
            d4 = data[12:20]
            age = struct.unpack('<I', data[20:24])[0]
            print('%08X%04X%04X%s%X' % (d1, d2, d3, d4.hex().upper(), age))
