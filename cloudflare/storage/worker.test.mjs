import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import gateway from './worker.mjs';

function fixture(){
  const sqlite=new DatabaseSync(':memory:');
  function prepared(sql,args=[]){return {bind(...values){return prepared(sql,values);},async first(){return sqlite.prepare(sql).get(...args)||null;},async all(){return {results:sqlite.prepare(sql).all(...args)};},async run(){return sqlite.prepare(sql).run(...args);}};}
  const DB={prepare:prepared,withSession(){return this;},async batch(statements){sqlite.exec('BEGIN');try{const result=[];for(const s of statements)result.push(await s.all());sqlite.exec('COMMIT');return result;}catch(error){sqlite.exec('ROLLBACK');throw error;}}};
  const objects=new Map(),FILES={async put(key,bytes){objects.set(key,new Uint8Array(bytes).slice());},async get(key){const value=objects.get(key);return value?{body:value,size:value.length}:null;},async delete(key){objects.delete(key);}};
  const env={DB,FILES,STORAGE_TOKEN:'fixture-only-storage-token-32-characters'};
  const request=async(path,method='GET',body,authorized=true)=>gateway.fetch(new Request('https://storage.test'+path,{method,headers:authorized?{'Authorization':'Bearer '+env.STORAGE_TOKEN}:{},body:body===undefined?undefined:typeof body==='string'||body instanceof Uint8Array?body:JSON.stringify(body)}),env);
  return {request,objects,env};
}
const digest=async bytes=>Buffer.from(await crypto.subtle.digest('SHA-256',bytes)).toString('hex');
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;

test('private gateway rejects unauthenticated requests',async()=>{const f=fixture();assert.equal((await f.request('/status','GET',undefined,false)).status,401);assert.equal((await f.request('/status')).status,200);});
test('verified blobs, atomic records, idempotency, and stale-writer protection',async()=>{
  const f=fixture(),bytes=new TextEncoder().encode('private photo'),hash=await digest(bytes),object='a'.repeat(32),key=hash+'-'+object;
  assert.equal((await f.request('/blobs/'+key,'PUT',bytes)).status,200);
  const change={expected:0,commit_id:id(1),rows:[{key:'inspections:1',value:'{"title":"Cloud report"}'}],files:[{path:'media/photo.jpg',sha:hash,object,size:bytes.length}]};
  assert.deepEqual(await (await f.request('/commit','POST',change)).json(),{revision:1});
  assert.deepEqual(await (await f.request('/commit','POST',change)).json(),{revision:1});
  const stale={...change,commit_id:id(2),rows:[{key:'inspections:2',value:'{}'}]};
  assert.equal((await f.request('/commit','POST',stale)).status,409);
  const rows=await (await f.request('/state?kind=rows')).json();assert.equal(rows.items.length,1);assert.equal(rows.items[0].key,'inspections:1');
  assert.equal((await f.request('/blobs/'+key,'DELETE')).status,409);
  const file=await f.request('/blobs/'+key);assert.equal(await file.text(),'private photo');
});
test('deletions persist and unreferenced objects are removed from R2',async()=>{
  const f=fixture(),bytes=new TextEncoder().encode('photo'),hash=await digest(bytes),object='a'.repeat(32),key=hash+'-'+object;await f.request('/blobs/'+key,'PUT',bytes);
  await f.request('/commit','POST',{expected:0,commit_id:id(1),files:[{path:'media/a.jpg',sha:hash,object,size:bytes.length}]});
  await f.request('/commit','POST',{expected:1,commit_id:id(2),removed_files:['media/a.jpg']});
  assert.deepEqual(await (await f.request('/gc','POST')).json(),{pending:0});assert.equal(f.objects.size,0);
});
test('invalid checksums and traversal paths are rejected',async()=>{
  const f=fixture();assert.equal((await f.request('/blobs/'+'0'.repeat(64)+'-'+'a'.repeat(32),'PUT',new Uint8Array([1]))).status,400);
  assert.equal((await f.request('/commit','POST',{expected:0,commit_id:id(1),files:[{path:'../escape',sha:'0'.repeat(64),object:'a'.repeat(32),size:1}]})).status,400);
});

test('deleting an old version cannot delete a new copy with identical contents',async()=>{
  const f=fixture(),bytes=new TextEncoder().encode('same photo'),hash=await digest(bytes),oldObject='a'.repeat(32),newObject='b'.repeat(32);
  await f.request('/blobs/'+hash+'-'+oldObject,'PUT',bytes);
  await f.request('/commit','POST',{expected:0,commit_id:id(1),files:[{path:'media/old.jpg',sha:hash,object:oldObject,size:bytes.length}]});
  await f.request('/commit','POST',{expected:1,commit_id:id(2),removed_files:['media/old.jpg']});
  await f.request('/blobs/'+hash+'-'+newObject,'PUT',bytes);
  await f.request('/commit','POST',{expected:2,commit_id:id(3),files:[{path:'media/new.jpg',sha:hash,object:newObject,size:bytes.length}]});
  await f.request('/gc','POST');
  assert.equal((await f.request('/blobs/'+hash+'-'+oldObject)).status,404);
  assert.equal(await (await f.request('/blobs/'+hash+'-'+newObject)).text(),'same photo');
});
