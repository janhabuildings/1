"""Authenticated deletion tracking and cross-device inspection artifacts."""
import json
import shutil
import uuid
from datetime import datetime,timezone
from pathlib import Path


def initialize(store):
    with store.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS report_runs(id TEXT PRIMARY KEY,inspection_id TEXT,path TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deleted_inspections(id TEXT PRIMARY KEY,deleted_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deleted_media(id TEXT PRIMARY KEY,inspection_id TEXT NOT NULL,deleted_at TEXT NOT NULL);''')


def deletions(store):
    with store.connect() as db:
        return {'inspections':[r['id'] for r in db.execute('SELECT id FROM deleted_inspections')],
                'media':[r['id'] for r in db.execute('SELECT id FROM deleted_media')]}


def unlink(store,path):
    target=Path(path).resolve()
    if target.is_relative_to(store.root.resolve()) and target.is_file(): target.unlink()


def delete_inspection(store,identity):
    now=datetime.now(timezone.utc).isoformat()
    with store.connect() as db:
        runs=[Path(r['path']).resolve() for r in db.execute('SELECT path FROM report_runs WHERE inspection_id=?',(identity,))]
        files=list(db.execute('SELECT path FROM media WHERE inspection_id=?',(identity,)))+list(db.execute('SELECT path FROM artifacts WHERE inspection_id=?',(identity,)))
        db.execute('INSERT OR IGNORE INTO deleted_media SELECT id,inspection_id,? FROM media WHERE inspection_id=?',(now,identity))
        db.execute('DELETE FROM media WHERE inspection_id=?',(identity,))
        db.execute('DELETE FROM artifacts WHERE inspection_id=?',(identity,))
        db.execute('DELETE FROM report_runs WHERE inspection_id=?',(identity,))
        db.execute('DELETE FROM inspections WHERE id=?',(identity,))
        db.execute('INSERT OR IGNORE INTO deleted_inspections VALUES (?,?)',(identity,now))
    runs += [Path(row['path']).resolve().parent.parent for row in files if str(row['path']).startswith(str(store.root/'reports'))]
    for row in files: unlink(store,row['path'])
    for run in set(runs):
        if run.parent != (store.root/'reports').resolve(): continue
        try: uuid.UUID(run.name)
        except ValueError: continue
        with store.connect() as db:
            remaining=db.execute('SELECT 1 FROM artifacts WHERE path LIKE ? LIMIT 1',(str(run)+'/%',)).fetchone()
            preview=db.execute('SELECT 1 FROM template_artifacts WHERE path LIKE ? LIMIT 1',(str(run)+'/%',)).fetchone()
        if not remaining and not preview and run.is_dir(): shutil.rmtree(run)
    return {'deleted':True}


def delete_media(store,identity):
    with store.connect() as db:
        row=db.execute('SELECT * FROM media WHERE id=?',(identity,)).fetchone()
        if not row: return {'deleted':True}
        db.execute('INSERT OR IGNORE INTO deleted_media VALUES (?,?,?)',(identity,row['inspection_id'],datetime.now(timezone.utc).isoformat()))
        db.execute('DELETE FROM media WHERE id=?',(identity,))
        inspection=db.execute('SELECT payload FROM inspections WHERE id=?',(row['inspection_id'],)).fetchone()
        if inspection:
            data=json.loads(inspection['payload'])
            for report in data.get('reports',[]):report['photo_references']=[i for i in report.get('photo_references',[]) if i!=identity]
            db.execute('UPDATE inspections SET payload=? WHERE id=?',(json.dumps(data),row['inspection_id']))
    unlink(store,row['path'])
    return {'deleted':True}


def artifacts(store,identity):
    store.get(identity)
    with store.connect() as db:
        rows=list(db.execute('SELECT id,filename,mime,path FROM artifacts WHERE inspection_id=? ORDER BY rowid DESC',(identity,)))
    latest={}
    for row in rows: latest.setdefault(Path(row['path']).parent.name,Path(row['path']).parent.parent.name)
    result=[dict(id=r['id'],filename=r['filename'],mime=r['mime'],equipment=Path(r['path']).parent.name,generation_id=Path(r['path']).parent.parent.name) for r in rows if Path(r['path']).parent.parent.name==latest[Path(r['path']).parent.name]]
    reports=[]
    for eq in dict.fromkeys(r['equipment'] for r in result):
        complete=any(r['equipment']==eq and r['filename'].endswith('.eml') for r in result)
        reports.append({'equipment':eq,'subject':'Saved '+eq+' report files','status':'local_draft_generated' if complete else 'docx_generated'})
    return {'artifacts':result,'reports':reports,
            'notice':'Saved report files from this backend. Verify the selected version before delivery.'}
