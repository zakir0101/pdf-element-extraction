# import enum
# from math import isnan
# import re
import time
from engine.pdf_utils import open_image_in_irfan
from .pdf_operator import PdfOperator
from .engine_state import EngineState
from .pdf_renderer import BaseRenderer
import cairo
from .pdf_utils import get_segments
from .pdf_detectors import (
    Question,
    QuestionDetector,
    Sequence,
    BaseDetector,
    find_questions_part_in_page,
)
import os
from os.path import sep


class QuestionRenderer(BaseRenderer):

    def __init__(
        self, state: EngineState, main_detector: BaseDetector
    ) -> None:
        super().__init__(state, main_detector)
        self.question_detector: QuestionDetector = main_detector
        self.mode = 1

    def draw_string_array(self, cmd: PdfOperator, is_single=False):
        glyph_array, char_seq, update_text_position = self.get_glyph_array(
            cmd, is_single
        )
        char_seq: Sequence = char_seq
        if self.should_skip_sequence(char_seq):
            update_text_position()
            return "", True
        if self.mode == 1:
            self.question_detector.handle_sequence(char_seq, self.page_number)

        self.draw_glyph_array(glyph_array)
        update_text_position()
        return "", True
