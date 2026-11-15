def scale(amount, servings_from, servings_to):
    """An ingredient amount for another number of servings."""
    if servings_from <= 0:
        raise ValueError("servings_from must be positive")
    return amount * servings_to / servings_from
