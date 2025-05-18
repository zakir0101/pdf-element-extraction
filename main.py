#! ./venv/bin/python
# PYTHON_ARGCOMPLETE_OK

import pprint
import traceback
from collections import defaultdict

#!/usr/bin/env python
import tqdm
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
from os.path import basename, sep
import os
import random as rand

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
            self.type = args.type
            self.wait_time = args.wait
            self.curr_file = None
            self.single = args.single
            self.exampaths: list[str] = args.exampath
            self.max_tj = args.max_tj
            self.missing_font = args.missing_font or None
            self.range: list[int] = self.convet_range_string_to_list(
                args.range
            )
            self.f_indecies = self.convet_range_string_to_list(
                args.file_indecies
            )
            self.clean = not args.no_clean

        self.TEST_SIZE = {
            "tiny": 1,
            "small": 3,
            "meduim": 7,
            "large": 11,
            "all": None,
        }
        if self.mode in ["test"]:
            self.test = (
                args.test_type
            )  # parser , detector-count , detector-full,
            self.group = args.group
            self.data = (
                [(os.path.basename(f), f) for f in args.path]
                if args.path
                else None
            )

            self.pause = args.pause
            self.size = self.TEST_SIZE.get(args.size) or None
            self.subjects = args.subjects or all_subjects
            self.max = args.max
            self.build_test_data()

            if "font" in self.test:
                self.pages = self.convet_range_string_to_list(args.range)
                if not self.data:
                    raise Exception("missing data for test-type font")

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
        # if self.range and
        #     self.end = self.page_count

    def build_test_data(
        self,
    ):
        if self.data is not None:
            return
            # self.data = [(os.path.basename(d), d) for d in self.data]
            return
        files = []
        if self.size is None:
            self.size = 12
        self.years = self.get_test_years()
        self.year_dict = {}
        for sub in self.subjects:
            if self.max and len(files) >= self.max:
                break
            spath = igcse_path + sep + sub + sep + "exams"
            sexams = [
                (f, spath + sep + f)
                for f in os.listdir(spath)
                if self.filter_exam(f, sub)
            ]
            if self.group == "random":
                rand.shuffle(sexams)
            if self.max and len(files) + len(sexams) > self.max:
                files.extend(sexams[: self.max - len(sexams)])
            else:
                files.extend(sexams)
        if self.test != "list":
            print(self.subjects)
            print("size = ", self.size)
            print("years", self.years)
            print("exams len =", len(files))
        self.data = files

    def filter_exam(self, ex_name: str, sub: str):
        if "qp" not in ex_name or not ex_name.endswith(".pdf"):
            return False
        ye = ex_name.split("_")[1][1:]
        if int(ye) not in self.years:
            return False

        if not self.year_dict.get(sub + ye):
            self.year_dict[sub + ye] = 1
            return True
        if self.year_dict[sub + ye] < self.size:
            self.year_dict[sub + ye] += 1
            return True
        return False

    def get_test_years(self):

        gr = self.group
        if gr == "latest":
            year = [23]
        elif "oldest" in gr:
            last = int(gr[-1]) if gr[-1].isdigit() else 0
            year = []
            for i in range(11, 11 + 1 + last):
                year.append(i)
        elif gr.startswith("gap"):
            period = gr[-1]
            if not period.isdigit():
                raise Exception("group gap period is not defiend")
            year = [i for i in range(23, 10, -int(period))]
        elif gr == "random":
            all = [i for i in range(11, 24)]
            # year = []
            # for i in range(6):
            year = rand.sample(all, k=6)
        elif gr.startswith("year"):
            ye = gr[4:]
            year = [int(ye)]
        else:
            raise Exception("group is not correctly defined")

        return year

    @classmethod
    def add_view_subparser(cls, subparsers: argparse._SubParsersAction):
        view: argparse.ArgumentParser = subparsers.add_parser(
            "view", help="view a a page/question/pdf"
        )
        view.add_argument("type", type=str, choices=["pages", "questions"])
        view.add_argument(
            "--exampath", "--path", type=str, default=None, nargs="*"
        )
        view.add_argument("--range", type=str, default=None)
        view.add_argument("--file-indecies", "-f", type=str, default=None)
        # view.add_argument("--pages", type=str, default="1")
        view.add_argument(
            "--wait",
            type=int,
            help="time to wait before viewing the next image",
        )
        view.add_argument("--max-tj", type=int, default=10000)
        view.add_argument("--missing-font", type=int, default=0)
        view.add_argument("--single", "-r", action="store_true", default=False)
        view.add_argument(
            "--no-clean", "-nc", action="store_true", default=False
        )
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
            "test_type",
            type=str,
            choices=[
                "list",
                "font-show",
                "font-missing",
                "parser",
                "questions-count",
                "questions-match",
            ],
        )

        test.add_argument("--path", type=str, default=None, nargs="*")
        years = []
        for i in range(11, 24):
            years.append(f"year{str(i)}")
        groups = [
            "latest",
            "oldest",
            "oldest2",
            "oldest4",
            "oldest6",
            "gap2",
            "gap4",
            "gap6",
            "random",
        ] + years
        test.add_argument(
            "--group",
            type=str,
            choices=groups,
        )

        test.add_argument("--range", type=str, default=None)
        test.add_argument(
            "--size",
            type=str,
            choices=["tiny", "small", "medium", "large", "all"],
        )

        test.add_argument("--max", type=int)

        test.add_argument("--pause", action="store_true", default=False)
        test.add_argument(
            "--subjects",
            "-s",
            type=str,
            nargs="*",
            choices=all_subjects,
            default=None,
        )
        test.set_defaults(func=do_tests)


def do_tests(args: CmdArgs):

    callbacks = {
        "list": do_list,
        "font-show": do_test_font,
        "font-missing": lambda x: do_test_font(x, "missing"),
        "parser": do_test_parser,
        "questions-count": lambda x: do_test_question(x, True),
        "questions-match": (lambda x: do_test_question(x, False)),
    }
    if callbacks.get(args.test):
        callbacks[args.test](args)


def do_list(args: CmdArgs):
    for f in args.data:
        print(f[1], end=" ")


missing_fonts = """
{'/Arial-BoldMT', '/Times-Italic', '/Times-Bold', '/Times-Roman'}

Iam trying to make a pdf-renderer app , and have some issue with fonts ( some font does not have embeded font file)

I have analyzed alot of pdf files ( of interest ) , and listed all the missing fonts in them (no embeded font file) , I will provide you with the list , and I want you to find a free alternative for each one of them , which comply with it and garanties :
1- similar char_width
2- same glyph_id -> char_code map
3- generally similary look and position in the bounding box

for each missing fontfamily find the corresponding free font file which satisfy the requirment , if possible tell me where I can download it 

at the end create a pythong dict which map each pdf "missing" file to the alternative font filename

here is the list of missing font:

{'/TimesNewRomanPSMT', '/Helvetica', '/TimesNewRomanPS-ItalicMT', '/Times-BoldItalic', '/Arial-ItalicMT', '/Helvetica-Bold', '/Helvetica-Oblique', '/CourierNewPSMT', '/ArialMT', '/TimesNewRomanPS-BoldItalicMT', '/Verdana', '/TimesNewRomanPS-BoldMT', '/Symbol', '/Verdana-Italic', '/Times-Italic', '/Arial-BoldMT', '/Times-Roman', '/Times-Bold'}
"""


def do_test_font(args: CmdArgs, t_type: str = "show"):
    print("TEsting fonts")
    engine: PdfEngine = PdfEngine(scaling=4, debug=True, clean=False)
    missing = set()
    for pdf in tqdm.tqdm(args.data):
        args.curr_file = pdf[1]
        args.max_tj = 4000
        engine.initialize_file(pdf[1])
        args.set_engine(engine)
        # bad_pages[pdf[1]] = []
        cur_range = args.pages or range(1, args.page_count + 1)
        for page in cur_range:
            try:
                engine.perpare_page_stream(page, QuestionRenderer)
                for font in engine.font_map.values():
                    if t_type == "show":
                        font.debug_font()
                    elif t_type == "missing":
                        if not font.is_type3 and font.use_toy_font:
                            missing.add(font.base_font)
            except Exception as e:
                print(e)
                print(f"{pdf[1]}:{page}")

    if t_type == "missing":
        print("missing fonts :>")
        print(missing)
        pass


def do_test_parser(args: CmdArgs):

    engine: PdfEngine = PdfEngine(scaling=4, debug=True, clean=False)
    errors_dict = {}
    bad_pages: dict[str, list[int]] = []
    exception_stats = {}  # defaultdict(lambda: (0, "empty", []))
    total_pages = 0
    total_passed = 0
    stop = False
    for pdf in tqdm.tqdm(args.data):
        if stop:
            break
        args.curr_file = pdf[1]
        args.max_tj = 4000
        engine.initialize_file(pdf[1])
        args.set_engine(engine)
        # bad_pages[pdf[1]] = []
        for page in range(1, args.page_count + 1):
            total_pages += 1
            try:
                engine.perpare_page_stream(page, QuestionRenderer)
                engine.debug_original_stream()
                engine.execute_stream_extract_question(
                    max_show=args.max_tj, mode=1
                )
                total_passed += 1
            except Exception as e:
                # bad_pages[pdf[1]] = []
                exception_key = get_exception_key(e)
                location = f"{pdf[1]}:{page}"
                print(f"Error: {location}")
                if exception_key not in exception_stats:
                    full_traceback = traceback.format_exc()
                    exception_stats[exception_key] = {
                        "count": 1,
                        "msg": full_traceback,
                        "location": [location],
                    }
                else:
                    exception_stats[exception_key]["count"] += 1
                    # exception_stats[exception_key]["files"].append(
                    # os.path.basename(pdf[0])
                    # )
                if args.pause:
                    stop = True
                    break
    print("\n**********************************")
    print("Total number of Pages = ", total_pages)
    print("Passt percent", round(total_passed / total_pages * 100), "%")

    for key, value in exception_stats.items():
        print("\n**********************************\n")
        print(key)
        print("count = ", value["count"])
        print("percent = ", round(value["count"] / total_pages * 100), "%")
        print(value["msg"])
        print(value["location"])
        print("\n\n\n")
        # pprint.pprint(exception_stats)


def get_exception_key(e: Exception):

    exc_type = type(e).__name__
    exc_msg = str(e)
    _, _, exc_traceback = sys.exc_info()
    if exc_traceback:
        tb_frames = traceback.extract_tb(exc_traceback)
        # Get the origin frame (where the exception was raised)
        origin_frame = tb_frames[0]
        filename = origin_frame.filename
        line_no = origin_frame.lineno
    else:
        filename, line_no = "unknown", 0

    exception_key = (exc_type, exc_msg, filename, line_no)
    return exception_key


def do_test_question(args: CmdArgs, only_count=True):
    pass


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
    engine: PdfEngine = PdfEngine(scaling=4, debug=True, clean=args.clean)
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
        show_single_image(args)


def show_single_image(args: CmdArgs):
    exam_name = os.path.basename(args.curr_file)
    print("\n")
    print("***************  exam  ******************")
    print(f"*********** ({exam_name}) ************")
    print(f"{args.curr_file}")
    engine: PdfEngine = args.engine
    detector = engine.question_detector
    surfs_dict = {}
    per_page = args.type == "pages"
    per_questions = args.type == "questions"
    missing_font_mode = args.missing_font or None
    rendererClass = QuestionRenderer if per_questions else BaseRenderer
    if per_page and not args.range:
        args.range = [i for i in range(1, args.page_count + 1)]
    missing_font_count = 0
    missing_font_names = set()
    for page in range(1, args.page_count + 1):
        if per_questions or page in args.range:
            engine.perpare_page_stream(page, rendererClass=rendererClass)
            engine.debug_original_stream()
            if (
                missing_font_mode
                and len(engine.state.list_all_missing_font()) == 0
            ):
                continue
            engine.execute_stream_extract_question(
                max_show=args.max_tj, mode=1
            )
            if (
                not missing_font_mode
                or engine.state.missing_font_count > args.missing_font
            ):
                curr_surf = engine.renderer.surface
                surfs_dict[page] = curr_surf
                detector.calc_page_segments_and_height(curr_surf, page, args)
                if args.missing_font:
                    missing_font_count += 1
                    missing_font_names.update(
                        engine.state.list_all_missing_font()
                    )

    questions: list[Question] = detector.question_list
    print("Page Numbers :", args.page_count)
    print("Question Numbers :", len(questions))

    if per_questions and len(questions) == 0:
        print(f"no Question detected in File {exam_name}")
        return

    if not missing_font_mode:
        detector.print_final_results(args.curr_file)
    else:
        print(
            f"Found {missing_font_count} Pages with missing Fonts (>{args.missing_font})\n"
        )
        print(">> replaced with :")
        print(missing_font_names)
        if missing_font_count == 0:

            return
    # if len(questions) > 0:

    if args.single:
        draw_and_preview(args, args.range, surfs_dict)
    else:
        for i in args.range:
            draw_and_preview(args, [i], surfs_dict)


def draw_and_preview(args: CmdArgs, range: list, surfs_dict):
    filename = args.engine.question_detector.draw_all_pages_to_single_png(
        surfs_dict, args, range, args.type == "questions"
    )
    if filename:
        preview_image(filename, args.wait_time)
        kill_with_taskkill()
    else:
        print("no image genrated !!")


def show_image_per_range_item(args: CmdArgs):
    engine: PdfEngine = args.engine
    for page in args.get_page_range():
        imgpath = (
            engine.perpare_page_stream(page, BaseRenderer)
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
        if f.endswith("png"):
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
