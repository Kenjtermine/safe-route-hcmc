def alert_level(water_level: float, alert_level_1: float, alert_level_2: float, alert_level_3: float) -> int:
    """Map a water level to the highest crossed alert threshold (0..3)."""
    if water_level >= alert_level_3: return 3
    if water_level >= alert_level_2: return 2
    if water_level >= alert_level_1: return 1
    return 0

def rain_class(rain_mm: float) -> int:
    '''
    Phân loại lượng mưa thành các mức cảnh báo.
    Returns:
        int: 0 for mưa nhỏ, 1 for mưa vừa, 2 for mưa lớn.
    '''
    if rain_mm < 20: return 0
    if rain_mm < 50: return 1
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
    Phân bậc alert floor được xây dựng dựa trên dự đoán của team về khả năng ngập lụt dựa trên các mức cảnh báo và cường độ mưa
'''
ALERT_FLOOR = [
    [0.0, 0.0, 0.0],
    [0.2, 0.4, 0.6],
    [0.4, 0.6, 0.8],
    [0.6, 0.8, 1.0],
]

def flood_probability(delta_h: float, rain_mm: float, alert: int = 0,
                      use_alert_floor: bool = False) -> float:
    '''
    Tính toán xác suất ngập lụt dựa trên delta_h, lượng mưa và mức cảnh báo.
    Returns:
        float: Xác suất ngập lụt (từ 0.0 đến 1.0).
    '''
    base = BASE_DECISION_TABLE[delta_h_class(delta_h)][rain_class(rain_mm)]
    if not use_alert_floor:
        return base
    if not isinstance(alert, int) or isinstance(alert, bool) or not 0 <= alert <= 3:
        raise ValueError("alert phải là số nguyên từ 0 đến 3")
    floor = ALERT_FLOOR[alert][rain_class(rain_mm)]
    return max(base, floor)

def decay_factor(dist_meters: float) -> float:
    """Distance confidence: 1 through 5 km, then decreases to a 0.2 floor."""
    if dist_meters < 0:
        raise ValueError("dist_meters không được âm")
    if dist_meters <= 5000:
        return 1.0
    return max(0.2, 5000.0 / dist_meters)

def apply_decay(flood_prob: float, dist_meters: float, threshold=5000) -> float:
    """Apply the documented distance decay (threshold retained for compatibility)."""
    factor = 1.0 if dist_meters <= threshold else max(0.2, threshold / dist_meters)
    return flood_prob * factor
