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


def radio_horizon(i):
    return 4.12 * math.sqrt(i['antenna1_m']) + 4.12 * math.sqrt(i['antenna2_m'])


def slant_range_wgs84(i):
    """Independent meridian/longitude chord identity, without ECEF coordinates."""
    a = 6378137.0
    flattening = 1 / 298.257223563
    eccentricity_squared = 2 * flattening - flattening * flattening
    latitude1, latitude2 = math.radians(i['lat1_deg']), math.radians(i['lat2_deg'])
    longitude_delta = math.radians(i['lon2_deg'] - i['lon1_deg'])
    radii = [a / math.sqrt(1 - eccentricity_squared * math.sin(latitude) ** 2)
             for latitude in (latitude1, latitude2)]
    heights = [i['ground1_m'] + i['antenna1_m'], i['ground2_m'] + i['antenna2_m']]
    radial = [(radius + height) * math.cos(latitude)
              for radius, height, latitude in zip(radii, heights, (latitude1, latitude2))]
    polar = [(radius * (1 - eccentricity_squared) + height) * math.sin(latitude)
             for radius, height, latitude in zip(radii, heights, (latitude1, latitude2))]
    horizontal_sq = (radial[1] - radial[0]) ** 2 + 4 * radial[0] * radial[1] * math.sin(longitude_delta / 2) ** 2
    return math.sqrt(horizontal_sq + (polar[1] - polar[0]) ** 2) / 1000


def fresnel_radius(i):
    a, b = i['d1_km'] * 1000, i['d2_km'] * 1000
    return math.sqrt(C / (i['frequency_ghz'] * 1e9) * a * b / (a + b))


def knife_edge_nu(i):
    h = i['obstacle_height_m']
    angle = h / (i['d1_km'] * 1000) + h / (i['d2_km'] * 1000)
    return math.copysign(math.sqrt(2 * h * angle * i['frequency_ghz'] * 1e9 / C), h)


def knife_edge_loss(i):
    # Independent algebraic form of the registered approximation.
    return 6.9 + 20 / math.log(10) * math.asinh(i['knife_edge_nu'] - 0.1)


def sea_reflection_two_ray(i):
    # Solve equal grazing angles on the parabolic Earth, rather than the card's
    # P.530 trigonometric closed form. No registered expression/tool is used.
    d = i['distance_km'] * 1000
    h1, h2 = i['height1_above_sea_m'], i['height2_above_sea_m']
    radius = 6375000 * i['k_factor']
    lo, hi = 0.0, d
    for _ in range(100):
        x = (lo + hi) / 2
        balance = h1 * (d - x) - h2 * x + x * (d - x) * (d - 2*x) / (2*radius)
        if balance > 0:
            lo = x
        else:
            hi = x
    x = (lo + hi) / 2
    # The published corrected-height coefficient uses 6370 km (12.74).
    corrected_radius = 6370000 * i['k_factor']
    a, b = h1 - x*x/(2*corrected_radius), h2 - (d-x)**2/(2*corrected_radius)
    if a <= 0 or b <= 0:
        raise ValueError('outside line of sight')
    phase = 2 * a * b / d * i['frequency_ghz'] / 0.3
    amplitude = 2 * abs(math.sin(math.pi * phase))
    if amplitude < 0.1:
        raise ValueError('near interference null')
    return -20 * math.log10(amplitude)


REFERENCE = {'fresnel_radius': (fresnel_radius, 0), 'knife_edge_nu': (knife_edge_nu, 1e-9),
             'knife_edge_loss': (knife_edge_loss, 1e-9), 'sea_reflection_two_ray': (sea_reflection_two_ray, 1e-5),
             'fspl_ghz': (fspl_ghz, 0.05), 'received_power': (received_power, 1e-9),
             'link_margin': (link_margin, 1e-9), 'radio_horizon': (radio_horizon, 1e-9),
             'slant_range_wgs84': (slant_range_wgs84, 1e-6)}


def agrees(tool_id, inputs, value):
    if tool_id not in REFERENCE:
        return False
    fn, tolerance = REFERENCE[tool_id]
    try:
        if tool_id == 'fresnel_radius':
            return math.isclose(fn(inputs), value, rel_tol=0.001)
        return abs(fn(inputs) - value) <= tolerance
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
