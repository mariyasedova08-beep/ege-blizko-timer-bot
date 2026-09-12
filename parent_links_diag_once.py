import os, sqlite3

DB = os.getenv('COREAPP_DB_PATH', '/data/coreapp.sqlite3')

with sqlite3.connect(DB) as c:
    c.row_factory = sqlite3.Row
    self_rows = c.execute('''
        SELECT s.id AS student_id,
               COALESCE(NULLIF(s.display_name,''), NULLIF(s.user_name,''), s.user_email, 'Ученик') AS student_name,
               s.telegram_user_id,
               pl.parent_name,
               pl.parent_username,
               pl.active,
               pl.linked_at
        FROM parent_links pl
        JOIN students s ON s.id = pl.student_id
        WHERE s.telegram_user_id IS NOT NULL
          AND pl.parent_telegram_user_id = s.telegram_user_id
        ORDER BY pl.linked_at
    ''').fetchall()
    print('PARENT_DIAG self_links_total=' + str(len(self_rows)), flush=True)
    for r in self_rows:
        print('PARENT_DIAG_SELF ' + '|'.join([
            str(r['student_id']), str(r['student_name']), str(r['telegram_user_id']),
            str(r['parent_name'] or ''), str(r['parent_username'] or ''),
            'active=' + str(r['active']), 'linked_at=' + str(r['linked_at'])
        ]), flush=True)

    sid = 11
    s = c.execute('''
        SELECT id,
               COALESCE(NULLIF(display_name,''), NULLIF(user_name,''), user_email, 'Ученик') AS student_name,
               telegram_user_id
        FROM students WHERE id=?
    ''',(sid,)).fetchone()
    print('PARENT_DIAG_STEPA exact=' + ('found' if s else 'missing'), flush=True)
    if s:
        print(f"PARENT_DIAG_STEPA student_id={s['id']}|name={s['student_name']}|student_tg={s['telegram_user_id']}", flush=True)
        links = c.execute('''
            SELECT parent_telegram_user_id,parent_name,parent_username,active,linked_at
            FROM parent_links WHERE student_id=? ORDER BY linked_at
        ''',(sid,)).fetchall()
        print(f"PARENT_DIAG_STEPA links={len(links)}", flush=True)
        for r in links:
            print('PARENT_DIAG_STEPA_LINK ' + '|'.join([
                'parent_tg=' + str(r['parent_telegram_user_id']),
                'name=' + str(r['parent_name'] or ''),
                'username=' + str(r['parent_username'] or ''),
                'active=' + str(r['active']),
                'linked_at=' + str(r['linked_at'])
            ]), flush=True)
        inv = c.execute('''
            SELECT created_at,expires_at,used_at,used_by,
                   CASE WHEN used_at IS NULL THEN 1 ELSE 0 END AS unused
            FROM parent_invites WHERE student_id=? ORDER BY created_at DESC
        ''',(sid,)).fetchall()
        print(f"PARENT_DIAG_STEPA invites={len(inv)}", flush=True)
        for r in inv:
            print('PARENT_DIAG_STEPA_INVITE ' + '|'.join([
                'created=' + str(r['created_at']),
                'expires=' + str(r['expires_at']),
                'used=' + str(r['used_at']),
                'used_by=' + str(r['used_by']),
                'unused=' + str(r['unused'])
            ]), flush=True)
