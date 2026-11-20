"""Copy reusable values from saved inspections without modifying their reports."""
import json
import uuid

MIGRATION = 'saved-row-history-v1'
LIMIT = 1000
KEYS = {'attendee': ('name', 'company', 'title'), 'open_item': ('location', 'action'), 'company': ('company',)}
LENGTHS = {'name':300, 'company':300, 'title':300, 'location':3000, 'action':5000}
EMPTY = {'', '-', 'pending', '[pending confirmation]', 'tbd', 'n/a', 'na'}


def signature(row):
    return (row['kind'], row.get('equipment',''), *(' '.join(row.get(key,'').split()).casefold() for key in KEYS[row['kind']]))


def import_history(store, *, once=False):
    with store.connect() as db:
        if once and db.execute('SELECT 1 FROM app_migrations WHERE id=?',(MIGRATION,)).fetchone():return None
        existing=[json.loads(row['payload']) for row in db.execute('SELECT payload FROM saved_rows')]
        known={signature(row) for row in existing}
        total=len(existing)
        counts=dict(inspections=0,attendees_added=0,open_items_added=0,duplicates=0,skipped_empty=0,skipped_invalid=0,limit_skipped=0)
        def add(kind, source, equipment=''):
            nonlocal total
            if not isinstance(source,dict):counts['skipped_invalid']+=1;return
            row=dict(id=str(uuid.uuid4()),kind=kind,equipment=equipment if kind=='open_item' else '',name='',company='',title='',location='',action='')
            for key in KEYS[kind]:
                value=source.get(key,'')
                if value is None:value=''
                if not isinstance(value,str) or len(value)>LENGTHS[key]:counts['skipped_invalid']+=1;return
                value=value.strip()
                row[key]='' if value.casefold() in EMPTY else value
            if not any(row[key] for key in KEYS[kind]):counts['skipped_empty']+=1;return
            identity=signature(row)
            if identity in known:counts['duplicates']+=1;return
            if total>=LIMIT:counts['limit_skipped']+=1;return
            db.execute('INSERT INTO saved_rows VALUES (?,?)',(row['id'],json.dumps(row)))
            known.add(identity);total+=1
            counts['attendees_added' if kind=='attendee' else 'open_items_added']+=1
        def people(container):
            values=container.get('attendees',[])
            if isinstance(values,list):
                for person in values:add('attendee',person)
        for record in db.execute('SELECT payload FROM inspections').fetchall():
            inspection=json.loads(record['payload']);counts['inspections']+=1
            people(inspection)
            reports=inspection.get('reports',[])
            if not isinstance(reports,list):continue
            for report in reports:
                if not isinstance(report,dict):continue
                people(report)
                equipment=report.get('equipment','')
                if equipment not in ('SF','SH','OT'):equipment=''
                items=report.get('open_items',[])
                if isinstance(items,list):
                    for item in items:add('open_item',item,equipment)
        if once:db.execute('INSERT INTO app_migrations VALUES (?,?)',(MIGRATION,json.dumps(counts)))
        return counts


def seed_companies(store, *, once=False):
    marker='company-values-v1'
    with store.connect() as db:
        if once and db.execute('SELECT 1 FROM app_migrations WHERE id=?',(marker,)).fetchone():return None
        existing=[json.loads(row['payload']) for row in db.execute('SELECT payload FROM saved_rows')]
        known={signature(row) for row in existing if row['kind']=='company'}
        counts={'companies_added':0,'limit_skipped':0}
        total=len(existing)
        for saved in existing:
            if saved['kind']!='attendee':continue
            for name in saved.get('company','').replace('\n',';').split(';'):
                name=name.strip()
                if name.casefold() in EMPTY:continue
                row=dict(id=str(uuid.uuid4()),kind='company',equipment='',name='',company=name,title='',location='',action='')
                key=signature(row)
                if key in known:continue
                if total>=LIMIT:counts['limit_skipped']+=1;continue
                db.execute('INSERT INTO saved_rows VALUES (?,?)',(row['id'],json.dumps(row)))
                known.add(key);total+=1;counts['companies_added']+=1
        if once:db.execute('INSERT INTO app_migrations VALUES (?,?)',(marker,json.dumps(counts)))
        return counts
