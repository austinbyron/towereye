"""Which die is on the tray: the selection shared by the hub, the readers,
and the template harvest. `auto` = every calibrated pool competes."""
import threading

AUTO = "auto"
FACES = {"d4": 4, "d6": 6, "d8": 8, "d10": 10, "d12": 12, "d20": 20}


def normalize(die) -> str | None:
    """Canonical die name ('d8', 'auto') or None for anything unknown."""
    if not isinstance(die, str):
        return None
    die = die.strip().lower()
    if die == AUTO or die in FACES:
        return die
    return None


class DieSelection:
    def __init__(self, die: str = AUTO):
        self._lock = threading.Lock()
        self._die = normalize(die) or AUTO

    @property
    def die(self) -> str:
        with self._lock:
            return self._die

    @property
    def faces(self) -> int | None:
        return FACES.get(self.die)

    def set(self, die) -> bool:
        """Adopt a die name; False (and no change) when it isn't one we know."""
        canon = normalize(die)
        if canon is None:
            return False
        with self._lock:
            self._die = canon
        return True

    def allows(self, value: int) -> bool:
        faces = self.faces
        return faces is None or 1 <= value <= faces
