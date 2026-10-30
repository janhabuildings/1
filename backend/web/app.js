'use strict';
const $ = id => document.getElementById(id);
const state = {token:'', id:null, reports:[], activeReport:null, attendees:[], media:[], candidates:null, urls:[], busy:false, cloudStorage:false, saveConflict:false, dirty:false, calendarFilled:new WeakMap()};
const common = ['title','project','inspection_date','request_date','client','requested_by','address','subject_project','calendar_text','notes','transcript'];
const equipmentLabel = code => code==='SF'?'Scaffold':code==='SH'?'Shed':'Other';
const today = () => {const d=new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function toast(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);$('status').style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>{$('status').style.display='none';},error?15000:6500);}
async function api(path,{method='GET',json,body,mime,headers={}}={}){
  const h={'Authorization':`Bearer ${state.token}`,...headers};if(json!==undefined){body=JSON.stringify(json);h['Content-Type']='application/json';}else if(mime)h['Content-Type']=mime;
  const response=await fetch(path,{method,headers:h,body,cache:'no-store',redirect:'error'});
  if(!response.ok){let detail=`Request failed (${response.status}).`;try{const e=await response.json();detail=typeof e.detail==='string'?e.detail:JSON.stringify(e.detail);}catch{}const error=new Error(detail);error.status=response.status;throw error;}
  return response;
}
async function json(path,options){return (await api(path,options)).json();}
async function action(task){if(state.busy)return;state.busy=true;$('workspace').inert=true;$('connection').inert=true;document.querySelectorAll('button').forEach(n=>n.disabled=true);try{if(saveFlight)await saveFlight.catch(()=>{});await task();}catch(e){toast(e.message,true);}finally{state.busy=false;$('workspace').inert=false;$('connection').inert=false;document.querySelectorAll('button').forEach(n=>n.disabled=n.dataset.adopted==='true');}}
let saveTimer=null, saveFlight=null, editRevision=0;
function scheduleSave(delay=1200){clearTimeout(saveTimer);if(state.cloudStorage&&!state.saveConflict&&state.token&&state.dirty)saveTimer=setTimeout(autoSave,delay);}
async function autoSave(){
  if(!state.cloudStorage||!state.token||!state.dirty||state.saveConflict)return;
  if(state.busy){scheduleSave();return;}
  try{await save();}catch(error){
    if(error.status===409)state.saveConflict=true;
    $('save-state').textContent='Not saved · '+error.message+(state.saveConflict?' · use Refresh saved':' · retrying');
    scheduleSave(10000);
  }
}
function markDirty(){editRevision++;state.dirty=true;$('save-state').textContent=state.cloudStorage?'Changes pending · saving automatically':'Unsaved changes';scheduleSave();}
window.addEventListener('online',()=>scheduleSave(0));
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')autoSave();});
function tab(name){document.querySelectorAll('.tab-content').forEach(n=>n.hidden=n.id!==`tab-${name}`);document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n.dataset.tab===name));}
function field(label,value,change,{type='text',options}={}){const wrapper=el('label',label);const input=el(options?'select':type==='textarea'?'textarea':'input');if(options){options.forEach(([v,t])=>{const option=el('option',t);option.value=v;input.append(option);});}else if(type==='textarea')input.rows=3;else input.type=type;input.setAttribute('aria-label',label);input.value=value??'';input.addEventListener(options?'change':'input',()=>{change(input.value);markDirty();});wrapper.append(input);return wrapper;}
function removeButton(label){const button=el('button','×','remove-icon');button.type='button';button.setAttribute('aria-label',label);button.title=label;return button;}
function siteChoice(label,value,change,options,separator='; '){
  let selected=[...new Set((value||'').split(separator==='\n'?/\n/:/[;\n]/).map(v=>v.trim()).filter(Boolean))];
  let active=-1;
  const root=el('div',undefined,'multi-choice');
  const search=el('input');search.type='search';search.placeholder=label;search.autocomplete='off';search.setAttribute('aria-label','Search '+label);search.setAttribute('role','combobox');search.setAttribute('aria-autocomplete','list');search.setAttribute('aria-expanded','false');const cell=el('div',undefined,'choice-cell');root.append(cell);
  const chosen=el('div',undefined,'choice-tags'),panel=el('div',undefined,'choice-panel'),choices=el('div',undefined,'choice-options'),custom=el('button',undefined,'choice-custom');
  choices.id='choices-'+crypto.randomUUID();choices.setAttribute('role','listbox');choices.setAttribute('aria-label',label);choices.setAttribute('aria-multiselectable','true');search.setAttribute('aria-controls',choices.id);custom.type='button';panel.append(choices,custom);panel.hidden=true;cell.append(chosen,search);root.append(panel);
  function open(){panel.hidden=false;search.setAttribute('aria-expanded','true');}
  function close(){panel.hidden=true;search.setAttribute('aria-expanded','false');search.removeAttribute('aria-activedescendant');active=-1;}
  function update(){change(selected.join(separator));markDirty();render();}
  function toggle(option){if(selected.includes(option))selected=selected.filter(v=>v!==option);else selected=option==='NA'?['NA']:[...selected.filter(v=>v!=='NA'),option];search.value='';active=-1;update();}
  function render(){
    search.placeholder=selected.length?'':label;
    chosen.replaceChildren();for(const item of selected){const tag=el('span',undefined,'choice-tag');const remove=removeButton('Remove '+item);remove.onclick=()=>{toggle(item);search.focus();};tag.append(el('span',item),remove);chosen.append(tag);}chosen.hidden=!selected.length;
    choices.replaceChildren();const query=search.value.trim().toLowerCase(),matches=options.filter(v=>!query||v.toLowerCase().includes(query));
    matches.forEach((option,index)=>{
      const row=el('div',undefined,'choice-option');row.id=choices.id+'-'+index;row.setAttribute('role','option');row.setAttribute('aria-label',label+': '+option);row.setAttribute('aria-selected',String(selected.includes(option)));row.classList.toggle('keyboard-active',active===index);
      const check=el('span',selected.includes(option)?'✓':'','choice-check');check.setAttribute('aria-hidden','true');row.append(el('span',option),check);row.onpointerdown=event=>event.preventDefault();row.onclick=()=>toggle(option);choices.append(row);
    });
    if(!matches.length)choices.append(el('p','No matching suggestions.','muted'));
    const text=search.value.trim();custom.textContent='Add custom: '+text;custom.hidden=!text||options.some(v=>v.toLowerCase()===text.toLowerCase())||selected.some(v=>v.toLowerCase()===text.toLowerCase());
    if(active>=0&&active<matches.length)search.setAttribute('aria-activedescendant',choices.id+'-'+active);else search.removeAttribute('aria-activedescendant');
  }
  search.onfocus=open;search.oninput=()=>{active=-1;render();open();};custom.onpointerdown=event=>event.preventDefault();custom.onclick=()=>{const text=search.value.trim();if(text&&!custom.hidden){selected=[...selected.filter(v=>v!=='NA'),text];search.value='';active=-1;update();search.focus();}};
  search.onkeydown=event=>{
    const rows=[...choices.querySelectorAll('[role=option]')];
    if(event.key==='Escape'){event.preventDefault();close();return;}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();open();active=rows.length?(active<0?(event.key==='ArrowDown'?0:rows.length-1):(active+(event.key==='ArrowDown'?1:-1)+rows.length)%rows.length):-1;render();choices.querySelector('.keyboard-active')?.scrollIntoView({block:'nearest'});}
    if(event.key==='Enter'){event.preventDefault();if(panel.hidden){open();return;}const exact=options.find(v=>v.toLowerCase()===search.value.trim().toLowerCase());if(active>=0&&rows[active])rows[active].click();else if(exact)toggle(exact);else if(!custom.hidden)custom.click();else rows[0]?.click();}
  };
  root.addEventListener('focusout',event=>{if(!root.contains(event.relatedTarget))close();});
  render();return root;
}

function correctiveActionField(value,change,options){
  const root=el('div',undefined,'action-autocomplete');const label=el('label','Corrective action');
  const input=el('textarea');input.value=value||'';input.rows=1;input.wrap='off';input.placeholder='Corrective items';input.setAttribute('aria-label','Corrective action');input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-expanded','false');input.setAttribute('aria-multiline','true');
  const panel=el('div',undefined,'choice-panel action-suggestions');panel.id='actions-'+crypto.randomUUID();panel.setAttribute('role','listbox');panel.setAttribute('aria-label','Corrective action suggestions');input.setAttribute('aria-controls',panel.id);panel.hidden=true;label.append(input);root.append(label,panel);
  let active=-1,matches=[];
  function context(){const caret=input.selectionStart??input.value.length,start=caret===0?0:input.value.lastIndexOf('\n',caret-1)+1;let end=input.value.indexOf('\n',caret);if(end<0)end=input.value.length;return {start,end,query:input.value.slice(start,caret).trim().toLowerCase()};}
  function close(){panel.hidden=true;active=-1;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');}
  function render(){
    const query=context().query,tokens=query.split(/\s+/).filter(Boolean);matches=options.filter(option=>tokens.every(token=>option.toLowerCase().includes(token)));
    panel.replaceChildren();matches.forEach((option,index)=>{const row=el('div',undefined,'choice-option');row.setAttribute('role','option');row.id=panel.id+'-'+index;row.setAttribute('aria-label',option);row.setAttribute('aria-selected',String(active===index));row.classList.toggle('keyboard-active',active===index);row.append(el('span',option));if(input.value.split('\n').some(line=>line.trim()===option)){const check=el('span','✓','choice-check');check.setAttribute('aria-hidden','true');row.append(check);}row.onpointerdown=event=>event.preventDefault();row.onclick=()=>choose(option);panel.append(row);});
    panel.hidden=!matches.length;input.setAttribute('aria-expanded',String(!panel.hidden));if(active>=0&&matches[active])input.setAttribute('aria-activedescendant',panel.id+'-'+active);else input.removeAttribute('aria-activedescendant');
  }
  function choose(option){
    const {start,end}=context(),before=input.value.slice(0,start),after=input.value.slice(end).replace(/^\n/,'');
    if(before.split('\n').some(line=>line.trim()===option)||after.split('\n').some(line=>line.trim()===option)){input.value=before+after;input.focus();input.setSelectionRange(before.length,before.length);change(input.value);markDirty();active=-1;render();return;}
    input.value=before+option+'\n'+after;const caret=before.length+option.length+1;input.focus();input.setSelectionRange(caret,caret);change(input.value);markDirty();active=-1;render();
  }
  input.oninput=()=>{change(input.value);markDirty();active=-1;render();};input.onfocus=()=>{active=-1;render();};input.onclick=()=>{active=-1;render();};
  input.onkeydown=event=>{
    if(event.key==='Escape'){event.preventDefault();close();return;}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){if(panel.hidden&&event.key==='ArrowUp')return;render();if(!matches.length)return;event.preventDefault();active=active<0?(event.key==='ArrowDown'?0:matches.length-1):(active+(event.key==='ArrowDown'?1:-1)+matches.length)%matches.length;render();panel.querySelector('.keyboard-active')?.scrollIntoView({block:'nearest'});}
    if(event.key==='Enter'&&!panel.hidden&&active>=0){event.preventDefault();choose(matches[active]);}
  };
  root.addEventListener('focusout',event=>{if(!root.contains(event.relatedTarget))close();});
  return root;
}

function reset(){clearTimeout(saveTimer);editRevision++;state.saveConflict=false;closePreview();state.id=null;state.reports=[];state.activeReport=null;state.attendees=[];state.media=[];state.candidates=null;state.calendarFilled=new WeakMap();state.urls.forEach(URL.revokeObjectURL);state.urls=[];common.forEach(k=>$(k).value='');$('calendar-content').open=false;$('capture-location').value='';$('capture-condition').value='';$('inspection_date').value=today();$('generated').replaceChildren();$('suggestions').replaceChildren();$('calendar-candidates').hidden=true;renderAttendees();renderReports();renderMedia();state.dirty=false;$('save-state').textContent='New inspection · not saved';$('saved').value='';tab('inspection');}
function addReport(equipment,activate=false){
  if(!state.reports.some(r=>r.equipment===equipment)){
    state.reports.push({equipment,status:'',permit:'',inspection_code:'',locations:'',drawings_on_site:'',drawings_approved:'',site:{},open_items:[],source_references:[],photo_references:[]});markDirty();
  }
  if(activate||!state.activeReport)state.activeReport=equipment;
  hydrateCalendarReport(state.reports.find(r=>r.equipment===equipment));
  renderReports();
}
function switchReport(equipment){
  const existing=state.reports.find(r=>r.equipment===equipment);
  if(existing){state.activeReport=equipment;renderReports();return;}
  const current=state.reports.find(r=>r.equipment===state.activeReport)||state.reports[0];
  if(!current){addReport(equipment,true);return;}
  current.equipment=equipment;state.activeReport=equipment;hydrateCalendarReport(current);renderReports();markDirty();
}
const attendeeRoles=['Competent Person/Site Supervisor','Safety Inspector','Competent Person/ Equipment Installation Supervisor','Competent Person','GC’s Project Manager','CM’s Representative','Owner’s Representative','PE'];
const attendeeCompanies=['NYC SCA','DSENY Engineering Services PC'];
function renderAttendees(){
  const root=$('attendees');root.replaceChildren();if(!state.attendees.length)root.append(el('p','No attendees entered. Add the people who actually attended.','empty'));
  state.attendees.forEach((a,i)=>{
    const row=el('div',undefined,'row attendee-row');
    const name=field('Name',a.name,v=>a.name=v);name.classList.add('attendee-name');name.querySelector('input').placeholder='Name';row.append(name);
    row.append(siteChoice('Company / agency',a.company,v=>a.company=v,attendeeCompanies),siteChoice('Role',a.title,v=>a.title=v,attendeeRoles));
    const remove=removeButton('Remove attendee');remove.onclick=()=>{state.attendees.splice(i,1);renderAttendees();markDirty();};row.append(remove);root.append(row);
  });
}
function renderReports(){const root=$('report-list');root.replaceChildren();
  if(!state.reports.some(r=>r.equipment===state.activeReport))state.activeReport=state.reports[0]?.equipment||null;
  for(const equipment of ['SF','SH','OT']){const button=$('add-'+equipment);button.setAttribute('aria-selected',String(state.activeReport===equipment));button.classList.toggle('selected',state.activeReport===equipment);}
if(!state.reports.length)root.append(el('p','Add a scaffold, shed or Other report to begin.','empty'));state.reports.forEach((r,index)=>{
  const card=el('article',undefined,'report-card');card.id='report-'+r.equipment;card.setAttribute('role','tabpanel');card.setAttribute('aria-labelledby','add-'+r.equipment);card.hidden=r.equipment!==state.activeReport;const heading=el('div',undefined,'section-heading');heading.append(el('h3',equipmentLabel(r.equipment)));const remove=removeButton('Remove report');remove.onclick=()=>{if(confirm('Remove this report from the draft?')){state.reports.splice(index,1);renderReports();markDirty();}};heading.append(remove);card.append(heading);
  card.append(field('Inspection result',r.status,v=>r.status=v,{options:[['','Not confirmed'],['OIs','Open items'],['No OIs','No open items']]}));
  const grid=el('div',undefined,'grid');[['permit','Permit number'],['inspection_code','Inspection number · VII / VIII'],['locations','Actually inspected locations / extents']].forEach(([k,l])=>grid.append(field(l,r[k],v=>r[k]=v)));
  ['drawings_on_site','drawings_approved'].forEach((k,i)=>grid.append(field(i?'Drawings DOB/SCA approved?':'PE drawings on site?',r[k],v=>r[k]=v,{options:[['','Not confirmed'],['Yes','Yes'],['No','No'],['NA','NA']]})));
  r.site=r.site||{};
  if(r.equipment==='OT'){
    card.append(field('Other inspection type',r.site.report_type||'Unknown / custom',v=>{r.site.report_type=v;renderReports();},{options:[['Shoring','Shoring'],['SStab','SStab'],['SOE','SOE (Support of Excavation)'],['Fall Protection','Fall Protection'],['Fence','Fence'],['Unknown / custom','Unknown / custom item']]}));
    card.append(field('Item name (for unknown / custom)',r.site.other_name||'',v=>r.site.other_name=v));
    card.append(field('Description / inspection scope',r.site.details||'',v=>r.site.details=v,{type:'textarea'}));
  }
  card.append(grid);card.append(el('h3',r.equipment==='OT'?'General inspection':'Equipment details'));const site=el('div',undefined,'grid');const fields=r.equipment==='OT'?[]:r.equipment==='SH'?[['length_ft','Length (ft)'],['sections','Individual sections'],['height_ft','Max height (ft)'],['width_ft','Max width (ft)']]:[['length_ft','Length (ft)'],['height_ft','Max height (ft)'],['tie_horizontal','Horizontal tie spacing'],['tie_vertical','Vertical tie spacing'],['planked_levels','Planked levels'],['outrigger_levels','Planked outrigger levels'],['tie_type','Tie type'],['dunnage_type','Dunnage type']];r.site=r.site||{};fields.forEach(([k,l])=>{const options=k==='tie_type'?['Masonry Anchor','Concrete Wall Anchor','Concrete Slab Anchor','Steel Beam Anchor','NA']:k==='dunnage_type'?['Grade','Roof','Shed','NA']:null;site.append(options?siteChoice(l,r.site[k],v=>r.site[k]=v,options):field(l,r.site[k],v=>r.site[k]=v));});card.append(site);
  if(r.equipment==='SF'){card.append(el('h3','Hoist and chute'));for(const kind of ['hoist','chute']){const name=kind==='hoist'?'Hoist':'Chute';card.append(field(name+' inspected?',r.site[kind+'_inspected'],v=>r.site[kind+'_inspected']=v,{options:[['','Not confirmed'],['Yes','Yes'],['No','No'],['NA','NA']]}));for(const [suffix,label] of [['locations','location(s)'],['height','height (ft)'],['model','model']])card.append(field(name+' '+label,r.site[kind+'_'+suffix],v=>r.site[kind+'_'+suffix]=v));}}
  card.append(el('h3','Open items'));const findings=el('div');(r.open_items||[]).forEach((f,i)=>{const row=el('div',undefined,'findings-row');const location=field('Location / occurrence',f.location,v=>f.location=v,{type:'textarea'});location.querySelector('textarea').rows=1;location.querySelector('textarea').wrap='off';row.append(location,correctiveActionField(f.action,v=>f.action=v,actionSuggestions[r.equipment]||[]));const remove=removeButton('Remove open item');remove.onclick=()=>{r.open_items.splice(i,1);renderReports();markDirty();};row.append(remove);findings.append(row);});card.append(findings);const add=el('button','+ Add open item','secondary');add.onclick=()=>{r.open_items.push({id:crypto.randomUUID(),location:'',action:''});renderReports();markDirty();};card.append(add);card.append(el('p','Do not choose No OIs while unresolved findings remain. Blank dimensions stay pending, not NA.','muted'));root.append(card);
});}
function payload(){const data={attendees:state.attendees,title:$('title').value.trim()||$('project').value.trim()||'New inspection',project:$('project').value,...Object.fromEntries(['client','request_date','requested_by','address','subject_project'].map(k=>[k,$(k).value])),inspection_date:$('inspection_date').value,calendar_text:$('calendar_text').value,notes:$('notes').value,transcript:$('transcript').value,reports:state.reports.map(r=>({...r,project:$('project').value,client:$('client').value,subject_project:$('subject_project').value,request_date:$('request_date').value,inspection_date:$('inspection_date').value,requested_by:$('requested_by').value,address:$('address').value,attendees:state.attendees,photo_references:[...new Set([...(r.photo_references||[]),...state.media.filter(m=>m.kind==='photo'&&m.equipment===r.equipment).map(m=>m.id)])]}))};if(!data.inspection_date)throw new Error('Choose the inspection date.');return data;}
async function save(){
  if(state.saveConflict)throw new Error('Saved records changed. Back up this draft as JSON, then use Refresh saved before saving again.');
  clearTimeout(saveTimer);
  if(saveFlight){await saveFlight;if(!state.dirty)return;return save();}
  const data=payload(),revision=editRevision;
  if(!state.id)state.id=crypto.randomUUID();
  const id=state.id,media=state.media.map(m=>({id:m.id,note:m.note||'',equipment:m.equipment||''}));
  $('save-state').textContent='Saving…';
  saveFlight=(async()=>{
    await json(`/inspections/${encodeURIComponent(id)}`,{method:'PUT',json:data});
    for(const m of media)await json(`/media/${encodeURIComponent(m.id)}`,{method:'PUT',json:m});
    state.dirty=editRevision!==revision;
    $('save-state').textContent=state.dirty?'Changes pending · saving automatically':`Saved · ${data.project||data.title}`;
    await refreshList();
  })();
  try{await saveFlight;}catch(error){state.dirty=true;if(error.status===409)state.saveConflict=true;$('save-state').textContent=state.saveConflict?'Not saved · use Refresh saved':('Not saved · '+error.message);throw error;}finally{saveFlight=null;if(state.dirty)scheduleSave();}
}

async function refreshList(){const records=await json('/inspections');const select=$('saved');select.replaceChildren(el('option','Choose an inspection…'));records.forEach(r=>{const option=el('option',`${r.title||r.project||'Inspection'} · ${r.inspection_date}`);option.value=r.id;select.append(option);});select.value=state.id||'';}
async function load(id){const record=await json(`/inspections/${encodeURIComponent(id)}`);reset();state.id=id;['title','project','inspection_date','calendar_text','notes','transcript'].forEach(k=>$(k).value=record[k]||'');state.reports=record.reports||[];const first=state.reports[0]||{};['client','request_date','requested_by','address','subject_project'].forEach(k=>$(k).value=record[k]||first[k]||'');state.attendees=record.attendees?.length?record.attendees:(first.attendees||[]);if(record.calendar_candidates){showCalendarCandidates(record.calendar_candidates,false);const before=JSON.stringify(payload());applyCalendar(false,false);state.dirty=before!==JSON.stringify(payload());}state.media=await json(`/inspections/${encodeURIComponent(id)}/media`);renderAttendees();renderReports();await renderMedia();showGenerated(await json(`/inspections/${encodeURIComponent(id)}/artifacts`));$('saved').value=id;$('save-state').textContent=state.dirty?'Calendar facts restored · review and save':'Loaded saved inspection';if(state.dirty)markDirty();}
async function renderMedia(){const root=$('media-list');root.replaceChildren();$('media-empty').hidden=state.media.length>0;state.urls.forEach(URL.revokeObjectURL);state.urls=[];for(const m of state.media){const card=el('article',undefined,'media-card');card.append(el('p',m.filename,'media-title'));if(m.kind==='photo'){const choose=el('label',undefined,'check');const checkbox=el('input');checkbox.type='checkbox';checkbox.dataset.photoId=m.id;choose.append(checkbox,document.createTextNode('Include in AI analysis'));card.append(choose);}const display=el(m.kind==='photo'?'img':'audio');if(m.kind==='photo')display.alt=m.note||'Inspection photo';else display.controls=true;card.append(display);card.append(field('Equipment',m.equipment,v=>m.equipment=v,{options:[['','Not assigned'],['SF','Scaffold'],['SH','Shed'],['OT','Other']]}),field('Location / observation',m.note,v=>m.note=v,{type:'textarea'}));const saveLabel=el('button','Save evidence label','secondary');saveLabel.onclick=()=>action(async()=>{await json(`/media/${encodeURIComponent(m.id)}`,{method:'PUT',json:{note:m.note||'',equipment:m.equipment||''}});toast('Evidence label saved.');});card.append(saveLabel);const remove=el('button','Delete evidence','danger');remove.onclick=()=>action(async()=>{if(!confirm('Delete this evidence from the inspection?'))return;await json(`/media/${m.id}`,{method:'DELETE'});state.media=state.media.filter(item=>item.id!==m.id);for(const report of state.reports)report.photo_references=(report.photo_references||[]).filter(id=>id!==m.id);await renderMedia();});card.append(remove);root.append(card);try{const response=await api(`/media/${encodeURIComponent(m.id)}`);const url=URL.createObjectURL(await response.blob());state.urls.push(url);if(card.isConnected)display.src=url;else URL.revokeObjectURL(url);}catch(e){card.append(el('p',e.message,'muted'));}}}
const calendarFieldMissing = value => ['','[pending confirmation]','pending','tbd'].includes((value||'').trim().toLowerCase());
function hydrateCalendarReport(report){
  if(!report||!state.candidates)return;
  const c=state.candidates,fields=c.fields||{},selected=(c.report_subjects||[]).find(row=>row.title===$('calendar-title').value&&row.equipment===report.equipment);
  const candidate=selected||(c.equipment||[]).find(row=>row.equipment===report.equipment)||{};
  const filled=state.calendarFilled.get(report)||{};
  for(const key of ['permit','inspection_code'])if(candidate[key]&&(calendarFieldMissing(report[key])||report[key]===filled[key])){report[key]=candidate[key];filled[key]=candidate[key];}
  for(const key of ['drawings_on_site','drawings_approved'])if(fields[key]&&calendarFieldMissing(report[key]))report[key]=fields[key];
  if(state.reports.length===1&&(!(c.equipment||[]).length||(c.equipment||[]).some(row=>row.equipment===report.equipment))&&fields.permit&&calendarFieldMissing(report.permit))report.permit=fields.permit;
  if(candidate.subject_project&&calendarFieldMissing($('subject_project').value))$('subject_project').value=candidate.subject_project;
  report.site=report.site||{};
  for(const key of ['report_type','other_name'])if(candidate[key]&&(calendarFieldMissing(report.site[key])||report.site[key]===filled['site_'+key])){report.site[key]=candidate[key];filled['site_'+key]=candidate[key];}
  state.calendarFilled.set(report,filled);
}
function applyCalendar(applyDates=false,createReports=true){
  const c=state.candidates;if(!c)return;
  if($('calendar-title').value)$('title').value=$('calendar-title').value;
  const fields=c.fields||{};
  for(const key of ['client','project','requested_by','address'])if(fields[key]&&calendarFieldMissing($(key).value))$(key).value=fields[key];
  for(const key of ['inspection_date','request_date'])if(fields[key]&&(applyDates||calendarFieldMissing($(key).value)))$(key).value=fields[key];
  if(createReports){
    const candidates=c.equipment||[],current=state.reports[0];
    const blank=current&&['status','permit','inspection_code','locations','drawings_on_site','drawings_approved'].every(k=>calendarFieldMissing(current[k]))&&Object.values(current.site||{}).every(calendarFieldMissing)&&['open_items','source_references','photo_references'].every(k=>!(current[k]||[]).length);
    if(candidates.length===1&&state.reports.length===1&&blank&&['SF','SH','OT'].includes(candidates[0].equipment)){
      current.equipment=candidates[0].equipment;state.activeReport=current.equipment;
    }
    for(const candidate of candidates){if(['SF','SH','OT'].includes(candidate.equipment))addReport(candidate.equipment);}
  }
  for(const report of state.reports)hydrateCalendarReport(report);
  const selected=(c.report_subjects||[]).find(row=>row.title===$('calendar-title').value);
  if(selected&&state.reports.some(r=>r.equipment===selected.equipment))state.activeReport=selected.equipment;
  else if(c.equipment?.length===1)state.activeReport=c.equipment[0].equipment;
  renderReports();
  const notice=$('calendar-report-notice');const report=selected&&state.reports.find(r=>r.equipment===selected.equipment);
  const conflict=report&&['inspection_code'].some(k=>selected[k]&&report[k]!==selected[k])||report&&selected.other_name&&report.site.other_name!==selected.other_name;
  notice.textContent=conflict?'Selected calendar subject differs from existing report facts. Existing entries were kept; review the inspection number and item name before generating.':(c.report_subjects||[]).filter(row=>row.equipment==='OT').length>1?'Choose the intended shoring/Other subject. Use separate inspections for different locations or inspection numbers; report outcomes remain unconfirmed.':'Only supplied facts are filled. Blank permits, dimensions, drawing alternatives and template attendees remain unconfirmed.';
  markDirty();toast('Calendar facts filled where available. Review the selected report, outcomes, attendees and drawing status.');
}

async function downloadArtifact(artifact){const response=await api(`/artifacts/${encodeURIComponent(artifact.id)}`);const url=URL.createObjectURL(await response.blob());downloadURL(url,artifact.filename);}
function downloadURL(url,name){const link=el('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
function showGenerated(result){const root=$('generated');root.replaceChildren();root.append(el('p',result.notice,'muted'));for(const r of result.reports){const card=el('div',undefined,'result-card');card.append(el('h3',r.subject),el('p',r.status==='local_draft_generated'?'Review files generated':'Conversion incomplete'));if(r.error)card.append(el('p',r.error));if(r.missing_fields?.length)card.append(el('p',`Pending: ${r.missing_fields.join(', ')}`));if(r.font_audit?.missing?.length)card.append(el('p',`Font substitutions: ${r.font_audit.missing.join(', ')}. Check wrapping and page breaks.`));for(const note of r.review_required||[])card.append(el('p',note,'muted'));const links=el('div',undefined,'downloads');const preview=preferredPreview(result.artifacts.filter(a=>a.equipment===r.equipment));if(preview){const button=el('button','Preview report','secondary');button.onclick=()=>action(()=>previewArtifact(preview));links.append(button);}for(const a of result.artifacts.filter(a=>a.equipment===r.equipment)){const button=el('button',`Download ${a.filename.endsWith('.pdf')?'PDF':a.filename.endsWith('.docx')?'DOCX':a.filename.endsWith('.eml')?'email (.eml)':'HTML'}`,'secondary');button.onclick=()=>action(()=>downloadArtifact(a));links.append(button);const remove=el('button','Delete file','danger');remove.onclick=()=>action(async()=>{if(!confirm('Delete this generated file?'))return;await json(`/artifacts/${a.id}`,{method:'DELETE'});result.artifacts=result.artifacts.filter(item=>item.id!==a.id);showGenerated(result);});links.append(remove);}card.append(links);root.append(card);}root.append(el('p','Email files are unsent local drafts. No Gmail/Outlook draft was created by this page. '+(result.reports.some(r=>r.visual_stamp)?'Your saved visual stamp was applied to the No OIs PDF; review it before delivery.':'No signature/stamp image was applied.'),'muted'));}
function sourceLink(url,label){try{const parsed=new URL(url);if(parsed.protocol!=='https:')return el('span',label);const a=el('a',label);a.href=parsed.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return el('span',label);}}
function showSuggestions(result){const root=$('suggestions');root.replaceChildren();const suggestions=result.suggestions||{};for(const warning of [...(suggestions.warnings||[]),...(suggestions.missing_information||[])])root.append(el('p',warning,'muted'));for(const f of suggestions.suggested_findings||[]){const card=el('div',undefined,'result-card');card.append(el('h3',f.observation),el('p',`Location: ${f.location||'Not identified'}`),el('p',`Suggested action: ${f.suggested_action||'Not provided'}`));if(f.source_quote)card.append(el('p',`Source: ${f.source_quote}`,'muted'));for(const check of f.uncertainties||[])card.append(el('p',`Field confirmation: ${check}`,'muted'));for(const ref of f.references||[]){if(ref.verified===false)card.append(el('p',`DRAFT · PDF pages ${(ref.source_pages||[]).join(', ')} · applicability unverified`,'muted'));card.append(sourceLink(ref.url,`${ref.agency} · ${ref.section}`),el('p',ref.quote,'muted'));}if(['SF','SH','OT'].includes(f.equipment)){const adopt=el('button',`Confirm and add as ${equipmentLabel(f.equipment)} open item`);adopt.onclick=()=>{addReport(f.equipment);const r=state.reports.find(r=>r.equipment===f.equipment);r.status='OIs';r.open_items.push({id:crypto.randomUUID(),location:f.location||'',action:f.suggested_action||''});if(f.photo_id)r.photo_references.push(f.photo_id);r.source_references.push(f.source_quote||'Inspector-reviewed AI suggestion');for(const ref of f.references||[])r.source_references.push(`${ref.verified===false?'DRAFT; applicability unverified':'Reference for review'}: ${ref.agency} ${ref.section} · PDF pages ${(ref.source_pages||[]).join(', ')} · ${ref.quote}`);renderReports();markDirty();adopt.dataset.adopted='true';adopt.disabled=true;adopt.textContent='Added · review in Reports';};card.append(adopt);}else card.append(el('p','Equipment is unclear; enter the finding manually after clarification.','muted'));root.append(card);}if(!(suggestions.suggested_findings||[]).length)root.append(el('p','No findings suggested. This does not establish No OIs.'));}

$('connect-form').onsubmit=e=>{e.preventDefault();action(async()=>{state.token=$('token').value.trim();try{const cap=await json('/capabilities');state.cloudStorage=cap.storage==='cloudflare';$('storage-notice').textContent=state.cloudStorage?'Cloud saving connected. Reports, evidence and generated files are stored privately in Cloudflare. Changes save automatically while connected.':'Temporary server storage. Download backups until cloud storage is connected.';$('token').value='';$('connection').hidden=true;$('workspace').hidden=false;$('capabilities').textContent=(cap.cloud_ai_configured?'AI analysis is configured. All outputs require review.':'Manual workflow available. AI analysis is not configured.')+(cap.report_fonts?.installed?' Private rendering fonts installed: '+cap.report_fonts.families.join(', ')+'.':cap.report_fonts?.error?' Font setup needs attention: '+cap.report_fonts.error:' Private Aptos fonts are not installed yet.');reset();await refreshList();toast('Connected securely to this backend.');}catch(e){state.token='';throw e;}});};
$('disconnect').onclick=()=>action(async()=>{if(state.dirty)await save();reset();state.token='';$('workspace').hidden=true;$('connection').hidden=false;$('token').value='';});
document.querySelectorAll('[data-tab]').forEach(n=>n.onclick=()=>{tab(n.dataset.tab);if(n.dataset.tab==='templates')action(refreshTemplates);if(n.dataset.tab==='reports')refreshStamps().catch(error=>toast(error.message,true));});common.forEach(k=>$(k).addEventListener('input',markDirty));
$('new').onclick=()=>action(async()=>{if(state.dirty)await save();reset();});
$('save').onclick=()=>action(async()=>{await save();toast('Inspection saved to the server.');});
$('refresh').onclick=()=>action(async()=>{const id=state.id;if(state.saveConflict){if(!confirm('Discard the conflicting local draft and load saved records? Download Backup inspection JSON first if you need this draft.'))return;state.saveConflict=false;await refreshList();if(id)await load(id);}else{await refreshList();if(id&&!state.dirty)await load(id);}toast('Refreshed from backend.');});
$('saved').onchange=()=>{const id=$('saved').value;if(id)action(async()=>{if(state.dirty)await save();await load(id);});};
$('add-attendee').onclick=()=>{state.attendees.push({id:crypto.randomUUID(),name:'',company:'',title:''});renderAttendees();markDirty();};['SF','SH','OT'].forEach(eq=>$(`add-${eq}`).onclick=()=>{document.activeElement?.blur();switchReport(eq);$('report-list').closest('.panel')?.scrollIntoView({block:'start',behavior:'auto'});});
function showCalendarCandidates(candidates,chooseSingle=true){
  state.candidates=candidates;const titles=candidates.titles||[],select=$('calendar-title');select.replaceChildren();
  const blank=el('option','Choose a title…');blank.value='';select.append(blank);
  for(const title of titles){const option=el('option',title);option.value=title;select.append(option);}
  select.value=titles.includes($('title').value)?$('title').value:chooseSingle&&titles.length===1?titles[0]:'';
  $('calendar-title-options').hidden=!titles.length;$('use-calendar-title').disabled=!select.value;
  $('candidate-text').textContent=JSON.stringify(candidates,null,2);$('calendar-candidates').hidden=false;
}
$('extract').onclick=()=>action(async()=>{
  showCalendarCandidates(await json('/calendar/extract',{method:'POST',json:{text:$('calendar_text').value}}));
  applyCalendar(true);$('calendar-content').open=false;toast('Available calendar facts filled. Choose a subject if several are listed, review Report facts, then save.');
});$('apply-calendar').onclick=()=>applyCalendar(true);
$('transcript-file').onchange=()=>action(async()=>{const file=$('transcript-file').files[0];if(!file)return;if(file.size>100000)throw new Error('Transcript text limit is 100,000 bytes.');$('transcript').value+=($('transcript').value?'\n\n':'')+await file.text();markDirty();$('transcript-file').value='';toast('Transcript imported. Review the text before adopting findings.');});
$('upload').onchange=()=>action(async()=>{
  const files=[...$('upload').files];if(!files.length)return;
  const location=$('capture-location').value.trim(),condition=$('capture-condition').value.trim();
  const photoNote=[location?'Location: '+location:'',condition?'Condition: '+condition:''].filter(Boolean).join('\n');
  const prepared=files.map(file=>{if(file.size>40*1024*1024)throw new Error(`${file.name}: maximum file size is 40 MB.`);const ext=file.name.split('.').pop().toLowerCase();const mime={jpg:'image/jpeg',jpeg:'image/jpeg',png:'image/png',m4a:'audio/mp4',wav:'audio/wav',mp3:'audio/mpeg'}[ext];if(!mime)throw new Error(`${file.name}: unsupported file type.`);return {file,mime};});
  await save();
  try{for(const {file,mime} of prepared){
    const media=await json(`/inspections/${encodeURIComponent(state.id)}/media?kind=${mime.startsWith('image/')?'photo':'audio'}&filename=${encodeURIComponent(file.name)}`,{method:'POST',body:file,mime,headers:{'X-Asset-ID':crypto.randomUUID()}});
    if(mime.startsWith('image/')&&photoNote)await json(`/media/${encodeURIComponent(media.id)}`,{method:'PUT',json:{note:photoNote,equipment:''}});
  }}
  finally{state.media=await json(`/inspections/${encodeURIComponent(state.id)}/media`);await renderMedia();$('upload').value='';}
  $('capture-location').value='';$('capture-condition').value='';
  toast('Evidence uploaded. Photo notes saved; labels remain editable.');
});
$('analyze').onclick=()=>action(async()=>{if(!$('ai-consent').checked)throw new Error('Confirm data-sharing consent before using AI analysis.');const ids=[...document.querySelectorAll('[data-photo-id]:checked')].map(n=>n.dataset.photoId);if(ids.length>6)throw new Error('Select at most six photos for analysis.');await save();showSuggestions(await json(`/inspections/${encodeURIComponent(state.id)}/analyze`,{method:'POST',json:{consent:true,media_ids:ids}}));});
async function generateReports(openPreview=false){if(!$('request_date').value)throw new Error('Enter the request date in Inspection before generating a report.');if(!state.reports.length)throw new Error('Add a scaffold, shed or Other report first.');for(const r of state.reports.filter(r=>!openPreview||r.equipment===state.activeReport)){if(!r.status)throw new Error(`Confirm the ${equipmentLabel(r.equipment)} outcome.`);if(r.status==='OIs'&&!r.open_items.length)throw new Error('Add the observed open items before generating an Open Items report.');if(r.status==='No OIs'&&r.open_items.length)throw new Error('No OIs conflicts with recorded findings. Resolve or remove those findings first.');}await save();const result=await json(`/inspections/${encodeURIComponent(state.id)}/reports${openPreview?'?equipment='+encodeURIComponent(state.activeReport):''}`,{method:'POST',json:{stamp_id:$('stamp-selected').value||null,stamp_reviewed:$('stamp-reviewed').checked}});showGenerated(result);toast('Report generation finished. Review pending fields and rendering notes.');if(openPreview){const artifact=preferredPreview(result.artifacts.filter(a=>a.equipment===state.activeReport));if(artifact)await previewArtifact(artifact);else throw new Error('No preview was generated. Check the conversion notes below.');}}
$('generate').onclick=()=>action(()=>generateReports());
$('preview-current').onclick=()=>action(()=>generateReports(true));
$('search').onclick=()=>action(async()=>{const result=await json($('draft-codes').checked?'/codes/draft/search':'/codes/search',{method:'POST',json:{query:$('code-query').value,on_date:$('inspection_date').value,semantic:$('semantic').checked,library:$('draft-library').value}});const root=$('code-results');root.replaceChildren(el('p',result.notice,'muted'));if(!result.results.length)root.append(el('p','No matching sections found in the selected library.'));for(const r of result.results){const card=el('div',undefined,'result-card');card.append(el('h3',`${r.agency} · ${r.section}`),el('p',r.title),el('p',r.text),el('p',r.verified===false?`DRAFT · PDF pages ${(r.source_pages||[]).join(', ')} · ${r.retrieval}`:`Effective ${r.effective_from} · ${r.retrieval}`,'muted'),r.url?sourceLink(r.url,'View authoritative source'):el('p',`Parent sections: ${(r.parent_sections||[]).join(', ')||'Chapter context'}`,'muted'));root.append(card);}});
$('export-json').onclick=()=>{try{const data={version:1,inspection:payload(),evidence_metadata:state.media.map(({id,filename,note,equipment,kind})=>({id,filename,note,equipment,kind})),notice:'Photo/audio bytes are not included. Keep the original files separately.'};downloadURL(URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),`inspection-${$('project').value.replace(/[^a-zA-Z0-9_-]/g,'_')||'draft'}.json`);toast('Backup downloaded. Original media must be kept separately.');}catch(e){toast(e.message,true);}};
window.addEventListener('beforeunload',event=>{if(state.token&&state.dirty){event.preventDefault();event.returnValue='';}});

async function refreshTemplates(){
  const data=await json('/templates');$('templates-storage').textContent=data.notice;
  $('template-fields').textContent='Available fields: '+data.fields.map(k=>'{{'+k+'}}').join(', ');
  const root=$('template-versions');root.replaceChildren();
  for(const slot of data.slots){
    const section=el('section',undefined,'panel');section.append(el('h2',`${equipmentLabel(slot.slice(0,2))} · ${slot.endsWith('-No OIs')?'No open items':'Open items'}`));
    for(const record of data.versions.filter(r=>r.slot===slot)){
      const card=el('article',undefined,'result-card');card.dataset.templateVersion=record.id;
      const active=data.active[slot]===record.id;
      card.append(el('h3',record.label+(active?' · ACTIVE':'')),el('p',`${record.mode==='legacy'?'Existing DSENY tables':'Placeholder layout'} · ${new Date(record.created_at).toLocaleString()}`,'muted'),el('p',`Version ${record.id}`,'muted'));
      for(const error of record.errors)card.append(el('p',error,'muted'));
      const actions=el('div',undefined,'downloads');
      const download=el('button','Download template DOCX','secondary');download.onclick=()=>action(async()=>{const response=await api(`/templates/${record.id}/download`);downloadURL(URL.createObjectURL(await response.blob()),`${record.slot}-${record.id}.docx`);});actions.append(download);
      const backup=el('button','Download version settings','secondary');backup.onclick=()=>action(async()=>{const metadata=await json(`/templates/${record.id}/metadata`);downloadURL(URL.createObjectURL(new Blob([JSON.stringify(metadata,null,2)],{type:'application/json'})),`${record.slot}-${record.id}.json`);});actions.append(backup);
      const preview=el('button','Generate sample','secondary');preview.onclick=()=>action(async()=>{const result=await json(`/templates/${record.id}/preview`,{method:'POST'});const panel=$('template-preview');panel.hidden=false;panel.replaceChildren(el('h2','Sample report — review before activation'),el('p',result.notice));for(const report of result.reports){for(const note of report.review_required||[])panel.append(el('p',note,'muted'));if(report.error)panel.append(el('p',report.error));if(report.font_audit?.missing?.length)panel.append(el('p','Check font substitutions: '+report.font_audit.missing.join(', ')));}for(const artifact of result.artifacts){if(/\.(pdf|html)$/i.test(artifact.filename)){const view=el('button','Preview sample '+(artifact.filename.endsWith('.pdf')?'PDF':'HTML'),'secondary');view.onclick=()=>action(()=>previewArtifact(artifact));panel.append(view);}const button=el('button',`Download sample ${artifact.filename.endsWith('.pdf')?'PDF':artifact.filename.endsWith('.docx')?'DOCX':artifact.filename.endsWith('.eml')?'email':'HTML'}`,'secondary');button.onclick=()=>action(()=>downloadArtifact(artifact));panel.append(button);}panel.append(el('p',result.preview_success?'Sample generated. Open the files, review layout, then confirm and activate the version below.':'Conversion did not complete. Fix the reported issue before activation.'));await refreshTemplates();panel.scrollIntoView({behavior:'smooth',block:'start'});});actions.append(preview);if(!record.builtin&&!active){const archive=el('button','Archive version','danger');archive.onclick=()=>action(async()=>{if(!confirm('Hide this inactive template version? Its source is retained for report history.'))return;await json(`/templates/${record.id}`,{method:'DELETE'});await refreshTemplates();});actions.append(archive);}card.append(actions);
      if(record.mode==='placeholders'&&record.fields.length){
        const details=el('details');details.append(el('summary','Field mapping · save changes as a new version'));
        const selectors=[];
        for(const name of record.fields){const label=el('label',`{{${name}}} receives`);const select=el('select');select.setAttribute('aria-label',`{{${name}}} receives`);select.append(new Option('Choose an inspection field',''));for(const field of data.fields)select.append(new Option(field,field));select.value=record.mapping[name]||(data.fields.includes(name)?name:'');label.append(select);details.append(label);selectors.push([name,select]);}
        const save=el('button','Save mapping as new version','secondary');save.onclick=()=>action(async()=>{const mapping={};for(const [name,select] of selectors){if(!select.value)throw new Error('Choose a field for '+name);mapping[name]=select.value;}await json(`/templates/${record.id}/mapping`,{method:'POST',json:{mapping}});await refreshTemplates();toast('Mapping saved as a draft version. Generate a fresh sample before activation.');});details.append(save);card.append(details);
      }
      if(!active){const label=el('label',undefined,'check');const reviewed=el('input');reviewed.type='checkbox';label.append(reviewed,document.createTextNode('I reviewed the sample layout, wording and field placement.'));card.append(label);const activate=el('button',record.builtin?'Restore original version':'Activate this version');activate.onclick=()=>action(async()=>{if(!reviewed.checked)throw new Error('Review the sample and confirm the checkbox first.');await json(`/templates/${record.id}/activate`,{method:'POST',json:{reviewed:true}});await refreshTemplates();toast('Template activated. New reports will use this version.');});card.append(activate);}
      section.append(card);
    }root.append(section);
  }
}
$('templates-refresh').onclick=()=>action(refreshTemplates);
$('template-upload').onclick=()=>action(async()=>{
  const file=$('template-file').files[0];if(!file)throw new Error('Choose a DOCX template.');if(file.size>10*1024*1024)throw new Error('DOCX upload limit is 10 MB.');
  const query=new URLSearchParams({slot:$('template-slot').value,mode:$('template-mode').value,label:$('template-label').value.trim()||file.name,filename:file.name});
  await json('/templates?'+query,{method:'POST',body:file,mime:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'});
  $('template-file').value='';await refreshTemplates();toast('Draft template uploaded. Review mapping and generate a sample before activation.');
});

$('delete-inspection').onclick=()=>action(async()=>{if(!state.id){reset();return;}if(!confirm('Delete this inspection and all its evidence/report files from the backend and synced devices?'))return;await json(`/inspections/${state.id}`,{method:'DELETE'});reset();await refreshList();toast('Inspection deleted. Other devices will remove it on refresh.');});
async function refreshStamps(){const items=await json('/signing-assets');const selected=$('stamp-selected').value;$('stamp-selected').replaceChildren(new Option('No stamp',''));for(const item of items)$('stamp-selected').append(new Option(item.owner,item.id));if(items.some(i=>i.id===selected))$('stamp-selected').value=selected;}
$('stamp-upload').onclick=()=>action(async()=>{const file=$('stamp-file').files[0];if(!file)throw new Error('Choose the stamp/signature image.');const owner=$('stamp-owner').value.trim();if(!owner)throw new Error('Enter the engineer name.');const item=await json('/signing-assets?'+new URLSearchParams({owner}),{method:'POST',body:file,mime:file.type});await refreshStamps();$('stamp-selected').value=item.id;toast('Stamp stored privately. Review your report and confirm before applying.');});
$('stamp-delete').onclick=()=>action(async()=>{const id=$('stamp-selected').value;if(!id)return;if(!confirm('Delete this saved stamp image? Previously generated PDFs are unchanged.'))return;await json(`/signing-assets/${id}`,{method:'DELETE'});await refreshStamps();});

['SF','SH','OT'].forEach(eq=>$('create-'+eq).onclick=()=>{addReport(eq,true);$('report-list').closest('.panel')?.scrollIntoView({block:'start',behavior:'auto'});});
document.querySelectorAll('.report-type-tabs [role=tab]').forEach((button,index)=>{button.onkeydown=event=>{const keys=['ArrowLeft','ArrowRight','Home','End'];if(!keys.includes(event.key))return;event.preventDefault();const buttons=[...document.querySelectorAll('.report-type-tabs [role=tab]')];const target=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;buttons[target].click();buttons[target].focus();};});
$('calendar-title').onchange=()=>{const title=$('calendar-title').value;$('use-calendar-title').disabled=!title;if(title){$('title').value=title;applyCalendar(false);}};
$('use-calendar-title').onclick=()=>{const title=$('calendar-title').value;if(!title)return;$('title').value=title;applyCalendar(false);toast('Inspection title updated. Confirm report outcomes separately.');};
