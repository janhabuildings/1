"""Durable Cloudflare mirror for the existing single-instance SQLite application.

D1 stores individual database records; R2 stores content-addressed files. All
mutations are serialized by the API and acknowledged only after a cloud commit.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from urllib.parse import urlsplit
import uuid

import httpx

TABLES=('inspections','media','artifacts','template_versions','template_archives',
        'template_artifacts','template_active','signing_assets','report_runs',
        'deleted_inspections','deleted_media')
FILE_TABLES=('media','artifacts','template_artifacts','signing_assets')


class CloudStorageError(RuntimeError): pass
class CloudConflict(CloudStorageError): pass


def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


class CloudStorage:
    def __init__(self,store,url,token,client=None):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise CloudStorageError('Cloud storage URL must be a private HTTPS gateway URL.')
        if not token: raise CloudStorageError('Configure a cloud storage token before enabling cloud storage.')
        self.store=store;self.root=store.root.resolve();self.revision=0
        self.rows={};self.files={};self.lazy=set();self.lock=threading.RLock();self.cleanup_needed=True;self._file_stats={};self._pending_files={}
        self.client=client or httpx.Client(base_url=url.rstrip('/')+'/',headers={'Authorization':'Bearer '+token},timeout=90,follow_redirects=False)

    @classmethod
    def from_env(cls,store,token):
        url=os.environ.get('INSPECTION_CLOUD_URL','').strip()
        if not url:return None
        return cls(store,url,os.environ.get('INSPECTION_CLOUD_TOKEN',token))

    def request(self,method,path,**kwargs):
        try:
            response=self.client.request(method,path.lstrip('/'),**kwargs)
        except httpx.HTTPError as error:
            raise CloudStorageError('Cloud storage is unavailable. Changes have not been confirmed saved; retry or download a JSON backup.') from error
        if response.status_code==409:raise CloudConflict('Cloud records changed on another server. Refresh saved records before retrying.')
        if not response.is_success:
            raise CloudStorageError(f'Cloud storage rejected the request ({response.status_code}). Check the gateway configuration; changes are not confirmed saved.')
        return response

    def path(self,relative):
        relative=Path(relative)
        target=(self.root/relative).resolve()
        if relative.is_absolute() or not relative.parts or not target.is_relative_to(self.root) or '..' in relative.parts:
            raise CloudStorageError('Cloud file path is invalid.')
        return target

    def pages(self,kind):
        result={};after=''
        while True:
            items=self.request('GET','state',params={'kind':kind,'after':after}).json()['items']
            for item in items:result[item['key' if kind=='rows' else 'path']]=item['value'] if kind=='rows' else {k:item[k] for k in ('sha','size','object')}
            if len(items)<20:return result
            after=items[-1]['key' if kind=='rows' else 'path']

    def restore(self):
        with self.lock:
            status=self.request('GET','status').json()
            if status.get('version')!=1:raise CloudStorageError('Unsupported cloud storage version.')
            rows=self.pages('rows');files=self.pages('files')
            if self.request('GET','status').json()['revision']!=status['revision']:
                raise CloudStorageError('Cloud records changed during startup. Restart the service and retry.')
            # The first connection imports any records still available locally.
            if status['revision']==0 and not rows and not files:
                self.revision=0;return
            parsed=[]
            for value in rows.values():
                record=json.loads(value);table=record['table'];data=record['data']
                if table not in TABLES:raise CloudStorageError('Unsupported cloud database record.')
                if 'path' in data:data['path']=str(self.path(data['path']))
                parsed.append((table,record['rowid'],data))
            # Fetch templates/stamps before exposing the restored database. Media
            # and report downloads are lazy, avoiding a full photo download on boot.
            lazy=set()
            for relative,info in files.items():
                path=self.path(relative);path.parent.mkdir(parents=True,exist_ok=True)
                if path.is_file() and path.stat().st_size==info['size'] and hashlib.sha256(path.read_bytes()).hexdigest()==info['sha']:continue
                if relative.startswith(('media/','reports/')):
                    path.write_bytes(b'');lazy.add(relative)
                else:self._download(path,info)
            with sqlite3.connect(self.store.database) as db:
                db.execute('PRAGMA foreign_keys=OFF')
                for table in TABLES:db.execute(f'DELETE FROM "{table}"')
                for table,rowid,data in parsed:
                    allowed={r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
                    if not set(data)<=allowed:raise CloudStorageError('Cloud data requires a newer app version.')
                    columns=['rowid',*data];values=[rowid,*data.values()]
                    db.execute(f'INSERT INTO "{table}" ('+','.join('"'+c+'"' for c in columns)+') VALUES ('+','.join('?' for _ in values)+')',values)
                if list(db.execute('PRAGMA foreign_key_check')):raise CloudStorageError('Cloud records failed consistency checks.')
            self.rows=rows;self.files=files;self.lazy=lazy;self.revision=status['revision'];self._pending_files.clear()
            self._file_stats={p:(self.path(p).stat().st_mtime_ns,self.path(p).stat().st_size) for p in files if p not in lazy}

    def _download(self,path,info):
        raw=self.request('GET','blobs/'+info['sha']+'-'+info['object']).content
        if len(raw)!=info['size'] or hashlib.sha256(raw).hexdigest()!=info['sha']:
            raise CloudStorageError('Cloud file checksum did not match. Download was not used.')
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.cloud-download')
        temporary.write_bytes(raw);temporary.replace(path)

    def materialize(self,path):
        with self.lock:
            relative=str(Path(path).resolve().relative_to(self.root))
            if relative in self.lazy:
                self._download(Path(path),self.files[relative]);self.lazy.remove(relative)
                stat=Path(path).stat();self._file_stats[relative]=(stat.st_mtime_ns,stat.st_size)

    def capture(self):
        rows={};paths=set()
        with self.store.connect() as db:
            for table in TABLES:
                info=list(db.execute(f'PRAGMA table_info("{table}")'))
                pk=next(r['name'] for r in info if r['pk']==1)
                for row in db.execute(f'SELECT rowid AS cloud_rowid,* FROM "{table}"'):
                    data=dict(row);rowid=data.pop('cloud_rowid')
                    if 'path' in data:
                        path=Path(data['path']).resolve()
                        if not path.is_relative_to(self.root):raise CloudStorageError('A stored file path is outside the inspection directory.')
                        data['path']=str(path.relative_to(self.root))
                        if table in FILE_TABLES:paths.add(path)
                    if table=='template_versions':paths.add(self.root/'templates'/(data['id']+'.docx'))
                    rows[table+':'+str(data[pk])]=canonical({'table':table,'rowid':rowid,'data':data})
        files={}
        for path in paths:
            relative=str(path.relative_to(self.root))
            if relative in self.lazy and path.is_file():files[relative]=self.files[relative];continue
            if not path.is_file():raise CloudStorageError('A referenced file is missing; cloud save was not completed.')
            stat=path.stat();signature=(stat.st_mtime_ns,stat.st_size)
            if self._file_stats.get(relative)==signature and relative in self.files:files[relative]=self.files[relative]
            elif self._pending_files.get(relative,{}).get('signature')==signature:files[relative]=self._pending_files[relative]['info']
            else:
                files[relative]={'sha':hashlib.sha256(path.read_bytes()).hexdigest(),'size':stat.st_size,'object':uuid.uuid4().hex}
                self._pending_files[relative]={'signature':signature,'info':files[relative]}
            self._file_stats[relative]=signature
        return rows,files

    def sync(self):
        with self.lock:
            if self.cleanup_needed:self.cleanup()
            rows,files=self.capture()
            changed=[{'key':key,'value':value} for key,value in rows.items() if self.rows.get(key)!=value]
            deleted=list(self.rows.keys()-rows.keys())
            changed_files=[dict(path=path,**value) for path,value in files.items() if self.files.get(path)!=value]
            removed=list(self.files.keys()-files.keys())
            if not (changed or deleted or changed_files or removed):return
            uploaded={(info['sha'],info['object']) for info in self.files.values()}
            for info in changed_files:
                if (info['sha'],info['object']) not in uploaded:
                    self.request('PUT','blobs/'+info['sha']+'-'+info['object'],content=self.path(info['path']).read_bytes(),headers={'Content-Type':'application/octet-stream'})
                    uploaded.add((info['sha'],info['object']))
            commit={'expected':self.revision,'commit_id':str(uuid.uuid4()),'rows':changed,'deletes':deleted,'files':changed_files,'removed_files':removed}
            # Repeat an uncertain transport failure with the same idempotency key.
            try:result=self.request('POST','commit',json=commit).json()
            except CloudConflict:raise
            except CloudStorageError:result=self.request('POST','commit',json=commit).json()
            self.revision=result['revision'];self.rows=rows;previous=self.files;self.files=files;self.lazy.intersection_update(files);self._pending_files.clear()
            self.cleanup_needed=True;self.cleanup()

    def cleanup(self):
        for _ in range(100):
            if self.request('POST','gc').json()['pending']==0:
                self.cleanup_needed=False;return
        raise CloudStorageError('Cloud deletion cleanup is still pending. Retry saving.')
