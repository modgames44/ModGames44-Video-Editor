import copy


class History:
    """Deshacer/rehacer por instantáneas de la lista de clips."""

    def __init__(self, limit=100):
        self.past = []
        self.future = []
        self.limit = limit
        self._future_backup = None

    def record(self, clips):
        self.past.append(copy.deepcopy(clips))
        self.past = self.past[-self.limit:]
        # Se conserva el futuro descartado por si la operación no se aplica.
        self._future_backup = self.future
        self.future = []

    def cancel_last(self):
        """Anula el último `record()` de una operación que finalmente falló.

        Antes se usaba `past.pop()`, que dejaba la pila de Rehacer vacía
        aunque la Timeline no hubiera cambiado.
        """
        if self.past:
            self.past.pop()
        if self._future_backup is not None:
            self.future = self._future_backup
        self._future_backup = None

    def undo(self, clips):
        if not self.past:
            return None
        self._future_backup = None
        self.future.append(copy.deepcopy(clips))
        return self.past.pop()

    def redo(self, clips):
        if not self.future:
            return None
        self._future_backup = None
        self.past.append(copy.deepcopy(clips))
        return self.future.pop()
