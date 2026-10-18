"""Import approved code sections into a portable SQLite keyword/vector index."""
import argparse
import asyncio
import json
import sqlite3
import hashlib
from pathlib import Path
from backend.core import Settings, Store, embed, put_code, validate_code

async def run(args):
    settings=Settings.from_env()
    if args.data_dir: settings.data_dir=args.data_dir
    if bool(args.input)==bool(args.index): raise ValueError('Choose either input JSON or --index, not both')
    if args.index:
        with sqlite3.connect(args.index.resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            records=[dict(row) for row in db.execute('SELECT * FROM codes')]
        for record in records:
            record['verified']=record['verified']==1
            record['embedding']=json.loads(record['embedding']) if record['embedding'] else None
            if hashlib.sha256(record['text'].encode()).hexdigest()!=record['digest']:
                raise ValueError('Reference index text checksum mismatch')
    else:
        records=json.loads(args.input.read_text())
    if not isinstance(records,list) or not records: raise ValueError('Expected a nonempty array of reviewed code sections')
    for record in records: validate_code(record)
    if args.require_verified and any(r.get('verified') is not True for r in records):
        raise ValueError('All records must be explicitly reviewed and verified for this build')
    if args.embed and not settings.ai_key: raise ValueError('AI_API_KEY is required for embedding; no records changed')
    # Stage all remote work before modifying the index; a provider error cannot leave half the batch applied.
    for record in records:
        if args.embed:
            record['embedding']=await embed(settings,record['text'])
            record['model']=settings.embedding_model
    store=Store(settings.data_dir)
    for record in records: put_code(store,record)
    print(f'Imported {len(records)} sections. Unverified records are excluded from app searches.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path,nargs='?')
    parser.add_argument('--index',type=Path,help='Merge only code sections from a portable SQLite index')
    parser.add_argument('--require-verified',action='store_true')
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--embed',action='store_true')
    try: asyncio.run(run(parser.parse_args()))
    except (ValueError,KeyError) as error: parser.exit(2,str(error)+'\n')
