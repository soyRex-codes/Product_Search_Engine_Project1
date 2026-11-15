"""Download immutable upstream ESCI files and verify Git LFS SHA-256 hashes."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

COMMIT = '7916cdf6ab75a462e77f20ab40428a10923998d5'
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/raw'
NAMES = ['shopping_queries_dataset_examples.parquet', 'shopping_queries_dataset_products.parquet', 'shopping_queries_dataset_sources.csv']

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {'repository': 'https://github.com/amazon-science/esci-data', 'commit': COMMIT, 'files': []}
    for name in NAMES:
        raw = f'https://raw.githubusercontent.com/amazon-science/esci-data/{COMMIT}/shopping_queries_dataset/{name}'
        with urlopen(raw, timeout=120) as response:
            content = response.read()
        expected = None
        size = len(content)
        if content.startswith(b'version https://git-lfs.github.com/spec/v1'):
            fields = dict(line.split(' ', 1) for line in content.decode().splitlines())
            expected = fields['oid'].split(':')[1]
            size = int(fields['size'])
            url = f'https://media.githubusercontent.com/media/amazon-science/esci-data/{COMMIT}/shopping_queries_dataset/{name}'
        else:
            url = raw
            expected = hashlib.sha256(content).hexdigest()
        path = DEST / name
        if not (path.exists() and path.stat().st_size == size and digest(path) == expected):
            temporary = path.with_suffix(path.suffix + '.part')
            print(f'Downloading {name}: {size:,} bytes', flush=True)
            if url == raw:
                temporary.write_bytes(content)
            else:
                with urlopen(url, timeout=120) as response, temporary.open('wb') as target:
                    while chunk := response.read(8 * 1024 * 1024):
                        target.write(chunk)
            if temporary.stat().st_size != size or digest(temporary) != expected:
                raise ValueError(f'Integrity failure: {name}')
            temporary.replace(path)
        manifest['files'].append({'name': name, 'bytes': size, 'sha256': expected})
        print(f'Verified {name}', flush=True)
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

if __name__ == '__main__':
    main()
