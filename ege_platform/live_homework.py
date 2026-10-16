"""Opt-in extension of EXISTING EGE BLIZKO teacher/student WebApps.

Not a second Telegram bot or identity database. All POST requests are authorized
using already-deployed EGE admin/student launch and Telegram initData verifiers.
Disabled by default; enable only after a production SQLite snapshot and review.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .homework_core import HomeworkStore, AccessDenied, InvalidAction
from .webapp_api import HomeworkAPI

ROOT = Path(__file__).resolve().parent
_PREVIOUS_GET = None
_PREVIOUS_POST = None
_INSTALLED = False
_API = None


def _page(self, filename):
    body = (ROOT / filename).read_bytes()
    self.send_response(200)
    self.send_header('Content-Type','text/html; charset=utf-8')
    self.send_header('Content-Length',str(len(body)))
    self.send_header('Cache-Control','no-store, private')
    self.send_header('X-Content-Type-Options','nosniff')
    self.send_header('Referrer-Policy','no-referrer')
    self.send_header('X-Frame-Options','SAMEORIGIN')
    self.end_headers()
    self.wfile.write(body)


def _get(self):
    path = urlsplit(self.path).path
    if path == '/lms/teacher':
        return _page(self, 'teacher_homework.html')
    if path == '/lms/student':
        return _page(self, 'student_homework.html')
    return _PREVIOUS_GET(self)


def _post(self):
    path = urlsplit(self.path).path
    if path != '/lms/api':
        return _PREVIOUS_POST(self)

    # Imports are deferred: never change any other bot's startup on import.
    import ege_admin_webapp
    import ege_student_webapp
    try:
        length = int(self.headers.get('Content-Length','0'))
        if length < 2 or length > 50000:
            self._send_json(413, {'ok':False,'error':'invalid_request_size'})
            return
        request = json.loads(self.rfile.read(length))
        if not isinstance(request, dict):
            raise InvalidAction('invalid request')
        role = request.get('role')
        if role == 'teacher':
            teacher_uid = ege_admin_webapp._validate_launch_token(request.get('launch'))
            if not teacher_uid or teacher_uid != ege_admin_webapp._admin_id():
                raise AccessDenied('unauthorized')
            data = _API.teacher(teacher_uid, request, ege_admin_webapp._student_rows())
        elif role == 'student':
            tg_uid = (
                ege_student_webapp._validate_telegram_init_data(request.get('init_data'))
                or ege_student_webapp._validate_launch_token(request.get('launch'))
            )
            if tg_uid is None:
                raise AccessDenied('unauthorized')
            student = ege_student_webapp.student_cabinet._student_by_telegram(int(tg_uid))
            if not student:
                raise AccessDenied('not a linked student')
            data = _API.student(int(student[0]), request)
        else:
            raise AccessDenied('unauthorized')
        self._send_json(200, data)
    except AccessDenied:
        self._send_json(403,{'ok':False,'error':'access_denied'})
    except (InvalidAction,ValueError,TypeError,KeyError,json.JSONDecodeError):
        self._send_json(400,{'ok':False,'error':'invalid_action'})
    except Exception as exc:
        # Never leak credentials, payload, answers or student data to logs.
        print('EGE LMS homework error: '+type(exc).__name__, flush=True)
        self._send_json(500,{'ok':False,'error':'internal_error'})


def install():
    global _PREVIOUS_GET,_PREVIOUS_POST,_INSTALLED,_API
    if _INSTALLED:
        return
    if os.getenv('EGE_PLATFORM_HOMEWORK_ENABLED') != '1':
        print('EGE LMS homework disabled (no database migrations)',flush=True)
        return
    import ege_student_webapp
    store = HomeworkStore(ege_student_webapp.bot.COREAPP_DB_PATH)
    store.initialize()  # additive lms_* tables; snapshot BEFORE activating feature
    _API = HomeworkAPI(store)
    handler = ege_student_webapp.bot.CoreAppWebhookHandler
    _PREVIOUS_GET = handler.do_GET
    _PREVIOUS_POST = handler.do_POST
    handler.do_GET = _get
    handler.do_POST = _post
    _INSTALLED = True
    print('EGE LMS homework active: existing identities, shared COREAPP DB',flush=True)
