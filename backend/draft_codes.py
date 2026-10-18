"""Read-only preview search over the uploaded Chapter 33 vector artifact."""
from array import array
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re

from backend.core import cosine
from backend.embed_staged import validate_vector

BUNDLE = Path(__file__).with_name('data') / 'chapter33.draft.json.gz'
NOTICE = ('Draft NYC Chapter 33 reference: source provenance, amendments and effective dates '
          'have not been reviewed. PDF page numbers refer to the uploaded file. '
          'Read parent provisions, exceptions and cross-references before applying an excerpt.')


@lru_cache(maxsize=1)
def load():
    raw = BUNDLE.read_bytes()
    expected = BUNDLE.with_suffix('.sha256').read_text().strip()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Draft reference bundle checksum mismatch')
    data = json.loads(gzip.decompress(raw))
    if not data.get('complete') or data.get('status') != 'draft':
        raise ValueError('Expected a complete draft vector artifact')
    dimensions = data['dimensions']
    ids = set()
    for record in data['records']:
        chunk = record['chunk']
        if chunk['id'] in ids or chunk.get('verified') is not False:
            raise ValueError('Invalid draft chunk identity or review flag')
        ids.add(chunk['id'])
        validate_vector(record['embedding'], dimensions)
        record['embedding'] = array('f', record['embedding'])
    if len(ids) != data['source_manifest']['retrieval_chunks']:
        raise ValueError('Draft chunk count mismatch')
    return data


def terms(text):
    return {word[:-1] if len(word)>4 and word.endswith("s") else word
            for word in re.findall(r"[\w.-]+", text.lower())}


def search(query, vector=None, model=None, limit=6):
    data = load()
    if vector is not None and (model != data['model'] or len(vector) != data['dimensions']):
        raise ValueError('Query embedding model or dimensions do not match the draft index')
    words = terms(query)
    ranked = []
    for record in data['records']:
        chunk = record['chunk']
        tokens = terms(chunk['section']+' '+chunk['text'])
        lexical = len(words & tokens) / max(len(words), 1)
        score = .55*lexical + .45*cosine(vector, record['embedding']) if vector is not None else lexical
        if score > 0:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [dict(chunk, agency='NYC DOB', source_sha256=data['source_sha256'],
                 retrieval='draft hybrid' if vector is not None else 'draft keyword', score=round(score, 4))
            for score, chunk in ranked[:limit]]
