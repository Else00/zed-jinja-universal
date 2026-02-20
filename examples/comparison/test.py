# === PURE PYTHON (no jinja) ===
def calculate_sum(numbers: list[int]) -> int:
    """Calculate the sum of a list of numbers."""
    total = 0
    for num in numbers:
        if num > 0:
            total += num
    return total


class Calculator:
    def __init__(self, name: str):
        self.name = name
        self.history = []

    def add(self, a: float, b: float) -> float:
        result = a + b
        self.history.append(result)
        return result
