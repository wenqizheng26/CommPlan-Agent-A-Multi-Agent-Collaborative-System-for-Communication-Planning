"""Whitelisted deterministic formula tools; catalog text cannot name arbitrary code."""
import math


WGS84_A_M = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def geodetic_to_ecef(lat_deg, lon_deg, height_m):
    """WGS84 geodetic latitude, longitude and ellipsoidal height to ECEF metres."""
    latitude = math.radians(lat_deg)
    longitude = math.radians(lon_deg)
    sin_lat = math.sin(latitude)
    cos_lat = math.cos(latitude)
    prime_vertical = WGS84_A_M / math.sqrt(1 - WGS84_E2 * sin_lat * sin_lat)
    x = (prime_vertical + height_m) * cos_lat * math.cos(longitude)
    y = (prime_vertical + height_m) * cos_lat * math.sin(longitude)
    z = (prime_vertical * (1 - WGS84_E2) + height_m) * sin_lat
    return x, y, z


def slant_range_wgs84(inputs):
    """Straight antenna-to-antenna chord in km; heights are WGS84 ellipsoid metres."""
    first = geodetic_to_ecef(inputs['lat1_deg'], inputs['lon1_deg'],
                             inputs['ground1_m'] + inputs['antenna1_m'])
    second = geodetic_to_ecef(inputs['lat2_deg'], inputs['lon2_deg'],
                              inputs['ground2_m'] + inputs['antenna2_m'])
    return math.dist(first, second) / 1000


def sea_reflection_two_ray(inputs):
    """P.530-19 spherical-Earth two-ray loss, for a visible smooth reflection."""
    names = ('frequency_ghz', 'distance_km', 'height1_above_sea_m',
             'height2_above_sea_m', 'k_factor')
    try:
        f, d, h1, h2, k = (inputs[name] for name in names)
        if any(isinstance(x, bool) or not math.isfinite(x) or x <= 0
               for x in (f, d, h1, h2, k)):
            raise ValueError('all inputs must be finite and positive')
        m = d * d * 1000 / (4 * k * 6375 * (h1 + h2))
        c = (h1 - h2) / (h1 + h2)
        arg = (3 * c / 2) * math.sqrt(3 * m / (m + 1)**3)
        # Clamp only roundoff at the analytic arccos domain boundary.
        b = 2 * math.sqrt((m + 1) / (3 * m)) * math.cos(
            math.pi / 3 + math.acos(max(-1.0, min(1.0, arg))) / 3)
        d1, d2 = d * (1 + b) / 2, d * (1 - b) / 2
        hp1, hp2 = h1 - d1 * d1 / (12.74 * k), h2 - d2 * d2 / (12.74 * k)
        if not (0 < d1 < d and 0 < d2 < d and hp1 > 0 and hp2 > 0):
            raise ValueError('reflection point is outside antenna line of sight')
        tau = (2 * f / 0.3) * hp1 * hp2 * 0.001 / d
        amplitude = 2 * abs(math.sin(math.pi * tau))
        if amplitude < 0.1:
            raise ValueError('near an interference null (loss > 20 dB)')
        result = -20 * math.log10(amplitude)
        if not math.isfinite(result):
            raise ValueError('nonfinite reflection loss')
        return result
    except (KeyError, TypeError, ArithmeticError) as exc:
        raise ValueError('invalid two-ray parameters') from exc


TOOLS = {'slant_range_wgs84': slant_range_wgs84,
         'sea_reflection_two_ray': sea_reflection_two_ray}
