# FT200 Run-Time Log Format

This document describes the run-time log files that the Flagtronics
FT200 in-car unit writes to its internal storage. It is written for
software integrators who collect these files and decode them in their
own tools.

| Item | Value |
| --- | --- |
| Document version | 1.0 (see `version.txt`) |
| Applies to | FT200 firmware 0.6.0.0 through 0.9.0.5 |
| Current log format | Version 6 |
| Reference decoder | [`ft200_log_decode.py`](ft200_log_decode.py) |

## Contents

1. [Collecting the logs](#1-collecting-the-logs)
2. [Data conventions](#2-data-conventions)
3. [File layout](#3-file-layout)
4. [File header](#4-file-header)
5. [Sample entries](#5-sample-entries)
6. [Field reference](#6-field-reference)
7. [Code tables](#7-code-tables)
8. [Timing](#8-timing)
9. [Impact records](#9-impact-records)
10. [Parsing procedure](#10-parsing-procedure)
11. [Format versions](#11-format-versions)
12. [Known limitations](#12-known-limitations)

## 1. Collecting the logs

### 1.1 When the unit logs

- The unit records one sample every 500 ms while it is powered and
  running.
- Logging starts at power-on only when the unit has no USB data
  connection. A unit powered from a PC for its whole session records
  nothing. Power it from the car harness, a battery, or a USB charger
  with no data connection.
- Logging pauses while the unit receives a track map over the air.
  No samples are written during the pause (see
  [8.4 Gaps](#84-gaps)).

### 1.2 Reading the files

1. After the session, connect the unit to a PC with a USB data cable.
2. The unit appears on the PC as a USB drive.
3. Copy the `logs` folder from the drive to the PC.

The drive root also holds `readme.txt`, which lists the unit's
firmware, apploader, bootrom and hardware versions, serial number and
device IDs. Copy it with the logs so each data set records the unit it
came from.

### 1.3 File names

| Name | Written by |
| --- | --- |
| `logC<n>.bin` | A unit running as an in-car display (normal use) |
| `logS<n>.bin` | A unit running in signboard mode |
| `log_<n>.bin` | Default name, used only if no mode set a prefix |

- `<n>` is a decimal file index with no leading zeros, from 0 to
  9999. It counts up by one per file and wraps from 9999 to 0.
- Sort files by the `start_time` in each file header, or by index
  with the wrap in mind. Sorting by name alone puts `logC10.bin`
  before `logC9.bin` and puts files after a wrap first.
- Every file is 65,535 bytes long, whatever it holds. The unused
  remainder is filled with `0xFF`.

### 1.4 Retention

The unit keeps the `logs` folder to about half of its 15.5 MiB
storage. When a new file would exceed that, the unit deletes the
oldest files first. A file with the version 6 in-car field set holds
about 12 minutes of samples, so the folder holds roughly the last
24 hours of run time (computed from the 64 KiB file size and the
45-byte sample entry). Collect logs before they roll off.

### 1.5 Clean shutdown and power loss

The unit buffers data in RAM and writes to storage in 4 KiB blocks.

| How the session ended | What the file contains |
| --- | --- |
| Power button held, low-battery shutdown, or a firmware update | All samples, then the file footer |
| Power lost without a shutdown | Samples up to the last 4 KiB block written; the final block (up to about 45 s) is lost and there is no footer |
| File filled up | All samples, then the file footer; logging continues in the next file |

A parser must accept files with no footer.

## 2. Data conventions

- All multi-byte values are little-endian.
- Structures are packed with no padding.
- `float32` is IEEE 754 single precision.
- Signed integers are two's complement.
- Byte strings in this document are written in file order, for
  example `54 E9`.

## 3. File layout

```text
+---------------------------+
| File header      37 bytes |  Section 4
+---------------------------+
| Record                    |  Sample entry (section 5) or
| Record                    |  impact record (section 9),
| ...                       |  in the order they were written
+---------------------------+
| File footer       8 bytes |  FE ED 00 0B AD C0 FF EE (may be absent)
+---------------------------+
| 0xFF fill to 65,535 bytes |
+---------------------------+
```

The file footer marks a point where the unit closed the file. On a
clean stop the unit writes it twice in a row. Treat a footer as a
marker, skip it, and keep reading. The end of the data is the first
byte that does not start a valid record (section 10).

## 4. File header

| Offset | Size | Type | Name | Description |
| --- | --- | --- | --- | --- |
| 0 | 8 | bytes | magic | `FE ED 0F FB AD C0 FF EE` |
| 8 | 8 | uint64 | start_time | Time the file was created, in ms. Meaning depends on firmware (section 8.1) |
| 16 | 1 | uint8 | version | Log format version (section 11) |
| 17 | 4 | uint32 | device_id | Device ID of the unit |
| 21 | 4 | uint8[4] | bootrom_version | Bootrom version, bytes in order `a.b.c.d` |
| 25 | 4 | uint8[4] | apploader_version | Apploader version, `a.b.c.d` |
| 29 | 4 | uint8[4] | firmware_version | Firmware version, `a.b.c.d` |
| 33 | 2 | uint16 | sample_period_ms | Time between samples. 500 in all released firmware |
| 35 | 2 | uint16 | timestamp_every | A sample carries an explicit timestamp once every this many samples. 120 in all released firmware |

Notes:

- The layout above applies to versions 4, 5 and 6.
- In signboard mode, `device_id` is the signboard ID listed in
  `readme.txt`, not the in-car device ID.
- Firmware bytes `00 09 00 05` mean firmware 0.9.0.5.

## 5. Sample entries

Each sample entry holds the values captured at one 500 ms tick.

```text
+-------+-------+----------------------------+-------+
| 54 E9 | mask  | field values, in bit order | 90 C4 |
+-------+-------+----------------------------+-------+
  2 B     2 B     variable                     2 B
```

- `54 E9` is the entry header and `90 C4` is the entry footer. Both
  are present in versions 5 and 6 only.
- `mask` is a uint16. Bit 15 (`0x8000`) is always set in a sample
  entry. Each other set bit means the matching field is present.
- Present fields follow the mask in ascending bit order, from bit 0
  up. Absent fields take no space.
- Each field has a fixed size (section 6), so the entry length is
  known from the mask alone.
- Bit 0 (timestamp) is set on one entry in every `timestamp_every`
  entries. All other bits are fixed by the unit's mode and do not
  change within a file.

Field sets used by released firmware:

| Mode | File prefix | Mask without timestamp | Mask with timestamp | Entry size |
| --- | --- | --- | --- | --- |
| In-car | `logC` | `0xBFFE` | `0xBFFF` | 45 / 53 bytes |
| Signboard | `logS` | `0xC73C` | `0xC73D` | 19 / 27 bytes |

## 6. Field reference

Version 6 layout. Versions 4 and 5 differ at bits 6 and 7 only
(section 11).

| Bit | Mask | Bytes | Layout | Field | Unit | In-car | Signboard |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `0x0001` | 8 | uint64 | Timestamp | ms since 00:00 UTC | ✓ | ✓ |
| 1 | `0x0002` | 9 | float32 lat, float32 lon, uint8 speed | GPS position and speed | degrees, degrees, mph | ✓ | |
| 2 | `0x0004` | 1 | uint8 | Timing zone | zone number | ✓ | ✓ |
| 3 | `0x0008` | 4 | int16 rssi, int16 snr | Radio signal of last received packet | dB magnitude, dB | ✓ | ✓ |
| 4 | `0x0010` | 1 | uint8 | Global flag state | code | ✓ | ✓ |
| 5 | `0x0020` | 1 | uint8 | Individual flag state | code | ✓ | ✓ |
| 6 | `0x0040` | 4 | uint16 external, uint16 backup | Supply voltages | mV | ✓ | |
| 7 | `0x0080` | 5 | int32 level, uint8 output | Display brightness | level, 0 to 255 | ✓ | |
| 8 | `0x0100` | 1 | int8 | Unit temperature | °C | ✓ | ✓ |
| 9 | `0x0200` | 2 | uint16 | Ambient light | lux | ✓ | ✓ |
| 10 | `0x0400` | 1 | uint8 | Command counter | count | ✓ | ✓ |
| 11 | `0x0800` | 1 | uint8 | Buttons | bit mask | ✓ | |
| 12 | `0x1000` | 6 | int16 x, y, z | Motion accelerometer | mG | ✓ | |
| 13 | `0x2000` | 3 | int8 x, y, z | High-G accelerometer | G | ✓ | |
| 14 | `0x4000` | 2 | uint8 code, uint8 type | Flag on the display | code, type | | ✓ |
| 15 | `0x8000` | 0 | | Sample entry marker | | ✓ | ✓ |

### 6.1 Timestamp

Time of day in milliseconds since 00:00 UTC, from 0 to 86,399,999.
See section 8 for how to time the entries that do not carry one.

### 6.2 GPS position and speed

- Latitude and longitude are WGS 84 decimal degrees, north and east
  positive. `float32` resolves about 1 m at these magnitudes.
- The values are from the last GPS fix the unit accepted. When the
  fix is lost, the last good position repeats.
- Speed is whole miles per hour from GPS ground speed.

### 6.3 Timing zone

The number of the timing zone the unit is in, as defined by the track
map loaded on the unit.

### 6.4 Radio signal

- `rssi` is the received signal strength of the last radio packet,
  stored as a positive magnitude. Negate it for dBm, so a stored 85 means
  -85 dBm.
- `snr` is the signal-to-noise ratio of the same packet in dB. It can
  be negative.
- Both hold their value until the next packet arrives.

### 6.5 Supply voltages

`external` is the voltage at the external power input. `backup` is the
backup battery voltage. Both in millivolts.

### 6.6 Display brightness

- `level` is the brightness step the driver selected with the
  buttons, from 1 up to the number of steps in the unit's light curve.
- `output` is the display drive level from 0 to 255 that the light
  curve produced for the current ambient light and `level`.

### 6.7 Unit temperature

Thermistor temperature rounded to the nearest whole degree Celsius.
Values below 0 °C are recorded wrong (section 12).

### 6.8 Ambient light

Averaged photo sensor reading in lux, used for automatic dimming.

### 6.9 Command counter

The low 8 bits of the command sequence counter in the most recent
command received from race control. A change shows that a new command
arrived.

### 6.10 Buttons

| Bit | Meaning when set |
| --- | --- |
| 0 | Button 1 pressed |
| 1 | Button 2 pressed |

### 6.11 Motion accelerometer

- Three int16 values, X then Y then Z, in milli-G (1000 = 1.000 G).
- Full scale is ±2 G on hardware before version 0.9.0 (LIS3DH sensor)
  and ±3 G on hardware 0.9.0 and later (BMI088 sensor). Values clip
  at full scale. The hardware version is in `readme.txt`.
- Axes, with the display upright and facing the viewer: +X to the
  viewer's left, +Y down, +Z toward the viewer. At rest Y reads about
  -1000.
- In a car with the unit facing the driver, a left-hand corner reads
  positive X and a right-hand corner negative X. Mount tilt adds a
  constant offset to X; measure it as the median X at low speed and
  subtract it.
- Each value is the most recent raw reading at the sample tick, with
  no filtering, averaging or peak hold. Single samples carry 0.2 to
  0.6 G of bump and kerb content on track. Average about 5 samples
  (2.5 s) before reading cornering loads.

### 6.12 High-G accelerometer

- Three int8 values, X then Y then Z, in whole G, from a ±100 G
  sensor. Resolution is 1 G, so this field reads near 0 in normal
  driving.
- X is side to side, Y top to bottom, Z front to back.
- Detailed impact data at 500 Hz is in impact records (section 9).

### 6.13 Flag on the display

Byte 0 is the code of what the display is showing. Byte 1 is the type,
which selects the table that byte 0 is read from (section 7.4).

## 7. Code tables

### 7.1 Global flag state

Byte values are ASCII characters.

| Value | Char | Meaning |
| --- | --- | --- |
| 0 | | No flag state |
| 66 | `B` | Blank |
| 67 | `C` | Code 35 |
| 68 | `D` | Black |
| 71 | `G` | Green |
| 72 | `H` | Checkered |
| 80 | `P` | Pits |
| 82 | `R` | Red |
| 91 | `[` | Full-course yellow |
| 94 | `^` | White |
| 255 | | Invalid |

### 7.2 Individual flag state

| Value | Meaning |
| --- | --- |
| 0 | None |
| 1 | Black flag |
| 2 | Meatball flag |
| 3 | Pit |
| 4 | Stalled |
| 75 | Accident alert, 10 G level |
| 76 | Accident alert, 25 G level |
| 77 | Accident alert, 50 G level |
| 78 | Accident alert, 75 G level |
| 79 | Accident alert, 100 G level |
| 89 | No individual flag; the unit is in a local yellow zone (`Y`) |
| 93 | No individual flag; the unit is in a local debris zone (`]`) |

### 7.3 Local zone flags

Used by the display field when its type is 2 (local). Values combine
bits: 1 yellow, 2 waving yellow, 4 debris, 8 white.

| Value | Meaning |
| --- | --- |
| 0 | None |
| 1 | Yellow |
| 2 | Waving yellow |
| 4 | Debris |
| 5 | Yellow and debris |
| 6 | Waving yellow and debris |
| 8 | White |
| 9 | Yellow and white |
| 10 | Waving yellow and white |
| 12 | Debris and white |
| 13 | Yellow, debris and white |
| 14 | Waving yellow, debris and white |
| 16 | Blue |
| 25 | Green |
| 26 | Checkered |
| 27 | Pit open |
| 28 | Pit closed |

### 7.4 Display type and code

| Type | Meaning | Read the code from |
| --- | --- | --- |
| 0 | Undefined | Code is 0 |
| 1 | Global flag | Table 7.1 |
| 2 | Local flag | Table 7.3 |
| 3 | Individual flag | Table 7.2 |
| 4 | Message | Table 7.5 |

### 7.5 Display messages

| Code | Message |
| --- | --- |
| 0 | None |
| 1 | Low battery |
| 2 | Bad power supply |
| 3 | High temperature |
| 4 | Firmware update required |
| 14 | Pit timer |
| 16 | `SLO`, speeding in the pits |
| 17 | `35`, Code 35 at or under the limit |
| 18 | `35` / `SLO`, Code 35 over the low limit |
| 19 | `SLO`, Code 35 over the high limit |
| 32 | No radio signal |
| 33 | Radio signal but no command received |

## 8. Timing

### 8.1 File start time

The meaning of `start_time` in the header depends on the firmware
version in the same header:

| Firmware | `start_time` holds |
| --- | --- |
| 0.9.0.0 and later | UTC Unix time in ms, when the unit had a GPS time fix at file creation |
| 0.9.0.0 and later, no GPS time yet | Milliseconds since power-on |
| Before 0.9.0.0 | Milliseconds since 00:00 UTC |

On 0.9.0.0 and later, a `start_time` below 946,684,800,000
(2000-01-01) means the unit had no GPS time when it created the file.
The unit sets its clock from GPS once it has at least 4 satellites,
horizontal accuracy of 15 m or better and HDOP of 5 or less.

### 8.2 Sample times

1. An entry with bit 0 set carries its own time of day.
2. Each following entry is `sample_period_ms` later than the one
   before it.
3. Entries before the first timestamp in a file are timed backward
   from it. The timestamp counter runs across files, so a file
   usually starts partway through a 120-entry cycle.
4. Re-anchor on every explicit timestamp. Do not carry a count across
   one.

### 8.3 Date and midnight

Entry timestamps are time of day only and wrap from 86,399,999 to 0
at midnight UTC. To build full UTC times on firmware 0.9.0.0 and
later:

1. Take the date of `start_time` (when it is a Unix time) as the date
   of the first entry.
2. Add one day each time the time of day drops by more than 12 hours
   from one entry to the next.

Before 0.9.0.0 the files carry no date. Take it from the session
records.

### 8.4 Gaps

The unit can skip samples, for example while it receives a track map
over the air. A skipped sample leaves no entry, so counting periods
across a gap places later entries too early until the next explicit
timestamp. Detect a gap by comparing each explicit timestamp with the
time counted from the previous one; any difference beyond a few
milliseconds is a gap. Explicit timestamps 120 entries apart normally
differ by 60,000 to 60,002 ms.

The unit's clock is also corrected from GPS while it runs. A
correction of more than 1 s shows as a step in the explicit
timestamps.

## 9. Impact records

When the high-G sensor measures more than 10 G in the horizontal
plane (X and Z combined) for long enough to pass the unit's glitch
filter, the unit saves the high-G data from 3 s before the event to
3 s after it. The data is written as one or more impact records,
placed between sample entries.

### 9.1 Impact record header

| Offset | Size | Type | Name | Description |
| --- | --- | --- | --- | --- |
| 0 | 8 | bytes | magic | `BE EF DE AF 12 34 56 78` |
| 8 | 4 | uint32 | size | Bytes of impact data that follow. Always a multiple of 6 |
| 12 | 8 | uint64 | written_time | Time the record was written, in ms (see below) |
| 20 | 2 | uint16 | rate_hz | Sample rate of the impact data. 500 in all released firmware |

The impact data follows the header directly: `size / 6` samples,
each three int16 values X, Y, Z in units of 0.1 G (100 mG). Axes are
as in section 6.12.

```text
+--------+--------+--------+
| X int16| Y int16| Z int16|  sample 1
+--------+--------+--------+
| X int16| Y int16| Z int16|  sample 2
+--------+--------+--------+
| ...                      |  sample size / 6
+--------+--------+--------+
```

### 9.2 Reading impact records

- `written_time` is when the unit wrote the record, which is after
  the last sample in it was captured. On firmware 0.9.0.0 and later
  it is milliseconds since 00:00 UTC. Before 0.9.0.0 it is
  milliseconds since power-on.
- One event usually produces two or more consecutive impact records.
  Their samples are continuous. Join them in file order to rebuild
  the event.
- When an impact record does not fit in the current file, the unit
  closes that file and starts the record at the beginning of the next
  file, right after the header.
- Sample entries continue around impact records at the normal
  500 ms rate.

## 10. Parsing procedure

1. Read the whole file. Check that bytes 0 to 7 are the file magic.
2. Read the header (section 4). Stop if the version is not one you
   support.
3. Set the read position to byte 37.
4. Loop:
   1. If the next 8 bytes are the file footer, skip 8 bytes and
      continue.
   2. If the next 8 bytes are the impact magic, read the impact
      record (section 9). Stop if `size` runs past the end of the
      file or is not a multiple of 6.
   3. Otherwise read a sample entry (section 5). Stop if the entry
      header is wrong (versions 5 and 6), bit 15 of the mask is
      clear, the entry runs past the end of the file, or the entry
      footer is wrong (versions 5 and 6).
5. The position where the loop stopped is the end of the data. In a
   complete file it is the start of the `0xFF` fill.

Do not stop at the first file footer. Do not treat leftover bytes
after the stop point as data.

## 11. Format versions

| Version | First firmware | Change |
| --- | --- | --- |
| 4 | 0.6.0.0 | Header adds device ID and bootrom, apploader and firmware versions (the layout in section 4) |
| 5 | 0.6.1.1 | Sample entries framed with `54 E9` and `90 C4` |
| 6 | 0.7.0.14 | Bits 6 and 7 redefined (below) |

Bits 6 and 7 in versions 4 and 5:

| Bit | Mask | Bytes | Layout | Field |
| --- | --- | --- | --- | --- |
| 6 | `0x0040` | 2 | uint16 | External supply voltage, mV |
| 7 | `0x0080` | 2 | uint16 | Backup battery voltage, mV |

Version 6 moved both voltages under bit 6 and gave bit 7 to display
brightness. All other bits are the same in versions 4, 5 and 6.

Firmware 0.9.0.0 changed the time base of `start_time` and of the
impact `written_time` without changing the format version (section
8.1 and 9.2). Use the firmware version in the header to choose.

Versions 1 to 3 were used only by firmware before 0.6.0.0 and are
not covered here.

## 12. Known limitations

These apply to firmware up to and including 0.9.0.5.

- Temperature below 0 °C is recorded wrong. For example -1 °C records
  as 54 and -5 °C as 50. Treat temperature values as unreliable when
  the unit may have been below freezing.
- Speed is stored in one byte. Speeds above 255 mph do not record
  correctly.
- A power cut without a clean shutdown loses up to the last 4 KiB of
  the open file (section 1.5).
- Samples skipped during an over-the-air track map transfer leave no
  entry (section 8.4).

## Reference decoder

[`ft200_log_decode.py`](ft200_log_decode.py) implements this document
for versions 4, 5 and 6. It needs Python 3.8 or later and no extra
packages.

```bash
python ft200_log_decode.py logC117.bin logC118.bin --out decoded
```

For each input it writes `<name>_samples.csv`, one row per sample
entry with UTC time where the file allows it, and `<name>_impacts.csv`
when the file holds impact records. RSSI is written as negative dBm
and impact data in G.
