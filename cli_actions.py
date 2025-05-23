import json
import pprint
import random
import traceback
from zlib import DEF_BUF_SIZE
import tqdm
import sys
import cairo
from collections import defaultdict
import time
from engine.pdf_renderer import BaseRenderer
from engine.pdf_engine import PdfEngine
from engine.pdf_stream_parser import PDFStreamParser
from engine.pdf_utils import (
    open_image_in_irfan,
    kill_with_taskkill,
    open_pdf_using_sumatra,
    open_files_in_nvim,
)
from engine.pdf_detectors import Question
from engine.pdf_question_renderer import QuestionRenderer
from main import CmdArgs, all_subjects, igcse_path
import os
from os.path import sep
import gui.pdf_tester_gui as gui
from engine.pdf_detectors import set_dubugging


# ******************************************************************
# ********************* CMD_MAKE **********************************
# ------------------------------------------------------------------
def do_tests(args: CmdArgs):
    pass


# ******************************************************************
# ********************* CMD_LIST **********************************
# ------------------------------------------------------------------


def do_tests(args: CmdArgs):

    callbacks = {
        "list": do_list,
        "font-show": do_test_font,
        "font-missing": lambda x: do_test_font(x, "missing"),
        "renderer-silent": do_test_renderer,
        "renderer-show": do_test_renderer,
        "parser": do_test_parser,
        "questions-count": do_test_question,
        "questions-match": do_test_question,
        "questions-show": do_test_question,
        "questions-save": do_test_question,
    }
    if callbacks.get(args.test):
        callbacks[args.test](args)


def do_list(args: CmdArgs):
    for f in args.data:
        print(f[1], end=" ")


def do_test_font(args: CmdArgs, t_type: str = "show"):
    print("TEsting fonts")
    engine: PdfEngine = PdfEngine(scaling=4, debug=True, clean=False)
    missing = set()
    for pdf in tqdm.tqdm(args.data):
        args.curr_file = pdf[1]
        args.max_tj = 4000
        engine.initialize_file(pdf[1])
        args.set_engine(engine)
        cur_range = args.range or range(1, args.page_count + 1)
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
                raise

    if t_type == "missing":
        print("missing fonts :>")
        print(missing)
        pass


def do_test_parser(args: CmdArgs):

    print("************* Testing Parser ****************\n\n")
    engine: PdfEngine = PdfEngine(scaling=4, debug=True, clean=False)
    errors_dict = {}
    exception_stats = {}  # defaultdict(lambda: (0, "empty", []))
    total_pages = 0
    total_passed = 0
    stop = False
    all_locations = []
    for pdf in tqdm.tqdm(args.data):
        if stop:
            break
        args.curr_file = pdf[1]
        args.max_tj = 4000
        engine.initialize_file(pdf[1])
        args.set_engine(engine)
        for page in range(1, args.page_count + 1):
            total_pages += 1
            try:
                engine.perpare_page_stream(page, QuestionRenderer)
                engine.debug_original_stream()
                parser = PDFStreamParser().parse_stream(engine.current_stream)
                for cmd in parser.iterate():
                    pass
                total_passed += 1
            except Exception as e:
                exception_key = get_exception_key(e)
                location = f"{pdf[1]}:{page}"
                print(f"Error: {location}")
                all_locations.append(location)
                if exception_key not in exception_stats:
                    full_traceback = traceback.format_exc()
                    exception_stats[exception_key] = {
                        "count": 1,
                        "msg": full_traceback,
                        "location": [location],
                    }
                else:
                    exception_stats[exception_key]["count"] += 1
                    exception_stats[exception_key]["location"].append(location)

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

    pprint.pprint(all_locations)
    with open(f"output{sep}fix_list.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(all_locations))


def do_test_renderer(args: CmdArgs):

    engine: PdfEngine = PdfEngine(scaling=4, debug=True, clean=False)
    errors_dict = {}
    exception_stats = {}  # defaultdict(lambda: (0, "empty", []))
    total_pages = 0
    total_passed = 0
    stop = False
    is_show = args.test == "renderer-show"
    # ----
    if is_show:
        gui.start(-1000, -1)
    wrong_rendered = []
    for pdf in tqdm.tqdm(args.data):
        if stop:
            break
        args.curr_file = pdf[1]
        args.max_tj = 4000
        engine.initialize_file(pdf[1])
        args.set_engine(engine)
        engine.clean = False
        pages_range = [i for i in range(1, args.page_count + 1)]
        if args.range:
            if args.range == "random":
                pages_range = random.sample(pages_range, k=args.size)
            elif isinstance(args.range, list):
                pages_range = [i for i in args.range if i in pages_range]
            else:
                raise Exception("unsupported range", args.range)
        for page in pages_range:
            total_pages += 1
            try:
                engine.perpare_page_stream(page, QuestionRenderer)
                engine.debug_original_stream()
                engine.execute_stream_extract_question(
                    max_show=args.max_tj, mode=0
                )
                if is_show:
                    surf = engine.renderer.surface
                    raitio = engine.default_width / engine.default_height
                    res = gui.show_page(surf, raitio)
                    print("status", res)
                    if res == gui.STATE_WRONG:
                        location = f"{pdf[1]}:{page}"
                        print("added to list")
                        wrong_rendered.append(location)
                    elif res == gui.STATE_CORRECT:
                        total_passed += 1
                    else:
                        gui.end()
                        stop = True
                        break

                else:

                    total_passed += 1

            except Exception as e:
                location = f"{pdf[1]}:{page}"
                print(f"Error: {location}")

                if not is_show:
                    exception_key = get_exception_key(e)
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
                    raise Exception(e)
                    stop = True
                    break

    print("\n**********************************")
    print("Total number of Pages = ", total_pages)
    print("Passt percent", round(total_passed / total_pages * 100), "%")
    if is_show:
        for i, f in enumerate(wrong_rendered):
            print(f"{i}. {f}")
        pass
    else:

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

    # in exams loop
    # in page loop


def do_test_question(
    args: CmdArgs,
):
    set_dubugging()
    is_show = args.test == "questions-show"
    is_match = args.test == "questions-match"
    is_count = args.test == "questions-count"
    is_save = args.test == "questions-save"
    clean = False  # args.clean
    engine: PdfEngine = PdfEngine(
        scaling=4, debug=True, clean=(is_show and clean)
    )
    question_count_dict = {}
    exception_stats = {}  # defaultdict(lambda: (0, "empty", []))
    total_pages = 0
    total_passed = 0
    exams_count_by_question_number = defaultdict(int)
    exams_names_by_question_number = defaultdict(list)
    bad_exams = []
    MIN_COUNT = round(len(args.data) / 6 * 0.1) or 1
    stop = False
    # ----
    if is_show:
        pass
        # gui.start(-1000, -1)
    wrong_rendered = []
    created_files = []
    for pdf in tqdm.tqdm(args.data):
        if stop:
            break

        exam_name = pdf[0].split(".")[0]
        subject_name = exam_name[:4]
        out_dir = f"{igcse_path}{sep}{subject_name}{sep}detected"
        os.makedirs(out_dir, exist_ok=True)
        out_file_name = f"{igcse_path}{sep}{subject_name}{sep}detected{sep}{exam_name}.json"
        if os.path.exists(out_file_name) and not args.force:
            created_files.append(out_file_name)
            print(f"skipping pre-saved file {pdf[1]}")
            continue

        surfs_dict = {}
        args.curr_file = pdf[1]
        args.max_tj = 4000
        engine.initialize_file(pdf[1])
        args.set_engine(engine)
        pages_range = [i for i in range(1, args.page_count + 1)]
        detector = engine.question_detector
        for page in pages_range:
            total_pages += 1
            try:
                engine.perpare_page_stream(page, QuestionRenderer)
                engine.debug_original_stream()
                engine.execute_stream_extract_question(
                    max_show=args.max_tj, mode=1
                )

                total_passed += 1
                if is_show:
                    pass
                    # raise
                    # surf = engine.renderer.surface
                    # detector.calc_page_segments_and_height(surf, page, args)
                    # surfs_dict[page] = surf
                    # raitio = engine.default_width / engine.default_height

                    # res = gui.show_page(surf, raitio)
                    # print("status", res)
                    # if res == gui.STATE_WRONG:
                    #     location = f"{pdf[1]}:{page}"
                    #     print("added to list")
                    #     wrong_rendered.append(location)
                    # elif res == gui.STATE_CORRECT:
                    #     total_passed += 1
                    # else:
                    #     gui.end()
                    #     stop = True
                    #     break
                else:
                    pass
            except Exception as e:
                location = f"{pdf[1]}:{page}"
                print(f"Error: {location}")
                if args.pause:
                    raise Exception(e)
                    stop = True
                    break
        detector.on_finish()
        questions: list[Question] = detector.question_list
        if is_show:

            print("Page Numbers :", args.page_count)
            print("Question Numbers :", len(questions))
            detector.print_final_results(args.curr_file)
            if args.open_pdf:
                open_pdf_using_sumatra(pdf[1])
                input("enter any key to continue")
        if is_save:
            q_dict_list = [q.__to_dict__() for q in questions]
            with open(out_file_name, "w", encoding="utf-8") as out_f:
                out_f.write(
                    json.dumps(q_dict_list, ensure_ascii=False, indent=4)
                )

            created_files.append(out_file_name)

            pass

        count_q = len(questions)
        if count_q <= 3:
            bad_exams.append(pdf[1])

        exams_count_by_question_number[count_q] += 1
        exams_names_by_question_number[count_q].append(pdf[1])

    if is_count or is_save:
        print("\n**********************************")
        print("Total number of Exams = ", len(args.data))
        print("Total number of pages= ", total_passed)
        print("STATS:")
        # pprint.pprint(exams_count_by_question_number)
        for q_count, ex_count in exams_count_by_question_number.items():
            print(f"{ex_count:3} Exams => QuestionNr: {q_count}")
            print(">>", exams_names_by_question_number[q_count], "\n")

        print("\n\n**********************************")
        print("exam_names with less than 3 questions !!")
        for ex in bad_exams:
            print(ex)

        print("\n\n**********************************")
        print(f"exam_names in groups with less than {MIN_COUNT} members!!")
        empty_group = {
            q_count: file_names
            for q_count, file_names in exams_names_by_question_number.items()
            if len(file_names) <= MIN_COUNT
        }
        for q_count, ex_names in empty_group.items():
            print(
                f"# ONLY {len(ex_names):3} Exams has {q_count:3} Questions  !!"
            )
            print(ex_names)

        print("\n\n\n")

    if is_save:
        limit = min(len(created_files) - 1, 10)
        open_files_in_nvim(created_files[-limit:])


# ******************************************************************
# ********************* CMD_LIST **********************************
# ------------------------------------------------------------------


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


# ******************************************************************
# ********************* CMD_VIEW **********************************
# ------------------------------------------------------------------


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
    if per_questions:
        set_dubugging()
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
                max_show=args.max_tj, mode=(1 if per_questions else 0)
            )
            if (
                not missing_font_mode
                or engine.state.missing_font_count > args.missing_font
            ):
                curr_surf = engine.renderer.surface
                surfs_dict[page] = curr_surf
                # print("about to show image")
                # f_name = f"output{sep}temp.png"
                # engine.renderer.save_to_png(f_name)
                # open_image_in_irfan(f_name)
                # return

                detector.calc_page_segments_and_height(curr_surf, page, args)
                if args.missing_font:
                    missing_font_count += 1
                    missing_font_names.update(
                        engine.state.list_all_missing_font()
                    )
    detector.on_finish()
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


def draw_and_preview(args: CmdArgs, b_range: list, surfs_dict):
    filename = args.engine.question_detector.draw_all_pages_to_single_png(
        surfs_dict, args, b_range, args.type == "questions"
    )
    if filename:
        preview_image(filename, args)
        kill_with_taskkill()
    else:
        print("no image genrated !!")


def preview_image(imgpath, args: CmdArgs):
    waiting_time = args.wait_time
    if args.open_pdf:
        open_pdf_using_sumatra(args.curr_file)
    open_image_in_irfan(imgpath)
    if waiting_time and waiting_time > 0:
        time.sleep(waiting_time)
    else:
        _ = input("Press Enter to continue...")


# ******************************************************************
# ********************* CMD_CLEAR **********************************
# ------------------------------------------------------------------


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


MAIN_CALLBACK = {
    "do_tests": do_tests,
    "list_items": list_items,
    "clear_temp_files": clear_temp_files,
    "view_element": view_element,
}

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
