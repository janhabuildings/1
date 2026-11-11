"""Inspection labels, separate from each report's email subject/outcome."""
import re


def equipment_code(name):
    value=re.sub(r'\s+',' ',name or '').strip()
    for pattern,code in [(r'^(SH|Sidewalk Shed)$','SH'),(r'^(SF|Supported Scaffold)$','SF'),
                         (r'^(SOE|Support of Excavation)$','SOE'),
                         (r'^(SStab|Structural Stability)$','SStab'),(r'^(FP|Fall Protection)$','FP')]:
        if re.fullmatch(pattern,value,re.I):return code
    return value


def calendar_equipment_labels(subjects, equipment):
    result=[]
    for row in subjects or equipment:
        kind=row.get('equipment')
        name=kind if kind in ('SH','SF') else row.get('other_name') or row.get('report_type') or 'Other'
        label=equipment_code(name)
        if label and label.casefold() not in {item.casefold() for item in result}:result.append(label)
    return result
