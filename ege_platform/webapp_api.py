"""Authenticated role-scoped API for the first EGE BLIZKO platform homework.

Callers MUST verify Telegram/launch credentials and derive identities server-side.
No role, student ID, tenant ID or grading key is accepted from the browser.
"""
import json

from .homework_core import HomeworkStore, AccessDenied, InvalidAction


def _number(value, label):
    if isinstance(value, bool):
        raise InvalidAction('invalid ' + label)
    try:
        result = int(value)
    except (ValueError, TypeError, OverflowError):
        raise InvalidAction('invalid ' + label) from None
    if result <= 0:
        raise InvalidAction('invalid ' + label)
    return result


class HomeworkAPI:
    def __init__(self, store: HomeworkStore):
        self.store = store

    def teacher(self, verified_teacher_uid, payload, roster):
        """Only the live teacher WebApp may call this after verified admin auth."""
        teacher = 'ege-admin:' + str(verified_teacher_uid)
        permitted = {
            str(x['id']): {'id': int(x['id']), 'name': str(x['name'])}
            for x in roster if x.get('linked') and x.get('id') is not None
        }
        action = str(payload.get('action') or 'overview')
        if action == 'overview':
            with self.store.connect() as db:
                courses = [dict(r) for r in db.execute(
                    'SELECT id,title FROM lms_courses WHERE teacher_uid=? ORDER BY id DESC',
                    (teacher,))]
                lessons = [dict(r) for r in db.execute(
                    'SELECT l.id,l.course_id,l.title FROM lms_lessons l '
                    'JOIN lms_courses c ON c.id=l.course_id '
                    'WHERE c.teacher_uid=? ORDER BY l.id DESC', (teacher,))]
                works = [dict(r) for r in db.execute(
                    'SELECT id,course_id,lesson_id,title,status FROM lms_assignments '
                    'WHERE teacher_uid=? ORDER BY id DESC',(teacher,))]
            return {'ok': True,'courses':courses,'lessons':lessons,'works':works,
                    'questions':self.store.bank(teacher),
                    'students':list(permitted.values())}
        if action == 'course_create':
            title = str(payload.get('title') or '').strip()
            if not 1 <= len(title) <= 120:
                raise InvalidAction('course title required')
            return {'ok':True,'course_id':self.store.create_course(teacher,title)}
        if action == 'lesson_create':
            title = str(payload.get('title') or '').strip()
            if not 1 <= len(title) <= 160:
                raise InvalidAction('lesson title required')
            return {'ok':True,'lesson_id':self.store.add_lesson(
                teacher,_number(payload.get('course_id'),'course'),title)}
        if action == 'question_create':
            if payload.get('verified') is not True:
                raise InvalidAction('approve the answer key before publishing to your bank')
            topic = str(payload.get('topic') or '').strip()
            body = str(payload.get('body') or '').strip()
            kind = str(payload.get('answer_type') or '').strip()
            if not 1 <= len(topic) <= 120 or not 1 <= len(body) <= 5000:
                raise InvalidAction('question fields required')
            keys = payload.get('answer_keys')
            if not isinstance(keys,list) or len(keys)>20 or any(len(str(x))>400 for x in keys):
                raise InvalidAction('invalid answer keys')
            qid = self.store.add_private_question(teacher,topic,body,kind,keys,
                                                  verified=True)
            return {'ok':True,'question_id':qid}
        if action == 'draft_create':
            students = payload.get('students')
            ids = payload.get('question_ids')
            if not isinstance(students,list) or not 1<=len(students)<=100 or (
                not isinstance(ids,list) or not 1<=len(ids)<=100
            ):
                raise InvalidAction('questions and recipients required')
            recipient_ids = [_number(item,'student') for item in students]
            if len(set(recipient_ids))!=len(recipient_ids) or any(str(x) not in permitted for x in recipient_ids):
                raise AccessDenied('unknown or unlinked student')
            qids = [_number(item,'question') for item in ids]
            course = _number(payload.get('course_id'),'course')
            for sid in recipient_ids:
                self.store.enroll(teacher,course,'core-student:'+str(sid))
            aid = self.store.create_draft(
                teacher,course,_number(payload.get('lesson_id'),'lesson'),
                str(payload.get('title') or 'Домашняя работа').strip()[:160],
                qids,['core-student:'+str(x) for x in recipient_ids])
            return {'ok':True,'assignment_id':aid}
        if action == 'publish':
            changed=self.store.publish(teacher,_number(payload.get('assignment_id'),'assignment'))
            return {'ok':True,'changed':changed}
        if action == 'results':
            return {'ok':True,'items':self.store.teacher_results(
                teacher,_number(payload.get('assignment_id'),'assignment'))}
        if action == 'review':
            sid=_number(payload.get('student_id'),'student')
            if str(sid) not in permitted:
                raise AccessDenied('unknown or unlinked student')
            self.store.review(
                teacher,_number(payload.get('assignment_id'),'assignment'),
                'core-student:'+str(sid),str(payload.get('decision') or ''),
                payload.get('manual_scores'),str(payload.get('feedback') or '')[:2000])
            return {'ok':True}
        raise InvalidAction('unknown action')

    def student(self, verified_student_internal_id, payload):
        """The live student WebApp must resolve the student from verified Telegram UID."""
        student = 'core-student:' + str(verified_student_internal_id)
        action = str(payload.get('action') or 'overview')
        if action == 'overview':
            with self.store.connect() as db:
                rows=db.execute(
                    """SELECT a.id,a.title,a.lesson_id,a.published_at,r.status,r.latest_attempt
                       FROM lms_assignments a
                       JOIN lms_recipients r ON a.id=r.assignment_id
                       WHERE a.status='published' AND r.student_uid=?
                       ORDER BY a.id DESC LIMIT 100""",(student,)).fetchall()
            return {'ok':True,'works':[dict(r) for r in rows],
                    'progress':self.store.student_progress(student)}
        if action == 'open':
            return {'ok':True,'data':self.store.student_assignment(
                student,_number(payload.get('assignment_id'),'assignment'))}
        if action == 'submit':
            sid=self.store.submit(
                student,_number(payload.get('assignment_id'),'assignment'),
                payload.get('answers'))
            return {'ok':True,'submission_id':sid}
        raise InvalidAction('unknown action')
