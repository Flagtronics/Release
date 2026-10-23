#!/usr/bin/env python3
"""Reference decoder for FT200 run-time log files (logC*.bin, logS*.bin).

Implements the format described in ft200-log-format.md in this folder.
Supports log versions 4, 5 and 6. Standard library only.

Usage:
    python ft200_log_decode.py <log.bin> [<log.bin> ...] [--out DIR]

For each input file this writes two CSV files to DIR (default: the
input file's folder):
    <name>_samples.csv   one row per sample entry
    <name>_impacts.csv   one row per high-G impact sample (if any)
"""
import argparse
import csv
import datetime
import os
import struct
import sys

FILE_HEADER = bytes.fromhex('FEED0FFBADC0FFEE')
FILE_FOOTER = bytes.fromhex('FEED000BADC0FFEE')
IMPACT_HEADER = bytes.fromhex('BEEFDEAF12345678')
ENTRY_HEADER = bytes.fromhex('54E9')
ENTRY_FOOTER = bytes.fromhex('90C4')

MS_PER_DAY = 86_400_000
UNIX_MS_2000 = 946_684_800_000   # below this, start_time is not a date

# (mask bit, struct format, column names), in the order fields are
# stored. Version 6 layout; versions 4 and 5 differ at 0x0040 and 0x0080.
FIELDS_V6 = [
    (0x0001, '<Q', ['timestamp_ms']),
    (0x0002, '<ffB', ['latitude', 'longitude', 'speed_mph']),
    (0x0004, '<B', ['zone']),
    (0x0008, '<hh', ['rssi_dbm', 'snr_db']),
    (0x0010, '<B', ['global_flag']),
    (0x0020, '<B', ['individual_flag']),
    (0x0040, '<HH', ['external_mv', 'backup_mv']),
    (0x0080, '<iB', ['brightness_level', 'brightness_output']),
    (0x0100, '<b', ['temperature_c']),
    (0x0200, '<H', ['ambient_lux']),
    (0x0400, '<B', ['command_counter']),
    (0x0800, '<B', ['buttons']),
    (0x1000, '<hhh', ['accel_x_mg', 'accel_y_mg', 'accel_z_mg']),
    (0x2000, '<bbb', ['highg_x_g', 'highg_y_g', 'highg_z_g']),
    (0x4000, '<BB', ['display_code', 'display_type']),
]
FIELDS_V4 = [f for f in FIELDS_V6 if f[0] not in (0x0040, 0x0080)]
FIELDS_V4.insert(6, (0x0040, '<H', ['external_mv']))
FIELDS_V4.insert(7, (0x0080, '<H', ['backup_mv']))

SEQUENCE_SAMPLE = 0x8000


class LogFormatError(Exception):
    pass


def parse_header(buf):
    """Return (header dict, offset of first record)."""
    if buf[:8] != FILE_HEADER:
        raise LogFormatError('missing file header')
    start_time, version = struct.unpack_from('<QB', buf, 8)
    if version not in (4, 5, 6):
        raise LogFormatError(f'log version {version} is not supported')
    did, br, al, fw, period, ts_every = struct.unpack_from(
        '<I4s4s4sHH', buf, 17)
    hdr = {
        'start_time': start_time,
        'version': version,
        'device_id': did,
        'bootrom_version': '.'.join(map(str, br)),
        'apploader_version': '.'.join(map(str, al)),
        'firmware_version': '.'.join(map(str, fw)),
        'firmware_tuple': tuple(fw),
        'sample_period_ms': period,
        'timestamp_every': ts_every,
    }
    return hdr, 8 + 29


def parse_records(buf, hdr, offset):
    """Yield ('sample', dict) and ('impact', dict) records in file order.

    Stops at the first byte that does not start a valid record, which is
    the 0xFF fill after the last record, or the end of the written data
    when the unit lost power before closing the file.
    """
    version = hdr['version']
    fields = FIELDS_V6 if version >= 6 else FIELDS_V4
    framed = version >= 5
    i = offset
    while i < len(buf):
        if buf[i:i + 8] == FILE_FOOTER:
            # A close marker; logging may resume after it in the same file
            i += 8
            continue
        if buf[i:i + 8] == IMPACT_HEADER:
            if i + 22 > len(buf):
                return
            size, written_ms, rate = struct.unpack_from('<IQH', buf, i + 8)
            data = buf[i + 22:i + 22 + size]
            if len(data) != size or size % 6:
                return
            yield 'impact', {
                'offset': i, 'written_ms': written_ms, 'rate_hz': rate,
                'samples': list(struct.iter_unpack('<hhh', data)),
            }
            i += 22 + size
            continue
        j = i
        if framed:
            if buf[j:j + 2] != ENTRY_HEADER:
                return
            j += 2
        if j + 2 > len(buf):
            return
        mask = struct.unpack_from('<H', buf, j)[0]
        if not mask & SEQUENCE_SAMPLE:
            return
        j += 2
        rec = {'offset': i, 'mask': mask}
        try:
            for bit, fmt, names in fields:
                if mask & bit:
                    rec.update(zip(names, struct.unpack_from(fmt, buf, j)))
                    j += struct.calcsize(fmt)
        except struct.error:
            return
        if framed:
            if buf[j:j + 2] != ENTRY_FOOTER:
                return
            j += 2
        yield 'sample', rec
        i = j


def start_is_date(hdr):
    """True when start_time holds UTC Unix milliseconds."""
    return (hdr['firmware_tuple'] >= (0, 9, 0, 0)
            and hdr['start_time'] >= UNIX_MS_2000)


def decode(path, out_dir):
    with open(path, 'rb') as f:
        buf = f.read()
    hdr, offset = parse_header(buf)
    base = os.path.splitext(os.path.basename(path))[0]

    samples, impacts = [], []
    for kind, rec in parse_records(buf, hdr, offset):
        if kind == 'impact':
            impacts.append(rec)
            continue
        if 'rssi_dbm' in rec:
            rec['rssi_dbm'] = -rec['rssi_dbm']   # stored as a magnitude
        samples.append(rec)

    # Time of day: count sample periods forward from each explicit
    # timestamp, and back from the first one for the samples before it
    period = hdr['sample_period_ms']
    t = None
    for rec in samples:
        if 'timestamp_ms' in rec:
            t = rec['timestamp_ms']
        elif t is not None:
            t = (t + period) % MS_PER_DAY
        rec['time_of_day_ms'] = t
    first = next((n for n, r in enumerate(samples)
                  if 'timestamp_ms' in r), None)
    if first is not None:
        t0 = samples[first]['timestamp_ms']
        for n in range(first):
            samples[n]['time_of_day_ms'] = (
                t0 - (first - n) * period) % MS_PER_DAY

    # UTC date: start from the day of the file start time, then add a day
    # each time the time of day passes midnight
    day = None
    if start_is_date(hdr) and samples and first is not None:
        start = hdr['start_time']
        day = start - start % MS_PER_DAY
        if samples[0]['time_of_day_ms'] < start % MS_PER_DAY - MS_PER_DAY // 2:
            day += MS_PER_DAY
    last = None
    for rec in samples:
        t = rec['time_of_day_ms']
        rec['utc'] = ''
        if day is None or t is None:
            continue
        if last is not None and t < last - MS_PER_DAY // 2:
            day += MS_PER_DAY
        last = t
        rec['utc'] = datetime.datetime.fromtimestamp(
            (day + t) / 1000, datetime.timezone.utc).isoformat()

    columns = ['offset', 'mask', 'utc', 'time_of_day_ms']
    columns += [n for _, _, names in
                (FIELDS_V6 if hdr['version'] >= 6 else FIELDS_V4)
                for n in names]
    sample_csv = os.path.join(out_dir, base + '_samples.csv')
    with open(sample_csv, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        w.writeheader()
        for rec in samples:
            w.writerow({k: ('' if rec.get(k) is None else rec.get(k, ''))
                        for k in columns})

    if impacts:
        impact_csv = os.path.join(out_dir, base + '_impacts.csv')
        with open(impact_csv, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['block', 'block_written_ms', 'rate_hz', 'index',
                        'x_g', 'y_g', 'z_g'])
            for n, blk in enumerate(impacts):
                for k, (x, y, z) in enumerate(blk['samples']):
                    w.writerow([n, blk['written_ms'], blk['rate_hz'], k,
                                x / 10, y / 10, z / 10])

    print(f"{path}: version {hdr['version']}, device {hdr['device_id']}, "
          f"firmware {hdr['firmware_version']}, start {hdr['start_time']}"
          f"{' (UTC date)' if start_is_date(hdr) else ''}, "
          f"{len(samples)} samples, {len(impacts)} impact blocks")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--out', help='output folder (default: beside input)')
    args = ap.parse_args()
    status = 0
    for path in args.files:
        out_dir = args.out or os.path.dirname(os.path.abspath(path))
        try:
            decode(path, out_dir)
        except (LogFormatError, OSError) as exc:
            print(f'{path}: {exc}', file=sys.stderr)
            status = 1
    return status


if __name__ == '__main__':
    sys.exit(main())
