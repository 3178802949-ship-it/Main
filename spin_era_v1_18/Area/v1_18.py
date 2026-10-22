"""Explicit formats on finite-era calendars; real dates remain evidence-qualified."""
from Area.v118 import *
from Area import v118 as previous
def validate_format(value):
    if type(value)is not int or value not in (3,5,7):raise ValueError('best_of must be 3,5,7')
    return value//2+1
VERSION='V1.18-AREA-1'

def calendar_for_year(year,mode='sandbox'):
    result=previous.calendar_for_year(year,mode)
    for event in result['events']:
        event.setdefault('competition_rules',dict(best_of=5 if event.get('kind')=='youth_singles' else 7,
            format_source='EXPLICIT_SIMULATION_DEFAULT_NOT_HISTORICAL_CERTIFICATION',group_format_locked=True))
    return result

def validate_calendar(calendar,year=None):
    result=previous.validate_calendar(calendar,year)
    for event in calendar.get('events',[]) if isinstance(calendar,dict) else []:
        if 'competition_rules' in event:
            try:validate_format(event['competition_rules']['best_of'])
            except (ValueError,KeyError,TypeError):result['errors'].append('INVALID_COMPETITION_FORMAT')
    result['valid']=not result['errors'];return result
