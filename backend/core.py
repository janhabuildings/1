from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse
import uuid

import httpx


@dataclass
class Settings:
    data_dir: Path
    token: str
    ai_key: str = ''
    ai_model: str = 'gpt-4.1-mini'
    embedding_model: str = 'text-embedding-3-small'
    office_bin: str = ''

    @classmethod
    def from_env(cls):
        return cls(Path(os.environ.get('INSPECTION_DATA_DIR', '/tmp/jbi-inspections')),
                   os.environ.get('INSPECTION_API_TOKEN',''),os.environ.get('AI_API_KEY',''),
                   os.environ.get('AI_MODEL','gpt-4.1-mini'),
                   os.environ.get('EMBEDDING_MODEL','text-embedding-3-small'),os.environ.get('DSENY_OFFICE_BIN',''))


class Store:
    def __init__(self, root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'media').mkdir(exist_ok=True)
        (self.root/'reports').mkdir(exist_ok=True)
        self.database=self.root/'inspections.sqlite3'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS inspections(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY, inspection_id TEXT NOT NULL, kind TEXT NOT NULL,
              mime TEXT NOT NULL, filename TEXT NOT NULL, path TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
              equipment TEXT NOT NULL DEFAULT '', FOREIGN KEY(inspection_id) REFERENCES inspections(id));
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, inspection_id TEXT NOT NULL,
              filename TEXT NOT NULL, mime TEXT NOT NULL, path TEXT NOT NULL,
              FOREIGN KEY(inspection_id) REFERENCES inspections(id));
            CREATE TABLE IF NOT EXISTS codes(id TEXT PRIMARY KEY, agency TEXT NOT NULL, section TEXT NOT NULL,
              title TEXT NOT NULL, text TEXT NOT NULL, url TEXT NOT NULL, effective_from TEXT NOT NULL,
              effective_to TEXT, verified INTEGER NOT NULL, embedding TEXT, model TEXT, digest TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.database,timeout=30)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback();raise
        finally: db.close()

    def get(self, identity):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM inspections WHERE id=?',(identity,)).fetchone()
        if not row: raise KeyError('Inspection not found')
        return json.loads(row['payload'])

    def save(self, payload):
        with self.connect() as db:
            db.execute('INSERT INTO inspections VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (payload['id'],json.dumps(payload)))
        return payload

    def list(self):
        with self.connect() as db:
            return [json.loads(r['payload']) for r in db.execute('SELECT payload FROM inspections ORDER BY rowid DESC')]

    def media(self, inspection):
        with self.connect() as db:
            return [{k:r[k] for k in ('id','inspection_id','kind','mime','filename','note','equipment')}
                    for r in db.execute('SELECT * FROM media WHERE inspection_id=? ORDER BY rowid',(inspection,))]

    def file(self, identity, table):
        if table not in ('media','artifacts','template_artifacts'): raise ValueError('Invalid table')
        with self.connect() as db:
            row=db.execute(f'SELECT * FROM {table} WHERE id=?',(identity,)).fetchone()
        if not row: raise KeyError('File not found')
        result=dict(row)
        path=Path(result['path']).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file(): raise KeyError('File unavailable')
        return result


def uid(): return str(uuid.uuid4())


def calendar_candidates(text):
    """Extract labeled source values as unconfirmed suggestions, never as findings."""
    lines=[s.strip() for s in text.splitlines() if s.strip()]
    labels={'Client:':'client','Project:':'project','Request date:':'request_date','Inspected on:':'inspection_date',
            'Request by:':'requested_by','Address:':'address'}
    result={}
    for i,line in enumerate(lines):
        if line in labels and i+1<len(lines) and lines[i+1] not in labels:
            value=lines[i+1]
            if labels[line].endswith('_date'):
                found=re.fullmatch(r'(\d{1,2})[./](\d{1,2})[./](\d{4})',value)
                if found:
                    m,d,y=map(int,found.groups())
                    try: value=date(y,m,d).isoformat()
                    except ValueError: continue
                else: continue
            result[labels[line]]=value
    patterns={'SH':r'Sidewalk Shed-([IVXLCDM\d]+)-Inspection-', 'SF':r'Supported Scaffold-([IVXLCDM\d]+)-Inspection-'}
    equipment=[]
    for key,pattern in patterns.items():
        subject=re.search(r'(\d{4}-\d\d-\d\d) (.+?) '+pattern,text,re.I)
        permit=re.search(r'([A-Z]\d+(?:-[A-Z0-9]+)?)\s+'+key+r'\b',text)
        item={'equipment':key}
        if subject:
            item.update(inspection_date=subject.group(1),subject_project=subject.group(2),inspection_code=subject.group(3))
        if permit: item['permit']=permit.group(1)
        if len(item)>1: equipment.append(item)
    return {'fields':result,'equipment':equipment,'confirmed':False,
            'notice':'Calendar template alternatives are not inspection results. Confirm all candidates.'}


def validate_code(record):
    for key in ('agency','section','title','text','url','effective_from'):
        if not isinstance(record.get(key),str) or not record[key].strip(): raise ValueError('Missing code field: '+key)
    host=(urlparse(record['url']).hostname or '').lower()
    domains={'OSHA':('osha.gov',),'NYC DOB':('nyc.gov',),'NYC SCA':('nycsca.org','nyc.gov')}
    if record['agency'] not in domains: raise ValueError('Unsupported code agency')
    if urlparse(record['url']).scheme!='https' or not any(host==d or host.endswith('.'+d) for d in domains[record['agency']]):
        raise ValueError('Source must use an authoritative HTTPS agency domain')
    start=date.fromisoformat(record['effective_from'])
    if record.get('effective_to') and date.fromisoformat(record['effective_to'])<start:
        raise ValueError('Code effective dates are reversed')
    vector=record.get('embedding')
    if vector is not None:
        if not isinstance(vector,list) or not vector or any(isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) for x in vector):
            raise ValueError('Invalid embedding')
        if not record.get('model'): raise ValueError('Embedding model is required')
    return record


def put_code(store, record):
    validate_code(record)
    digest=hashlib.sha256(record['text'].encode()).hexdigest()
    identity=record.get('id') or hashlib.sha256((record['agency']+record['section']+record['effective_from']).encode()).hexdigest()
    with store.connect() as db:
        db.execute('INSERT INTO codes VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                   'agency=excluded.agency,section=excluded.section,effective_from=excluded.effective_from,'
                   'title=excluded.title,text=excluded.text,url=excluded.url,effective_to=excluded.effective_to,'
                   'verified=excluded.verified,embedding=excluded.embedding,model=excluded.model,digest=excluded.digest',
                   (identity,record['agency'],record['section'],record['title'],record['text'],record['url'],
                    record['effective_from'],record.get('effective_to'),int(record.get('verified') is True),
                    json.dumps(record['embedding']) if record.get('embedding') else None,record.get('model'),digest))
    return identity


async def embed(settings, text):
    if not settings.ai_key: raise ValueError('AI_API_KEY is not configured')
    async with httpx.AsyncClient(timeout=45) as client:
        response=await client.post('https://api.openai.com/v1/embeddings',headers={'Authorization':'Bearer '+settings.ai_key},
                                   json={'model':settings.embedding_model,'input':text})
        response.raise_for_status()
        return response.json()['data'][0]['embedding']


def cosine(a,b):
    if len(a)!=len(b): return 0.0
    norm=math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/norm if norm else 0.0


def search_codes(store, query, on_date, vector=None, model=None, limit=6):
    date.fromisoformat(on_date)
    words=set(re.findall(r'[\w.-]+',query.lower()))
    with store.connect() as db:
        rows=db.execute('SELECT * FROM codes WHERE verified=1 AND effective_from<=? '
                        'AND (effective_to IS NULL OR effective_to>=?)',(on_date,on_date)).fetchall()
    results=[]
    for row in rows:
        candidate=dict(row)
        tokens=set(re.findall(r'[\w.-]+',(row['title']+' '+row['section']+' '+row['text']).lower()))
        lexical=len(words & tokens)/max(1,len(words))
        semantic=cosine(vector,json.loads(row['embedding'])) if vector and row['embedding'] and row['model']==model else 0
        score=.55*lexical+.45*max(0,semantic) if vector else lexical
        if score<=0: continue
        for key in ('embedding','verified'): candidate.pop(key,None)
        candidate.update(score=round(score,5),retrieval='hybrid' if vector and row['embedding'] and row['model']==model else 'keyword')
        results.append(candidate)
    return sorted(results,key=lambda x:x['score'],reverse=True)[:limit]
