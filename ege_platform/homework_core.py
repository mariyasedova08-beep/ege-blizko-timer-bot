"""ЕГЭ БЛИЗКО: isolated homework vertical slice. NOT wired to production.

The caller must derive tenant/student identity from a verified session.
Never expose answer_keys to a student and never reuse PREPODMIN data.
"""
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path


class AccessDenied(Exception):
    pass


class InvalidAction(Exception):
    pass


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS lms_courses(
 id INTEGER PRIMARY KEY, teacher_uid TEXT NOT NULL, title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lms_enrollments(
 course_id INTEGER NOT NULL REFERENCES lms_courses(id), student_uid TEXT NOT NULL,
 PRIMARY KEY(course_id, student_uid));
CREATE TABLE IF NOT EXISTS lms_lessons(
 id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES lms_courses(id),
 title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lms_questions(
 id INTEGER PRIMARY KEY, owner_uid TEXT,
 bank TEXT NOT NULL CHECK(bank IN ('shared','private')),
 version INTEGER NOT NULL DEFAULT 1,
 status TEXT NOT NULL CHECK(status IN ('draft','verified','archived')),
 topic TEXT NOT NULL, body TEXT NOT NULL,
 answer_type TEXT NOT NULL CHECK(answer_type IN ('sequence','number','text','extended')),
 answer_keys TEXT NOT NULL, max_score INTEGER NOT NULL CHECK(max_score>0),
 CHECK((bank='shared' AND owner_uid IS NULL) OR
       (bank='private' AND owner_uid IS NOT NULL)));
CREATE TABLE IF NOT EXISTS lms_assignments(
 id INTEGER PRIMARY KEY, teacher_uid TEXT NOT NULL,
 course_id INTEGER NOT NULL REFERENCES lms_courses(id),
 lesson_id INTEGER NOT NULL REFERENCES lms_lessons(id),
 title TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
 question_ids TEXT NOT NULL, due_at TEXT, published_at TEXT);
CREATE TABLE IF NOT EXISTS lms_assignment_items(
 assignment_id INTEGER NOT NULL REFERENCES lms_assignments(id),
 ordinal INTEGER NOT NULL, question_id INTEGER NOT NULL,
 version INTEGER NOT NULL, topic TEXT NOT NULL, body TEXT NOT NULL,
 answer_type TEXT NOT NULL, answer_keys TEXT NOT NULL, max_score INTEGER NOT NULL,
 PRIMARY KEY(assignment_id, ordinal));
CREATE TABLE IF NOT EXISTS lms_recipients(
 assignment_id INTEGER NOT NULL REFERENCES lms_assignments(id),
 student_uid TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'not_started',
 latest_attempt INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(assignment_id,student_uid));
CREATE TABLE IF NOT EXISTS lms_submissions(
 id INTEGER PRIMARY KEY, assignment_id INTEGER NOT NULL,
 student_uid TEXT NOT NULL, attempt INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('checking','accepted','revision_requested')),
 answers TEXT NOT NULL, auto_scores TEXT NOT NULL,
 final_scores TEXT, feedback TEXT,
 submitted_at TEXT NOT NULL DEFAULT(datetime('now')), reviewed_at TEXT,
 UNIQUE(assignment_id,student_uid,attempt),
 FOREIGN KEY(assignment_id,student_uid) REFERENCES lms_recipients(assignment_id,student_uid));
CREATE TABLE IF NOT EXISTS lms_events(
 id INTEGER PRIMARY KEY, assignment_id INTEGER NOT NULL, actor_uid TEXT NOT NULL,
 kind TEXT NOT NULL, details TEXT NOT NULL DEFAULT '{}',
 happened_at TEXT NOT NULL DEFAULT(datetime('now')));
"""


def _uid(value):
    uid = str(value or '').strip()
    if not uid or len(uid) > 128:
        raise InvalidAction('invalid identity')
    return uid


def _json(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def _score(answer, kind, keys, max_points):
    answer = str(answer if answer is not None else '').strip()
    if kind == 'extended':
        return None  # only a teacher may grade an extended answer
    if not answer:
        return 0
    if kind == 'sequence':
        return max_points if answer.isascii() and answer.isdigit() and answer in keys else 0
    if kind == 'number':
        try:
            number = Decimal(answer.replace(',', '.'))
            if not number.is_finite():
                return 0
            return max_points if any(number == Decimal(str(k).replace(',', '.')) for k in keys) else 0
        except (InvalidOperation, ValueError):
            return 0
    if kind == 'text':
        clean = ' '.join(answer.casefold().split())
        return max_points if clean in {' '.join(str(k).casefold().split()) for k in keys} else 0
    raise InvalidAction('unsupported answer type')


class HomeworkStore:
    def __init__(self, db_path):
        self.path = str(Path(db_path))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        with self.connect() as db:
            db.executescript(SCHEMA)

    @staticmethod
    def _course(db, teacher_uid, course_id):
        course = db.execute(
            'SELECT * FROM lms_courses WHERE id=? AND teacher_uid=?',
            (course_id, _uid(teacher_uid))
        ).fetchone()
        if course is None:
            raise AccessDenied('course unavailable')
        return course

    @staticmethod
    def _assignment(db, teacher_uid, assignment_id):
        work = db.execute(
            'SELECT * FROM lms_assignments WHERE id=? AND teacher_uid=?',
            (assignment_id, _uid(teacher_uid))
        ).fetchone()
        if work is None:
            raise AccessDenied('assignment unavailable')
        return work

    def create_course(self, teacher_uid, title):
        with self.connect() as db:
            return db.execute(
                'INSERT INTO lms_courses(teacher_uid,title) VALUES(?,?)',
                (_uid(teacher_uid), str(title).strip())
            ).lastrowid

    def enroll(self, teacher_uid, course_id, student_uid):
        with self.connect() as db:
            self._course(db, teacher_uid, course_id)
            db.execute('INSERT OR IGNORE INTO lms_enrollments VALUES(?,?)',
                       (course_id, _uid(student_uid)))

    def add_lesson(self, teacher_uid, course_id, title):
        with self.connect() as db:
            self._course(db, teacher_uid, course_id)
            return db.execute('INSERT INTO lms_lessons(course_id,title) VALUES(?,?)',
                              (course_id, str(title).strip())).lastrowid

    def _insert_question(self, owner, bank, topic, body, answer_type, keys, max_score, verified):
        if answer_type not in ('sequence','number','text','extended'):
            raise InvalidAction('invalid answer type')
        if not str(body).strip() or not str(topic).strip() or int(max_score) < 1:
            raise InvalidAction('missing question fields')
        if answer_type != 'extended' and (
            not isinstance(keys, list) or not keys or
            not all(str(k).strip() for k in keys)
        ):
            raise InvalidAction('approved answer keys required')
        with self.connect() as db:
            return db.execute(
                """INSERT INTO lms_questions
                (owner_uid,bank,status,topic,body,answer_type,answer_keys,max_score)
                VALUES(?,?,?,?,?,?,?,?)""",
                (owner, bank, 'verified' if verified else 'draft',
                 str(topic).strip(), str(body).strip(), answer_type,
                 _json(keys), int(max_score))
            ).lastrowid

    def add_private_question(self, teacher_uid, topic, body, answer_type,
                             keys, max_score=1, verified=False):
        return self._insert_question(
            _uid(teacher_uid), 'private', topic, body,
            answer_type, keys, max_score, verified
        )

    def add_shared_verified_question(self, curator_authorized, topic, body,
                                     answer_type, keys, max_score=1):
        # A production caller must verify the curator's role server-side.
        if curator_authorized is not True:
            raise AccessDenied('curator permission required')
        return self._insert_question(
            None, 'shared', topic, body, answer_type, keys, max_score, True
        )

    def bank(self, teacher_uid):
        with self.connect() as db:
            rows = db.execute(
                """SELECT id,bank,version,topic,body,answer_type,max_score
                FROM lms_questions WHERE status='verified'
                AND (bank='shared' OR (bank='private' AND owner_uid=?))
                ORDER BY id""", (_uid(teacher_uid),)
            ).fetchall()
            return [dict(row) for row in rows]  # no keys

    def create_draft(self, teacher_uid, course_id, lesson_id, title,
                     question_ids, recipients):
        teacher_uid = _uid(teacher_uid)
        question_ids = list(question_ids)
        recipients = [_uid(item) for item in recipients]
        if not question_ids or len(set(question_ids)) != len(question_ids):
            raise InvalidAction('questions required; no duplicates')
        if not recipients or len(set(recipients)) != len(recipients):
            raise InvalidAction('recipients required; no duplicates')
        with self.connect() as db:
            self._course(db, teacher_uid, course_id)
            if not db.execute('SELECT 1 FROM lms_lessons WHERE id=? AND course_id=?',
                              (lesson_id, course_id)).fetchone():
                raise AccessDenied('lesson unavailable')
            for student_uid in recipients:
                if not db.execute(
                    'SELECT 1 FROM lms_enrollments WHERE course_id=? AND student_uid=?',
                    (course_id, student_uid)
                ).fetchone():
                    raise AccessDenied('student not enrolled')
            for qid in question_ids:
                if not db.execute(
                    """SELECT 1 FROM lms_questions WHERE id=? AND status='verified'
                    AND (bank='shared' OR (bank='private' AND owner_uid=?))""",
                    (qid, teacher_uid)
                ).fetchone():
                    raise AccessDenied('question unavailable or unverified')
            aid = db.execute(
                """INSERT INTO lms_assignments
                (teacher_uid,course_id,lesson_id,title,question_ids)
                VALUES(?,?,?,?,?)""",
                (teacher_uid, course_id, lesson_id, str(title).strip(), _json(question_ids))
            ).lastrowid
            db.executemany('INSERT INTO lms_recipients(assignment_id,student_uid) VALUES(?,?)',
                           [(aid, uid) for uid in recipients])
            return aid

    def publish(self, teacher_uid, assignment_id):
        """Idempotent publication with private, frozen answer-key snapshots."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            assignment = self._assignment(db, teacher_uid, assignment_id)
            if assignment['status'] == 'published':
                return False
            for pos, qid in enumerate(json.loads(assignment['question_ids']), 1):
                q = db.execute(
                    """SELECT * FROM lms_questions WHERE id=? AND status='verified'
                    AND (bank='shared' OR owner_uid=?)""",
                    (qid, _uid(teacher_uid))
                ).fetchone()
                if q is None:
                    raise InvalidAction('question no longer verified')
                db.execute(
                    """INSERT INTO lms_assignment_items
                    (assignment_id,ordinal,question_id,version,topic,body,
                    answer_type,answer_keys,max_score) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (assignment_id, pos, qid, q['version'], q['topic'],
                     q['body'], q['answer_type'], q['answer_keys'], q['max_score'])
                )
            db.execute(
                """UPDATE lms_assignments SET status='published',
                   published_at=datetime('now') WHERE id=?""", (assignment_id,)
            )
            db.execute('INSERT INTO lms_events(assignment_id,actor_uid,kind) VALUES(?,?,?)',
                       (assignment_id, _uid(teacher_uid), 'published'))
            return True

    def student_assignment(self, student_uid, assignment_id):
        with self.connect() as db:
            row = db.execute(
                """SELECT a.id,a.title,a.lesson_id,r.status,r.latest_attempt
                FROM lms_assignments a JOIN lms_recipients r ON a.id=r.assignment_id
                WHERE a.id=? AND r.student_uid=? AND a.status='published'""",
                (assignment_id, _uid(student_uid))
            ).fetchone()
            if row is None:
                raise AccessDenied('assignment unavailable')
            questions = db.execute(
                """SELECT ordinal,topic,body,answer_type,max_score
                FROM lms_assignment_items WHERE assignment_id=? ORDER BY ordinal""",
                (assignment_id,)
            ).fetchall()
            return {'assignment':dict(row),'questions':[dict(q) for q in questions]}

    def submit(self, student_uid, assignment_id, answers):
        student_uid = _uid(student_uid)
        if not isinstance(answers, dict):
            raise InvalidAction('answers must map ordinals to values')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            recipient = db.execute(
                """SELECT r.status,r.latest_attempt
                FROM lms_recipients r JOIN lms_assignments a ON a.id=r.assignment_id
                WHERE a.id=? AND r.student_uid=? AND a.status='published'""",
                (assignment_id, student_uid)
            ).fetchone()
            if recipient is None:
                raise AccessDenied('assignment unavailable')
            if recipient['status'] not in ('not_started','revision_requested'):
                raise InvalidAction('already submitted; revision not requested')
            items = db.execute(
                """SELECT ordinal,answer_type,answer_keys,max_score
                FROM lms_assignment_items WHERE assignment_id=? ORDER BY ordinal""",
                (assignment_id,)
            ).fetchall()
            normalized = {str(k):str(v).strip() for k,v in answers.items()}
            if set(normalized) != {str(q['ordinal']) for q in items}:
                raise InvalidAction('answers must match question ordinals')
            auto = {
                str(q['ordinal']):_score(
                    normalized[str(q['ordinal'])], q['answer_type'],
                    json.loads(q['answer_keys']), q['max_score']
                ) for q in items
            }
            attempt = recipient['latest_attempt']+1
            submission_id = db.execute(
                """INSERT INTO lms_submissions
                (assignment_id,student_uid,attempt,status,answers,auto_scores)
                VALUES(?,?,?,'checking',?,?)""",
                (assignment_id, student_uid, attempt, _json(normalized), _json(auto))
            ).lastrowid
            db.execute(
                """UPDATE lms_recipients SET status='checking',latest_attempt=?
                WHERE assignment_id=? AND student_uid=?""",
                (attempt, assignment_id, student_uid)
            )
            db.execute(
                'INSERT INTO lms_events(assignment_id,actor_uid,kind,details) VALUES(?,?,?,?)',
                (assignment_id, student_uid, 'submitted', _json({'attempt':attempt}))
            )
            return submission_id

    def review(self, teacher_uid, assignment_id, student_uid, decision,
               manual_scores=None, feedback=''):
        if decision not in ('accepted','revision_requested'):
            raise InvalidAction('invalid decision')
        if decision == 'revision_requested' and not str(feedback).strip():
            raise InvalidAction('revision requires a reason')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._assignment(db, teacher_uid, assignment_id)
            student_uid = _uid(student_uid)
            recipient = db.execute(
                'SELECT * FROM lms_recipients WHERE assignment_id=? AND student_uid=?',
                (assignment_id, student_uid)
            ).fetchone()
            if recipient is None or recipient['status'] != 'checking':
                raise InvalidAction('no attempt awaiting review')
            attempt = db.execute(
                """SELECT * FROM lms_submissions WHERE assignment_id=?
                AND student_uid=? AND attempt=? AND status='checking'""",
                (assignment_id, student_uid, recipient['latest_attempt'])
            ).fetchone()
            if attempt is None:
                raise InvalidAction('submission unavailable')
            points = json.loads(attempt['auto_scores'])
            maximum = {
                str(x['ordinal']):x['max_score']
                for x in db.execute(
                    'SELECT ordinal,max_score FROM lms_assignment_items WHERE assignment_id=?',
                    (assignment_id,)
                )
            }
            for ordinal, score in (manual_scores or {}).items():
                ordinal = str(ordinal)
                if ordinal not in maximum or type(score) is not int or not 0 <= score <= maximum[ordinal]:
                    raise InvalidAction('invalid teacher score')
                points[ordinal] = score
            if decision == 'accepted' and any(s is None for s in points.values()):
                raise InvalidAction('extended answers require manual grading')
            db.execute(
                """UPDATE lms_submissions SET status=?,final_scores=?,feedback=?,
                reviewed_at=datetime('now') WHERE id=?""",
                (decision, _json(points), str(feedback), attempt['id'])
            )
            db.execute(
                """UPDATE lms_recipients SET status=?
                WHERE assignment_id=? AND student_uid=?""",
                (decision, assignment_id, student_uid)
            )
            db.execute(
                'INSERT INTO lms_events(assignment_id,actor_uid,kind,details) VALUES(?,?,?,?)',
                (assignment_id,_uid(teacher_uid),'reviewed',
                 _json({'decision':decision,'student_uid':student_uid}))
            )

    def teacher_results(self, teacher_uid, assignment_id):
        with self.connect() as db:
            self._assignment(db, teacher_uid, assignment_id)
            return [dict(row) for row in db.execute(
                """SELECT r.student_uid,r.status,r.latest_attempt,
                s.answers,s.auto_scores,s.final_scores,s.feedback
                FROM lms_recipients r LEFT JOIN lms_submissions s
                  ON s.assignment_id=r.assignment_id AND s.student_uid=r.student_uid
                  AND s.attempt=r.latest_attempt
                WHERE r.assignment_id=? ORDER BY r.student_uid""",
                (assignment_id,)
            )]

    def student_progress(self, student_uid):
        with self.connect() as db:
            rows = db.execute(
                """SELECT s.assignment_id,a.title,s.attempt,s.final_scores
                FROM lms_submissions s JOIN lms_assignments a ON s.assignment_id=a.id
                JOIN lms_recipients r
                  ON r.assignment_id=s.assignment_id AND r.student_uid=s.student_uid
                WHERE s.student_uid=? AND s.status='accepted' AND a.status='published'
                ORDER BY s.id""", (_uid(student_uid),)
            ).fetchall()
            result = []
            for row in rows:
                points = json.loads(row['final_scores'])
                maximum = db.execute(
                    'SELECT SUM(max_score) FROM lms_assignment_items WHERE assignment_id=?',
                    (row['assignment_id'],)
                ).fetchone()[0]
                result.append({
                    'assignment_id':row['assignment_id'],'title':row['title'],
                    'attempt':row['attempt'],'points':sum(points.values()),
                    'max_points':maximum
                })
            return result
