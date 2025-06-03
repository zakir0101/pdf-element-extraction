import cairo
from models.question import QuestionBase

# from engine.pdf_engine import PdfEngine
# from engine.pdf_renderer import BaseRenderer
from models.core_models import Subject
from os.path import sep
import json
from .pdf_utils import igcse_path, all_subjects


def on_statrt():
    pass


def get_subjects():
    return all_subjects


def get_subject_papers(subject_id: str):
    pass


def get_papers_topics(subject_id: str, paper: int):
    pass


def get_topics_question(subject_id, paper: int, topic: str):
    pass


def get_question_surface(question_id: str) -> cairo.ImageSurface:
    pass


exam_id, subj_id, ex_path_json, ex_path_pdf = ["not-a-subject"] + [""] * 3
ex_q_list, engine = [None] * 2


def set_current_exam(exam_id_or_pdf_name):
    global exam_id, subj_id, ex_path_json, ex_path_pdf, ex_q_list, engine
    if exam_id in exam_id_or_pdf_name:
        return

    exam_id = exam_id_or_pdf_name
    exam_id = exam_id.split(".")[0]
    subj_id = exam_id.split("_")[0]
    ex_path_json = (
        f"{igcse_path}{sep}{subj_id}{sep}detected{sep}{exam_id}.json"
    )
    ex_path_pdf = f"{igcse_path}{sep}{subj_id}{sep}exams{sep}{exam_id}.pdf"
    engine = None
    ex_q_list = []


def get_curr_exam_questions() -> list[QuestionBase]:
    global ex_path_json, ex_q_list
    if ex_q_list:
        return ex_q_list
    ex_json = json.loads(open(ex_path_json, "r", encoding="utf-8").read())
    q_list: QuestionBase = []
    for qd in ex_json:
        q_list.append(QuestionBase.__from_dict__(qd, shallow=True))
    ex_q_list = q_list
    return q_list


# def render_curr_exam_question_on_surface(
#     q_nr, scale=4, clean=False, debug=False
# ):
#     global exam_id, subj_id, ex_path_json, ex_path_pdf, engine
#     q_list = get_curr_exam_questions()
#     if q_nr > len(ex_q_list):
#         print(f"SKIPING: exam {exam_id} has only {len(q_list)} Question !!")
#         return None
#     engine = PdfEngine(scale, debug, clean)
#     engine.initialize_file(ex_path_pdf)
#
#     # TODO: use the new PdfEngine API
#     engine.question_detector.preset_detectors(
#         engine.scaled_page_height * scale,
#         engine.scaled_page_width * scale,
#         q_list,
#     )
#     q = q_list[q_nr - 1]
#     surfs_dict: dict[int, cairo.ImageSurface] = {}
#
#     for page in q.pages:
#         print("rendering page ..", page)
#         engine.load_page_content(page, BaseRenderer)
#         if debug:
#             engine.debug_original_stream()
#         engine.execute_page_stream(mode=-1)
#         curr_surf = engine.renderer.surface
#         surfs_dict[page] = curr_surf
#         engine.question_detector.calc_page_segments_and_height(
#             curr_surf, page, is_question=True
#         )
#         print(
#             "number of seq", len(engine.question_detector.page_segments[page])
#         )
#
#     # engine.question_detector.on_finish()
#
#     out_surf = engine.question_detector.draw_all_pages_to_single_png(
#         surfs_dict, None, [q_nr], per_question=True
#     )
#
#     return out_surf


def get_question_orc_text(question_id: str):
    pass


def get_question_embeddings(question_id: str):
    pass


def load_subjects_files():
    sub_dict: dict[str, Subject] = {}
    for sub in all_subjects:
        sub_dict[sub] = Subject(sub)
    return sub_dict


# *****************************************************
# ************   Internal Tools (Only) ****************


def ocr_a_question_and_save_result(q_surface: cairo.ImageSurface):
    pass


def embedd_a_question_and_save_result(q_ocr_text: str):
    pass
