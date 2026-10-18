"""Build a resumable draft vector artifact; never writes the app's reviewed index."""
import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path

import httpx

from backend.core import Settings


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


async def build(staging, output, settings, batch_size=32, transport=None):
    if not 1 <= batch_size <= 128:
        raise ValueError('Batch size must be between 1 and 128')
    manifest = json.loads((staging / 'manifest.json').read_text())
    source_hash = hashlib.sha256((staging / 'source.pdf').read_bytes()).hexdigest()
    if source_hash != manifest['sha256']:
        raise ValueError('Source PDF checksum mismatch')
    raw = (staging / 'chunks.review.json').read_bytes()
    chunks = json.loads(raw)
    if not chunks or len({c['id'] for c in chunks}) != len(chunks):
        raise ValueError('Expected nonempty chunks with unique IDs')
    identity = dict(source_sha256=source_hash, chunks_sha256=hashlib.sha256(raw).hexdigest(),
                    model=settings.embedding_model)
    artifact = dict(identity, status='draft', active_index_updated=False,
                    source_manifest=manifest, records=[], complete=False)
    if output.exists():
        artifact = json.loads(output.read_text())
        if any(artifact.get(k) != v for k, v in identity.items()):
            raise ValueError('Existing output belongs to a different source or model')
    records = artifact['records']
    if len(records) > len(chunks):
        raise ValueError('Invalid checkpoint length')
    dimensions = None
    for record, chunk in zip(records, chunks):
        if record['chunk'] != chunk:
            raise ValueError('Checkpoint chunk mismatch')
        dimensions = validate_vector(record['embedding'], dimensions)
    pending = chunks[len(records):]
    if pending and not settings.ai_key:
        raise ValueError('AI_API_KEY is required; configure it securely, never in chat')
    output.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=90, transport=transport) as client:
        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            response = await client.post('https://api.openai.com/v1/embeddings',
                headers={'Authorization': 'Bearer ' + settings.ai_key},
                json={'model': settings.embedding_model, 'input': [c['text'] for c in batch]})
            # Do not include provider response bodies or credentials in error messages.
            if response.status_code != 200:
                raise ValueError(f'Embedding provider returned HTTP {response.status_code}; rerun to resume')
            payload = response.json()
            rows = sorted(payload['data'], key=lambda row: row['index'])
            if [r['index'] for r in rows] != list(range(len(batch))):
                raise ValueError('Embedding response has missing or duplicate indices')
            additions = []
            for chunk, row in zip(batch, rows):
                dimensions = validate_vector(row['embedding'], dimensions)
                additions.append({'chunk': chunk, 'embedding': row['embedding']})
            records.extend(additions)
            artifact['dimensions'] = dimensions
            artifact['complete'] = len(records) == len(chunks)
            save(output, artifact)
            print(f'Embedded {len(records)}/{len(chunks)} draft chunks', flush=True)
    return artifact


def validate_vector(vector, dimensions):
    if not isinstance(vector, list) or not vector or any(
        isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in vector
    ) or not any(vector):
        raise ValueError('Provider returned an invalid vector')
    if dimensions is not None and len(vector) != dimensions:
        raise ValueError('Embedding dimensions changed')
    return len(vector)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('staging', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--batch-size', type=int, default=32)
    args = parser.parse_args()
    try:
        asyncio.run(build(args.staging, args.output, Settings.from_env(), args.batch_size))
    except (ValueError, KeyError, httpx.HTTPError) as error:
        # HTTP errors can contain URLs but we never log request headers or server bodies.
        parser.exit(2, f'{type(error).__name__}: {error}\n')


if __name__ == '__main__':
    main()
