def total(lines, tax_rate):
    """The total of (quantity, unit price) lines, with tax."""
    net = sum(q * p for q, p in lines)
    return round(net * (1 + tax_rate), 2)
