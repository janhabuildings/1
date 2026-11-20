'use strict';
let savedRows=[];
const savedSummary=row=>(row.kind==='attendee'?[row.name,row.company,row.title]:[row.equipment,row.location,row.action]).filter(Boolean).join(' · ');
async function refreshSavedRows(){savedRows=await json('/saved-rows');renderSavedRows();}
function renderSavedRows(){const root=$('saved-rows');root.replaceChildren();if(!savedRows.length)root.append(el('p','Save attendee or open-item rows while drafting to reuse them in future inspections.','muted'));for(const saved of savedRows){const row=el('div',undefined,'result-card');row.append(el('p',savedSummary(saved)));const remove=removeButton('Delete saved suggestion');remove.onclick=()=>action(async()=>{await json('/saved-rows/'+encodeURIComponent(saved.id),{method:'DELETE'});await refreshSavedRows();});row.append(remove);root.append(row);}}
async function saveReusableRow(row){await json('/saved-rows',{method:'POST',json:row});await refreshSavedRows();toast('Row saved for reuse across inspections.');}
function attachSavedRows(root,kind,key,equipment,apply){
  const input=root.querySelector('input,textarea');if(!input)return;
  const panel=el('div',undefined,'saved-row-suggestions');panel.setAttribute('aria-label','Saved row suggestions');panel.hidden=true;root.append(panel);
  function render(){const query=input.value.trim().toLocaleLowerCase();panel.replaceChildren();const matches=query.length<2?[]:savedRows.filter(row=>row.kind===kind&&(!equipment||!row.equipment||row.equipment===equipment)&&(row[key]||'').toLocaleLowerCase().includes(query)).slice(0,5);for(const saved of matches){const button=el('button','Use saved: '+savedSummary(saved),'secondary');button.type='button';button.onpointerdown=e=>e.preventDefault();button.onclick=()=>{apply(saved);panel.hidden=true;};panel.append(button);}panel.hidden=!matches.length;}
  input.addEventListener('input',render);input.addEventListener('focus',render);root.addEventListener('focusout',event=>{if(!root.contains(event.relatedTarget))panel.hidden=true;});
}
function applyTranscriptDraft(draft){
  for(const fact of draft.facts){const input=$(fact.field);if(input&&!input.value.trim()&&fact.value.trim())input.value=fact.value;}
  for(const person of draft.attendees){if(![person.name,person.company,person.title].some(v=>v.trim()))continue;const existing=state.attendees.find(row=>(person.name&&row.name.toLocaleLowerCase()===person.name.toLocaleLowerCase())||(!row.name&&person.company&&row.company===person.company&&row.title===person.title));if(existing){for(const key of ['name','company','title'])if(!existing[key])existing[key]=person[key];}else insertAttendee({id:crypto.randomUUID(),name:person.name,company:person.company,title:person.title});}
  for(const item of draft.open_items){if(!['SF','SH','OT'].includes(item.equipment)||(!item.location.trim()&&!item.action.trim()))continue;addReport(item.equipment);const report=state.reports.find(row=>row.equipment===item.equipment);if(!report.open_items.some(row=>row.location===item.location&&row.action===item.action))report.open_items.push({id:crypto.randomUUID(),location:item.location,action:item.action});report.calendar_title='';setReportOutcome(report,'OIs');}
  updateInspectionTitle(true);renderAttendees();renderReports();markDirty();
}
function showTranscriptDraft(draft,inspectionID){
  const root=$('transcript-draft');root.replaceChildren();root.append(el('h3','Review and edit transcript draft'),el('p','Applying fills empty common facts, merges attendees and adds open items. Existing facts and report-specific attendee lists are preserved. New open items remove the stamp from their report.','muted'));
  for(const warning of draft.warnings)root.append(el('p',warning,'muted'));
  const apply=el('button','Apply reviewed draft');
  function refreshApply(){apply.disabled=state.id!==inspectionID||draft.open_items.some(row=>!['SF','SH','OT'].includes(row.equipment));apply.dataset.adopted=String(apply.disabled);}
  function section(title,rows,type){const box=el('div');box.append(el('h3',title));for(const row of rows){const card=el('div',undefined,'result-card');
    if(type==='fact')card.append(field(row.field,row.value,value=>row.value=value));
    else if(type==='attendee')for(const key of ['name','company','title'])card.append(field(key==='title'?'Role':key,row[key],value=>row[key]=value));
    else {card.append(field('Equipment',row.equipment,value=>{row.equipment=value;refreshApply();},{options:[['unknown','Choose equipment'],['SF','Scaffold'],['SH','Shed'],['OT','Other']]}));card.append(field('Location / occurrence',row.location,value=>row.location=value),field('Corrective action',row.action,value=>row.action=value,{type:'textarea'}));}
    card.append(el('p','Transcript: '+row.source_quote,'muted'));
    if(row.matched_saved_id)card.append(el('p','Exact saved-row match · missing details filled from your library','muted'));
    for(const saved of row.saved_matches||[]){const choose=el('button','Use saved: '+savedSummary(saved),'secondary');choose.onclick=()=>{for(const key of type==='attendee'?['name','company','title']:['location','action','equipment'])if(saved[key])row[key]=saved[key];row.matched_saved_id=saved.id;showTranscriptDraft(draft,inspectionID);};card.append(choose);}
    const remove=removeButton('Remove draft suggestion');remove.onclick=()=>{rows.splice(rows.indexOf(row),1);showTranscriptDraft(draft,inspectionID);};card.append(remove);box.append(card);
  }root.append(box);}
  section('Common facts',draft.facts,'fact');section('Attendees',draft.attendees,'attendee');section('Open items',draft.open_items,'open_item');
  apply.onclick=()=>{if(state.id!==inspectionID){toast('Inspection changed. Analyze its transcript again.',true);return;}applyTranscriptDraft(draft);root.replaceChildren(el('p','Draft applied. Review and edit the inspection and report cells.'));};
  const cancel=el('button','Discard draft','secondary');cancel.onclick=()=>root.replaceChildren();root.append(apply,cancel);refreshApply();
}
document.addEventListener('DOMContentLoaded',()=>{
$('import-saved-rows').onclick=()=>action(async()=>{const result=await json('/saved-rows/import-history',{method:'POST'});await refreshSavedRows();toast(`Imported ${result.attendees_added} attendee rows and ${result.open_items_added} open-item rows from ${result.inspections} inspections. Duplicates skipped: ${result.duplicates}.`+(result.limit_skipped?` ${result.limit_skipped} rows exceeded the library limit.`:''));});
$('refresh-saved-rows').onclick=()=>action(refreshSavedRows);
$('transcript-analyze').onclick=()=>action(async()=>{if(!$('transcript-ai-consent').checked)throw new Error('Allow transcript sharing before using AI.');if(!$('transcript').value.trim())throw new Error('Enter or transcribe speech first.');await save();const id=state.id;const result=await json('/inspections/'+encodeURIComponent(id)+'/transcript-draft',{method:'POST',json:{consent:true}});showTranscriptDraft(result.draft,id);});

});
