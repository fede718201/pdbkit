# pdbkit

Python toolkit to grab PDB debug symbols from Microsoft's symbol server and dump type definitions (structs, unions, enums) as C headers with field offsets. The whole idea came from [wbenny/pdbex](https://github.com/wbenny/pdbex) - I just wanted something similar in pure Python, no compilation needed.

## Usage

```bash
# extract the GUID from a DLL
python get_guid.py ./dlls/ntdll.dll

# download the matching PDB
echo "1EB9FACB04B940CBB22B5BD738A64B641" > guids.txt
python download_pdb_files.py --name ntdll.pdb --pdb guids.txt --dir ./symbols

# dump a struct
python pdbex.py _EPROCESS ./symbols/1EB9FACB04B940CBB22B5BD738A64B641/ntdll.pdb

# dump everything
python pdbex.py '*' ./symbols/1EB9FACB04B940CBB22B5BD738A64B641/ntdll.pdb -o out.h

# list all types
python pdbex.py -l ntdll.pdb

# search
python pdbex.py ntdll.pdb -s THREAD
```

## Install

```
pip install -r requirements.txt
```

PS: The code is rough, no proper comments, naming is all over the place. I wrote this for myself and didn't really clean it up before pushing. PRs welcome if you feel like fixing stuff.
