from models.core_models import SymSequence


class BaseDetector:
    def __init__(self) -> None:
        self.curr_page = -1
        self.height = 0
        self.width = 0
        pass

    def attach(self, page_width, page_height, page: int):
        self.height = page_height
        self.width = page_width
        self.curr_page = page

    def handle_sequence(self, seq: SymSequence, page: int):
        pass

    def on_finish(
        self,
    ):
        pass


class LineDetector(BaseDetector):
    pass


class ParagraphDetector(BaseDetector):
    pass


class TableDetector(BaseDetector):
    pass


class GraphDetector(BaseDetector):
    pass


class InlineImageDetector(BaseDetector):
    pass


# def find_questions_part_in_page(
#
#     q: QuestionBase, page: int
# ) -> list[QuestionBase]:
#     parts: list[QuestionBase] = []
#     if page not in q.pages:
#         return []
#
#     if len(q.pages) == 1:
#         parts.append(q)
#     else:
#         for p in q.parts:
#             parts.extend(find_questions_part_in_page(p, page))
#     return parts
