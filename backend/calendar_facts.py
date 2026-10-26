"""Calendar subject metadata, kept separate from template outcomes and findings."""
import re
from datetime import date


def report_subjects(text):
    products=[]
    collecting=False
    for line in text.splitlines():
        match=re.match(r'^\s*Product Inspected\s*:\s*(.*)',line,re.I)
        if match:
            collecting=True;line=match.group(1)
        elif collecting and re.match(r'^\s*(?:Permit|Address|Section|PE Drawings|Drawings DOB)',line,re.I):collecting=False
        if collecting and line.strip():products.append(re.sub(r'\s+',' ',line).strip())
    rows=[]
    for line in text.splitlines():
        title=re.sub(r'\s+',' ',line).strip()
        match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}) (.+?)-([IVXLCDM\d]+)\s*-\s*Inspection\s*-\s*(?:No\s+OIs|OIs|PE\s+CERT\s+OF\s+USE)',title,re.I)
        if not match:continue
        try:date.fromisoformat(match[1])
        except ValueError:continue
        prefix=match[2].strip()
        product=next((p for p in sorted(products,key=len,reverse=True) if prefix.casefold().endswith(' '+p.casefold())),None)
        if not product:
            found=re.search(r'(Supported Scaffold|Sidewalk Shed|Fall Protection|SOE|Fence|Shoring|SStab)$',prefix,re.I)
            if found:product=found[1]
        equipment='SF' if product and product.casefold()=='supported scaffold' else 'SH' if product and product.casefold()=='sidewalk shed' else 'OT'
        row={'title':title,'equipment':equipment,'inspection_date':match[1],'inspection_code':match[3]}
        if product:
            row['subject_project']=prefix[:-len(product)].strip()
            if equipment=='OT':
                row['other_name']=product
                row['report_type']={'soe':'SOE','fall protection':'Fall Protection','fence':'Fence','shoring':'Shoring','sstab':'SStab'}.get(product.casefold(),'Unknown / custom')
        if not any(r['title']==title for r in rows):rows.append(row)
    return rows
