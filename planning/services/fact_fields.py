"""Parameters that only the fact store supplies: each link end's position and antenna height.

They are the inputs of slant_range_wgs84 and radio_horizon. They have no text labels on
purpose: the rule parser never reads them from prose, so a site record or a value the user
types for that field is their only source.
"""
from formula_rag.parsing import FIELDS

END = {1: '发射端', 2: '接收端'}
# Site position key -> parameter pattern, label, unit.
POSITION = (('lat', 'lat{}_deg', '纬度', 'deg'), ('lon', 'lon{}_deg', '经度', 'deg'),
            ('ground_m', 'ground{}_m', '地面高程', 'm'), ('antenna_m', 'antenna{}_m', '天线离地高度', 'm'))
FACT_FIELDS = {pattern.format(end): (END[end] + name, unit) for end in (1, 2) for _, pattern, name, unit in POSITION}


def field_label(field):
    return FACT_FIELDS[field][0] if field in FACT_FIELDS else FIELDS[field][0]


def field_unit(field):
    return FACT_FIELDS[field][1] if field in FACT_FIELDS else FIELDS[field][1]
