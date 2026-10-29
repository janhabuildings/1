// Private storage gateway. STORAGE_TOKEN is a Worker secret, never a source variable.
const MAX_FILE = 40 * 1024 * 1024;
const MAX_DELTA = 1500000;
const initialized = new WeakMap();
const headers = {'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
const reply = (body,status=200) => new Response(JSON.stringify(body),{status,headers});
const hex = buffer => [...new Uint8Array(buffer)].map(x=>x.toString(16).padStart(2,'0')).join('');
const sha = data => crypto.subtle.digest('SHA-256',data);
const validHash = value => typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
const validPath = value => typeof value==='string' && value.length<2048 && !value.startsWith('/') && !value.includes('\\') && !value.includes('\0') && value.split('/').every(p=>p && p!=='.' && p!=='..');
async function authorized(request,token){
  const supplied=request.headers.get('Authorization') || '';
  const [a,b]=await Promise.all([sha(new TextEncoder().encode(supplied)),sha(new TextEncoder().encode('Bearer '+token))]);
  const x=new Uint8Array(a),y=new Uint8Array(b);let difference=0;for(let i=0;i<x.length;i++)difference|=x[i]^y[i];return difference===0;
}
async function database(env){
  const db=env.DB.withSession?env.DB.withSession('first-primary'):env.DB;
  if(!initialized.has(env.DB))initialized.set(env.DB,db.batch([
    db.prepare('CREATE TABLE IF NOT EXISTS storage_meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, last_commit TEXT NOT NULL)'),
    db.prepare("INSERT OR IGNORE INTO storage_meta VALUES (1,0,'')"),
    db.prepare('CREATE TABLE IF NOT EXISTS storage_rows (key TEXT PRIMARY KEY, payload TEXT NOT NULL)'),
    db.prepare('CREATE TABLE IF NOT EXISTS storage_files (path TEXT PRIMARY KEY, sha TEXT NOT NULL, size INTEGER NOT NULL, object TEXT NOT NULL)'),
    db.prepare('CREATE TABLE IF NOT EXISTS storage_gc (key TEXT PRIMARY KEY)')
  ]).catch(error=>{initialized.delete(env.DB);throw error;}));
  await initialized.get(env.DB);
  return db;
}
async function cleanup(db,env){
  const pending=await db.prepare('SELECT key FROM storage_gc LIMIT 15').all();
  for(const item of pending.results){
    const used=await db.prepare("SELECT COUNT(*) AS count FROM storage_files WHERE sha||'-'||object=?").bind(item.key).first();
    if(!used.count)await env.FILES.delete('blobs/'+item.key);
    await db.prepare('DELETE FROM storage_gc WHERE key=?').bind(item.key).run();
  }
  return (await db.prepare('SELECT COUNT(*) AS count FROM storage_gc').first()).count;
}
export default {
  async scheduled(event,env,ctx){ctx.waitUntil((async()=>cleanup(await database(env),env))());},
  async fetch(request,env){
    if(!env.STORAGE_TOKEN || !env.DB || !env.FILES)return reply({error:'Configure STORAGE_TOKEN and both storage bindings.'},503);
    if(!await authorized(request,env.STORAGE_TOKEN))return reply({error:'Authentication required'},401);
    try {
      const url=new URL(request.url),db=await database(env);
      if(url.pathname==='/status' && request.method==='GET'){
        const state=await db.prepare('SELECT revision,last_commit FROM storage_meta WHERE id=1').first();
        return reply({version:1,...state});
      }
      if(url.pathname==='/state' && request.method==='GET'){
        const kind=url.searchParams.get('kind'),after=url.searchParams.get('after')||'';
        if(!['rows','files'].includes(kind))return reply({error:'Invalid collection'},400);
        const result=kind==='rows'
          ?await db.prepare('SELECT key,payload AS value FROM storage_rows WHERE key>? ORDER BY key LIMIT 20').bind(after).all()
          :await db.prepare('SELECT path,sha,size,object FROM storage_files WHERE path>? ORDER BY path LIMIT 20').bind(after).all();
        return reply({items:result.results});
      }
      if(url.pathname==='/gc' && request.method==='POST')return reply({pending:await cleanup(db,env)});
      const blob=url.pathname.match(/^\/blobs\/([a-f0-9]{64})-([a-f0-9]{32})$/);
      if(blob){
        const key='blobs/'+blob[1]+'-'+blob[2];
        if(request.method==='PUT'){
          if(Number(request.headers.get('Content-Length'))>MAX_FILE)return reply({error:'File too large'},413);
          const bytes=await request.arrayBuffer();if(bytes.byteLength>MAX_FILE)return reply({error:'File too large'},413);
          if(hex(await sha(bytes))!==blob[1])return reply({error:'File checksum mismatch'},400);
          await env.FILES.put(key,bytes,{httpMetadata:{contentType:'application/octet-stream'}});return reply({stored:true});
        }
        if(request.method==='GET'){
          const object=await env.FILES.get(key);if(!object)return reply({error:'File not found'},404);
          return new Response(object.body,{headers:{'Content-Type':'application/octet-stream','Cache-Control':'no-store','Content-Length':String(object.size)}});
        }
        if(request.method==='DELETE'){
          const used=await db.prepare('SELECT COUNT(*) AS count FROM storage_files WHERE sha=? AND object=?').bind(blob[1],blob[2]).first();
          if(used.count)return reply({error:'File is still referenced'},409);
          await env.FILES.delete(key);return reply({deleted:true});
        }
      }
      if(url.pathname==='/commit' && request.method==='POST'){
        if(Number(request.headers.get('Content-Length'))>MAX_DELTA)return reply({error:'Metadata too large'},413);
        const raw=await request.text();if(new TextEncoder().encode(raw).length>MAX_DELTA)return reply({error:'Metadata too large'},413);
        const data=JSON.parse(raw),{expected,commit_id,rows=[],deletes=[],files=[],removed_files=[]}=data;
        if(!Number.isSafeInteger(expected)||expected<0||typeof commit_id!=='string'||!/^[a-f0-9-]{36}$/.test(commit_id))return reply({error:'Invalid commit'},400);
        if(![rows,deletes,files,removed_files].every(Array.isArray)||rows.length+deletes.length+files.length+removed_files.length>10000)return reply({error:'Invalid change set'},400);
        if(rows.some(r=>typeof r.key!=='string'||r.key.length>256||typeof r.value!=='string'||new TextEncoder().encode(r.value).length>1500000)||deletes.some(k=>typeof k!=='string')||files.some(f=>!validPath(f.path)||!validHash(f.sha)||typeof f.object!=='string'||!/^[a-f0-9]{32}$/.test(f.object)||!Number.isSafeInteger(f.size)||f.size<0)||removed_files.some(p=>!validPath(p)))return reply({error:'Invalid metadata'},400);
        const current=await db.prepare('SELECT revision,last_commit FROM storage_meta WHERE id=1').first();
        if(current.last_commit===commit_id)return reply({revision:current.revision});
        if(current.revision!==expected)return reply({error:'Storage changed on another server. Reload before saving.'},409);
        // Only the authenticated backend commits metadata, after uploads succeed.
        const guard='(SELECT last_commit FROM storage_meta WHERE id=1)=?';
        const result=await db.batch([
          db.prepare('UPDATE storage_meta SET revision=revision+1,last_commit=? WHERE id=1 AND revision=? RETURNING revision').bind(commit_id,expected),
          db.prepare(`DELETE FROM storage_rows WHERE key IN (SELECT value FROM json_each(?)) AND ${guard}`).bind(JSON.stringify(deletes),commit_id),
          db.prepare(`INSERT INTO storage_rows(key,payload) SELECT json_extract(value,'$.key'),json_extract(value,'$.value') FROM json_each(?) WHERE ${guard} ON CONFLICT(key) DO UPDATE SET payload=excluded.payload`).bind(JSON.stringify(rows),commit_id),
          db.prepare(`INSERT OR IGNORE INTO storage_gc(key) SELECT sha||'-'||object FROM storage_files WHERE (path IN (SELECT value FROM json_each(?)) OR path IN (SELECT json_extract(value,'$.path') FROM json_each(?))) AND ${guard}`).bind(JSON.stringify(removed_files),JSON.stringify(files),commit_id),
          db.prepare(`DELETE FROM storage_files WHERE path IN (SELECT value FROM json_each(?)) AND ${guard}`).bind(JSON.stringify(removed_files),commit_id),
          db.prepare(`INSERT INTO storage_files(path,sha,size,object) SELECT json_extract(value,'$.path'),json_extract(value,'$.sha'),json_extract(value,'$.size'),json_extract(value,'$.object') FROM json_each(?) WHERE ${guard} ON CONFLICT(path) DO UPDATE SET sha=excluded.sha,size=excluded.size,object=excluded.object`).bind(JSON.stringify(files),commit_id)
        ]);
        const revision=result[0].results?.[0]?.revision;
        return revision?reply({revision}):reply({error:'Storage changed on another server. Reload before saving.'},409);
      }
      return reply({error:'Not found'},404);
    } catch(error){return reply({error:'Cloud storage request failed. Check Worker logs.'},500);}
  }
};
