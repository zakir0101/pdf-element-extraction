import cairo
from .pdf_utils import igcse_path,all_subjects




def get_subjects():
    rturn all_subjects

def get_subject_papers(subject_id:str):
    pass

def get_papers_topics(subject_id:str,paper:int):
    pass

def get_topics_question(subject_id,paper:int,topic:str):
    pass

def get_question_surface(question_id:str) -> cairo.cairo.ImageSurface:
    pass

def get_exams_question(exam_id:str) :
    pass

def get_question_orc_text(question_id:str):
    pass

def get_question_embeddings(question_id:str):
    pass


def ocr_a_question_and_save_result(q_surface:cairo.ImageSurface):
    pass

def embedd_a_question_and_save_result(q_ocr_text:str):
    pass




