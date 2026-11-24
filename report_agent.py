"""Template-preserving inspection report generation; never sends mail."""
import argparse
from copy import deepcopy
from datetime import date
from email.message import EmailMessage
from email.policy import SMTP
from html import escape
import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from docx import Document
from docx.table import _Cell
from docx.shared import Inches, Pt
from lxml import etree

ROOT = Path(__file__).resolve().parent
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'


# The supplied original masters contain these two example PE seal images.
# Remove only these audited images, preserving logos and user-supplied artwork.
EXAMPLE_STAMP_HASHES = {
    'ebbcc91f3e0ba726a792da6f4d62cad2a35a465444a8865af0e37e9d01c9cd70',
    'fec9042ab2d600092143bbc6052a9e9a53a79182003cd1d0a6a206f3ac095125',
}


def example_stamp_rel_ids(doc):
    return {identity for identity,rel in doc.part.rels.items()
            if not rel.is_external and 'image' in rel.reltype
            and hashlib.sha256(rel.target_part.blob).hexdigest() in EXAMPLE_STAMP_HASHES}


def strip_example_stamp_nodes(root,relationships):
    changed=False
    for drawing in list(root.iter(W+'drawing')):
        if any(node.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed') in relationships for node in drawing.iter()):
            drawing.getparent().remove(drawing);changed=True
    return changed


def require(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Missing or invalid {name}')
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError(f'Invalid control character in {name}')
    return value.strip()


def is_pe(title):
    return any(re.sub(r'[^A-Z]','',part.upper())=='PE' for part in re.split(r'[;\n]',str(title)))


def physical_cells(row):
    return [_Cell(tc,row._parent) for tc in row._tr.tc_lst]


def separate_sections(doc):
    targets=[table._element for table in list(doc.tables)[2:5]]
    if len(doc.tables)==4:
        section=next((p._p for p in doc.paragraphs if p.text.strip().startswith("Section 4")),None)
        if section is not None: targets.append(section)
    for target in targets:
        # A new page already separates Section 3 from the preceding table.
        previous=target.getprevious()
        if previous is not None and previous.find('.//'+W+'pageBreakBefore') is not None: continue
        for _ in range(2):
            paragraph=etree.Element(W+'p');props=etree.SubElement(paragraph,W+'pPr')
            spacing=etree.SubElement(props,W+'spacing')
            for key,value in (('before','0'),('after','0'),('line','240'),('lineRule','auto')):spacing.set(W+key,value)
            target.addprevious(paragraph)


def validate(data, *, draft=False):
    if data.get('equipment') not in ('SF', 'SH', 'OT'):
        raise ValueError('equipment must be SF, SH or OT')
    if data.get('status') not in ('OIs', 'No OIs'):
        raise ValueError('status must be OIs or No OIs; do not infer from missing findings')
    for name in ('client', 'project', 'requested_by', 'permit', 'address', 'locations', 'inspection_code'):
        require(data.get(name), name)
    for name in ('request_date', 'inspection_date'):
        date.fromisoformat(require(data.get(name), name))
    for name in ('drawings_on_site', 'drawings_approved'):
        if data.get(name) not in (('Yes', 'No', 'NA', '[Pending confirmation]') if draft else ('Yes', 'No', 'NA')):
            raise ValueError(f'{name} must be Yes, No, or NA')
    attendees = data.get('attendees')
    if not isinstance(attendees, list) or not attendees:
        raise ValueError('Provide actual attendees, including the inspecting PE')
    for attendee in attendees:
        for name in ('name', 'company', 'title'):
            require(attendee.get(name), 'attendee.' + name)
    if not any(is_pe(a['title']) for a in attendees):
        raise ValueError('An inspecting PE attendee must be provided')
    items = data.get('open_items')
    if not isinstance(items, list):
        raise ValueError('open_items must be an explicit list')
    if bool(items) != (data['status'] == 'OIs'):
        raise ValueError('Open items conflict with report status')
    for item in items:
        for name in ('location', 'action'):
            require(item.get(name), 'open_item.' + name)
    if data['equipment']=='OT': require(product(data),'Other item name')
    fields = () if data['equipment']=='OT' else ('length_ft', 'height_ft', 'sections', 'width_ft') if data['equipment'] == 'SH' else (
        'length_ft', 'height_ft', 'tie_horizontal', 'tie_vertical', 'planked_levels',
        'outrigger_levels', 'tie_type', 'dunnage_type')
    for name in fields:
        require(data.get('site', {}).get(name), 'site.' + name)
    if data['equipment']=='SF':
        for kind in ('hoist','chute'):
            answer=data.get('site',{}).get(kind+'_inspected','')
            if answer and answer not in ('Yes','No','NA','[Pending confirmation]'):
                raise ValueError(kind+'_inspected must be Yes, No or NA')
    if draft:
        return  # Report-only review draft: no mail headers or recipient claims.
    for name in ('sender', 'to', 'cc'):
        values = data.get(name)
        values = [values] if name == 'sender' else values
        if not isinstance(values, list) or not values:
            raise ValueError(f'{name} is required; use verified client recipients and inspections mailbox')
        for address in values:
            if not isinstance(address, str) or not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+', address):
                raise ValueError(f'Invalid email in {name}')
    if data['sender'].casefold() not in [x.casefold() for x in data['cc']]:
        raise ValueError('CC must include the DSENY inspections sender mailbox')
    if data.get('recipients_confirmed') is not True:
        raise ValueError('Confirm recipients belong to the client; never copy calendar attendees blindly')


def replace_cell(cell, value):
    """Keep all paragraph/run formatting, replacing only text and inline content."""
    p = cell.paragraphs[0]
    exemplar = next((r for r in p.runs if r.text.strip()), p.runs[0] if p.runs else None)
    props = deepcopy(exemplar._r.rPr) if exemplar is not None and exemplar._r.rPr is not None else None
    for paragraph in list(cell._tc.findall(W + 'p'))[1:]:
        cell._tc.remove(paragraph)
    for child in list(p._p):
        if child.tag != W + 'pPr':
            p._p.remove(child)
    run = p.add_run(str(value))
    if props is not None:
        run._r.insert(0, props)


def set_rows(table, start, entries):
    exemplar = deepcopy(table.rows[start]._tr)
    for row in list(table.rows)[start:]:
        table._tbl.remove(row._tr)
    for entry in entries:
        table._tbl.append(deepcopy(exemplar))
        for index,(cell,value) in enumerate(zip(physical_cells(table.rows[-1]),entry)):
            replace_cell(cell,value)
            if index==0:
                for paragraph in cell.paragraphs:
                    props=paragraph._p.get_or_add_pPr()
                    old=props.find(W+'numPr')
                    if old is not None: props.remove(old)
                    num=etree.SubElement(props,W+'numPr');etree.SubElement(num,W+'numId').set(W+'val','0')


# Supported stable placeholders; unknown fields are never silently dropped.
TEMPLATE_FIELDS = tuple(('client project subject_project requested_by permit address locations inspection_code '
    'request_date inspection_date drawings_on_site drawings_approved product status attendees open_items '
    'source_references photo_references').split()) + tuple('site.'+k for k in (
    'length_ft','height_ft','sections','width_ft','tie_horizontal','tie_vertical',
    'planked_levels','outrigger_levels','tie_type','dunnage_type','hoist_inspected','chute_inspected','hoist_locations','hoist_height','hoist_model','chute_locations','chute_height','chute_model','report_type','other_name','details'))
TOKEN = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}')


def template_values(data):
    result={key:str(data.get(key,'')) for key in TEMPLATE_FIELDS if not key.startswith('site.')}
    for key in ('request_date','inspection_date'):
        result[key]=date.fromisoformat(data[key]).strftime('%m.%d.%Y')
    result['product']=product(data)
    result['attendees']='\n'.join(' | '.join(a[k] for k in ('name','company','title')) for a in data['attendees'])
    result['open_items']='\n'.join(f'{i}. {x["location"]}: {x["action"]}' for i,x in enumerate(data['open_items'],1)) or 'No open items.'
    for key in ('source_references','photo_references'): result[key]='\n'.join(data.get(key,[]))
    for key in TEMPLATE_FIELDS:
        if key.startswith('site.'): result[key]=str(data.get('site',{}).get(key[5:],'[Pending confirmation]'))
    return result


def no_open_items_email(calendar_text):
    """Return the calendar's No OIs cover text, without interpreting instructions."""
    source=str(calendar_text or '').replace('\r\n','\n').replace('\r','\n')
    heading=re.compile(r'^\s*IF\s+NO\s+(?:OPEN\s+ITEMS?|OIs?)\s+REPORT\s*:\s*$',re.I|re.M)
    boundary=re.compile(r'^\s*(?:[+=]{4,}|IF\s+OPEN\s+ITEMS?\s+REPORT\s*:|DSENY\s+Engineering|Title\s*:|Section\s+1\b)',re.I|re.M)
    candidates=[]
    for marker in heading.finditer(source):
        remaining=source[marker.end():]
        end=boundary.search(remaining)
        body=remaining[:end.start() if end else len(remaining)].strip()
        if re.match(r'Dear\s+Client\b',body,re.I) and re.search(r'no\s+open\s+items?',body,re.I):
            candidates.append(body)
    unique=list(dict.fromkeys(candidates))
    return unique[0] if len(unique)==1 else None


def number_report_pages(output):
    """Add centered PAGE of NUMPAGES fields without rewriting unrelated DOCX parts."""
    output=Path(output)
    parser=etree.XMLParser(resolve_entities=False,load_dtd=False,no_network=True)
    relns='http://schemas.openxmlformats.org/package/2006/relationships'
    office='http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
    contentns='http://schemas.openxmlformats.org/package/2006/content-types'
    with ZipFile(output) as package:
        infos=package.infolist();parts={item.filename:package.read(item.filename) for item in infos}
    document=etree.fromstring(parts['word/document.xml'],parser)
    relationships=etree.fromstring(parts['word/_rels/document.xml.rels'],parser)
    content_types=etree.fromstring(parts['[Content_Types].xml'],parser)
    sections=document.findall('.//'+W+'sectPr')
    if not sections:return
    relations={node.get('Id'):node for node in relationships}
    def register(name,kind):
        partname='/'+name
        if not any(node.get('PartName')==partname for node in content_types):
            node=etree.SubElement(content_types,'{'+contentns+'}Override');node.set('PartName',partname);node.set('ContentType','application/vnd.openxmlformats-officedocument.wordprocessingml.'+kind+'+xml')
    def relationship(target,kind):
        suffix=1;identity='rIdJBI'+kind.title()
        while identity in relations:suffix+=1;identity='rIdJBI'+kind.title()+str(suffix)
        node=etree.SubElement(relationships,'{'+relns+'}Relationship');node.set('Id',identity);node.set('Type',office+kind);node.set('Target',target);relations[identity]=node
        return identity
    inherited={};footers={}
    for index,section in enumerate(sections):
        current=dict(inherited)
        for reference in section.findall(W+'footerReference'):current[reference.get(W+'type')]=reference.get('{'+office[:-1]+'}id')
        if not current.get('default'):
            number=1;name='word/jbi-page-footer.xml'
            while name in parts:number+=1;name=f'word/jbi-page-footer{number}.xml'
            parts[name]=etree.tostring(etree.Element(W+'ftr',nsmap={'w':NS['w']}),xml_declaration=True,encoding='UTF-8',standalone=True)
            register(name,'footer');current['default']=relationship(name.removeprefix('word/'),'footer')
        for kind in ('default','first','even'):
            identity=current.get(kind) or current['default'];relation=relations.get(identity)
            if relation is None or relation.get('Type')!=office+'footer' or relation.get('TargetMode')=='External':raise ValueError('Invalid report footer relationship')
            import posixpath
            target=posixpath.normpath(posixpath.join('word',relation.get('Target','')))
            if not target.startswith('word/') or target not in parts:raise ValueError('Report footer part is unavailable')
            footers[target]=None
            current[kind]=identity
        for reference in list(section.findall(W+'footerReference')):section.remove(reference)
        position=sum(child.tag==W+'headerReference' for child in section)
        for kind in ('default','first','even'):
            reference=etree.Element(W+'footerReference');reference.set(W+'type',kind);reference.set('{'+office[:-1]+'}id',current[kind]);section.insert(position,reference);position+=1
        margins=section.find(W+'pgMar')
        if margins is not None:margins.set(W+'footer','360')
        numbering=section.find(W+'pgNumType')
        if numbering is None:
            numbering=etree.Element(W+'pgNumType');next_node=section.find(W+'cols')
            if next_node is None:next_node=section.find(W+'docGrid')
            section.insert(list(section).index(next_node) if next_node is not None else len(section),numbering)
        numbering.set(W+'fmt','decimal');numbering.attrib.pop(W+'start',None)
        if index==0:numbering.set(W+'start','1')
        inherited=current
    for index,name in enumerate(footers,1):
        footer=etree.fromstring(parts[name],parser)
        for paragraph in list(footer.findall(W+'p')):
            text=''.join(node.text or '' for node in paragraph.iter(W+'t')).strip()
            owned=paragraph.xpath('.//w:bookmarkStart[starts-with(@w:name,"JBI_PageCount_")]',namespaces=NS)
            codes=' '.join(node.text or '' for node in paragraph.iter(W+'instrText'))
            page_only=bool(re.search(r'\b(?:PAGE|NUMPAGES)\b',codes)) and bool(re.fullmatch(r'(?:Page\s*)?\d*\s*(?:(?:of|/)\s*\d*)?',text,re.I))
            empty=not text and not paragraph.xpath('.//w:drawing | .//w:pict',namespaces=NS)
            if owned or page_only or empty:footer.remove(paragraph)
        paragraph=etree.SubElement(footer,W+'p');props=etree.SubElement(paragraph,W+'pPr');etree.SubElement(props,W+'jc').set(W+'val','center')
        spacing=etree.SubElement(props,W+'spacing')
        for key,value in (('before','0'),('after','0'),('line','220'),('lineRule','exact')):spacing.set(W+key,value)
        bookmark=etree.SubElement(paragraph,W+'bookmarkStart');bookmark.set(W+'id',str(9000+index));bookmark.set(W+'name','JBI_PageCount_'+str(index))
        def run():
            node=etree.SubElement(paragraph,W+'r');properties=etree.SubElement(node,W+'rPr');fonts=etree.SubElement(properties,W+'rFonts')
            for key in ('ascii','hAnsi'):fonts.set(W+key,'Aptos')
            etree.SubElement(properties,W+'sz').set(W+'val','18');etree.SubElement(properties,W+'color').set(W+'val','000000')
            return node
        def field(instruction):
            begin=etree.SubElement(run(),W+'fldChar');begin.set(W+'fldCharType','begin');begin.set(W+'dirty','true')
            code=etree.SubElement(run(),W+'instrText');code.set('{http://www.w3.org/XML/1998/namespace}space','preserve');code.text=' '+instruction+' '
            etree.SubElement(run(),W+'fldChar').set(W+'fldCharType','separate');etree.SubElement(run(),W+'t').text='1'
            etree.SubElement(run(),W+'fldChar').set(W+'fldCharType','end')
        field('PAGE');separator=etree.SubElement(run(),W+'t');separator.set('{http://www.w3.org/XML/1998/namespace}space','preserve');separator.text=' of ';field('NUMPAGES')
        etree.SubElement(paragraph,W+'bookmarkEnd').set(W+'id',str(9000+index))
        parts[name]=etree.tostring(footer,xml_declaration=True,encoding='UTF-8',standalone=True)
    settings=etree.fromstring(parts['word/settings.xml'],parser)
    update=settings.find(W+'updateFields')
    if update is None:update=etree.SubElement(settings,W+'updateFields')
    update.set(W+'val','true')
    for name,tree in [('word/document.xml',document),('word/_rels/document.xml.rels',relationships),('[Content_Types].xml',content_types),('word/settings.xml',settings)]:parts[name]=etree.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True)
    with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.docx',delete=False) as handle:temporary=Path(handle.name)
    try:
        with ZipFile(temporary,'w',compression=ZIP_DEFLATED) as package:
            for info in infos:package.writestr(info,parts.pop(info.filename))
            for name,content in parts.items():package.writestr(name,content)
        temporary.replace(output)
    finally:temporary.unlink(missing_ok=True)


def fill_placeholders(data, output, source, mapping, reserve_signature=False):
    values=template_values(data)
    example_ids=example_stamp_rel_ids(Document(source))
    parser=etree.XMLParser(resolve_entities=False,load_dtd=False,no_network=True)
    with ZipFile(source) as original, ZipFile(output,'w') as result:
        for item in original.infolist():
            content=original.read(item.filename)
            if item.filename.startswith('word/') and item.filename.endswith('.xml'):
                root=etree.fromstring(content,parser)
                changed=strip_example_stamp_nodes(root,example_ids) if item.filename=='word/document.xml' else False
                for paragraph in root.iter(W+'p'):
                    # Tokens may be split across Word runs. Replace from the right so offsets remain stable.
                    nodes=list(paragraph.iter(W+'t'))
                    text=''.join(n.text or '' for n in nodes)
                    offsets=[];position=0
                    for node in nodes:
                        offsets.append((position,position+len(node.text or ''),node));position=offsets[-1][1]
                    matches=list(TOKEN.finditer(text))
                    if matches: changed=True
                    for match in reversed(matches):
                        key=mapping.get(match[1],match[1])
                        if key not in values: raise ValueError('Unmapped template field: '+match[1])
                        first=next(i for i,(a,b,_) in enumerate(offsets) if a<=match.start()<b)
                        last=next(i for i,(a,b,_) in enumerate(offsets) if a<match.end()<=b)
                        a,_,node=offsets[first];prefix=(node.text or '')[:match.start()-a]
                        end_a,_,end_node=offsets[last];suffix=(end_node.text or '')[match.end()-end_a:]
                        node.text=prefix+values[key]+(suffix if first==last else '')
                        node.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
                        # Convert inserted line breaks to Word line-break nodes without changing run properties.
                        if '\n' in (node.text or ''):
                            pieces=node.text.split('\n');node.text=pieces[0]
                            parent=node.getparent();index=parent.index(node)+1
                            for piece in pieces[1:]:
                                parent.insert(index,etree.Element(W+'br'));index+=1
                                next_node=etree.Element(W+'t');next_node.text=piece
                                next_node.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
                                parent.insert(index,next_node);index+=1
                        if first!=last:
                            for _,_,middle in offsets[first+1:last]: middle.text=''
                            end_node.text=suffix
                if item.filename=='word/document.xml':changed=space_report_sections(root.find(W+'body')) or changed
                if changed: content=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
            result.writestr(item,content)
    number_report_pages(output)
    return source


def compact_no_ois_layout(doc):
    """Use two pages for normal reports; stamp overlays page two rather than reserving space."""
    for section in doc.sections:
        section.top_margin=Inches(0.5);section.bottom_margin=Inches(0.5)
    # Empty template paragraphs are layout padding, not inspection content.
    for paragraph in list(doc.paragraphs):
        if not paragraph.text.strip() and not paragraph._p.xpath('.//w:drawing | .//w:pict | .//w:object'):
            paragraph._p.getparent().remove(paragraph._p)
    revised=doc.core_properties.identifier=="DSENY-2026-10-25"
    # Compact only legacy oversized labels/dates; new master typography is authoritative.
    if not revised:
        table=doc.tables[1]
        for row_index,cols in ((2,range(6)),(3,(0,)),(4,(0,1))):
            for col in cols:
                for paragraph in physical_cells(table.rows[row_index])[col].paragraphs:
                    for run in paragraph.runs: run.font.size=Pt(10)
        for paragraph in doc.paragraphs:
            if '347-730-6990' in paragraph.text:
                for run in paragraph.runs:run.font.size=Pt(10)
        # The complete scaffold table has extra hoist/chute rows; keep the small
        # specification text readable while leaving room for the full conclusion.
        for row in doc.tables[3].rows:
            for cell in physical_cells(row):
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_after=Pt(0)
                    for run in paragraph.runs:run.font.size=Pt(10)
        in_conclusion=False
        for paragraph in doc.paragraphs:
            if paragraph.text.strip().startswith('Section 4'):in_conclusion=True
            if in_conclusion:
                paragraph.paragraph_format.space_after=Pt(0)
                paragraph.paragraph_format.line_spacing=1.0
                for run in paragraph.runs:run.font.size=Pt(10)
    if revised:
        # Preserve master font sizes/colors; remove inherited paragraph padding
        # in the certificate body to keep the established compact page layout.
        children=list(doc._element.body)
        boundary=children.index(doc.tables[4]._element)
        for paragraph in doc.paragraphs:
            if children.index(paragraph._p)>boundary:
                paragraph.paragraph_format.space_before=Pt(0)
                paragraph.paragraph_format.space_after=Pt(0)
                paragraph.paragraph_format.line_spacing=1.0
                if paragraph._p.xpath('./w:pPr/w:numPr'):
                    paragraph.paragraph_format.left_indent=Inches(0.15)
                    paragraph.paragraph_format.first_line_indent=Inches(-0.1)
        for row in doc.tables[3].rows:
            for cell in physical_cells(row):
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_before=Pt(0)
                    paragraph.paragraph_format.space_after=Pt(0)
                    paragraph.paragraph_format.line_spacing=1.0
    # Sections 1 and 2 stay together on page one. Section 3 begins page two.
    page=etree.Element(W+'p');props=etree.SubElement(page,W+'pPr')
    etree.SubElement(props,W+'pageBreakBefore')
    spacing=etree.SubElement(props,W+'spacing');spacing.set(W+'before','0');spacing.set(W+'after','0')
    doc.tables[3]._element.addprevious(page)


def no_ois_narrative(source=None):
    """Copy the user's original No OIs wording and run formatting, without instructions."""
    original=Document(source or ROOT/'templates/New Template Full.docx')
    paragraphs=original.paragraphs
    if len(original.tables)>=14:
        return [deepcopy(original.tables[4].cell(0,0).paragraphs[0]._p)] + [deepcopy(p._p) for p in original.tables[11].cell(0,0).paragraphs[4:19] if p.text.strip()]
    if len(original.tables)==5 and 'CERTIFICATE OF COMPLETED INSTALLATION' in original.tables[4].cell(0,0).text:
        children=list(original._element.body);boundary=children.index(original.tables[4]._element)
        return [deepcopy(original.tables[4].cell(0,0).paragraphs[0]._p)] + [deepcopy(p._p) for p in paragraphs if children.index(p._p)>boundary and p.text.strip()]
    start=next(i for i,p in enumerate(paragraphs) if p.text.strip()=='Section 4')
    end=next(i for i in range(start,len(paragraphs)) if paragraphs[i].text.startswith('DSENY adheres'))
    return [deepcopy(p._p) for p in paragraphs[start:end+1]
            if not p.text.strip().startswith('A. IF')]


REPORT_GAP_POINTS = 11
REPORT_GAP_PREFIX = 'JBI_ReportGap_'


def space_report_sections(body):
    """One explicit line at report landmarks, shared by DOCX, PDF and email."""
    if body is None:return False
    def query(node,expression):return etree.XPath(expression,namespaces=NS)(node)
    def text(node):return ' '.join(''.join(query(node,'.//w:t/text()')).split())
    def empty(node):
        return node is not None and node.tag==W+'p' and not text(node) and not query(node,'.//w:drawing | .//w:pict | .//w:br | .//w:pageBreakBefore | .//w:sectPr')
    ids=[int(value) for value in query(body,'.//w:bookmarkStart/@w:id') if value.isdigit()]
    bookmark=max(ids,default=0)+1
    def gap(anchor,before,name):
        nonlocal bookmark
        direction='getprevious' if before else 'getnext'
        node=getattr(anchor,direction)()
        while empty(node):
            following=getattr(node,direction)();body.remove(node);node=following
        paragraph=etree.Element(W+'p');props=etree.SubElement(paragraph,W+'pPr')
        spacing=etree.SubElement(props,W+'spacing')
        for key,value in (('before','0'),('after','0'),('line',str(REPORT_GAP_POINTS*20)),('lineRule','exact')):spacing.set(W+key,value)
        etree.SubElement(props,W+'keepNext')
        start=etree.SubElement(paragraph,W+'bookmarkStart');start.set(W+'id',str(bookmark));start.set(W+'name',REPORT_GAP_PREFIX+name)
        run=etree.SubElement(paragraph,W+'r');rpr=etree.SubElement(run,W+'rPr');etree.SubElement(rpr,W+'sz').set(W+'val',str(REPORT_GAP_POINTS*2))
        etree.SubElement(run,W+'t').text='\u00a0'
        etree.SubElement(paragraph,W+'bookmarkEnd').set(W+'id',str(bookmark));bookmark+=1
        anchor.addprevious(paragraph) if before else anchor.addnext(paragraph)
    children=list(body);changed=False
    letterhead=next((node for node in children if node.tag==W+'tbl' and re.search(r'DSENY\s+Engineering\s+Services',text(node),re.I)),None)
    if letterhead is not None:
        gap(letterhead,True,'BeforeLetterhead');gap(letterhead,False,'AfterLetterhead');changed=True
    title=next((node for node in children if node.tag==W+'p' and re.match(r'^Title\s*:',text(node),re.I)),None)
    if title is not None:gap(title,False,'AfterTitle');changed=True
    section3=next((node for node in children if node.tag==W+'tbl' and re.match(r'^Section\s*3\b',text(node),re.I)),None)
    if section3 is not None:gap(section3,False,'AfterSection3');changed=True
    section5=next((node for node in children if node.tag in (W+'p',W+'tbl') and re.match(r'^Section\s*5\b',text(node),re.I)),None)
    if section5 is not None:gap(section5,True,'BeforeSection5');changed=True
    return changed


def fill_report(data, output, *, draft=False, template=None, template_mode="legacy", mapping=None, reserve_signature=False):
    validate(data, draft=draft)
    variant = 'Ois' if data['status'] == 'OIs' else 'N-Ois'
    source = ROOT / 'templates' / f'New Template {data["equipment"]}-{variant}.docx'
    if template is not None: source=Path(template)
    if template_mode == "placeholders":
        return fill_placeholders(data,output,source,mapping or {},reserve_signature)
    if template_mode != "legacy": raise ValueError("Unsupported template mode")
    doc = Document(source)
    strip_example_stamp_nodes(doc._element,example_stamp_rel_ids(doc))
    if data['equipment']=='OT' and len(doc.tables)>3 and sum('Section 3' in r.cells[0].text for r in doc.tables[3].rows)>1: prepare_other_layout(doc,data)
    for paragraph in doc.paragraphs:
        if '347-730-6990' in paragraph.text:
            props=paragraph._p.get_or_add_pPr();indent=props.find(W+'ind')
            if indent is not None: props.remove(indent)
    table = doc.tables[1]
    while len(table.rows)>8 and all(not c.text.strip() for c in physical_cells(table.rows[-1])):
        table._tbl.remove(table.rows[-1]._tr)
    values = {(1,1): data['client'], (1,3): data['project'],
              (2,1): date.fromisoformat(data['request_date']).strftime('%m.%d.%Y'),
              (2,3): date.fromisoformat(data['inspection_date']).strftime('%m.%d.%Y'),
              (2,5): data['requested_by'], (3,1): product(data),
              (4,1): data['permit'], (5,1): data['address'],
              (6,1): data['drawings_on_site'], (7,1): data['drawings_approved']}
    for (row, col), value in values.items():
        replace_cell(physical_cells(table.rows[row])[col],value)
    set_rows(doc.tables[2], 1, [(str(i),a['name'],a['company'],a['title']) for i,a in enumerate(data['attendees'],1)])
    site = doc.tables[3]
    # Actual physical cells avoid aliasing merged grid cells.
    rows = [list(row.cells) for row in site.rows]
    loc_index = next(i for i,r in enumerate(rows) if r[0].text.strip() == 'LOCATION/S:')
    replace_cell(physical_cells(site.rows[loc_index])[1],data['locations'])
    measures = data['site']
    if data['equipment']=='OT':
        detail=deepcopy(site.rows[loc_index]._tr);site._tbl.append(detail)
        replace_cell(site.rows[-1].cells[0],'Description / scope:')
        replace_cell(physical_cells(site.rows[-1])[1],data.get('site',{}).get('details') or 'Not provided')
    elif data['equipment'] == 'SH':
        for col, key in ((1,'length_ft'),(3,'sections'),(5,'height_ft'),(7,'width_ft')):
            replace_cell(physical_cells(site.rows[loc_index+1])[col],measures[key])
    else:
        physical = []
        for cell in site.rows[loc_index+1].cells:
            if not physical or cell._tc is not physical[-1]._tc:
                physical.append(cell)
        for col,key in ((1,'length_ft'),(3,'height_ft'),(5,'tie_horizontal'),(7,'tie_vertical')):
            replace_cell(physical[col], measures[key])
        replace_cell(physical_cells(site.rows[loc_index+2])[1],measures['planked_levels'])
        replace_cell(physical_cells(site.rows[loc_index+2])[3],measures['outrigger_levels'])
        replace_cell(physical_cells(site.rows[loc_index+3])[1],measures['tie_type'])
        replace_cell(physical_cells(site.rows[loc_index+4])[1],measures['dunnage_type'])
        # Reuse the original scaffold master rows for the full hoist/chute fields.
        if len(site.rows) <= loc_index+5:
            master = Document(ROOT/'templates/New Template SF-Ois.docx').tables[3]
            extra_start=next(i for i,row in enumerate(master.rows) if physical_cells(row)[0].text.strip()=='Hoist Inspected?')
            for row in list(master.rows)[extra_start:extra_start+6]: site._tbl.append(deepcopy(row._tr))
        extras = [('hoist_inspected',1),('chute_inspected',1),('hoist_locations',1),
                  ('hoist_height',1),('chute_locations',1),('chute_height',1)]
        for offset,(key,col) in enumerate(extras,loc_index+5):
            flag = 'hoist_inspected' if key.startswith('hoist') else 'chute_inspected'
            value = measures.get(key) or ('NA' if measures.get(flag) in ('No','NA') else '[Pending confirmation]')
            replace_cell(physical_cells(site.rows[offset])[col],value)
        for offset,key in ((loc_index+8,'hoist_model'),(loc_index+10,'chute_model')):
            flag = 'hoist_inspected' if key.startswith('hoist') else 'chute_inspected'
            replace_cell(physical_cells(site.rows[offset])[3],measures.get(key) or ('NA' if measures.get(flag) in ('No','NA') else '[Pending confirmation]'))
    if data['equipment']=='SF' and data['status']=='No OIs' and doc.core_properties.identifier=='DSENY-2026-10-25':
        # The master's preparation instructions remove unused equipment rows.
        for offset,kind in sorted([(loc_index+7,'hoist'),(loc_index+8,'hoist'),(loc_index+9,'chute'),(loc_index+10,'chute')],reverse=True):
            if measures.get(kind+'_inspected') in ('No','NA'):site._tbl.remove(site.rows[offset]._tr)
    if data['status'] == 'OIs':
        t = doc.tables[4]
        start = next(i for i,row in enumerate(t.rows) if row.cells[0].text.strip() == 'Number') + 1
        set_rows(t, start, [(str(i), item['location'], item['action']) for i,item in enumerate(data['open_items'],1)])
        for row in doc.tables[5].rows:
            replace_cell(row.cells[1], '')
    elif data['equipment']=='OT' and len(doc.tables)==6:
        t=doc.tables[4]
        for paragraph in no_ois_narrative(source):t._element.addprevious(paragraph)
        doc.tables[5]._element.getparent().remove(doc.tables[5]._element)
        t._element.getparent().remove(t._element)
    if data['status']=='No OIs': compact_no_ois_layout(doc)
    separate_sections(doc)
    space_report_sections(doc._element.body)
    # Copy all original package parts verbatim except the populated main document.
    xml = etree.tostring(doc._element, xml_declaration=True, encoding='UTF-8', standalone=True)
    with ZipFile(source) as original, ZipFile(output, 'w') as result:
        for item in original.infolist():
            result.writestr(item, xml if item.filename == 'word/document.xml' else original.read(item.filename))
    number_report_pages(output)
    return source


def prepare_other_layout(doc,data):
    # Use only the Full master's general sections, never its instruction text or example deficiencies.
    site=doc.tables[3];rows=list(site.rows)
    start=next(i for i,r in enumerate(rows) if ' '.join(r.cells[0].text.split())=='Section 3 Location')
    for row in rows:
        if row not in rows[start:start+2]: site._tbl.remove(row._tr)
    findings=doc.tables[4];rows=list(findings.rows)
    start=next(i for i,r in enumerate(rows) if ' '.join(r.cells[0].text.split())=='Section 4 Open Items')
    for row in rows[:start]: findings._tbl.remove(row._tr)
    body=doc._element.body;children=list(body)
    first=children.index(doc.tables[0]._element);second=children.index(doc.tables[1]._element)
    for index,child in enumerate(children):
        if child.tag!=W+'p': continue
        text=''.join(child.itertext()).strip()
        keep=first<index<second or (data['status']=='OIs' and any(marker in text for marker in (
            'Section 5, Client certification','Upon completion of corrected open items','I have personally and visually inspected')))
        if not keep: body.remove(child)


def product(data):
    if data['equipment']=='OT':
        site=data.get('site',{});kind=site.get('report_type','Unknown / custom')
        return require(site.get('other_name') if kind in ('','Unknown / custom','Other','Unknown') else kind,'Other item name')
    return 'Supported Scaffold' if data['equipment'] == 'SF' else 'Sidewalk Shed'


def subject(data):
    suffix='PE CERT OF USE' if data['status']=='No OIs' else data['status']
    return f'{data["inspection_date"]} {data["project"]} {product(data)}-{data["inspection_code"]}-Inspection-{suffix}'


def convert(docx, directory, kind):
    office = shutil.which('libreoffice') or shutil.which('soffice')
    if not office and (ROOT/'.tools/bin/libreoffice').is_file():
        office = str(ROOT/'.tools/bin/libreoffice')
    if not office:
        raise RuntimeError('LibreOffice Writer is required for PDF/HTML conversion; install it or convert with Microsoft Word')
    with tempfile.TemporaryDirectory(prefix='inspection-office-') as profile:
        result = subprocess.run([office, '-env:UserInstallation=' + Path(profile).as_uri(), '--headless',
                                 '--convert-to', kind, '--outdir', str(directory), str(docx)],
                                capture_output=True, text=True, timeout=120)
    suffix = 'html' if kind.startswith('html') else 'pdf'
    output = directory / (docx.stem + '.' + suffix)
    if result.returncode or not output.is_file() or not output.stat().st_size:
        raise RuntimeError(f'Office conversion failed: {result.stderr or result.stdout}')
    if suffix == 'pdf' and not output.read_bytes().startswith(b'%PDF-'):
        raise RuntimeError('Converter did not produce a PDF')
    return output


def build(data, directory):
    validate(data)
    directory.mkdir(parents=True, exist_ok=True)
    title = subject(data)
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)
    target = directory / safe
    if target.exists():
        raise ValueError('Output already exists; use a new directory to preserve earlier drafts')
    target.mkdir()
    docx = target / (safe + '.docx')
    fill_report(data, docx)
    manifest = {'subject': title, 'status': 'report_generated', 'docx': docx.name,
                'outlook_draft_created': False, 'sent': False, 'delivery_ready': False,
                'rendering_note': 'Exact template fonts and Word/Outlook appearance require verification; conversion may substitute fonts.',
                'review_required': ['Check fonts, table layout and page breaks in Word/Outlook',
                                    'Verify source facts, inspection findings and recipients']}
    manifest_file = target / 'manifest.json'
    try:
        msg = EmailMessage(policy=SMTP)
        msg['Subject'], msg['From'], msg['To'], msg['Cc'] = title, data['sender'], ', '.join(data['to']), ', '.join(data['cc'])
        msg['X-Unsent'] = '1'
        if data['status'] == 'OIs':
            html_path = convert(docx, target, 'html:HTML (StarWriter)')
            html = html_path.read_text(encoding='utf-8')
            # Avoid an email that references local images inaccessible to recipients.
            if re.search(r'<img\b', html, re.I):
                raise RuntimeError('HTML contains images; inline/CID embedding is needed before email packaging')
            msg.set_content('Please view this inspection report in an HTML-capable email client.')
            msg.add_alternative(html, subtype='html')
        else:
            pdf = convert(docx, target, 'pdf')
            # Conversion never constitutes professional signing/sealing.
            text = ('Dear Client,\n\nEQ inspection report provided here. There are no open items. '
                    'Certification for use is included in the conclusion in the attached PDF.\n'
                    'See attached; please print & keep at the jobsite. It is the responsibility of the '
                    'contractor to ensure these reports are forwarded to all appropriate parties.\n\n')
            text += 'Regards,\n' + next(a['name'] for a in data['attendees'] if is_pe(a['title']))
            text = no_open_items_email(data.get('calendar_text','')) or text
            msg.set_content(text)
            msg.add_alternative('<html><body>' + ''.join('<p>'+escape(p).replace('\n','<br>')+'</p>' for p in text.split('\n\n')) + '</body></html>', subtype='html')
            msg.add_attachment(pdf.read_bytes(), maintype='application', subtype='pdf', filename=pdf.name)
            manifest['pdf'] = pdf.name
            manifest['review_required'].append('PE must sign/seal the PDF; update cover wording only after signature verification')
        eml = target / (safe + '.eml')
        eml.write_bytes(bytes(msg))
        manifest.update(status='local_draft_generated', eml=eml.name)
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        manifest.update(status='conversion_blocked', error=str(error))
    manifest_file.write_text(json.dumps(manifest, indent=2))
    return manifest_file, manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'output')
    args = parser.parse_args()
    try:
        path, result = build(json.loads(args.input.read_text()), args.output.resolve())
        print(path)
        if result['status'] == 'conversion_blocked':
            parser.exit(2, result['error'] + '\nDOCX retained; no complete email draft produced.\n')
    except (ValueError, KeyError) as error:
        parser.exit(2, str(error) + '\n')
