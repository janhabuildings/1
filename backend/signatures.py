"""Private reusable visual stamp assets; placement never creates a cryptographic signature."""
from io import BytesIO
import hashlib
from pathlib import Path
import re
from PIL import Image
from backend.core import uid
from report_agent import is_pe


def initialize(store):
    (store.root/'signing').mkdir(exist_ok=True)
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS signing_assets(id TEXT PRIMARY KEY,owner TEXT NOT NULL,sha256 TEXT NOT NULL,path TEXT NOT NULL)')


def save(store,content,owner):
    if not owner.strip() or len(owner)>200: raise ValueError('Enter the engineer name associated with this signature/stamp')
    if len(content)>4*1024*1024: raise ValueError('Stamp image limit is 4 MB')
    try:
        with Image.open(BytesIO(content)) as im:
            if im.format not in ('PNG','JPEG') or im.width*im.height>16000000: raise ValueError('Use a PNG/JPEG image up to 16 megapixels')
            im.verify()
    except Exception as error: raise ValueError('Invalid stamp image; use PNG or JPEG') from error
    digest=hashlib.sha256(content).hexdigest()
    with store.connect() as db:
        row=db.execute('SELECT id FROM signing_assets WHERE sha256=? AND owner=?',(digest,owner.strip())).fetchone()
        if row:return {'id':row['id'],'owner':owner.strip(),'sha256':digest}
    identity=uid();path=store.root/'signing'/(identity+'.image');path.write_bytes(content)
    with store.connect() as db:db.execute('INSERT INTO signing_assets VALUES (?,?,?,?)',(identity,owner.strip(),digest,str(path)))
    return {'id':identity,'owner':owner.strip(),'sha256':digest}


def get(store,identity):
    with store.connect() as db: row=db.execute('SELECT * FROM signing_assets WHERE id=?',(identity,)).fetchone()
    if not row: raise KeyError('Signing image not found')
    record=dict(row)
    if not Path(record['path']).is_file(): raise KeyError('Signing image file not available')
    content=Path(record['path']).read_bytes()
    if hashlib.sha256(content).hexdigest()!=record['sha256']: raise ValueError('Signing image checksum changed')
    return record


def validate_owner(asset,reports):
    normalize=lambda text:re.sub(r'\W+','',text.casefold())
    for report in reports:
        if report['status']!='No OIs': continue
        if not any(is_pe(a.get('title','')) and normalize(a.get('name',''))==normalize(asset['owner']) for a in report.get('attendees',[])):
            raise ValueError('The saved stamp engineer must match an actual PE attendee on each No OIs report')


def apply(pdf,asset):
    from pypdf import PdfReader,PdfWriter
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    reader=PdfReader(pdf);writer=PdfWriter()
    for page in reader.pages:writer.add_page(page)
    first=writer.pages[0]
    if len(writer.pages)<2:writer.add_blank_page(width=float(first.mediabox.width),height=float(first.mediabox.height))
    page=writer.pages[1];width=float(page.mediabox.width);height=float(page.mediabox.height)
    buffer=BytesIO();canvas=Canvas(buffer,pagesize=(width,height))
    canvas.drawImage(ImageReader(asset['path']),width-235,60,width=180,height=144,preserveAspectRatio=True,anchor='c',mask='auto')
    canvas.setFont('Helvetica',8);canvas.drawRightString(width-55,50,'PE signature/seal: '+asset['owner'])
    canvas.save();buffer.seek(0);page.merge_page(PdfReader(buffer).pages[0])
    output=pdf.with_suffix('.stamping.tmp')
    with output.open('wb') as stream:writer.write(stream)
    output.replace(pdf)
    return {'asset_id':asset['id'],'sha256':asset['sha256'],'owner':asset['owner'],'page':2,'cryptographic_signature':False}
