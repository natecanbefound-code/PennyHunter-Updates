#!/usr/bin/env python3
"""Validate owner-approved CSVs and build PennyHunter's offline feed. No scraping."""
import csv
import datetime as dt
import io
import pathlib
import sys
from decimal import Decimal, InvalidOperation

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIELDS = ['upc', 'retailer', 'status', 'price', 'date', 'source', 'product']
STATUSES = {'reported_penny', 'verified_purchase', 'clearance_candidate'}


def valid_gtin(value):
    if len(value) not in (8, 12, 13, 14) or not value.isascii() or not value.isdigit():
        return False
    body, check = value[:-1], int(value[-1])
    weighted = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(body)))
    return (10 - weighted % 10) % 10 == check


def main():
    records = {}
    files = sorted((ROOT / 'approved').glob('*.csv'))
    if not files:
        raise ValueError('No CSVs in approved/; leaving existing feed unchanged')
    for path in files:
        with path.open(newline='', encoding='utf-8-sig') as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
                raise ValueError(f'{path.name}: missing required columns {FIELDS}')
            for line, row in enumerate(reader, 2):
                try:
                    if None in row or any(row.get(k) is None for k in FIELDS):
                        raise ValueError('Malformed row')
                    item = {k: row[k].strip() for k in FIELDS}
                    if not valid_gtin(item['upc']):
                        raise ValueError('Invalid UPC check digit')
                    if not item['retailer'] or not item['product'] or not item['source']:
                        raise ValueError('Retailer, product and source are required')
                    if item['status'] not in STATUSES:
                        raise ValueError('Unsupported status')
                    date = dt.date.fromisoformat(item['date'])
                    amount = Decimal(item['price'])
                    if not amount.is_finite() or not (Decimal('0') <= amount <= Decimal('100000')):
                        raise ValueError('Invalid price')
                    item['price'] = f'{amount:.2f}'
                    if any(len(v) > 300 for v in item.values()):
                        raise ValueError('Value too long')
                    key = (item['retailer'].lower(), item['upc'], item['source'].lower())
                    if key not in records or date >= dt.date.fromisoformat(records[key]['date']):
                        records[key] = item
                except (ValueError, InvalidOperation) as exc:
                    raise ValueError(f'{path.name}:{line}: {exc}') from exc
    if not records or len(records) > 5000:
        raise ValueError('Invalid record count; existing feed retained')
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(sorted(records.values(), key=lambda r: (r['retailer'], r['upc'], r['source'])))
    payload = output.getvalue()
    if len(payload.encode('utf-8')) > 2_000_000:
        raise ValueError('Feed too large; existing feed retained')
    (ROOT / 'penny-reports.csv').write_text(payload, encoding='utf-8', newline='')
    print(f'Validated and built {len(records)} reports from {len(files)} input file(s)')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Update aborted: {exc}', file=sys.stderr)
        sys.exit(1)
