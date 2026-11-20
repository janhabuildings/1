"""Conservative labeled-text extraction. No network, AI, or report mutation."""
import re
import uuid

LABELS = {
    'attendee':'name','attendees':'name','name':'name','company':'company','company name':'company',
    'agency':'company','company / agency':'company','role':'title','title':'title',
    'equipment':'equipment','product':'equipment','location':'location','occurrence':'location',
    'corrective action':'action','action':'action','open item':'open_item','observation':'observation',
    'client':'client','project':'project','address':'address','requested by':'requested_by',
    'request date':'request_date','inspection date':'inspection_date','inspected on':'inspection_date',
}
LABEL = '|'.join(re.escape(key) for key in sorted(LABELS,key=len,reverse=True))
SPLIT = re.compile(r'[\r\n]+|(?<=[.;!?])\s+(?=(?:'+LABEL+r')\b)|;\s*(?=(?:'+LABEL+r')\b)|,\s*(?=(?:'+LABEL+r')\s*(?::|\s))',re.I)
FIELD = re.compile(r'^\s*('+LABEL+r')\b\s*(?::|=|\s+-\s+)?\s*(.+?)\s*$',re.I)
NEGATED = re.compile(r'\b(?:no open items?|no deficiencies|not required|no need|do not|already (?:fixed|repaired|corrected|completed)|(?:has|have) been (?:fixed|repaired|corrected))\b',re.I)
LIMITS={'name':300,'company':300,'title':300,'location':3000,'action':5000,'project':200,'client':1000,'address':2000,'requested_by':1000,'request_date':10,'inspection_date':10}


def norm(text):return ' '.join(re.findall(r'\w+',text.casefold()))


def similarity(left,right):
    left=norm(left)[:400];right=norm(right)[:400]
    if not left or not right:return 0
    if left==right:return 1
    previous=list(range(len(right)+1))
    for i,a in enumerate(left,1):
        current=[i]
        for j,b in enumerate(right,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(a!=b)))
        previous=current
    return 1-previous[-1]/max(len(left),len(right))


def match_saved(row,library,kind):
    keys=('name',) if kind=='attendee' else ('action','location')
    ranked=[]
    for saved in library:
        if saved.get('kind')!=kind:continue
        if kind=='open_item' and row['equipment']!='unknown' and saved.get('equipment','') not in ('',row['equipment']):continue
        score=max((similarity(row[key],saved.get(key,'')) for key in keys if len(norm(row[key]))>=3),default=0)
        if score>=0.64:ranked.append((score,saved))
    ranked.sort(key=lambda value:value[0],reverse=True)
    row['saved_matches']=[saved for _,saved in ranked[:5]];row['matched_saved_id']=None
    exact=[saved for score,saved in ranked if score==1]
    if len(exact)==1:
        saved=exact[0];row['matched_saved_id']=saved['id']
        for key in (('name','company','title') if kind=='attendee' else ('action','location')):
            if not row[key]:row[key]=saved.get(key,'')
        if kind=='open_item' and row['equipment']=='unknown' and saved.get('equipment'):row['equipment']=saved['equipment']


def equipment_code(value):
    text=norm(value)
    if text in ('sf','scaffold','supported scaffold'):return 'SF'
    if text in ('sh','shed','sidewalk shed'):return 'SH'
    if text in ('ot','other','soe','support of excavation','shoring','sstab','structural stability','fp','fall protection','fence','structural netting','structural netting as ohp'):return 'OT'
    return 'unknown'


def extract(text,library=()):
    draft={'attendees':[],'open_items':[],'facts':[],'warnings':['Coded extraction only; no AI service was used. Review every value before applying.']}
    person=None;item=None;equipment='unknown';equipment_start=None;seen_facts=set()
    def warn(message):
        if message not in draft['warnings'] and len(draft['warnings'])<30:draft['warnings'].append(message)
    def flush_person():
        nonlocal person
        if person and any(person.get(key) for key in ('name','company','title')):
            row={key:person.get(key,'') for key in ('name','company','title')}
            quote=text[person['start']:person['end']].strip()
            if len(quote)<=5000 and len(draft['attendees'])<50 and not re.search(r'\b(?:absent|not present|not attending|did not attend|not an attendee|not on site|not here)\b',quote,re.I) and not re.match(r'^(?:not|no)\b',row['name'],re.I):
                row.update(id=str(uuid.uuid4()),source_quote=quote);match_saved(row,library,'attendee');draft['attendees'].append(row)
        person=None
    def flush_item():
        nonlocal item,equipment_start
        if item and (item.get('action') or item.get('location')):
            quote=text[item['start']:item['end']].strip()
            if len(quote)<=5000 and len(draft['open_items'])<100:
                row=dict(id=str(uuid.uuid4()),equipment=item['equipment'],location=item.get('location',''),action=item.get('action',''),source_quote=quote)
                if not NEGATED.search(quote):
                    match_saved(row,library,'open_item');draft['open_items'].append(row)
                    if not row['action']:warn('A location has no explicit corrective action. Fill it or remove the item before applying.')
                else:warn('A negated or already-corrected item was not added; review its wording manually.')
        item=None;equipment_start=None
    cuts=[(match.start(),match.end()) for match in SPLIT.finditer(text)];start=0
    for end,next_start in cuts+[(len(text),len(text))]:
        chunk=text[start:end];chunk_start=start;start=next_start
        match=FIELD.match(chunk)
        if not match:continue
        key=LABELS[match[1].casefold()];value=match[2].strip().rstrip('.!?').strip()
        if not value:continue
        if key in LIMITS and len(value)>LIMITS[key]:warn('A value exceeded its cell limit and was left for manual entry.');continue
        if key in ('name','company','title'):
            flush_item()
            if person and key in person:flush_person()
            if person is None:person={'start':chunk_start,'end':end}
            person[key]=value;person['end']=end
        elif key=='equipment':
            flush_person();flush_item();equipment=equipment_code(value);equipment_start=chunk_start
            if equipment=='unknown':warn('Equipment was not recognized. Assign the report type before applying.')
        elif key in ('location','action','open_item','observation'):
            flush_person()
            if key=='observation':warn('Observations are not automatically converted into corrective actions.');continue
            if NEGATED.search(value):item=None;equipment_start=None;warn('A negated or already-corrected item was not added; review its wording manually.');continue
            target='action' if key=='open_item' else key
            if item and ((target in item and item[target]) or (target=='location' and item.get('action'))):flush_item()
            if item is None:item={'equipment':equipment,'start':equipment_start if equipment_start is not None else chunk_start,'end':end}
            item[target]=value;item['end']=end
            if key=='open_item':warn('Confirm that the open-item wording describes the corrective action you want in the report.')
        else:
            flush_person();flush_item()
            if key in seen_facts:warn('Repeated common facts were left for review; only the first labeled value is proposed.');continue
            if key.endswith('_date'):
                from datetime import date
                try:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError
                    date.fromisoformat(value)
                except ValueError:warn('Use YYYY-MM-DD for coded date extraction.');continue
            seen_facts.add(key);draft['facts'].append({'field':key,'value':value,'source_quote':chunk.strip()})
    flush_person();flush_item()
    if not any(draft[key] for key in ('attendees','open_items','facts')):warn('No labeled values found. Try: Attendee: John Smith. Company: ABC. Role: Site Supervisor. Equipment: Scaffold. Location: North. Action: Install missing pins. Or choose optional AI for unstructured notes.')
    return draft
