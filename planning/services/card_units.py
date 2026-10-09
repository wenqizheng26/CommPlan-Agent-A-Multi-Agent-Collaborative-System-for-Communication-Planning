"""Explicit same-dimension scalar conversions for reviewed formula cards."""
import math
import re

# Logarithmic units are distinct dimensions; no power/log or temperature-offset guesses.
UNITS = {}
def _add(dimension, entries):
    for unit, scale in entries.items():
        UNITS[unit] = (dimension, scale)

_add('frequency', {'Hz':1, 'kHz':1e3, 'MHz':1e6, 'GHz':1e9,
                   '赫兹':1, '千赫兹':1e3, '兆赫兹':1e6, '吉赫兹':1e9})
_add('length', {'m':1, 'km':1e3, 'cm':.01, 'mm':.001, '米':1, '千米':1e3, '公里':1e3})
_add('speed', {'m/s':1, 'km/h':1/3.6, '米/秒':1, '千米/小时':1/3.6, '公里/小时':1/3.6})
_add('temperature', {'K':1, '开尔文':1})
_add('celsius', {'°C':1, '℃':1})
_add('time', {'s':1, 'ms':.001, 'us':1e-6, 'μs':1e-6, 'ns':1e-9, '秒':1})
_add('power', {'W':1, 'mW':.001, 'kW':1000, '瓦':1, '毫瓦':.001, '千瓦':1000})
_add('angle', {'deg':1, '°':1, '度':1, 'rad':180/math.pi})
_add('bit_rate', {'bit/s':1, 'bps':1, 'kbit/s':1e3, 'kbps':1e3,
                  'Mbit/s':1e6, 'Mbps':1e6, 'Gbit/s':1e9, 'Gbps':1e9})
for _unit in ('dB', 'dBm', 'dBW', 'dBi', 'dBm/Hz', 'dBW/Hz', 'dB-Hz', '1', '%', '1/s'):
    _add(_unit, {_unit:1})
UNIT_PATTERN = '|'.join(('(?<=\\s)' if u[0].isdigit() else '')+re.escape(u)
                        for u in sorted(UNITS, key=len, reverse=True))

def supported_unit(unit):
    return type(unit) is str and unit in UNITS

def convert_unit(value, unit, target):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('FINITE_NUMBER_REQUIRED')
    if unit not in UNITS or target not in UNITS or UNITS[unit][0] != UNITS[target][0]:
        raise ValueError('UNIT_MISMATCH')
    result = value * UNITS[unit][1] / UNITS[target][1]
    if not math.isfinite(result):
        raise ValueError('FINITE_NUMBER_REQUIRED')
    return result
