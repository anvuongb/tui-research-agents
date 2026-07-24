from textual.message import Message

from tui_agents.sources.arxiv import SearchResult
from tui_agents.storage.models import Distillation, Paper


class ProgressUpdate(Message, bubble=True):
    def __init__(self, source: str, stage: str, message_text: str, percent: float = 0.0):
        self.source = source
        self.stage = stage
        self.message_text = message_text
        self.percent = percent
        super().__init__()


class SearchResultsReady(Message, bubble=True):
    def __init__(self, results: list[SearchResult]):
        self.results = results
        super().__init__()


class PapersUpdated(Message, bubble=True):
    def __init__(self):
        super().__init__()


class DistillationReady(Message, bubble=True):
    def __init__(self, paper_id: str, distillation: Distillation):
        self.paper_id = paper_id
        self.distillation = distillation
        super().__init__()
