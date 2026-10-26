'use strict';
let previewURL=null,previewFile=null;
function preferredPreview(artifacts){return artifacts.find(a=>/\.pdf$/i.test(a.filename))||artifacts.find(a=>/\.html$/i.test(a.filename));}
function clearPreview(){
  $('preview-frame').removeAttribute('src');$('preview-frame').removeAttribute('srcdoc');
  if(previewURL)URL.revokeObjectURL(previewURL);previewURL=null;previewFile=null;
}
function closePreview(){if($('report-preview').open)$('report-preview').close();clearPreview();}
function safePreviewHTML(source){
  const doc=new DOMParser().parseFromString(source,'text/html');
  doc.querySelectorAll('script,iframe,object,embed,base,link,meta,form,input,button,textarea,select,svg,math').forEach(node=>node.remove());
  doc.querySelectorAll('*').forEach(node=>{for(const attr of [...node.attributes])if(/^on/i.test(attr.name)||['href','src','srcset','action','formaction','background','xlink:href'].includes(attr.name.toLowerCase()))node.removeAttribute(attr.name);});
  const policy=doc.createElement('meta');policy.httpEquiv='Content-Security-Policy';policy.content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; form-action 'none'; base-uri 'none'";doc.head.prepend(policy);
  const viewport=doc.createElement('meta');viewport.name='viewport';viewport.content='width=device-width, initial-scale=1';doc.head.append(viewport);
  return '<!doctype html>'+doc.documentElement.outerHTML;
}
async function previewArtifact(artifact){
  if(!/\.(pdf|html)$/i.test(artifact.filename))throw new Error('This file can be downloaded but cannot be previewed.');
  const response=await api(`/artifacts/${encodeURIComponent(artifact.id)}`);
  const pdf=/\.pdf$/i.test(artifact.filename);
  const content=pdf?await response.arrayBuffer():await response.text();
  if(pdf&&new TextDecoder().decode(content.slice(0,5))!=='%PDF-')throw new Error('The PDF is unavailable. Regenerate the report and try again.');
  clearPreview();previewFile=artifact;
  const frame=$('preview-frame');frame.title=pdf?'PDF report preview':'Formatted report preview';
  $('preview-title').textContent=artifact.filename;
  $('preview-note').textContent=pdf?'Preview of the generated PDF. If your browser cannot display it here, use Download file.':'Preview of the formatted HTML report. Word page breaks may differ. Use Download file to keep a copy.';
  if(pdf){frame.removeAttribute('sandbox');previewURL=URL.createObjectURL(new Blob([content],{type:'application/pdf'}));frame.src=previewURL+'#toolbar=1&navpanes=0&view=FitH';}
  else{frame.setAttribute('sandbox','');frame.srcdoc=safePreviewHTML(content);}
  $('report-preview').showModal();
}
$('preview-close').onclick=closePreview;
$('report-preview').addEventListener('close',clearPreview);
$('preview-download').onclick=()=>{if(previewFile)action(()=>downloadArtifact(previewFile));};
