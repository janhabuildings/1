"""Offline plugin runner. Produces MIME/Gmail handoff files; never accesses Gmail."""
import argparse
import base64
from copy import deepcopy
from email.message import EmailMessage
from email.policy import SMTP
from html import escape
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

PLUGIN = Path(__file__).resolve().parents[1]
core_spec = importlib.util.spec_from_file_location('dseny_report_core', PLUGIN/'runtime/report_agent.py')
reports = importlib.util.module_from_spec(core_spec)
core_spec.loader.exec_module(reports)
from lxml import etree

PENDING = '[Pending confirmation]'
COMMON_FIELDS = ('client','project','requested_by','permit','address','locations','inspection_code')
SH_FIELDS = ('length_ft','height_ft','sections','width_ft')
SF_FIELDS = ('length_ft','height_ft','tie_horizontal','tie_vertical','planked_levels','outrigger_levels','tie_type','dunnage_type')


def prepare(data):
    """Make missing facts explicit, without choosing dates or inspection results."""
    data = deepcopy(data)
    missing = []
    for key in COMMON_FIELDS:
        if not data.get(key):
            data[key] = PENDING
            missing.append(key)
    for key in ('drawings_on_site','drawings_approved'):
        if not data.get(key):
            data[key] = PENDING
            missing.append(key)
    if not data.get('attendees'):
        data['attendees'] = []
        missing.append('attendees')
    for i, attendee in enumerate(data['attendees']):
        for key in ('name','company','title'):
            if not attendee.get(key):
                attendee[key] = PENDING
                missing.append(f'attendees[{i}].{key}')
    if not any(a['title'].strip().upper() == 'PE' for a in data['attendees']):
        data['attendees'].append({'name': PENDING, 'company':'DSENY Engineering Services PC','title':'PE'})
        missing.append('inspecting_pe')
    for key in SH_FIELDS if data.get('equipment') == 'SH' else SF_FIELDS:
        data.setdefault('site', {})
        if not data['site'].get(key):
            data['site'][key] = PENDING
            missing.append('site.'+key)
    # Caller-supplied pending placeholders must also be reported.
    def visit(value, path=''):
        if isinstance(value,dict):
            for key,item in value.items(): visit(item, f'{path}.{key}' if path else key)
        elif isinstance(value,list):
            for i,item in enumerate(value): visit(item,f'{path}[{i}]')
        elif isinstance(value,str) and ('[pending' in value.lower() or '[confirm' in value.lower()):
            if path not in missing: missing.append(path)
    visit(data)
    reports.validate(data, draft=True)
    return data, missing


def font_audit(docx):
    """Report actual requested font families; never silently declare substitution exact."""
    families = set()
    with ZipFile(docx) as z:
        for member in ('word/document.xml','word/styles.xml'):
            tree = etree.fromstring(z.read(member))
            for node in tree.xpath('//w:rFonts',namespaces=reports.NS):
                for attribute in ('ascii','hAnsi'):
                    font = node.get(reports.W+attribute)
                    if font and font not in ('inherit','Symbol'):
                        families.add(font)
    missing = []
    if shutil.which('fc-match'):
        for family in sorted(families):
            match=subprocess.run(['fc-match','-f','%{family}',family],capture_output=True,text=True,timeout=10)
            names={name.strip().casefold() for name in match.stdout.split(',')}
            if match.returncode or family.casefold() not in names: missing.append(family)
        return {'requested':sorted(families),'missing':missing,'verified':True}
    # Windows font presence still requires a rendering comparison in Word.
    return {'requested':sorted(families),'missing':None,'verified':False}


def office_convert(docx, directory, kind, renderer):
    if renderer == 'word':
        if sys.platform != 'win32':
            raise RuntimeError('Microsoft Word conversion must run on Windows with desktop Word installed')
        powershell=shutil.which('powershell.exe')
        if not powershell:
            raise RuntimeError('Windows PowerShell is not available')
        dest=directory/(docx.stem+'.'+kind)
        completed=subprocess.run([powershell,'-NoProfile','-NonInteractive','-File',str(PLUGIN/'scripts/word_convert.ps1'),
                                  '-InputPath',str(docx),'-OutputPath',str(dest),'-Format',kind],
                                 capture_output=True,text=True,timeout=120)
        if completed.returncode or not dest.is_file() or not dest.stat().st_size:
            raise RuntimeError('Word conversion failed: '+completed.stderr.strip())
        if kind=='pdf' and not dest.read_bytes().startswith(b'%PDF-'):
            raise RuntimeError('Word output is not a PDF')
        return dest
    # Permit an explicit trusted Office binary, otherwise use platform installation.
    office=os.environ.get('DSENY_OFFICE_BIN')
    if office:
        if not Path(office).is_file(): raise RuntimeError('DSENY_OFFICE_BIN does not exist')
        with tempfile.TemporaryDirectory(prefix='dseny-office-') as profile:
            completed=subprocess.run([office,'-env:UserInstallation='+Path(profile).as_uri(),'--headless','--convert-to',
                                      'html:HTML (StarWriter)' if kind=='html' else 'pdf','--outdir',str(directory),str(docx)],
                                     capture_output=True,text=True,timeout=120)
        dest=directory/(docx.stem+'.'+kind)
        if completed.returncode or not dest.is_file() or not dest.stat().st_size:
            raise RuntimeError('Office conversion failed: '+(completed.stderr or completed.stdout).strip())
        if kind=='pdf' and not dest.read_bytes().startswith(b'%PDF-'):
            raise RuntimeError('Office output is not a PDF')
        return dest
    return reports.convert(docx,directory,'html:HTML (StarWriter)' if kind=='html' else 'pdf')


def email_html(path):
    from lxml import html
    tree=html.fromstring(path.read_text(encoding='utf-8-sig'))
    if tree.xpath('//img | //object | //iframe | //script | //link[@href] | //form'):
        raise RuntimeError('HTML references unsupported images, objects or external assets; embed them before drafting')
    for node in tree.xpath('//*[@src or @background]'):
        raise RuntimeError('HTML contains an unresolved resource')
    # Page counters from the Word document do not belong in an inline report.
    for node in tree.xpath('//div[@title="footer"] | //meta[@name="author" or @name="changedby"]'):
        node.getparent().remove(node)
    return html.tostring(tree,encoding='unicode',method='html')


def check_address(address):
    if not isinstance(address,str) or not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',address):
        raise ValueError('Invalid email address in mailbox configuration')
    return address


def generate(request, output, renderer='libreoffice'):
    if renderer not in ('libreoffice','word'):
        raise ValueError('renderer must be libreoffice or word')
    entries=request.get('reports')
    if not isinstance(entries,list) or not entries:
        raise ValueError('Provide one report per equipment type in reports[]')
    mailbox=request.get('mailbox',{})
    account=check_address(mailbox.get('account','janhabuildings@gmail.com'))
    to=[check_address(x) for x in mailbox.get('to',[])]
    cc=[check_address(x) for x in mailbox.get('cc',[])]
    if to or cc:
        if mailbox.get('recipients_confirmed') is not True:
            raise ValueError('Verify client recipients before setting recipients_confirmed=true')
    prepared=[prepare(entry) for entry in entries]
    if len({data['equipment'] for data,_ in prepared}) != len(prepared):
        raise ValueError('Use one report per equipment type in each run')
    titles=[reports.subject(dict(data,project=data.get('subject_project') or data['project'])) for data,_ in prepared]
    if any('\r' in title or '\n' in title for title in titles):
        raise ValueError('Email subjects cannot contain line breaks')
    if len(set(titles))!=len(titles):
        raise ValueError('Duplicate report subjects; provide one report per equipment inspection')
    if output.exists():
        raise ValueError('Output directory already exists; use a new run directory')
    output.mkdir(parents=True)
    result={'version':1,'gmail_account':account,'gmail_drafts_created':False,'sent':False,'reports':[]}
    for (data,missing),title in zip(prepared,titles):
        safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',title)
        if len(safe)>170: raise ValueError('Report subject is too long for artifact filenames')
        folder=output/data['equipment'];folder.mkdir()
        docx=folder/(safe+' - DRAFT.docx')
        reports.fill_report(data,docx,draft=True)
        audit=font_audit(docx)
        entry={'equipment':data['equipment'],'subject':title,'docx':str(docx),'missing_fields':missing,
               'font_audit':audit,'renderer':renderer,'delivery_ready':False,'status':'docx_generated',
               'review_required':['Inspect actual document page breaks and email table layout',
                                  'Confirm inspection facts and pending fields'],
               'source_references':data.get('source_references',[]),'photo_references':data.get('photo_references',[])}
        if data['status']=='No OIs':
            entry['review_required'].append('PE must sign/seal the final PDF; conversion is not a signature')
        try:
            attachments=[]
            if data['status']=='OIs':
                html_file=office_convert(docx,folder,'html',renderer)
                content=email_html(html_file)
                html_file.write_text(content,encoding='utf-8')
                entry['html_file']=str(html_file)
            else:
                pdf=office_convert(docx,folder,'pdf',renderer)
                entry['pdf']=str(pdf)
                attachments=[{'path':str(pdf),'filename':pdf.name,'mime_type':'application/pdf',
                              'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}]
                body=('Dear Client,\n\nEQ inspection report provided here. There are no open items. '
                      'Certification for use is included in the conclusion in the attached PDF.\n'
                      'See attached; please print & keep at the jobsite. It is the responsibility of the contractor '
                      'to ensure these reports are forwarded to all appropriate parties.\n\nRegards,\n'+
                      next(a['name'] for a in data['attendees'] if a['title'].strip().upper()=='PE'))
                content='<html><body>'+''.join('<p>'+escape(p).replace('\n','<br>')+'</p>' for p in body.split('\n\n'))+'</body></html>'
                html_file=folder/(safe+' - Cover.html');html_file.write_text(content)
                entry['html_file']=str(html_file)
            msg=EmailMessage(policy=SMTP)
            msg['Subject']=title;msg['From']=account;msg['X-Unsent']='1'
            if to: msg['To']=', '.join(to)
            if cc: msg['Cc']=', '.join(cc)
            msg.set_content('Review draft. View the HTML version for the formatted inspection report.')
            msg.add_alternative(content,subtype='html')
            for attachment in attachments:
                msg.add_attachment(Path(attachment['path']).read_bytes(),maintype='application',subtype='pdf',filename=attachment['filename'])
            eml=folder/(safe+' - DRAFT.eml');eml.write_bytes(bytes(msg))
            # Actual Gmail API drafts.create request if a host tool accepts a raw MIME draft.
            raw=folder/'gmail-raw.json'
            raw.write_text(json.dumps({'message':{'raw':base64.urlsafe_b64encode(bytes(msg)).decode()}}))
            # Connector-neutral handoff; the host must map to the actual tool schema.
            handoff={'account':account,'subject':title,'body_html':content,'to':to,'cc':cc,
                     'attachments':attachments,'eml_path':str(eml),'raw_mime_json_path':str(raw),
                     'create_draft_only':True,'review_only':True}
            handoff_file=folder/'gmail-handoff.json';handoff_file.write_text(json.dumps(handoff,indent=2))
            entry.update(status='local_draft_generated',eml=str(eml),gmail_handoff=str(handoff_file))
        except (RuntimeError,subprocess.TimeoutExpired,OSError) as error:
            entry.update(status='conversion_blocked',error=str(error))
        result['reports'].append(entry)
    (output/'manifest.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--renderer',choices=['libreoffice','word'],default='libreoffice')
    args=parser.parse_args()
    try:
        result=generate(json.loads(args.input.read_text()),args.output.resolve(),args.renderer)
        print(args.output.resolve()/'manifest.json')
        if any(e['status']=='conversion_blocked' for e in result['reports']):
            parser.exit(2,'Conversion blocked for at least one report; see manifest. DOCX retained.\n')
    except (ValueError,KeyError,TypeError) as error:
        parser.exit(2,str(error)+'\n')


if __name__=='__main__': main()
