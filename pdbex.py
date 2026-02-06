#!/usr/bin/env python3

import sys, struct, argparse, os

try:
    import pdbparse
    from pdbparse import tpi as tpi_module
except ImportError:
    print("pip install pdbparse construct", file=sys.stderr)
    sys.exit(1)

def _toidx(val):
    if val is None: return None
    if isinstance(val, int): return val
    for a in ('tpi_idx', 'type_index'):
        if hasattr(val, a): return int(getattr(val, a))
    if hasattr(val, 'index'):
        v = val.index
        if isinstance(v, int): return v
    try: return int(val)
    except: pass
    for a in dir(val):
        if a.startswith('_'): continue
        v = getattr(val, a, None)
        if isinstance(v, int) and v >= 0x1000: return v
    return None

_BASE = {
    0x00: "T_NOTYPE", 0x03: "void", 0x08: "HRESULT",
    0x10: "signed char", 0x11: "short", 0x12: "long", 0x13: "__int64", 0x14: "__int128",
    0x20: "unsigned char", 0x21: "unsigned short", 0x22: "unsigned long",
    0x23: "unsigned __int64", 0x24: "unsigned __int128",
    0x30: "unsigned char", 0x31: "unsigned short", 0x32: "unsigned long", 0x33: "unsigned __int64",
    0x40: "float", 0x41: "double", 0x42: "long double", 0x43: "__float128",
    0x68: "char", 0x69: "unsigned char", 0x70: "char", 0x71: "wchar_t",
    0x72: "short", 0x73: "unsigned short", 0x74: "int", 0x75: "unsigned int",
    0x76: "__int64", 0x77: "unsigned __int64",
}

_BASE_SZ = {
    0x03:0, 0x10:1, 0x20:1, 0x68:1, 0x69:1, 0x70:1, 0x30:1,
    0x11:2, 0x21:2, 0x71:2, 0x72:2, 0x73:2, 0x31:2,
    0x12:4, 0x22:4, 0x74:4, 0x75:4, 0x32:4, 0x40:4,
    0x13:8, 0x23:8, 0x76:8, 0x77:8, 0x33:8, 0x41:8,
    0x42:10, 0x14:16, 0x24:16, 0x43:16,
}

def _resolve_base(ti):
    base = ti & 0xFF
    mode = (ti >> 8) & 0xF
    s = _BASE.get(base, f"/* 0x{base:02X} */")
    if mode in (1,2,3,4,5,6): return f"{s} *"
    return s

class Resolver:
    def __init__(self, path):
        self.pdb = pdbparse.parse(path, fast_load=False)
        if not hasattr(self.pdb, 'STREAM_TPI'):
            self.pdb.STREAM_TPI = self.pdb.streams[2]
            self.pdb.STREAM_TPI.load(unnamed_hack=True, elim_fwdrefs=True)
        self.types = self.pdb.STREAM_TPI.types
        self._cache = {}
        self._printed = set()
        self.structs, self.unions, self.enums = {}, {}, {}
        for idx, t in self.types.items():
            lt = getattr(t, 'leaf_type', None)
            name = getattr(t, 'name', None)
            if not name or name.startswith('<'): continue
            prop = getattr(t, 'prop', None)
            if prop and getattr(prop, 'fwdref', False): continue
            if lt in ('LF_STRUCTURE','LF_STRUCTURE_ST'): self.structs[name] = idx
            elif lt in ('LF_UNION','LF_UNION_ST'): self.unions[name] = idx
            elif lt in ('LF_ENUM','LF_ENUM_ST'): self.enums[name] = idx

    def _fields(self, fl_idx):
        idx = _toidx(fl_idx)
        if idx is None: return []
        fl = self.types.get(idx)
        if fl is None: return []
        return getattr(fl, 'substructs', []) or []

    def resolve(self, ti, ctx=None):
        ti = _toidx(ti)
        if ti is None: return ("void", "")
        if isinstance(ti, int) and ti < 0x1000: return (_resolve_base(ti), "")
        k = (ti, ctx)
        if k in self._cache: return self._cache[k]
        t = self.types.get(ti)
        if t is None:
            r = (f"/* 0x{ti:X} */", "")
            self._cache[k] = r
            return r
        lt = getattr(t, 'leaf_type', '')
        r = self._leaf(t, lt, ctx)
        self._cache[k] = r
        return r

    def _leaf(self, t, lt, ctx):
        if lt == 'LF_POINTER':
            b, s = self.resolve(_toidx(getattr(t, 'utype', None)))
            if b.startswith("/* func:"): return (b, s)
            attr = getattr(t, 'ptr_attr', None)
            if attr and getattr(attr, 'isconst', False): return (f"{b} * const", s)
            return (f"{b} *", s)
        if lt in ('LF_ARRAY','LF_ARRAY_ST'):
            et = _toidx(getattr(t, 'elemtype', getattr(t, 'element_type', None)))
            sz = getattr(t, 'size', 0)
            b, _ = self.resolve(et)
            esz = self._sz(et)
            if esz and esz > 0: return (b, f"[{sz//esz}]")
            if sz > 0: return (b, f"[/* {sz}b */]")
            return (b, "[]")
        if lt == 'LF_MODIFIER':
            b, s = self.resolve(_toidx(getattr(t, 'modified_type', None)))
            mod = getattr(t, 'modifier', None)
            p = []
            if mod:
                if getattr(mod, 'MOD_const', False): p.append("const")
                if getattr(mod, 'MOD_volatile', False): p.append("volatile")
            if p: return (" ".join(p) + " " + b, s)
            return (b, s)
        if lt == 'LF_BITFIELD':
            b, _ = self.resolve(_toidx(getattr(t, 'base_type', None)))
            return (b, f" : {getattr(t, 'length', 0)}")
        if lt in ('LF_STRUCTURE','LF_STRUCTURE_ST'):
            return (f"struct {getattr(t, 'name', '<anon>')}", "")
        if lt in ('LF_UNION','LF_UNION_ST'):
            return (f"union {getattr(t, 'name', '<anon>')}", "")
        if lt in ('LF_ENUM','LF_ENUM_ST'):
            return (f"enum {getattr(t, 'name', '<anon>')}", "")
        if lt in ('LF_PROCEDURE','LF_MFUNCTION'):
            return self._proc(t)
        return (f"/* {lt} */", "")

    def _proc(self, t):
        ret, _ = self.resolve(_toidx(getattr(t, 'rvtype', None)))
        ali = _toidx(getattr(t, 'arglist', None))
        args = "void"
        if ali is not None:
            al = self.types.get(ali)
            if al:
                ats = getattr(al, 'arg_type', [])
                if hasattr(ats, '__iter__') and not isinstance(ats, (str, bytes)):
                    a = [f"{self.resolve(_toidx(x))[0]}{self.resolve(_toidx(x))[1]}" for x in ats]
                    if a: args = ", ".join(a)
        return (f"/* func: {ret} (*)({args}) */", "")

    def _sz(self, ti):
        ti = _toidx(ti)
        if ti is None: return 0
        if isinstance(ti, int) and ti < 0x1000:
            mode = (ti >> 8) & 0xF
            if mode in (4,5): return 4
            if mode == 6: return 8
            if mode in (1,2,3): return 2
            return _BASE_SZ.get(ti & 0xFF, 0)
        t = self.types.get(ti)
        if t is None: return 0
        lt = getattr(t, 'leaf_type', '')
        if lt in ('LF_STRUCTURE','LF_STRUCTURE_ST','LF_UNION','LF_UNION_ST'):
            return getattr(t, 'size', 0)
        if lt in ('LF_ENUM','LF_ENUM_ST'):
            u = _toidx(getattr(t, 'utype', None))
            return self._sz(u) if u else 4
        if lt == 'LF_POINTER': return 8
        if lt in ('LF_ARRAY','LF_ARRAY_ST'): return getattr(t, 'size', 0)
        if lt == 'LF_MODIFIER': return self._sz(_toidx(getattr(t, 'modified_type', None)))
        if lt == 'LF_BITFIELD': return self._sz(_toidx(getattr(t, 'base_type', None)))
        return 0

    def dump(self, name, inline=False):
        idx = self.structs.get(name) or self.unions.get(name) or self.enums.get(name)
        if idx is None:
            alt = f"_{name}" if not name.startswith('_') else name[1:]
            idx = self.structs.get(alt) or self.unions.get(alt) or self.enums.get(alt)
            if idx is not None: name = alt
        if idx is None: return f"/* '{name}' not found */\n"
        out = []
        if inline:
            for di in self._deps(idx, set()):
                if di not in self._printed:
                    c = self._fmt(di)
                    if c: out.append(c)
                    self._printed.add(di)
        c = self._fmt(idx)
        if c: out.append(c); self._printed.add(idx)
        return "\n".join(out)

    def _fmt(self, ti):
        t = self.types.get(ti)
        if t is None: return ""
        lt = getattr(t, 'leaf_type', '')
        name = getattr(t, 'name', '')
        if lt in ('LF_STRUCTURE','LF_STRUCTURE_ST'): return self._fmt_struct(t, name, "struct")
        if lt in ('LF_UNION','LF_UNION_ST'): return self._fmt_struct(t, name, "union")
        if lt in ('LF_ENUM','LF_ENUM_ST'): return self._fmt_enum(t, name)
        return ""

    def _fmt_struct(self, t, name, kw):
        sz = getattr(t, 'size', 0)
        lines = [f"typedef {kw} {name}", "{"]
        for f in self._fields(getattr(t, 'fieldlist', None)):
            flt = getattr(f, 'leaf_type', '')
            if flt in ('LF_MEMBER','LF_MEMBER_ST'):
                off = getattr(f, 'offset', 0)
                fn = getattr(f, 'name', '?')
                ts, sx = self.resolve(_toidx(getattr(f, 'index', None)))
                lines.append(f"  /* 0x{off:04X} */ {ts} {fn}{sx};")
            elif flt in ('LF_NESTTYPE','LF_NESTTYPE_ST'):
                nn = getattr(f, 'name', '')
                if nn: lines.append(f"  /* nested: {nn} */")
            elif flt in ('LF_STMEMBER','LF_STMEMBER_ST'):
                fn = getattr(f, 'name', '?')
                ts, sx = self.resolve(_toidx(getattr(f, 'index', None)))
                lines.append(f"  /* static */ {ts} {fn}{sx};")
            elif flt in ('LF_BCLASS','LF_BCLASS_ST'):
                bs, _ = self.resolve(_toidx(getattr(f, 'index', None)))
                off = getattr(f, 'offset', 0)
                lines.append(f"  /* 0x{off:04X} */ /* base: {bs} */")
        td = name[1:] if name.startswith('_') else name
        lines.append(f"}} {td}, *P{td}; /* 0x{sz:X} */")
        return "\n".join(lines) + "\n"

    def _fmt_enum(self, t, name):
        lines = [f"typedef enum {name}", "{"]
        fields = self._fields(getattr(t, 'fieldlist', None))
        for i, f in enumerate(fields):
            if getattr(f, 'leaf_type', '') in ('LF_ENUMERATE','LF_ENUMERATE_ST'):
                en = getattr(f, 'name', '')
                ev = getattr(f, 'value', 0)
                c = "," if i < len(fields)-1 else ""
                lines.append(f"  {en} = 0x{ev:X}{c}")
        td = name[1:] if name.startswith('_') else name
        lines.append(f"}} {td};")
        return "\n".join(lines) + "\n"

    def _deps(self, ti, visited):
        ti = _toidx(ti)
        if ti is None or ti in visited: return []
        visited.add(ti)
        t = self.types.get(ti)
        if t is None: return []
        lt = getattr(t, 'leaf_type', '')
        deps = []
        if lt in ('LF_STRUCTURE','LF_STRUCTURE_ST','LF_UNION','LF_UNION_ST'):
            for f in self._fields(getattr(t, 'fieldlist', None)):
                if getattr(f, 'leaf_type', '') in ('LF_MEMBER','LF_MEMBER_ST'):
                    d = self._find_dep(_toidx(getattr(f, 'index', None)))
                    if d and d != ti:
                        deps.extend(self._deps(d, visited))
                        deps.append(d)
        return deps

    def _find_dep(self, ti):
        ti = _toidx(ti)
        if ti is None or (isinstance(ti, int) and ti < 0x1000): return None
        t = self.types.get(ti)
        if t is None: return None
        lt = getattr(t, 'leaf_type', '')
        if lt in ('LF_STRUCTURE','LF_STRUCTURE_ST','LF_UNION','LF_UNION_ST','LF_ENUM','LF_ENUM_ST'):
            prop = getattr(t, 'prop', None)
            if prop and getattr(prop, 'fwdref', False):
                n = getattr(t, 'name', '')
                return self.structs.get(n) or self.unions.get(n) or self.enums.get(n)
            return ti
        if lt == 'LF_POINTER': return None
        if lt in ('LF_ARRAY','LF_ARRAY_ST'):
            return self._find_dep(_toidx(getattr(t, 'elemtype', getattr(t, 'element_type', None))))
        if lt == 'LF_MODIFIER':
            return self._find_dep(_toidx(getattr(t, 'modified_type', None)))
        return None

    def list_all(self):
        s = set()
        s.update(self.structs.keys(), self.unions.keys(), self.enums.keys())
        return sorted(s)

def main():
    p = argparse.ArgumentParser(description="pdbex.py")
    p.add_argument('symbol', nargs='?')
    p.add_argument('pdb', nargs='?')
    p.add_argument('-o', '--output')
    p.add_argument('-a', '--inline-all', action='store_true')
    p.add_argument('-l', '--list', action='store_true')
    p.add_argument('-s', '--search')
    args = p.parse_args()

    pdb_path = args.pdb
    if not pdb_path:
        if args.symbol and args.symbol.endswith('.pdb') and os.path.exists(args.symbol):
            pdb_path = args.symbol; args.list = True
        else:
            p.print_help(); sys.exit(1)

    if not os.path.exists(pdb_path):
        print(f"'{pdb_path}' not found", file=sys.stderr); sys.exit(1)

    print(f"Loading {pdb_path}...", file=sys.stderr)
    try: r = Resolver(pdb_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr); sys.exit(1)

    print(f"{len(r.structs)} structs, {len(r.unions)} unions, {len(r.enums)} enums", file=sys.stderr)

    out = open(args.output, 'w') if args.output else sys.stdout

    try:
        if args.search:
            q = args.search.upper()
            for n in r.list_all():
                if q in n.upper(): print(n, file=out)
            return
        if args.list or args.symbol is None:
            for n in r.list_all(): print(n, file=out)
            return

        print(f"/*\n * PDB: {os.path.basename(pdb_path)}\n */\n", file=out)

        if args.symbol == '*':
            for n in r.list_all():
                c = r.dump(n)
                if c and 'not found' not in c: print(c, file=out)
        else:
            print(r.dump(args.symbol, inline=args.inline_all), file=out)
    finally:
        if args.output and out != sys.stdout:
            out.close()
            print(f"-> {args.output}", file=sys.stderr)

if __name__ == '__main__':
    main()
