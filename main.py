#! ./venv/bin/python
# PYTHON_ARGCOMPLETE_OK


#!/usr/bin/env python

import argparse
import sys
import argcomplete
import re
import json
from subprocess import call
import cairo
import time
from engine.pdf_renderer import BaseRenderer
from engine.pdf_engine import PdfEngine
from argparse import ArgumentParser
from engine.pdf_utils import open_image_in_irfan, kill_with_taskkill

from engine.pdf_detectors import Question
from fontTools.unicode import Unicode
from fontTools.agl import AGL2UV, toUnicode  # import AGL2UV
from engine.pdf_question_renderer import QuestionRenderer
from os.path import sep
import os


if os.name == "nt":  # Windows
    ansi = "ansi"
    d_drive = "D:"
else:
    ansi = "iso_8859_1"
    d_drive = "/mnt/d"

igcse_path = f"{d_drive}{sep}Drive{sep}IGCSE"
all_subjects = [
    f
    for f in os.listdir(igcse_path)
    if os.path.isdir(igcse_path + sep + f) and f.isdigit()
]
# print(all_subjects)


class CmdArgs:
    def __init__(self, args: argparse.Namespace):

        self.mode = args.mode
        if self.mode in ["view"]:
            self.pages = args.pages
            self.type = args.type
            if self.pages:
                sp = self.pages.split("-")
                self.start = int(sp[0])
                self.end = int(sp[1]) if len(sp) == 2 else None
            self.wait_time = args.wait
            self.curr_file = None
            self.exampaths: list[str] = args.exampath
            self.max_tj = args.max_tj
            self.q_nr: str = self.convet_range_string_to_list(
                args.questions_nr
            )
            self.f_indecies = self.convet_range_string_to_list(
                args.file_indecies
            )
            # if self.f_indecies is not None and not self.f_indecies.digits():
            #     raise Exception("file-indecies must be integer values")

        if self.mode in ["test_module"]:
            self.test = args.test_module

        if self.mode in ["list"]:
            self.item = args.item
            self.subjects = args.subjects
            self.year = args.year
            self.exam = args.exam
            self.full = args.full
            self.row = args.row

    def convet_range_string_to_list(self, string: str):
        if string is None:
            return None
        sp = string.split(",")
        output = []
        for el in sp:
            if el.isdigit():
                output.append(int(el))
            else:
                sp2 = el.split("-")
                if len(sp2) != 2:
                    raise Exception(f"invalid range {el}")
                e1, e2 = sp2[0], sp2[1]
                if not e1.isdigit() or not e2.isdigit():
                    raise Exception(f"invalid range {el}")
                e1, e2 = int(e1), int(e2)
                for i in range(e1, e2 + 1):
                    output.append(i)

        return sorted(output)

    def set_engine(self, engine: PdfEngine):
        self.engine = engine
        self.page_count = len(engine.pages)
        if self.end is None:
            self.end = self.page_count

    def get_page_range(self):
        return range(self.start, self.end + 1)

    @classmethod
    def add_view_subparser(cls, subparsers: argparse._SubParsersAction):
        view: argparse.ArgumentParser = subparsers.add_parser(
            "view", help="view a a page/question/pdf"
        )
        view.add_argument(
            "--type", type=str, choices=["page", "p", "question", "q", "pdf"]
        )
        view.add_argument(
            "--exampath", "--path", type=str, default=None, nargs="*"
        )
        view.add_argument("--questions_nr", type=str, default=None)
        view.add_argument("--file-indecies", type=str, default=None)
        view.add_argument("--pages", type=str, default="1")
        view.add_argument(
            "--wait",
            type=int,
            help="time to wait before viewing the next image",
        )
        view.add_argument("--max-tj", type=int, default=10000)
        view.set_defaults(func=view_element)

    @classmethod
    def add_clear_subparser(cls, subparsers: argparse._SubParsersAction):
        clear: argparse.ArgumentParser = subparsers.add_parser(
            "clear", help="clear temp files"
        )
        clear.set_defaults(func=clear_temp_files)

    @classmethod
    def add_list_subparser(cls, subparsers: argparse._SubParsersAction):
        li: argparse.ArgumentParser = subparsers.add_parser(
            "list",
            help="list existing pdf exams / subjects / questions, and filter them",
        )
        li.add_argument(
            "item",
            type=str,
            choices=["subjects", "sub", "exams", "ex", "questions", "q"],
        )
        li.add_argument(
            "--subjects",
            "-s",
            type=str,
            nargs="*",
            choices=all_subjects,
            default=None,
        )
        li.add_argument(
            "--year",
            "-y",
            type=str,
            choices=[f"{n:02}" for n in range(1, 27)],
            default=None,
        )
        li.add_argument("--exam", "-ex", type=str, default=None)
        li.add_argument("--full", "-f", action="store_true", default=None)
        li.add_argument("--row", "-r", action="store_true", default=True)
        li.set_defaults(func=list_items)

    @classmethod
    def add_test_subparser(cls, subparsers: argparse._SubParsersAction):
        test: argparse.ArgumentParser = subparsers.add_parser(
            "test", help="run test on a set of exam pdfs"
        )
        test.add_argument(
            "test_module",
            type=str,
            choices=["detector"],
        )


def list_items(args: CmdArgs):
    search_item = args.item
    callbacks = [
        ("subjects", list_subjects),
        ("exams", list_exams),
        ("questions", list_questions),
    ]
    for name, cback in callbacks:
        if name.startswith(search_item):
            cback(args)


def list_questions(args: CmdArgs):
    pass


def list_exams(args: CmdArgs):
    subs = args.subjects or all_subjects
    exams = []

    def filter_exam(ex_name: str):
        if "qp" not in ex_name or not ex_name.endswith(".pdf"):
            return False
        if not args.year or not args.year.isdigit:
            return True
        return ex_name.split("_")[1][1:] == args.year

    for s in subs:
        if s not in all_subjects:
            continue
        spath = f"{igcse_path}{sep}{s}{sep}exams"
        sexams = [
            (f, spath + sep + f) for f in os.listdir(spath) if filter_exam(f)
        ]
        exams.extend(sexams)
    seperator = " " if args.row else "\n"
    for ex in exams:
        full = args.full or False
        print(ex[int(full)], end=seperator)


def list_subjects(args: CmdArgs):
    for sub in all_subjects:
        print(sub)


def view_element(args: CmdArgs):
    test_files = [
        "9702_m23_qp_12.pdf",
        "9709_m23_qp_32.pdf",
        "9709_m23_qp_22.pdf",
        "9709_m23_qp_12.pdf",
        "9709_w23_qp_31.pdf",
        "9702_m23_qp_22.pdf",
    ]
    engine: PdfEngine = PdfEngine(scaling=4, debug=True)
    args.exampaths = args.exampaths or [
        f"PDFs{sep}{f}" for f in test_files
    ]  #  []
    if args.f_indecies:
        args.exampaths = [
            f for i, f in enumerate(args.exampaths) if i in args.f_indecies
        ]
    for i, curr_file in enumerate(args.exampaths):
        engine.initialize_file(curr_file)
        args.set_engine(engine)
        args.curr_file = curr_file
        if "pdf".startswith(args.type):
            show_pdf(args)
        elif "page".startswith(args.type):
            show_page(args)


def show_pdf(args: CmdArgs):

    engine: PdfEngine = args.engine
    detector = engine.question_detector
    surfs_dict = {}
    # sys.stdout = open(f"output{sep}detector_output.md", "w", encoding="utf-8")

    for page in args.get_page_range():
        engine.get_page_stream(page, QuestionRenderer)
        width = engine.default_width * engine.scaling
        height = engine.default_height * engine.scaling

        engine.debug_original_stream().execute_stream_extract_question(
            max_show=args.max_tj, mode=1
        )
        curr_surf = engine.renderer.surface
        surfs_dict[page] = curr_surf
        detector.calc_page_segments_and_height(curr_surf, page)

    questions: list[Question] = detector.question_list

    detector.print_final_results(args.curr_file)
    if len(questions) > 0:
        filename = detector.draw_all_pages_to_single_png(
            surfs_dict, args.curr_file
        )
        preview_image(filename, args.wait_time)
        kill_with_taskkill()


def show_page(args: CmdArgs):
    engine: PdfEngine = args.engine
    for page in args.get_page_range():
        imgpath = (
            engine.get_page_stream(page, BaseRenderer)
            .debug_original_stream()
            .execute_stream(max_show=args.max_tj)
        )
        preview_image(imgpath, args.wait_time)

    kill_with_taskkill()


def clear_temp_files(args: CmdArgs):
    for f in os.listdir("temp"):
        print(f"removing {f}")
        os.remove(f"temp{sep}{f}")
    for f in os.listdir("output"):
        if f.startswith("glyphs_"):
            print(f"removing {f}")
            os.remove(f"output{sep}{f}")


def preview_image(imgpath, waiting_time):
    open_image_in_irfan(imgpath)
    if waiting_time and waiting_time > 0:
        time.sleep(waiting_time)
    else:
        _ = input("Press Enter to continue...")


def test_image_cairo():
    width, height = 100, 100
    surface = cairo.ImageSurface(cairo.Format.RGB24, width, height)
    data = surface.get_data()
    for y in range(50 - 20, 50 + 20):
        for x in range(50 - 20, 50 + 20):
            index = y * surface.get_stride() + x * 4
            data[index] = 255  # red
            data[index + 1] = 255  # green
            data[index + 2] = 255  # blue
    surface.write_to_png("im.png")


def test_cairo():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 300)
    ctx = cairo.Context(surface)
    char = "A"
    font_size = 10
    first = None
    for i in range(1, 6):

        ctx.select_font_face(
            "Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL
        )
        curr_size = font_size * i
        ctx.set_font_size(curr_size)
        extent = ctx.text_extents(char)
        width, height = [extent.x_advance, extent.height]
        print("width", width, "height", height)
        if i > 1:
            ratio = width / first[0]
            print("height ratio", ratio, "expected", i)
            print("correction_factor", ratio / i)
        if i == 1:
            first = (width, height)


def test_cairo_renderer():
    engine: PdfEngine = PdfEngine("9702_m23_qp_12.pdf")
    state = engine.state
    renderer = BaseRenderer(state)
    renderer.initialize(800, 600)
    renderer.draw_line(0, 0, 800, 600)
    renderer.save_to_png("output.png")


if __name__ == "__main__":
    # test_cario_matrix_operation()
    # test_offset()

    parser = ArgumentParser()
    # arg.add_argument(
    #     "mode", type=str, choices=["show", "main","clear","test"], default="main"
    # )
    parser.set_defaults(func=lambda x: print("no args provided"))
    subparsers = parser.add_subparsers(dest="mode")
    CmdArgs.add_view_subparser(subparsers=subparsers)
    CmdArgs.add_clear_subparser(subparsers=subparsers)
    CmdArgs.add_test_subparser(subparsers=subparsers)
    CmdArgs.add_list_subparser(subparsers=subparsers)
    parser.parse_known_args()
    argcomplete.autocomplete(parser, exclude=["b", "q", "ex", "sub"])
    nm = parser.parse_args()
    nm.func(CmdArgs(nm))

    # mode = nm.mode
    # mode2 = nm.mode2
    # if mode == "main":
    #     main(nm.pages)
    # elif mode == "show":
    #     draw_page(nm.page)
    # elif mode == "clear":
    #     clear_temp_files()
    # elif mode == "test":
    #
