import copy

class History:
    def __init__(self, limit=100):
        self.past=[]; self.future=[]; self.limit=limit
    def record(self, clips):
        self.past.append(copy.deepcopy(clips)); self.past=self.past[-self.limit:]; self.future.clear()
    def undo(self, clips):
        if not self.past:return None
        self.future.append(copy.deepcopy(clips));return self.past.pop()
    def redo(self, clips):
        if not self.future:return None
        self.past.append(copy.deepcopy(clips));return self.future.pop()
