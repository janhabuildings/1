/* Account management stays in memory; personal access keys are displayed once. */
let workspaceUsers=[];
async function workspaceConnected(){
  state.user=await json('/workspace/me');
  $('connection-state').textContent=state.user.name+' · '+state.user.role;
  $('workspace-admin').hidden=state.user.role!=='admin';
  document.querySelector('[data-tab="templates"]').hidden=state.user.role!=='admin';
  $('import-saved-rows').hidden=state.user.role!=='admin';
  if(state.user.role==='admin')await refreshWorkspaceUsers();
}
async function refreshWorkspaceUsers(){
  workspaceUsers=await json('/workspace/users');
  const list=$('workspace-users');list.replaceChildren();
  for(const user of workspaceUsers){
    const row=el('div',undefined,'actions');row.append(el('span',`${user.name} · ${user.email} · ${user.role} · ${user.active?'Active':'Inactive'}`));
    const toggle=el('button',user.active?'Deactivate':'Reactivate','secondary');toggle.type='button';toggle.onclick=()=>action(async()=>{await json('/workspace/users/'+encodeURIComponent(user.id),{method:'PATCH',json:{active:!user.active}});await refreshWorkspaceUsers();});
    const rotate=el('button','Replace access key','secondary');rotate.type='button';rotate.onclick=()=>action(async()=>{
      if(!confirm('Replace this person’s key? Their previous key will stop working.'))return;
      showWorkspaceKey(await json('/workspace/users/'+encodeURIComponent(user.id),{method:'PATCH',json:{rotate_key:true}}));
    });row.append(toggle,rotate);list.append(row);
  }
  renderWorkspaceAssignments();
}
function showWorkspaceKey(user){
  $('workspace-key-label').textContent='Personal key for '+user.name+' — give it privately to this user. It will not be shown again.';
  $('workspace-key').value=user.access_key;$('workspace-key-box').hidden=false;
}
function renderWorkspaceAssignments(){
  const box=$('workspace-assignment');box.replaceChildren();
  if(state.user?.role!=='admin')return;
  if(!state.id){box.append(el('p','Save or open an inspection to assign it.','muted'));return;}
  const record=(state.records||[]).find(row=>row.id===state.id);
  const selected=new Set(record?.assigned_user_ids||[]);
  const users=[{id:'workspace-owner',name:'Workspace owner',active:true},...workspaceUsers.filter(user=>user.active)];
  for(const user of users){const label=el('label',undefined,'check'),input=el('input');input.type='checkbox';input.value=user.id;input.checked=selected.has(user.id);label.append(input,document.createTextNode(user.name));box.append(label);}
  const save=el('button','Save assignments');save.type='button';save.onclick=()=>action(async()=>{
    const ids=[...box.querySelectorAll('input:checked')].map(input=>input.value);
    await json('/inspections/'+encodeURIComponent(state.id)+'/assignments',{method:'PUT',json:{assigned_user_ids:ids}});
    await refreshList();toast('Inspection assignments saved.');
  });box.append(save);
}
$('workspace-user-form').onsubmit=event=>{event.preventDefault();action(async()=>{
  const user=await json('/workspace/users',{method:'POST',json:{name:$('workspace-user-name').value,email:$('workspace-user-email').value,role:$('workspace-user-role').value}});
  showWorkspaceKey(user);$('workspace-user-form').reset();await refreshWorkspaceUsers();
});};
$('workspace-key-dismiss').onclick=()=>{$('workspace-key').value='';$('workspace-key-label').textContent='';$('workspace-key-box').hidden=true;};
