"""Independent reimplementations of plan-capable cards, used only to check results.

They deliberately do not evaluate the card expression. Published values always come
from the registered card; a mismatch beyond tolerance fails validation.
"""
import math

C = 299792458


def fspl_ghz(i):
    # Exact 4*pi*d*f/c; the registered P.525 card rounds its constant (~0.048 dB).
    return 20 * (math.log10(i['frequency_ghz']) + math.log10(i['distance_km']) + 12 + math.log10(4 * math.pi / C))


def received_power(i):
    gains = i['tx_power_dbm'] + i['tx_gain_dbi'] + i['rx_gain_dbi']
    losses = i['tx_loss_db'] + i['rx_loss_db'] + i['path_loss_db'] + i['extra_loss_db']
    return gains - losses


def link_margin(i):
    return i['rx_power_dbm'] - i['rx_threshold_dbm'] - i['reserve_db']


REFERENCE = {'fspl_ghz': (fspl_ghz, 0.05), 'received_power': (received_power, 1e-9), 'link_margin': (link_margin, 1e-9)}


def agrees(tool_id, inputs, value):
    if tool_id not in REFERENCE:
        return False
    fn, tolerance = REFERENCE[tool_id]
    try:
        return abs(fn(inputs) - value) <= tolerance
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
