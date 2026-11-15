def summary(readings):
    """The lowest, highest and mean reading."""
    if not readings:
        raise ValueError("no readings")
    return min(readings), max(readings), sum(readings) / len(readings)
