from dataclasses import dataclass

def alert_level(water_level: float, alert_level_1: float, alert_level_2: float, alert_level_3: float) -> int:
    if water_level >= alert_level_1: return 1
    if water_level >= alert_level_2: return 2
    if water_level >= alert_level_3: return 3
    return 0

def rain_class(rain_mm: float) -> int:
    '''
    Classifies the rain intensity based on mm per hour.
    Returns:
        int: 0 for light rain, 1 for moderate rain, 2 for heavy rain.
    '''
    if rain_mm < 20: return 0
    if rain_mm > 20 and rain_mm < 50: return 1
    if rain_mm >= 50: return 2
    return 0

def delta_h_class(delta_h: float) -> int:
    '''
    Classifies the delta_h value.
    Returns:
        int: 0 for low, 1 for medium, 2 for high.
    '''
    if delta_h <= 0: return 0
    if delta_h > 0 and delta_h < 0.2: return 1
    if delta_h >= 0.2: return 2
    return 0

'''Base decision table with risk = table[delta_h_class][rain_class]'''
BASE_DECISION_TABLE = [
    [0.0, 0.3, 0.6],
    [0.4, 0.6, 0.8],
    [0.8, 0.9, 1.0],
]
'''Alert floor for minimum flood probability for each alert level alert_floor = table[alert_level][rain_class]
    This alert floor is created by team so not ensuring that the flood probability is not below a certain threshold for each alert level.
'''
ALERT_FLOOR = [
    [0.0, 0.0, 0.0],
    [0.2, 0.4, 0.6],
    [0.4, 0.6, 0.8],
    [0.6, 0.8, 1.0],
]

decay_factor = 0.5
  
def flood_probability(delta_h: float, rain_mm: float, alert) -> float:
    '''
    Calculates the flood probability based on delta_h and rain intensity.
    Returns:
        float: Flood probability between 0 and 1.
    '''
    base = BASE_DECISION_TABLE[delta_h_class(delta_h)][rain_class(rain_mm)]
    floor = ALERT_FLOOR[alert][rain_class(rain_mm)]
    return max(base, floor)

def apply_decay(flood_prob: float, dist_meters: float, threshold=5000) -> float:
    '''
    Applies a decay factor to the flood probability based on distance.
    '''
    if dist_meters > threshold:
        return flood_prob * decay_factor