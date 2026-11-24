"""One company workspace with individual high-entropy, revocable access keys."""
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import secrets
from urllib.parse import unquote
from fastapi import HTTPException
from backend.core import uid

principal = ContextVar('workspace_principal', default=None)
TABLES = ('workspace_users','inspection_access','stamp_access','workspace_events')

def now(): return datetime.now(timezone.utc).isoformat()

def initialize(store):
    with store.connect() as db:
        for table in TABLES:
            db.execute(f'CREATE TABLE IF NOT EXISTS {table}(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')

class Workspace:
    def __init__(self,store,bootstrap): self.store=store;self.bootstrap=bootstrap
    def rows(self,table):
        with self.store.connect() as db:return [json.loads(r['payload']) for r in db.execute(f'SELECT payload FROM {table}')]
    def get(self,table,identity):
        with self.store.connect() as db:row=db.execute(f'SELECT payload FROM {table} WHERE id=?',(identity,)).fetchone()
        return json.loads(row['payload']) if row else None
    def put(self,table,row):
        with self.store.connect() as db:db.execute(f'INSERT INTO {table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(row['id'],json.dumps(row)))
    def event(self,action,target):
        self.put('workspace_events',{'id':uid(),'at':now(),'actor_id':self.current()['id'],'action':action,'target_id':target})
    @staticmethod
    def current():
        value=principal.get()
        if value is None:raise HTTPException(401,'Sign in with your personal access key')
        return value
    @staticmethod
    def public(user):return {k:v for k,v in user.items() if k!='key_hash'}
    def authenticate(self,header):
        if not self.bootstrap and not self.rows('workspace_users'):raise HTTPException(503,'Configure INSPECTION_API_TOKEN before using this service')
        supplied=header[7:] if header and header.startswith('Bearer ') else ''
        if not supplied or len(supplied)>512:raise HTTPException(401,'Authentication required',headers={'WWW-Authenticate':'Bearer'})
        if self.bootstrap and secrets.compare_digest(supplied.encode(),self.bootstrap.encode()):
            return {'id':'workspace-owner','name':'Workspace owner','role':'admin','active':True,'bootstrap':True}
        digest=hashlib.sha256(supplied.encode()).hexdigest()
        for user in self.rows('workspace_users'):
            if user.get('active') and secrets.compare_digest(digest,user.get('key_hash','')):return self.public(user)
        raise HTTPException(401,'Access key is invalid or deactivated',headers={'WWW-Authenticate':'Bearer'})
    def admin(self):
        if self.current()['role']!='admin':raise HTTPException(403,'Administrator access required')
    def create_user(self,name,email,role):
        self.admin()
        if not name.strip() or role not in ('admin','inspector'):raise HTTPException(422,'Provide a name and valid role')
        if any(u['email'].casefold()==email.strip().casefold() for u in self.rows('workspace_users')):raise HTTPException(409,'An account with that email already exists')
        key='jbi_'+secrets.token_urlsafe(32)
        row={'id':uid(),'name':name.strip(),'email':email.strip(),'role':role,'active':True,'created_at':now(),'key_hash':hashlib.sha256(key.encode()).hexdigest()}
        self.put('workspace_users',row);self.event('user_created',row['id'])
        return dict(self.public(row),access_key=key)
    def change_user(self,identity,active=None,rotate=False):
        self.admin();row=self.get('workspace_users',identity)
        if not row:raise HTTPException(404,'User not found')
        if identity==self.current()['id'] and active is False:raise HTTPException(409,'Use another administrator to deactivate this account')
        if active is not None:row['active']=active
        key=None
        if rotate:
            key='jbi_'+secrets.token_urlsafe(32);row['key_hash']=hashlib.sha256(key.encode()).hexdigest()
        self.put('workspace_users',row);self.event('key_rotated' if rotate else 'user_updated',identity)
        return dict(self.public(row),**({'access_key':key} if key else {}))
    def allowed(self,identity):
        if self.current()['role']=='admin':return True
        row=self.get('inspection_access',identity)
        return bool(row and self.current()['id'] in row['assigned_user_ids'])
    def check_inspection(self,identity,allow_new=False):
        with self.store.connect() as db:
            exists=db.execute('SELECT 1 FROM inspections WHERE id=?',(identity,)).fetchone()
            deleted=db.execute('SELECT 1 FROM deleted_inspections WHERE id=?',(identity,)).fetchone()
        if allow_new and not exists and not deleted:return
        if not self.allowed(identity):raise HTTPException(404,'Inspection not found or not assigned to your account')
    def register(self,identity):
        if self.get('inspection_access',identity):return
        user=self.current()
        self.put('inspection_access',{'id':identity,'created_by':user['id'],'assigned_user_ids':[user['id']],'updated_at':now()})
    def assign(self,identity,ids):
        self.admin();self.store.get(identity)
        if len(set(ids))!=len(ids):raise HTTPException(422,'Duplicate assignee')
        for user_id in ids:
            user=self.get('workspace_users',user_id)
            if user_id!='workspace-owner' and (not user or not user['active']):raise HTTPException(422,'Choose active workspace users')
        row=self.get('inspection_access',identity) or {'id':identity,'created_by':'workspace-owner'}
        row['previous_assigned_user_ids']=list(set(row.get('previous_assigned_user_ids',[])+row.get('assigned_user_ids',[])))
        row.update(assigned_user_ids=ids,updated_at=now());self.put('inspection_access',row);self.event('inspection_assigned',identity)
        return row
    def stamp_allowed(self,identity):
        row=self.get('stamp_access',identity)
        return (row['user_id'] if row else 'workspace-owner')==self.current()['id']
    def check_stamp(self,identity):
        if not self.stamp_allowed(identity):raise HTTPException(404,'Stamp not found for this account')
    def authorize_path(self,path,method):
        parts=[unquote(p) for p in path.strip('/').split('/')]
        root=parts[0] if parts else ''
        if root=='workspace' and len(parts)>1 and parts[1] in ('users','audit'):self.admin()
        if root=='inspections' and len(parts)>1:self.check_inspection(parts[1],allow_new=method=='PUT' and len(parts)==2)
        elif root in ('media','artifacts') and len(parts)==2:
            with self.store.connect() as db:row=db.execute('SELECT inspection_id FROM '+root+' WHERE id=?',(parts[1],)).fetchone()
            if row:self.check_inspection(row['inspection_id'])
            else:
                if root=='media':
                    with self.store.connect() as db:deleted=db.execute('SELECT inspection_id FROM deleted_media WHERE id=?',(parts[1],)).fetchone()
                    if deleted:self.check_inspection(deleted['inspection_id']);return
                if self.current()['role']!='admin':raise HTTPException(404,'File not found')
        elif root=='signing-assets' and len(parts)>1:self.check_stamp(parts[1])
        elif root=='templates' and method!='GET':self.admin()
        elif root=='codes' and method!='GET' and path not in ('/codes/search','/codes/draft/search'):self.admin()
        elif path=='/saved-rows/import-history':self.admin()
