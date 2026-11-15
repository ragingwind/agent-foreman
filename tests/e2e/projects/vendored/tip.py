def split(total, people, tip_percent):
    """What each person pays, tip included, rounded up to the cent."""
    import math
    return math.ceil(total * (1 + tip_percent / 100) / people * 100) / 100
