import json
import pprint
import random
import traceback
import tqdm
import sys
from collections import defaultdict
from engine.pdf_engine import PdfEngine
from engine.pdf_stream_parser import PDFStreamParser
from engine.pdf_utils import (
    open_pdf_using_sumatra,
    open_files_in_nvim,
)
from engine.pdf_detectors import QuestionBase
from engine.pdf_question_renderer import QuestionRenderer
from main import CmdArgs, all_subjects, igcse_path
import os
from os.path import sep
import gui.pdf_tester_gui as gui
from engine.pdf_detectors import enable_detector_dubugging
from models.core_models import Subject
import engine.pdf_gui_api as api


# ******************************************************************
# ********************* CMD_MAKE **********************************
# ------------------------------------------------------------------
def do_make(args: CmdArgs):
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
        "pre-questions-show": do_show_question,
        "questions-save": do_test_question,
        # -----
        "subjects": do_test_subjects_syllabus,
        "view-question": show_question,
        "view-page": show_page,
    }
    if callbacks.get(args.test):
        callbacks[args.test](args)


def do_test_subjects_syllabus(args: CmdArgs):

    subjects_dict = api.load_subjects_files()
    for sub in args.subjects:
        sub_obj: Subject = subjects_dict[sub]
        print("\n\n******************************************")
        print(f"****************  {sub} *****************")
        for paper in sub_obj.papers.values():
            if args.data and str(paper.number) not in args.data:
                print(f"skipping paper {paper.number}", args.data)
                continue
            print(f"\n************+ Paper Nr {paper.number} ***************")
            print(f"************+ Paper {paper.name} ***************")
            # empty_chaps = []
            for chap in paper.chapters:
                if args.range and chap.number not in args.range:
                    print(args.range, chap.number)
                    continue
                print(f"\n{chap.number}: {chap.name}, .... description =>")
                print("___________________________")
                if args.pause:
                    print(chap.description, "\n\n")
                cleaned_desc = (
                    chap.description.replace("description", "")
                    .replace("examples", "")
                    .replace("\n", "")
                    .replace("core", "")
                    .replace("extended", "")
                    .replace("*", "")
                    .replace(" ", "")
                    .replace(":", "")
                )
                print("char_count = ", len(cleaned_desc))
                if not chap.description or len(cleaned_desc) == 0:
                    raise Exception("Found an emtpy chapter ... ")


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
                engine.load_page_content(page, QuestionRenderer)
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
    # errors_dict = {}
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
                engine.load_page_content(page, QuestionRenderer)
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
    # errors_dict = {}
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
                engine.load_page_content(page, QuestionRenderer)
                engine.debug_original_stream()
                engine.execute_page_stream(max_show=args.max_tj, mode=0)
                if is_show:
                    surf = engine.renderer.surface
                    raitio = (
                        engine.scaled_page_width / engine.scaled_page_height
                    )
                    res = gui.show_page(surf, raitio)
                    print("status", res)
                    if res == gui.STATE_WRONG:
                        location = f"{pdf[1]}:{page}"
                        print("added to list")
                        wrong_rendered.append(location)
                    elif res == gui.STATE_CORRECT:
                        total_passed += 1
                    else:
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


def do_show_question(args: CmdArgs):

    # clean = False  # args.clean
    stop = False
    gui.start(-1000, -1)
    for pdf in tqdm.tqdm(args.data):
        if stop:
            break
        api.set_current_exam(pdf[0])
        q_list = api.get_curr_exam_questions()

        for q in q_list:
            if args.range and int(q.label) not in args.range:
                continue

            q_surf = api.render_curr_exam_question_on_surface(
                int(q.label), scale=4, clean=False
            )

            res = gui.show_page(q_surf)
            if res == gui.STATE_DONE:
                stop = True
                break


def do_test_question(
    args: CmdArgs,
):
    enable_detector_dubugging()
    is_show = args.test == "questions-show"
    is_count = args.test == "questions-count"
    is_save = args.test == "questions-save"
    clean = False  # args.clean
    engine: PdfEngine = PdfEngine(
        scaling=4, debug=True, clean=(is_show and clean)
    )
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

        # surfs_dict = {}
        args.curr_file = pdf[1]
        args.max_tj = 4000
        engine.initialize_file(pdf[1])
        args.set_engine(engine)
        pages_range = [i for i in range(1, args.page_count + 1)]
        detector = engine.question_detector
        for page in pages_range:
            total_pages += 1
            try:
                engine.load_page_content(page, QuestionRenderer)
                engine.debug_original_stream()
                engine.execute_page_stream(max_show=args.max_tj, mode=1)

                total_passed += 1
            except Exception as e:
                location = f"{pdf[1]}:{page}"
                print(f"Error: {location}")
                if args.pause:
                    raise Exception(e)
                    stop = True
                    break
        detector.on_finish()
        questions: list[QuestionBase] = detector.question_list
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


def show_question(args: CmdArgs):
    debugging = args.debug and PdfEngine.M_DEBUG_DETECTOR
    clean = args.clean and (
        PdfEngine.O_CROP_EMPTY_LINES | PdfEngine.O_CLEAN_HEADER_FOOTER
    )
    engine: PdfEngine = PdfEngine(4, debugging, clean)
    engine.set_files(args.data)
    gui.start(-1, -1)
    for pdf_index in range(engine.all_pdf_count):
        is_ok = engine.proccess_next_pdf_file()
        print("\n")
        print("***************  exam  ******************")
        print(f"{engine.pdf_path}")
        if not is_ok:
            break
        engine.extract_questions_from_pdf()
        for nr in args.range:
            q_surf = engine.render_a_question(nr)
            gui.show_page(q_surf, True)


def show_page(args: CmdArgs):
    debugging = args.debug and PdfEngine.M_DEBUG
    clean = 0  # args.clean and(  PdfEngine.O_CLEAN_HEADER_FOOTER )
    engine: PdfEngine = PdfEngine(4, debugging, clean)
    engine.set_files(args.data)
    gui.start(-1, -1)
    for pdf_index in range(engine.all_pdf_count):
        is_ok = engine.proccess_next_pdf_file()
        print("\n")
        print("***************  exam  ******************")
        print(f"{engine.pdf_path}")
        if not is_ok:
            print("Exiting ..")
            break
        for page in args.range:
            surf = engine.render_pdf_page(page)
            stat = gui.show_page(surf, True)
            if stat == gui.STATE_DONE:
                return


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
