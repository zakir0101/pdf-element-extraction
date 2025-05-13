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
        # self.tolerance = 20
        # self.left_most_list: list[Tuple] = []
        # self.left_most_x: int = 1000
        # self.expected_next_number = 1
        # self.question_ctxs = []
        # self.question_surfaces = []
        # self.min_ys = []
        # self.curr_miny = 0

    def draw_string_array(self, cmd: PdfOperator, is_single=False):
        glyph_array, char_seq, update_text_position = self.get_glyph_array(
            cmd, is_single
        )
        char_seq: Sequence = char_seq
        if self.should_skip_sequence(char_seq):
            update_text_position()
            return
        if self.mode == 1:
            self.question_detector.handle_sequence(char_seq, self.page_number)

        self.draw_glyph_array(glyph_array)
        update_text_position()

    def execute_command(self, cmd: PdfOperator):

        if cmd.name in self.state.do_sync_after:
            # print("syncing matrix, after ", cmd.name)
            self.sync_matrix()
        func = self.functions_map.get(cmd.name)
        if func:
            func(cmd)

    # def save_questions_to_pngs(self, exam_name: str):
    #     folder = exam_name.split(".")[0]
    #     folder = f"output{sep}{folder}"
    #     os.makedirs(folder, exist_ok=True)
    #     q_nr = [ml[0] for ml in self.left_most_list]
    #
    #     for i, q in enumerate(self.question_detector.question_list):
    #         q: Question = q
    #         if self.page_number not in q.pages:
    #             continue
    #         parts = find_questions_part_in_page(q, self.page_number)
    #
    #         filename = f"{folder}{sep}Question-{str(q_nr[i])}.png"
    #         _, _, y0, d = lm
    #         if i + 1 < len(self.left_most_list):
    #             _, _, y1, d = self.left_most_list[i + 1]
    #             dy = 0
    #         else:
    #             y1 = self.height
    #             dy = d * 4
    #         lm_h = y1 - y0 + dy
    #         lm_w = self.width
    #
    #         segments = get_segments(self.surface, y0, y1, 4 * d)
    #         print("number of segs = ", len(segments))
    #         # subsurf = self.surface.create_for_rectangle(
    #         #     0, y0 - d * 2, lm_w, lm_h
    #         # )
    #         out_height = sum(seg_h + 2 * d for _, seg_h in segments)
    #         out_height += 2 * d
    #         out_surf = cairo.ImageSurface(
    #             self.surface.get_format(), self.width, int(out_height)
    #         )
    #         ctx = cairo.Context(out_surf)
    #         dest_y = 0
    #         print("d is ", d)
    #         for i, (src_y, seg_h) in enumerate(segments):
    #             factor = 2
    #             if len(segments) == i + 1:
    #                 factor = 4
    #             sub = self.surface.create_for_rectangle(
    #                 0, src_y - 2 * d, self.width, seg_h + factor * d
    #             )
    #             ctx.set_source_surface(sub, 0, dest_y)
    #             ctx.paint()
    #             dest_y += seg_h + 2 * d
    #
    #         out_surf.write_to_png(filename)
    #         open_image_in_irfan(filename)
    #         time.sleep(5)
    #         # input("Press Enter to continue...")
    #         self.kill_with_taskkill()

    # curr_y = char_array[0][2]
    # if self.mode == 2 and curr_y >= self.min_ys[self.curr_miny]:
    #     # self.ctx = self.question_ctxs[self.curr_miny]
    #     self.surface = self.question_surfaces[self.curr_miny]
    #     self.surface.create_for_rectangle
    #     ctx = self.ctx
    #     y0 = self.left_most_list[self.curr_miny][2]
    #     ctx.set_source_surface(self.surface, 0, y0)
    #     ctx.set_source_rgb(1, 1, 1)  # White
    #     ctx.paint()
    #     ctx.set_source_rgb(0, 0, 0)  # Black
    #     print("incrementing miny ++")
    #     self.curr_miny += 1
    #     self.adjust_matrix_for_question()
    #
    # if self.mode == 1:
    # else:

    # def start_partioning(
    #     self,
    # ):
    #
    #     self.mode = 2
    #     self.default_ctx = self.ctx
    #     for i, lm in enumerate(self.left_most_list):
    #         _, _, y0 = lm
    #         self.min_ys.append(y0 - 20)
    #         if i + 1 < len(self.left_most_list):
    #             _, _, y1 = self.left_most_list[i + 1]
    #         else:
    #             y1 = self.height
    #             self.min_ys.append(self.height + 200)
    #
    #         lm_h = y1
    #         lm_w = self.width
    #         surface = cairo.ImageSurface(
    #             cairo.FORMAT_ARGB32, round(lm_w), round(lm_h - 30)
    #         )
    #         self.question_surfaces.append(surface)
    #         # self.question_ctxs.append(ctx)
    #
    #     self.curr_miny = 0
    #     # print(self.question_ctxs)
    #     print(self.min_ys)
    #     print(self.height)

    # def find_left_most(self, char_array):
    #     for i, char_t in enumerate(char_array):
    #         char, x, y, w, h = char_t
    #         diff = x - self.left_most_x
    #
    #         if not char or char == " ":
    #             continue
    #
    #         if diff < 0:
    #             self.left_most_x = x
    #
    #         if (
    #             len(char) > 1 or not char.isdigit()
    #         ):  # is symbole or is not a number , so ignore the sequence ,
    #
    #             break
    #
    #         if i + 1 < len(char_array):
    #             n_char, nx, ny, _, _ = char_array[i + 1]
    #             if n_char.isdigit() and (nx - x) < 2 * w:
    #                 char = char + n_char
    #
    #         if abs(diff) < w:
    #             self.left_most_list.append((char, x, y, 2 * h))
    #         elif diff < 0:
    #             self.left_most_list = [(char, x, y, 2 * h)]
    #         break

    # def save_to_png(self, filename: str) -> None:
    #     """Save the rendered content to a PNG file."""
    #     return
    #     self.kill_with_taskkill()
    #     print("saving image")
    #     if self.surface is None:
    #         raise ValueError("Renderer is not initialized")
    #     self.surface.write_to_png(filename)
    #     open_image_in_irfan(filename)
