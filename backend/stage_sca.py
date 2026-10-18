"""Stage the uploaded SCA safety manual without treating its rules as agent instructions."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from pypdf import PdfReader
from backend.stage_pdf import retrieval_chunks

MAJOR = re.compile(r'^\s*(\d{1,2})\.\s+([A-Z][A-Z ,/&()–—-]{4,})\s*$')
SUB = re.compile(r'^\s*(\d{1,2}(?:\.\d+)+)\s+(.+)')


def segment(pages):
    records=[]
    current=None
    chapter=0
    occurrences={}
    for number,text in pages:
        if current and current['text'] and not current['text'].endswith('\n'):
            current['text']+='\n'
            current['page_spans'][-1]['end']=len(current['text'])
        for line in text.splitlines(keepends=True):
            major=MAJOR.match(line)
            sub=SUB.match(line)
            heading=None
            if major and int(major[1])==chapter+1:
                chapter=int(major[1]);heading=(major[1],major[2].strip())
            elif sub and chapter and int(sub[1].split('.')[0])==chapter:
                heading=(sub[1],sub[2].strip())
            if heading or current is None:
                if current: records.append(current)
                section,title=heading or ('front-matter','Cover and table of contents (not substantive requirements)')
                occurrences[section]=occurrences.get(section,0)+1
                parts=section.split('.')
                current={'section':section,'title':title,'text':'','source_pages':[], 'page_spans':[],
                    'record_id':section+':'+str(occurrences[section]),
                    'parent_sections':['.'.join(parts[:i]) for i in range(1,len(parts))],
                    'verified':False,'effective_from':None,'effective_to':None}
            start=len(current['text']);current['text']+=line
            if number not in current['source_pages']: current['source_pages'].append(number)
            if current['page_spans'] and current['page_spans'][-1]['page']==number:
                current['page_spans'][-1]['end']=len(current['text'])
            else: current['page_spans'].append({'page':number,'start':start,'end':len(current['text'])})
    if current: records.append(current)
    for record in records:
        record['requires_visual_review']=bool(re.search(r'\b(table|figure|exception|continued)\b',record['text'],re.I))
    return records


def stage(pdf,output):
    if output.exists(): raise ValueError('Choose a new staging directory')
    reader=PdfReader(pdf)
    pages=[(i+1,p.extract_text() or '') for i,p in enumerate(reader.pages)]
    empty=[n for n,t in pages if not t.strip()]
    if empty: raise ValueError(f'Pages require OCR or visual review: {empty}')
    records=segment(pages)
    chunks=retrieval_chunks(records)
    # Preserve front matter for audit but exclude it from retrieval/embedding.
    chunks=[c for c in chunks if c['section']!='front-matter']
    if not chunks: raise ValueError('No substantive manual sections detected')
    manifest={'source_filename':pdf.name,'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
        'agency':'NYC SCA','document':'NYC SCA Safety Manual — uploaded as January 2026 updates',
        'pdf_pages':len(pages),'section_records':len(records),'retrieval_chunks':len(chunks),
        'source_url':None,'source_url_verified':False,'effective_dates_verified':False,
        'active_index_updated':False,'embeddings_generated':False,
        'edition_note':'Filename says January 2026; page headers say SCA Safety Programs 2025. Edition and effective dates are unverified.',
        'extraction_note':'Numbered headings and continuations are retained. Unnumbered headings remain in parent section text; section numbers are not invented. Front matter is retained but excluded from embeddings.',
        'review_required':['Verify source, edition and applicability to project',
            'Check visual tables, figures, unnumbered headings and cross-page continuations',
            'Review dates per provision before using as a reviewed compliance source']}
    output.mkdir(parents=True)
    shutil.copy2(pdf,output/'source.pdf')
    for name,value in [('pages.json',[{'page':n,'text':t} for n,t in pages]),
                       ('sections.review.json',records),('chunks.review.json',chunks),('manifest.json',manifest)]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(stage(args.pdf,args.output),indent=2))
