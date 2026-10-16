"""Temporary-SQLite regression tests for the first EGE BLIZKO homework."""
import json
import tempfile
import unittest
from pathlib import Path
from ege_platform.homework_core import HomeworkStore, AccessDenied, InvalidAction


class HomeworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = HomeworkStore(Path(self.temp.name) / 'test.sqlite3')
        self.store.initialize()
        self.course = self.store.create_course('teacher1', 'ЕГЭ Химия')
        self.store.enroll('teacher1', self.course, 'student1')
        self.store.enroll('teacher1', self.course, 'student2')
        self.lesson = self.store.add_lesson('teacher1', self.course, 'Оксиды')
        self.q1 = self.store.add_private_question(
            'teacher1','Оксиды','Введите последовательность','sequence',
            ['0132'],verified=True
        )
        self.q2 = self.store.add_shared_verified_question(
            True,'Оксиды','Укажите число','number',['0,25']
        )
        self.q3 = self.store.add_private_question(
            'teacher1','Оксиды','Обоснуйте решение','extended',[],verified=True
        )

    def tearDown(self):
        self.temp.cleanup()

    def work(self, questions=None):
        return self.store.create_draft(
            'teacher1',self.course,self.lesson,'ДЗ №1',
            questions or [self.q1,self.q2],['student1']
        )

    def test_end_to_end_teacher_student_result(self):
        aid = self.work()
        self.assertTrue(self.store.publish('teacher1',aid))
        self.assertFalse(self.store.publish('teacher1',aid))
        view = self.store.student_assignment('student1',aid)
        self.assertEqual(len(view['questions']),2)
        self.assertNotIn('answer_keys',json.dumps(view))
        self.store.submit('student1',aid,{'1':'0132','2':'0.25'})
        self.assertEqual(self.store.teacher_results('teacher1',aid)[0]['status'],'checking')
        self.store.review('teacher1',aid,'student1','accepted')
        self.assertEqual(self.store.student_progress('student1')[0]['points'],2)

    def test_digit_sequence_differs_from_number(self):
        aid=self.work()
        self.store.publish('teacher1',aid)
        self.store.submit('student1',aid,{'1':'132','2':'0,25'})
        scores=json.loads(self.store.teacher_results('teacher1',aid)[0]['auto_scores'])
        self.assertEqual(scores,{'1':0,'2':1})

    def test_revision_creates_second_immutable_attempt(self):
        aid=self.work()
        self.store.publish('teacher1',aid)
        self.store.submit('student1',aid,{'1':'132','2':'0.25'})
        with self.assertRaises(InvalidAction):
            self.store.submit('student1',aid,{'1':'0132','2':'0.25'})
        with self.assertRaises(InvalidAction):
            self.store.review('teacher1',aid,'student1','revision_requested')
        self.store.review('teacher1',aid,'student1','revision_requested',
                          feedback='Исправьте последовательность')
        self.store.submit('student1',aid,{'1':'0132','2':'0.25'})
        self.store.review('teacher1',aid,'student1','accepted')
        with self.store.connect() as db:
            rows=db.execute(
                'SELECT attempt,answers FROM lms_submissions WHERE assignment_id=? ORDER BY attempt',
                (aid,)
            ).fetchall()
        self.assertEqual(len(rows),2)
        self.assertEqual(json.loads(rows[0]['answers'])['1'],'132')
        self.assertEqual(self.store.student_progress('student1')[0]['attempt'],2)

    def test_manual_extended_answer(self):
        aid=self.work([self.q3])
        self.store.publish('teacher1',aid)
        self.store.submit('student1',aid,{'1':'Решение'})
        with self.assertRaises(InvalidAction):
            self.store.review('teacher1',aid,'student1','accepted')
        self.store.review('teacher1',aid,'student1','accepted',manual_scores={'1':1})
        self.assertEqual(self.store.student_progress('student1')[0]['points'],1)

    def test_tenant_and_recipient_isolation(self):
        aid=self.work()
        self.store.publish('teacher1',aid)
        with self.assertRaises(AccessDenied):
            self.store.teacher_results('teacher2',aid)
        with self.assertRaises(AccessDenied):
            self.store.publish('teacher2',aid)
        with self.assertRaises(AccessDenied):
            self.store.student_assignment('student2',aid)
        with self.assertRaises(AccessDenied):
            self.store.submit('student2',aid,{'1':'0132','2':'0.25'})
        with self.assertRaises(AccessDenied):
            self.store.create_draft('teacher2',self.course,self.lesson,'x',[self.q1],['student1'])

    def test_banks_do_not_leak_keys_or_private_questions(self):
        self.assertEqual(len(self.store.bank('teacher1')),3)
        self.assertEqual(len(self.store.bank('teacher2')),1)
        self.assertNotIn('answer_keys',json.dumps(self.store.bank('teacher1')))
        other=self.store.create_course('teacher2','Other')
        self.store.enroll('teacher2',other,'student2')
        lesson=self.store.add_lesson('teacher2',other,'Other')
        with self.assertRaises(AccessDenied):
            self.store.create_draft('teacher2',other,lesson,'x',[self.q1],['student2'])

    def test_published_work_is_frozen(self):
        aid=self.work()
        self.store.publish('teacher1',aid)
        with self.store.connect() as db:
            db.execute(
                """UPDATE lms_questions SET body='changed',answer_keys='["0"]' WHERE id=?""",
                (self.q1,)
            )
        self.assertEqual(
            self.store.student_assignment('student1',aid)['questions'][0]['body'],
            'Введите последовательность'
        )
        self.store.submit('student1',aid,{'1':'0132','2':'0.25'})
        scores=json.loads(self.store.teacher_results('teacher1',aid)[0]['auto_scores'])
        self.assertEqual(scores['1'],1)

    def test_unverified_question_and_draft_are_not_visible(self):
        bad=self.store.add_private_question(
            'teacher1','Оксиды','Требует сверки','text',['ответ'],verified=False
        )
        with self.assertRaises(AccessDenied):
            self.store.create_draft('teacher1',self.course,self.lesson,'x',[bad],['student1'])
        aid=self.work()
        with self.assertRaises(AccessDenied):
            self.store.student_assignment('student1',aid)
        with self.store.connect() as db:
            db.execute("UPDATE lms_questions SET status='draft' WHERE id=?",(self.q1,))
        with self.assertRaises(InvalidAction):
            self.store.publish('teacher1',aid)
        with self.store.connect() as db:
            self.assertEqual(db.execute(
                'SELECT COUNT(*) FROM lms_assignment_items WHERE assignment_id=?',
                (aid,)
            ).fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
