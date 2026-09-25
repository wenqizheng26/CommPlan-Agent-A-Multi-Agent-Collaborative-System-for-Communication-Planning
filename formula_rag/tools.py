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


TOOLS = {'slant_range_wgs84': slant_range_wgs84}
