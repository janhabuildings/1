"""Extract a code PDF into review-only, page-traceable sections and bounded chunks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

MAJOR=re.compile(r'^\s*(?:[‡†*]+\s*)?SECTION\s+BC\s+(33\d{2})\b',re.I)
SUBSECTION=re.compile(r'^\s*(?:[‡†*]+\s*)?(33\d{2}(?:\.\d+)+)\s+(.+)')


def segment_pages(pages):
    records=[]
    current=None
    def start(section,title):
        return {'section':section,'title':title,'text':'','source_pages':[],
                'page_spans':[],'verified':False,'effective_from':None,'effective_to':None}
    for page_number,text in pages:
        if current and current['text'] and not current['text'].endswith('\n'):
            current['text']+='\n'  # Preserve a word boundary at the physical PDF page break.
            if current['page_spans']: current['page_spans'][-1]['end']=len(current['text'])
        for line in text.splitlines(keepends=True):
            major=MAJOR.match(line);sub=SUBSECTION.match(line)
            if major or sub:
                if current and current['text'].strip(): records.append(current)
                section=major.group(1) if major else sub.group(1)
                title='BC '+section if major else sub.group(2).strip().split('. ')[0][:200]
                current=start(section,title)
            if current is None: current=start('preamble','Chapter preamble and amendment notes')
            offset=len(current['text']);current['text']+=line
            if page_number not in current['source_pages']: current['source_pages'].append(page_number)
            if current['page_spans'] and current['page_spans'][-1]['page']==page_number:
                current['page_spans'][-1]['end']=len(current['text'])
            else: current['page_spans'].append({'page':page_number,'start':offset,'end':len(current['text'])})
    if current and current['text'].strip(): records.append(current)
    occurrences={}
    for record in records:
        section=record['section'];occurrences[section]=occurrences.get(section,0)+1
        record['record_id']=section+':'+str(occurrences[section])
        parts=section.split('.')
        record['parent_sections']=['.'.join(parts[:i]) for i in range(1,len(parts))] if section!='preamble' else []
        record['requires_visual_review']=bool(re.search(r'\b(TABLE|FIGURE|Exceptions?)\b',record['text'],re.I))
    return records


def retrieval_chunks(records,size=6000,overlap=400):
    if overlap>=size or overlap<0: raise ValueError('Chunk overlap must be smaller than size')
    result=[]
    for record in records:
        start=0;number=0;text=record['text']
        while start<len(text):
            end=min(start+size,len(text));number+=1
            if end<len(text):
                boundary=text.rfind('\n',start+size//2,end)
                if boundary>start: end=boundary+1
            chunk={'id':record['record_id']+':chunk'+str(number),'section':record['section'],
                   'section_record_id':record['record_id'],'title':record['title'],'text':text[start:end],
                   'source_pages':[span['page'] for span in record['page_spans'] if span['start']<end and span['end']>start],
                   'parent_sections':record['parent_sections'],'character_start':start,'character_end':end,
                   'verified':False,'effective_from':None,'not_ready_for_ingestion':True,
                   'context_requirement':'Retrieve the complete section and parent provisions, exceptions and cross-references before interpreting this excerpt.'}
            result.append(chunk)
            if end==len(text): break
            start=max(start+1,end-overlap)
    return result


def stage(pdf,output):
    from pypdf import PdfReader
    if output.exists(): raise ValueError('Choose a new staging directory; existing review work is preserved')
    reader=PdfReader(pdf)
    pages=[(i+1,page.extract_text() or '') for i,page in enumerate(reader.pages)]
    empty=[number for number,text in pages if not text.strip()]
    if empty: raise ValueError('Text extraction failed on pages '+str(empty)+'; OCR/visual review is required')
    records=segment_pages(pages);chunks=retrieval_chunks(records)
    if not chunks: raise ValueError('No text chunks extracted')
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    output.mkdir(parents=True)
    shutil.copy2(pdf,output/'source.pdf')
    (output/'pages.json').write_text(json.dumps([{'page':n,'text':t} for n,t in pages],ensure_ascii=False,indent=2))
    (output/'sections.review.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    (output/'chunks.review.json').write_text(json.dumps(chunks,ensure_ascii=False,indent=2))
    summary={'source_filename':pdf.name,'sha256':digest,'agency':'NYC DOB',
             'document':'2022 NYC Building Code, Chapter 33 — Safeguards During Construction or Demolition',
             'pdf_pages':len(pages),'section_records':len(records),'retrieval_chunks':len(chunks),
             'source_url':None,'source_url_verified':False,'effective_dates_verified':False,
             'active_index_updated':False,'embeddings_generated':False,
             'review_required':['Confirm source provenance and edition/amendments',
                                'Assign section-specific effective dates and applicable code edition',
                                'Compare extracted tables, figures, exceptions and cross-page continuations against PDF',
                                'Preserve parent provisions and cross-references in retrieval context',
                                'Explicitly approve eligible source sections before ingestion/embedding'],
             'pdf_metadata':{str(k):str(v) for k,v in (reader.metadata or {}).items()}}
    (output/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try: print(json.dumps(stage(args.pdf,args.output),ensure_ascii=False,indent=2))
    except ValueError as error: parser.exit(2,str(error)+'\n')
