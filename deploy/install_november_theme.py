#!/usr/bin/python3
"""Add a date-gated November skin to two live HTML files; never restart bot."""
import base64
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import time
import urllib.request

APP = Path('/opt/bots/ege-blizko')
STATE = Path('/var/lib/ege-november-theme-20261101')
RELEASE = 'EGE-NOVEMBER-THEME-20261101-REVIEWED'
ROLLBACK = RELEASE+'-ROLLBACK'
FILES = {'teacher':'ege_admin_webapp.html','student':'ege_student_webapp.html'}
URLS = {'teacher':'/admin-app','student':'/student-app'}
CSS = base64.b64decode('Lyog0JXQk9CtINCR0JvQmNCX0JrQniDCtyDQndC+0Y/QsdGA0YwuIEFkZGl0aXZlIGNhYmluZXQgc2tpbjsgbm8gY291cnNlIGxvZ2ljLiAqLwpib2R5LmVnZS1ub3ZlbWJlcnsKIC0tbWlsazojRjhGNUYyOy0taW5rOiMyNDIwMjU7LS1zb2Z0OiNFRURGRTY7LS1ob3Q6I0I2Mzg3MDstLXBpbms6I0I2Mzg3MDsKIC0tcGFwZXI6I0ZGRkRGQTstLWxpbmU6I0U1REFERTstLW11dGVkOiM3MTYzNkM7LS1yZWQ6I0I2Mzc1ODsKIC0tc2hhZG93OjAgOHB4IDI4cHggcmdiYSg2NCw0MCw1MywuMDQ1KTsKIGJhY2tncm91bmQ6cmFkaWFsLWdyYWRpZW50KGVsbGlwc2UgYXQgOCUgMyUsI0VERTJFOCAwLHRyYW5zcGFyZW50IDM4JSksCiBsaW5lYXItZ3JhZGllbnQoMTYwZGVnLCNGOEY1RjIsI0YyRUVFRCA4NSUpO2NvbG9yOnZhcigtLWluayk7CiBiYWNrZ3JvdW5kLWF0dGFjaG1lbnQ6Zml4ZWQ7Cn0KLmVnZS1ub3ZlbWJlciAuYXBwe3BhZGRpbmctdG9wOjI0cHh9Ci5lZ2Utbm92ZW1iZXIgLnRvcHthbGlnbi1pdGVtczpjZW50ZXI7bWFyZ2luLWJvdHRvbToxOXB4fQouZWdlLW5vdmVtYmVyIGgxLC5lZ2Utbm92ZW1iZXIgLmJyYW5ke2ZvbnQtd2VpZ2h0OjY1MDtsZXR0ZXItc3BhY2luZzotLjA0ZW19Ci5lZ2Utbm92ZW1iZXIgLmJyYW5kLXBpbGx7YmFja2dyb3VuZDojRTlEQ0UzO2NvbG9yOiM3MTUxNjM7Zm9udC13ZWlnaHQ6NjUwO2xldHRlci1zcGFjaW5nOi4xZW07Zm9udC1zaXplOjEwcHg7Ym9yZGVyOjFweCBzb2xpZCAjRTBDREQ3fQouZWdlLW5vdmVtYmVyIC5sb2dvLC5lZ2Utbm92ZW1iZXIgLmF2YXRhcntiYWNrZ3JvdW5kOiNGM0VBRjA7Ym9yZGVyOjFweCBzb2xpZCAjRTNENERDO2JveC1zaGFkb3c6bm9uZX0KLmVnZS1ub3ZlbWJlciAuaGVyb3tiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCgxMjBkZWcsI0ZGRkRGQiwjRjJFNkVEKTtib3JkZXItY29sb3I6I0RGQ0VENztib3gtc2hhZG93Om5vbmV9Ci5lZ2Utbm92ZW1iZXIgLmhlcm8tdGl0bGUsLmVnZS1ub3ZlbWJlciAuaGVybyAuaGVsbG97Zm9udC13ZWlnaHQ6NjUwfQouZWdlLW5vdmVtYmVyIC5oZXJvIC5iaWd7Zm9udC13ZWlnaHQ6NjUwfQouZWdlLW5vdmVtYmVyIC5wcm9ncmVzc3tiYWNrZ3JvdW5kOiNFNkQ5RTA7aGVpZ2h0OjZweH0KLmVnZS1ub3ZlbWJlciAucHJvZ3Jlc3MgaSwuZWdlLW5vdmVtYmVyIC5wcm9ncmVzcz5kaXZ7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsI0Q5QTZCRiwjQUUzNzZBKX0KLmVnZS1ub3ZlbWJlciAuY2FyZCwuZWdlLW5vdmVtYmVyIC5saXN0LC5lZ2Utbm92ZW1iZXIgLmRheS1wYW5lbCwuZWdlLW5vdmVtYmVyIC5hY3Rpb24sCi5lZ2Utbm92ZW1iZXIgLnN0YXRib3gsLmVnZS1ub3ZlbWJlciAuc3R1ZGVudC1jYXJkLC5lZ2Utbm92ZW1iZXIgLmFuYWx5dGljcy1jYXJkewogYm9yZGVyLWNvbG9yOnZhcigtLWxpbmUpO2JveC1zaGFkb3c6MCA0cHggMThweCByZ2JhKDY0LDQwLDUzLC4wMjUpOwp9Ci5lZ2Utbm92ZW1iZXIgLmNhcmQucGluaywuZWdlLW5vdmVtYmVyIC5kYXktcGFuZWwudG9tb3Jyb3d7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoMTI1ZGVnLCNGRkZERkEsI0YzRTlFRSl9Ci5lZ2Utbm92ZW1iZXIgLmNhcmQgLm51bSwuZWdlLW5vdmVtYmVyIC5jYXJkIGIsLmVnZS1ub3ZlbWJlciAuc3RhdGJveCBie2ZvbnQtd2VpZ2h0OjY1MH0KLmVnZS1ub3ZlbWJlciAuY2FyZCAubGFiZWwsLmVnZS1ub3ZlbWJlciAuc2VjdGlvbi10aXRsZSBzdHJvbmcsLmVnZS1ub3ZlbWJlciAucm93LXRpdGxle2ZvbnQtd2VpZ2h0OjY1MH0KLmVnZS1ub3ZlbWJlciAua3VsZWssLmVnZS1ub3ZlbWJlciAua3VsZWstaGVyb3tiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCgxMjVkZWcsI0Y0RUJFRiwjRTlEOUUzKTtib3JkZXItY29sb3I6I0RDQzdEMztib3gtc2hhZG93Om5vbmV9Ci5lZ2Utbm92ZW1iZXIgLmRpc2NvdW50LC5lZ2Utbm92ZW1iZXIgLnByb2JuaWstc3VtbWFyeXtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCgxMjVkZWcsI0ZGRkRGQiwjRjRFQkYwKTtib3JkZXItY29sb3I6dmFyKC0tbGluZSk7Ym94LXNoYWRvdzpub25lfQouZWdlLW5vdmVtYmVyIC5yYW5rLWhlcm97YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoMTIwZGVnLCMzNDJDMzUsIzU1NDA0RCl9Ci5lZ2Utbm92ZW1iZXIgLnRhYnN7YmFja2dyb3VuZDpyZ2JhKDI0OCwyNDUsMjQyLC45Nyk7Ym9yZGVyLXRvcC1jb2xvcjojREZEMUQ4fQouZWdlLW5vdmVtYmVyIC50YWIuYWN0aXZle2JhY2tncm91bmQ6I0VFREZFNztjb2xvcjojOEQyODU1fQouZWdlLW5vdmVtYmVyIGJ1dHRvbjpmb2N1cy12aXNpYmxlLC5lZ2Utbm92ZW1iZXIgYTpmb2N1cy12aXNpYmxle291dGxpbmU6MnB4IHNvbGlkICNBMzMxNjQ7b3V0bGluZS1vZmZzZXQ6NHB4fQouZWdlLW5vdmVtYmVyIC5ub3ZlbWJlci1iYW5uZXJ7CiBwb3NpdGlvbjpyZWxhdGl2ZTtpc29sYXRpb246aXNvbGF0ZTtvdmVyZmxvdzpoaWRkZW47bWluLWhlaWdodDoxODJweDsKIHBhZGRpbmc6MjRweCAxNzBweCAyNHB4IDI0cHg7bWFyZ2luOjAgMCAxNnB4O2JvcmRlci1yYWRpdXM6MjRweDsKIGNvbG9yOiMzMzJBMzI7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoMTEyZGVnLCNGMUU2RUMgMCUsI0U4RDhFMiA2MiUsI0RFRDBEQiAxMDAlKTsKIGJvcmRlcjoxcHggc29saWQgI0Q4QzNEMDtib3gtc2hhZG93Omluc2V0IDAgMXB4IHJnYmEoMjU1LDI1NSwyNTUsLjgpOwp9Ci5lZ2Utbm92ZW1iZXIgLm5vdmVtYmVyLWJhbm5lcjo6YWZ0ZXJ7CiBjb250ZW50OiIiO3Bvc2l0aW9uOmFic29sdXRlO2luc2V0OjA7ei1pbmRleDotMTtwb2ludGVyLWV2ZW50czpub25lOwogYmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoMTcwZGVnLHJnYmEoMjU1LDI1NSwyNTUsLjQ4KSx0cmFuc3BhcmVudCAzOCUpLAogcmFkaWFsLWdyYWRpZW50KGVsbGlwc2UgYXQgMTAwJSAxMDAlLHJnYmEoMjU1LDI1NSwyNTUsLjU1KSx0cmFuc3BhcmVudCA1NSUpOwp9Ci5lZ2Utbm92ZW1iZXIgLm5vdmVtYmVyLWV5ZWJyb3d7Zm9udC1zaXplOjlweDtmb250LXdlaWdodDo2NTA7bGV0dGVyLXNwYWNpbmc6LjIyZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOiM3MzU2Njg7bWFyZ2luLWJvdHRvbToxM3B4fQouZWdlLW5vdmVtYmVyIC5ub3ZlbWJlci10aXRsZXtmb250LXNpemU6MzFweDtmb250LXdlaWdodDo1NTA7bGluZS1oZWlnaHQ6MS4wODtsZXR0ZXItc3BhY2luZzotLjA0NWVtO21hcmdpbjowO21heC13aWR0aDozMzBweH0KLmVnZS1ub3ZlbWJlciAubm92ZW1iZXItdGl0bGUgZW17Zm9udC1zdHlsZTpub3JtYWw7Y29sb3I6Izk4NDM2RH0KLmVnZS1ub3ZlbWJlciAubm92ZW1iZXItY29weXtmb250LXNpemU6MTJweDtsaW5lLWhlaWdodDoxLjU7Y29sb3I6IzZDNTQ2NDttYXJnaW46MTJweCAwIDA7bWF4LXdpZHRoOjI5MHB4fQouZWdlLW5vdmVtYmVyIC5ub3ZlbWJlci1hcnR7cG9zaXRpb246YWJzb2x1dGU7cmlnaHQ6MDtib3R0b206MDtoZWlnaHQ6MTAwJTt3aWR0aDoxODBweDtwb2ludGVyLWV2ZW50czpub25lfQouZWdlLW5vdmVtYmVyIC5ub3ZlbWJlci1sYWJlbHtwb3NpdGlvbjphYnNvbHV0ZTtyaWdodDoxN3B4O2JvdHRvbToxMnB4O2ZvbnQtc2l6ZTo4cHg7bGV0dGVyLXNwYWNpbmc6LjEyZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOiM3NzVENzB9CkBtZWRpYShtYXgtd2lkdGg6NDgwcHgpewogLmVnZS1ub3ZlbWJlciAuYXBwe3BhZGRpbmctdG9wOjE4cHh9CiAuZWdlLW5vdmVtYmVyIC5ub3ZlbWJlci1iYW5uZXJ7bWluLWhlaWdodDoxOTBweDtwYWRkaW5nOjIycHggMTEycHggMjJweCAxOXB4O2JvcmRlci1yYWRpdXM6MjNweH0KIC5lZ2Utbm92ZW1iZXIgLm5vdmVtYmVyLXRpdGxle2ZvbnQtc2l6ZToyOHB4fQogLmVnZS1ub3ZlbWJlciAubm92ZW1iZXItYXJ0e3dpZHRoOjEyOXB4O3JpZ2h0Oi01cHg7aGVpZ2h0OjkyJX0KIC5lZ2Utbm92ZW1iZXIgLm5vdmVtYmVyLWNvcHl7Zm9udC1zaXplOjExcHg7bWF4LXdpZHRoOjIxNXB4fQogLmVnZS1ub3ZlbWJlciAubm92ZW1iZXItZXllYnJvd3tmb250LXNpemU6OHB4O2xldHRlci1zcGFjaW5nOi4xN2VtfQogLmVnZS1ub3ZlbWJlciAubm92ZW1iZXItbGFiZWx7cmlnaHQ6MTBweDtmb250LXNpemU6N3B4fQp9CkBtZWRpYShwcmVmZXJzLXJlZHVjZWQtbW90aW9uOnJlZHVjZSl7LmVnZS1ub3ZlbWJlciAqe3Njcm9sbC1iZWhhdmlvcjphdXRvIWltcG9ydGFudH19CkBtZWRpYSBwcmludHsuZWdlLW5vdmVtYmVyIC5ub3ZlbWJlci1iYW5uZXJ7ZGlzcGxheTpub25lfX0K').decode()
JS = base64.b64decode('LyogRGVjb3JhdGl2ZSBvbmx5OiBuZXZlciByZWFkcyBzdHVkZW50IGRhdGEsIHNlbmRzIHJlcXVlc3RzIG9yIGVkaXRzIGRlYWRsaW5lcy4gKi8KKGZ1bmN0aW9uICgpIHsKICd1c2Ugc3RyaWN0JzsKIHZhciBzb3VyY2UgPSBkb2N1bWVudC5jdXJyZW50U2NyaXB0OwogdmFyIHJvbGUgPSBzb3VyY2UgJiYgc291cmNlLmdldEF0dHJpYnV0ZSgnZGF0YS1jYWJpbmV0LXJvbGUnKTsKIGlmIChyb2xlICE9PSAndGVhY2hlcicgJiYgcm9sZSAhPT0gJ3N0dWRlbnQnKSByZXR1cm47CiAvLyAxIE5vdmVtYmVyIDIwMjYsIDAwOjAwIEV1cm9wZS9Nb3Njb3cgKFVUQyswMzowMCksIGluZGVwZW5kZW50IG9mCiAvLyB0aGUgYnJvd3NlcidzIHNlbGVjdGVkIHRpbWUgem9uZS4gVW50aWwgdGhlbiB0aGUgY3VycmVudCBza2luIGlzIHVudG91Y2hlZC4KIHZhciBzdGFydHNBdCA9IERhdGUucGFyc2UoJzIwMjYtMTAtMzFUMjE6MDA6MDBaJyk7CiB2YXIgYWN0aXZhdGVkID0gZmFsc2U7CiB2YXIgY2xvY2tUaW1lcjsKIGZ1bmN0aW9uIGFjdGl2YXRlKCkgewogaWYgKGRvY3VtZW50LmJvZHkuZ2V0QXR0cmlidXRlKCdkYXRhLWVnZS1zZWFzb24nKSA9PT0gJ25vdmVtYmVyLTIwMjYnKSByZXR1cm47CiBkb2N1bWVudC5ib2R5LnNldEF0dHJpYnV0ZSgnZGF0YS1lZ2Utc2Vhc29uJywgJ25vdmVtYmVyLTIwMjYnKTsKIGRvY3VtZW50LmJvZHkuY2xhc3NMaXN0LmFkZCgnZWdlLW5vdmVtYmVyJyk7CiB2YXIgYXBwID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwcCcpOwogaWYgKCFhcHApIHJldHVybjsKIC8vIEEgc21hbGwgb3JpZ2luYWwgdmVjdG9yIGlsbHVzdHJhdGlvbjogYmFyZSBicmFuY2hlcywgdHdvIGxlYXZlcywgZnJvc3QKIC8vIGFuZCBLdWxlaydzIHVwcmlnaHQgZWFycyB3aXRoIGEgZHVzdHkgcm9zZSBzY2FyZi4gTm8gcGhvdG8vbmV0d29yayBhc3NldC4KIHZhciBhcnQgPSAnPHN2ZyBjbGFzcz0ibm92ZW1iZXItYXJ0IiB2aWV3Qm94PSIwIDAgMTgwIDIwMCIgYXJpYS1oaWRkZW49InRydWUiIGZvY3VzYWJsZT0iZmFsc2UiPicrCiAnPGcgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjODg3MTg0IiBzdHJva2Utd2lkdGg9IjEuMiIgb3BhY2l0eT0iLjU1Ij48cGF0aCBkPSJNMTU5IDE4MFExNDYgMTE3IDE2NSAxOU0xNTcgOTVMMTI2IDU3IDExOCAzME0xNTEgMTE5TDE3OCA4NU0xNjAgNjNMMTc4IDM4TTE0NiAxNjNMMTI0IDE0MCIvPjxwYXRoIGQ9Ik0xMjggNjBMMTA0IDU1TTEyNyA1OUwxMzUgMzdNMTczIDkxTDE3NyA2NE0xNjMgMzZMMTUwIDE5Ii8+PC9nPicrCiAnPGcgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjRkZGREZDIiBzdHJva2Utd2lkdGg9Ii44IiBvcGFjaXR5PSIuODUiPjxwYXRoIGQ9Ik0xNjQgMjRMMTYyIDYxTTExOSAzMUwxMjYgNTVNMTUyIDEyMEwxNzUgODkiLz48cGF0aCBkPSJNMzQgMjl2MTJtLTUtNmgxMG0tOC00IDYgOG0wLTgtNiA4TTkyIDE5djhtLTMtNGg2Ii8+PC9nPicrCiAnPGcgZmlsbD0iI0I5OEQ5MCIgb3BhY2l0eT0iLjgiPjxwYXRoIGQ9Ik0xMjAgMTI5cS0xNi0xMi0xNiA0IDkgMTEgMTYtNFoiLz48cGF0aCBkPSJNMTQ1IDE3NHEtMTMtNS0xMCA5IDExIDQgMTAtOVoiLz48L2c+JysKICc8ZWxsaXBzZSBjeD0iOTEiIGN5PSIxODgiIHJ4PSI0MiIgcnk9IjQiIGZpbGw9IiM5OTgwOTQiIG9wYWNpdHk9Ii4xMiIvPicrCiAnPHBhdGggZD0iTTYyIDE1NnEtMTEgNy05IDI3aDcxcTAtMjEtMTctMjkiIGZpbGw9IiNGRkY5RjIiIHN0cm9rZT0iIzY5NTY2NCIgc3Ryb2tlLXdpZHRoPSIxLjIiLz4nKwogJzxwYXRoIGQ9Ik02MiAxMTZMNTMgNjJxLTItMTEgNy00bDI5IDM3TTkxIDk1bDMxLTM2cTgtOSA2IDRsLTYgNTUiIGZpbGw9IiMzQzM0M0QiIHN0cm9rZT0iIzNDMzQzRCIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+JysKICc8cGF0aCBkPSJNNjIgOTFsLTMtMjIgMTggMjRNMTA0IDkzbDE3LTI0LTQgMjgiIGZpbGw9IiNCQTlEOUYiLz4nKwogJzxwYXRoIGQ9Ik02MSAxMDRxMjctMjUgNTUgMGw5IDMzcS0xIDI5LTM0IDMwLTM0LTEtMzctMjhaIiBmaWxsPSIjNDIzOTQzIiBzdHJva2U9IiM2OTU2NjQiIHN0cm9rZS13aWR0aD0iMS4xIi8+JysKICc8cGF0aCBkPSJNODkgOTRxLTYgMjEtMTMgMzRsLTYgMjJxMTkgMjEgNDEgMGwtNi0yMnEtMTEtMTYtMTItMzQiIGZpbGw9IiNGRkY5RjIiLz4nKwogJzxwYXRoIGQ9Ik02MSAxMTZxOC03IDE2IDFsLTQgOC0xMy0xTTEwNCAxMThxNy04IDE1LTFsMSA3LTEzIDEiIGZpbGw9IiNCQTkxNkQiLz4nKwogJzxlbGxpcHNlIGN4PSI3MiIgY3k9IjEyNiIgcng9IjIuNSIgcnk9IjMiIGZpbGw9IiMyMjFGMjUiLz48ZWxsaXBzZSBjeD0iMTA5IiBjeT0iMTI2IiByeD0iMi41IiByeT0iMyIgZmlsbD0iIzIyMUYyNSIvPicrCiAnPHBhdGggZD0iTTg0IDE0MHE3LTUgMTQgMC0xIDctNyA4LTctMi03LTgiIGZpbGw9IiMyOTI0MkQiLz48cGF0aCBkPSJNOTEgMTQ4djZtLTYgMHE2IDUgMTIgMCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNjk1NjY0IiBzdHJva2Utd2lkdGg9IjEuMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIi8+JysKICc8cGF0aCBkPSJNNTggMTU4cTM0IDExIDY1LTFsMSAxNXEtMzUgMTItNjgtMVoiIGZpbGw9IiNBQTYzODciLz48cGF0aCBkPSJNMTA2IDE2NmwxMyAzIDMgMjItMTYtM1oiIGZpbGw9IiNCNzdBOTkiLz48cGF0aCBkPSJNMTA5IDE4OXY0bTUtM3Y0bTUtM3YzIiBzdHJva2U9IiNBQTYzODciIHN0cm9rZS13aWR0aD0iMS41Ii8+JysKICc8L3N2Zz4nOwogZnVuY3Rpb24gYmFubmVyKCkgewogIHZhciBzZWN0aW9uID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnc2VjdGlvbicpOwogIHNlY3Rpb24uY2xhc3NOYW1lID0gJ25vdmVtYmVyLWJhbm5lcic7CiAgc2VjdGlvbi5zZXRBdHRyaWJ1dGUoJ2FyaWEtbGFiZWwnLCAn0J3QvtGP0LHRgNGMLiDQl9C40LzQsCDQsdC70LjQt9C60L4nKTsKICBzZWN0aW9uLmlubmVySFRNTCA9ICc8ZGl2IGNsYXNzPSJub3ZlbWJlci1leWVicm93Ij7QndC+0Y/QsdGA0Ywgwrcg0JXQk9CtINCR0JvQmNCX0JrQnjwvZGl2PicrCiAgICc8aDIgY2xhc3M9Im5vdmVtYmVyLXRpdGxlIj7Ql9C40LzQsCDQsdC70LjQt9C60L4uPGJyPjxlbT7QldCT0K0g0YLQvtC20LUuPC9lbT48L2gyPicrCiAgICc8cCBjbGFzcz0ibm92ZW1iZXItY29weSI+Jysocm9sZSA9PT0gJ3RlYWNoZXInID8KICAgICfQotCy0L7QuSDRiNGC0LDQsSDQv9C+0LTQs9C+0YLQvtCy0LrQuC48YnI+0JLRgdGRINCy0LDQttC90L7QtSDigJQg0L/QvtC0INGA0YPQutC+0LkuJyA6CiAgICAn0JfQsCDQvtC60L3QvtC8INC/0YDQvtGF0LvQsNC00L3QtdC1Ljxicj7QkiDQt9C90LDQvdC40Y/RhSDigJQg0LHQvtC70YzRiNC1INGD0LLQtdGA0LXQvdC90L7RgdGC0LguJykrJzwvcD4nK2FydCsKICAgJzxzcGFuIGNsYXNzPSJub3ZlbWJlci1sYWJlbCI+0JrRg9C70ZHQuiDRgNGP0LTQvtC8PC9zcGFuPic7CiAgcmV0dXJuIHNlY3Rpb247CiB9CiBmdW5jdGlvbiBkZWNvcmF0ZSgpIHsKICB2YXIgdG9wID0gcm9sZSA9PT0gJ3N0dWRlbnQnID8gYXBwLnF1ZXJ5U2VsZWN0b3IoJyN2aWV3LWhvbWUgPiAudG9wJykgOiBhcHAucXVlcnlTZWxlY3RvcignOnNjb3BlID4gLnRvcCcpOwogIGlmICghdG9wIHx8ICh0b3AubmV4dEVsZW1lbnRTaWJsaW5nICYmIHRvcC5uZXh0RWxlbWVudFNpYmxpbmcuY2xhc3NMaXN0LmNvbnRhaW5zKCdub3ZlbWJlci1iYW5uZXInKSkpIHJldHVybjsKICB0b3AuaW5zZXJ0QWRqYWNlbnRFbGVtZW50KCdhZnRlcmVuZCcsIGJhbm5lcigpKTsKIH0KIHZhciBwZW5kaW5nID0gZmFsc2U7CiB2YXIgb2JzZXJ2ZXIgPSBuZXcgTXV0YXRpb25PYnNlcnZlcihmdW5jdGlvbiAoKSB7CiAgaWYgKHBlbmRpbmcpIHJldHVybjsKICBwZW5kaW5nID0gdHJ1ZTsKICByZXF1ZXN0QW5pbWF0aW9uRnJhbWUoZnVuY3Rpb24gKCkgeyBwZW5kaW5nID0gZmFsc2U7IGRlY29yYXRlKCk7IH0pOwogfSk7CiBkZWNvcmF0ZSgpOwogb2JzZXJ2ZXIub2JzZXJ2ZShhcHAsIHtjaGlsZExpc3Q6IHRydWUsIHN1YnRyZWU6IHJvbGUgPT09ICdzdHVkZW50J30pOwogd2luZG93LmFkZEV2ZW50TGlzdGVuZXIoJ3BhZ2VoaWRlJywgZnVuY3Rpb24gKGV2ZW50KSB7CiAgaWYgKCFldmVudC5wZXJzaXN0ZWQpIG9ic2VydmVyLmRpc2Nvbm5lY3QoKTsKIH0pOwogfQogZnVuY3Rpb24gY2hlY2tDbG9jaygpIHsKICBpZiAoYWN0aXZhdGVkKSByZXR1cm47CiAgaWYgKGNsb2NrVGltZXIpIHdpbmRvdy5jbGVhclRpbWVvdXQoY2xvY2tUaW1lcik7CiAgdmFyIHJlbWFpbmluZyA9IHN0YXJ0c0F0IC0gRGF0ZS5ub3coKTsKICBpZiAocmVtYWluaW5nIDw9IDApIHsKICAgYWN0aXZhdGVkID0gdHJ1ZTsKICAgZG9jdW1lbnQucmVtb3ZlRXZlbnRMaXN0ZW5lcigndmlzaWJpbGl0eWNoYW5nZScsIGNoZWNrQ2xvY2spOwogICB3aW5kb3cucmVtb3ZlRXZlbnRMaXN0ZW5lcigncGFnZXNob3cnLCBjaGVja0Nsb2NrKTsKICAgYWN0aXZhdGUoKTsKICAgcmV0dXJuOwogIH0KICAvLyBSZWNoZWNrIGNsb2NrIGFkanVzdG1lbnRzIGFuZCB3YWtlLXVwczsgbm8gbmV0d29yayBvciBzZXJ2ZXIgam9icy4KICBjbG9ja1RpbWVyID0gd2luZG93LnNldFRpbWVvdXQoY2hlY2tDbG9jaywgTWF0aC5taW4ocmVtYWluaW5nLCA2MDAwMCkpOwogfQogZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigndmlzaWJpbGl0eWNoYW5nZScsIGNoZWNrQ2xvY2spOwogd2luZG93LmFkZEV2ZW50TGlzdGVuZXIoJ3BhZ2VzaG93JywgY2hlY2tDbG9jayk7CiBjaGVja0Nsb2NrKCk7Cn0oKSk7Cg==').decode()
PATCHER = base64.b64decode('IiIiQXBwZW5kIGEgc2VsZi1jb250YWluZWQgdmlzdWFsIHNraW4gd2l0aG91dCByZXBsYWNpbmcgcHJvZHVjdGlvbiBIVE1ML0pTLiIiIgpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKClJPT1QgPSBQYXRoKF9fZmlsZV9fKS5yZXNvbHZlKCkucGFyZW50c1sxXQpTVEFSVCA9ICc8IS0tIEVHRS1OT1ZFTUJFUi0yMDI2OlNUWUxFIC0tPicKU0NSSVBUID0gJzwhLS0gRUdFLU5PVkVNQkVSLTIwMjY6U0NSSVBUIC0tPicKCgpkZWYgdHJhbnNmb3JtKGRhdGEsIHJvbGUsIGNzcz1Ob25lLCBzY3JpcHQ9Tm9uZSk6CiAgICBpZiByb2xlIG5vdCBpbiAoJ3RlYWNoZXInLCAnc3R1ZGVudCcpOgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ05PVkVNQkVSX0lOVkFMSURfUk9MRScpCiAgICBjc3MgPSAoUk9PVC8nZWdlX25vdmVtYmVyX3RoZW1lLmNzcycpLnJlYWRfdGV4dCgpIGlmIGNzcyBpcyBOb25lIGVsc2UgY3NzCiAgICBzY3JpcHQgPSAoUk9PVC8nZWdlX25vdmVtYmVyX3RoZW1lLmpzJykucmVhZF90ZXh0KCkgaWYgc2NyaXB0IGlzIE5vbmUgZWxzZSBzY3JpcHQKICAgIHNvdXJjZSA9IGRhdGEuZGVjb2RlKCd1dGYtOCcpCiAgICBzdHlsZV9ibG9jayA9IFNUQVJUKydcbjxzdHlsZSBpZD0iZWdlLW5vdmVtYmVyLXRoZW1lIj5cbicrY3NzKydcbjwvc3R5bGU+XG4nCiAgICBzY3JpcHRfYmxvY2sgPSBTQ1JJUFQrJ1xuPHNjcmlwdCBpZD0iZWdlLW5vdmVtYmVyLWRlY29yIiBkYXRhLWNhYmluZXQtcm9sZT0iJytyb2xlKyciPlxuJytzY3JpcHQrJ1xuPC9zY3JpcHQ+XG4nCiAgICBpZiBTVEFSVCBpbiBzb3VyY2Ugb3IgU0NSSVBUIGluIHNvdXJjZToKICAgICAgICBpZiBzb3VyY2UuY291bnQoc3R5bGVfYmxvY2spPT0xIGFuZCBzb3VyY2UuY291bnQoc2NyaXB0X2Jsb2NrKT09MToKICAgICAgICAgICAgcmV0dXJuIGRhdGEKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdOT1ZFTUJFUl9FWElTVElOR19USEVNRV9ESUZGRVJTJykKICAgIGlmIHNvdXJjZS5jb3VudCgnPC9oZWFkPicpIT0xIG9yIHNvdXJjZS5jb3VudCgnPC9ib2R5PicpIT0xIG9yICdpZD0iYXBwIicgbm90IGluIHNvdXJjZToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdOT1ZFTUJFUl9VTktOT1dOX0hUTUxfU1RSVUNUVVJFJykKICAgIHNvdXJjZSA9IHNvdXJjZS5yZXBsYWNlKCc8L2hlYWQ+JyxzdHlsZV9ibG9jaysnPC9oZWFkPicsMSkKICAgIHNvdXJjZSA9IHNvdXJjZS5yZXBsYWNlKCc8L2JvZHk+JyxzY3JpcHRfYmxvY2srJzwvYm9keT4nLDEpCiAgICByZXR1cm4gc291cmNlLmVuY29kZSgndXRmLTgnKQo=')
START = '2026-11-01T00:00:00+03:00'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transform(source, role):
    namespace = {'__file__':__file__}
    exec(compile(PATCHER,'november_theme_patch.py','exec'),namespace)
    return namespace['transform'](source,role,CSS,JS)


def regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise RuntimeError('NON_REGULAR_FILE')


def metadata(path):
    info = path.stat()
    return {'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}


def atomic(path, data, info):
    fd, temporary = tempfile.mkstemp(prefix='.november-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush()
            os.fchown(stream.fileno(),info['uid'],info['gid'])
            os.fchmod(stream.fileno(),info['mode']); os.fsync(stream.fileno())
        os.replace(temporary,path)
        fd = os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def get_page(role):
    request = urllib.request.Request('http://127.0.0.1:8080'+URLS[role],
        headers={'Cache-Control':'no-cache'})
    with urllib.request.urlopen(request,timeout=10) as response:
        if response.status!=200: raise RuntimeError('CABINET_HTML_HTTP_FAILED')
        return response.read()


def health():
    with urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=5) as response:
        if response.status!=200: raise RuntimeError('HEALTH_FAILED')


def api_check(settings, kind, uid):
    payload = f'{int(uid)}.{int(time.time())+120}'
    signature = hmac.new(str(settings['BOT_TOKEN']).encode(),
        (f'ege-{kind}-webapp:'+payload).encode(),hashlib.sha256).hexdigest()
    request = urllib.request.Request(f'http://127.0.0.1:8080/{kind}-app/api',
        data=json.dumps({'launch':payload+'.'+signature,'view':'home'}).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=10) as response:
        data = json.loads(response.read())
        if response.status!=200 or data.get('ok') is not True:
            raise RuntimeError('AUTHENTICATED_CABINET_FAILED')
    print('NOVEMBER_THEME_API_OK kind='+kind,flush=True)


def credentials():
    path = APP/'runtime-vars.json'; regular(path)
    settings = json.loads(path.read_text())
    database = APP/'data/coreapp_webhooks.db'
    if not settings.get('BOT_TOKEN') or str(settings.get('COREAPP_DB_PATH'))!=str(database):
        raise RuntimeError('RUNTIME_CONFIGURATION_UNVERIFIED')
    with sqlite3.connect(f'file:{database}?mode=ro',uri=True) as connection:
        students = [int(r[0]) for r in connection.execute('''SELECT DISTINCT telegram_user_id
            FROM students WHERE active=1 AND course_id=? AND telegram_user_id>0
            ORDER BY telegram_user_id LIMIT 2''',('6a8c4641d6c9f299cf1387a6',))]
    if len(students)!=2: raise RuntimeError('LINKED_STUDENTS_UNVERIFIED')
    return settings,students


def read_backups():
    if not STATE.is_dir() or STATE.is_symlink() or STATE.stat().st_uid!=os.geteuid() or stat.S_IMODE(STATE.stat().st_mode)&0o077:
        raise RuntimeError('BACKUP_DIRECTORY_UNVERIFIED')
    path = STATE/'metadata.json'; regular(path)
    records = json.loads(path.read_text())
    if set(records)!=set(FILES): raise RuntimeError('BACKUP_METADATA_UNVERIFIED')
    for role, name in FILES.items():
        path = STATE/name; regular(path)
        if digest(path.read_bytes())!=records[role]['sha256']:
            raise RuntimeError('BACKUP_INTEGRITY_FAILED')
    return records


def rollback():
    records = read_backups()
    # Validate both files first. Never erase a subsequent deployment.
    for role,name in FILES.items():
        path = APP/name; regular(path)
        original = (STATE/name).read_bytes()
        if path.read_bytes() not in (original,transform(original,role)):
            raise RuntimeError('ROLLBACK_CONFLICT_NEWER_HTML')
    for role,name in FILES.items():
        atomic(APP/name,(STATE/name).read_bytes(),records[role]['metadata'])
    health()
    for role,name in FILES.items():
        if get_page(role)!=(STATE/name).read_bytes():
            raise RuntimeError('ROLLBACK_HTML_NOT_SERVED')
    print('NOVEMBER_THEME_ROLLBACK_OK_NO_RESTART_DATABASE_UNCHANGED',flush=True)


def apply():
    health()
    settings,students = credentials()
    if os.path.lexists(STATE):
        records = read_backups()
        for role,name in FILES.items():
            path = APP/name; regular(path)
            expected = transform((STATE/name).read_bytes(),role)
            if path.read_bytes()!=expected or get_page(role)!=expected:
                raise RuntimeError('EXISTING_STATE_REQUIRES_REVIEW')
        print('NOVEMBER_THEME_ALREADY_ARMED_NO_RESTART start='+START,flush=True)
        return
    originals,updates,records = {},{},{}
    # Read current VPS files, not copies from GitHub. Preflight proves these
    # are the actual served templates and transformation is append-only.
    for role,name in FILES.items():
        path = APP/name; regular(path)
        source = path.read_bytes()
        if get_page(role)!=source: raise RuntimeError('LIVE_TEMPLATE_NOT_MATCHING_FILE')
        text = source.decode()
        anchor = 'renderHome' if role=='teacher' else 'view-home'
        if anchor not in text or 'class="top"' not in text:
            raise RuntimeError('UNKNOWN_CABINET_LAYOUT')
        updates[role] = transform(source,role)
        if updates[role]==source: raise RuntimeError('THEME_ALREADY_PRESENT_WITHOUT_BACKUP')
        originals[role] = source
        records[role] = {'sha256':digest(source),'metadata':metadata(path)}
    STATE.mkdir(mode=0o700)
    for role,name in FILES.items():
        fd = os.open(STATE/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(originals[role]);stream.flush();os.fsync(stream.fileno())
    fd = os.open(STATE/'metadata.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(records,stream);stream.flush();os.fsync(stream.fileno())
    read_backups()
    for role,name in FILES.items():
        if (APP/name).read_bytes()!=originals[role] or metadata(APP/name)!=records[role]['metadata']:
            raise RuntimeError('SOURCE_CHANGED_AFTER_BACKUP')
    stage = 'atomic_html'
    try:
        for role,name in FILES.items():
            atomic(APP/name,updates[role],records[role]['metadata'])
        stage = 'served_html'
        for role in FILES:
            if get_page(role)!=updates[role]: raise RuntimeError('UPDATED_HTML_NOT_SERVED')
        stage = 'cabinet_apis'
        api_check(settings,'admin',1032290944)
        for uid in students: api_check(settings,'student',uid)
        health()
    except Exception as error:
        print(f'NOVEMBER_THEME_RELEASE_FAILURE stage={stage} error={type(error).__name__}',flush=True)
        rollback()
        raise RuntimeError('NOVEMBER_THEME_AUTO_ROLLBACK_COMPLETED') from None
    print('NOVEMBER_THEME_ARMED_OK_BACKUPS_AND_CABINETS_VERIFIED start='+START,flush=True)
    print('NOVEMBER_THEME_NO_RESTART_NO_DATABASE_OR_MESSAGE_QUEUE_WRITES',flush=True)


def main():
    if os.geteuid()!=0 or len(sys.argv)!=2 or sys.argv[1] not in (RELEASE,ROLLBACK):
        raise RuntimeError('LITERAL_ROOT_ACTION_REQUIRED')
    with open('/run/lock/ege-blizko-autodeploy.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if sys.argv[1]==RELEASE: apply()
        else: rollback()


if __name__=='__main__':
    try: main()
    except Exception as error:
        print('NOVEMBER_THEME_STOPPED '+type(error).__name__+': '+str(error),file=sys.stderr)
        sys.exit(1)
