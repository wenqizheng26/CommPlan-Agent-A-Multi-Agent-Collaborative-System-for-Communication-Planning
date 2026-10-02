"""Explicit assumptions for the optional cross-sea supplement plans."""

def missing_conditions(order, conditions):
    required = set()
    if 'knife_edge_loss' in order:
        required.add('single_knife_edge')
    if 'sea_reflection_two_ray' in order:
        required.add('smooth_sea')
    return sorted(required - set(conditions))
