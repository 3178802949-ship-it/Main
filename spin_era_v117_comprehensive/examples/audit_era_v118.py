"""Execute declared-date and inherited calendar checks without inventing history."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Area import v118 as Area


def main():
    calendars = []
    for year in range(2000, 2029):
        calendar = Area.calendar_for_year(year)
        check = Area.validate_calendar(calendar)
        assert check['valid'], (year, check)
        calendars.append(dict(year=year, events=len(calendar['events']),
            historical_calendar_verified=check['historical_calendar_verified'],
            warnings=check['warnings']))
    future_source = dict(source_id='SYNTHETIC_TEMPORAL_FIXTURE', source_date='2024-01-01')
    old_context = Area.validate_context('2006-02-01', sources=[future_source], allow_design_priors=True)
    assert old_context['source_partition']['available'] == []
    assert old_context['source_partition']['design_priors'][0]['not_in_world_knowledge']
    rejected = []
    for invalid in ('1999-12-31', '2028-07-31', '2029-01-01'):
        try:
            Area.ensure_date(invalid)
        except ValueError:
            rejected.append(invalid)
    assert len(rejected) == 3
    files = ['Area/v118.py', 'Area/v117.py', 'Area/__init__.py',
             'data/calendar_2027_v117.json', 'data/calendar_2028_v117.json',
             'examples/audit_era_v118.py']
    report = dict(version=Area.VERSION, status='DECLARED_CONTEXT_AND_CALENDAR_CHECKS_PASSED',
        calendar_years_checked=29, calendars=calendars, rejected_dates=rejected,
        synthetic_future_source_case=old_context,
        source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files},
        limitations=['Only source-date declarations were checked; this does not authenticate documents.',
                    'Complete verified real 2025/2026 schedules are not present.',
                    'Forward Olympic dates remain a sandbox window, not independently verified table-tennis dates.',
                    'No equipment chronology is invented from player names or modern papers.'])
    output = ROOT / 'reports/comprehensive/ERA_AUDIT.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=report['status'], years=len(calendars), output=str(output)), ensure_ascii=False))


if __name__ == '__main__':
    main()
