import os, sys, logging, argparse, requests

MICROSOFT_SYMBOL_STORE = "https://msdl.microsoft.com/download/symbols"

def try_download_pdb(url, filename, guid, output_filename):
    pdb_url = f"{url}/{filename}/{guid}/{filename}"
    logging.debug("[-] testing url : %s" % pdb_url)
    response = requests.get(pdb_url, stream=True)
    if response.status_code != 200:
        logging.warning("[x] not found pdb at url : %s" % pdb_url)
        return response.status_code
    logging.info("[+] found pdb at url : %s" % pdb_url)
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)
    with open(output_filename, 'wb') as f:
        for data in response.iter_content(32*1024):
            f.write(data)
    return response.status_code

if __name__ == '__main__':
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    p = argparse.ArgumentParser("download pdb from microsoft symbol store")
    p.add_argument("--name", type=str, required=True)
    p.add_argument("--pdb", type=str, required=True)
    p.add_argument("--dir", type=str, required=True)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.getLogger().setLevel(logging.DEBUG if args.verbose else logging.INFO)
    with open(args.pdb, "r") as f:
        guids = f.read().split()
    for guid in guids:
        out = os.path.join(args.dir, guid, args.name)
        try_download_pdb(MICROSOFT_SYMBOL_STORE, args.name, guid, out)
