"""HostelAtlas admin Database tab: table health with row counts, the schema update script, a read-only table
browser and an optional SQL console. Loaded automatically by api/index.py after _ops.

The console runs any SQL (create tables, alter, select, ...) through the admin_sql() database function. It is off
unless DB_CONSOLE_KEY is set in Vercel; every run must carry that key, statements that change or delete data need
an explicit confirmation, runs are rate limited, and the last 100 runs are kept in settings 'audit:sql'."""
import os, re, hmac, time

TABLES = ('hostels', 'floors', 'beds', 'applications', 'payments', 'tickets', 'bookings', 'settings', 'otps')
BROWSE = {'applications': 'created_at.desc', 'payments': 'created_at.desc', 'tickets': 'created_at.desc', 'hostels': 'created_at',
          'floors': 'hostel_id,level', 'beds': 'hostel_id,code', 'bookings': 'created_at.desc'}
DANGER = re.compile(r'\b(drop|truncate|delete|update|alter|revoke|grant|reassign|security)\b', re.I)

UPDATE_SQL = r"""-- N.N Reddy Hostels database update. Safe to run more than once.
create table if not exists otps (email text primary key, h text not null, exp bigint not null, tries int not null default 0);
create table if not exists settings (key text primary key, value jsonb not null default '{}');
alter table otps alter column tries set default 0;
create unique index if not exists applications_one_live_bed on applications (bed_id)
  where status in ('assigned','paid','verified','resident');

-- Fee history: every charge and payment after check-in
create table if not exists payments (
  id uuid primary key default gen_random_uuid(),
  app_id uuid not null references applications on delete cascade,
  hostel_id uuid not null references hostels,
  kind text not null check (kind in ('charge','payment')),
  amount int not null check (amount > 0),
  label text, ref text, period text,
  status text not null default 'verified' check (status in ('submitted','verified','rejected')),
  due_at timestamptz,
  created_at timestamptz default now()
);
create index if not exists payments_app on payments (app_id);
create unique index if not exists payments_one_rent_per_month on payments (app_id, period)
  where kind = 'charge' and period is not null;
alter table applications add column if not exists rent int;

-- Saving a floor plan never deletes beds that bookings or applications point to
create or replace function sync_beds(p_floor uuid, p_hostel uuid, p_beds jsonb)
returns void language plpgsql as $$
begin
  insert into beds (hostel_id, floor_id, code, price)
  select p_hostel, p_floor, x->>'code', coalesce((x->>'price')::int, 0) from jsonb_array_elements(p_beds) x
  on conflict (floor_id, code) do update set price = excluded.price, status = 'available';
  delete from beds where floor_id = p_floor and code not in (select x->>'code' from jsonb_array_elements(p_beds) x)
    and not exists (select 1 from bookings where bed_id = beds.id)
    and not exists (select 1 from applications where bed_id = beds.id);
  update beds set status = 'unavailable' where floor_id = p_floor and code not in (select x->>'code' from jsonb_array_elements(p_beds) x);
end $$;

-- SQL console for Admin > Database. Only the server can call it, and only when DB_CONSOLE_KEY is set in Vercel.
create or replace function admin_sql(q text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare r jsonb;
begin
  if q ~* '^\s*(select|with|values|table)\s' and position(';' in q) = 0 then
    execute 'select coalesce(jsonb_agg(t), ''[]''::jsonb) from (' || q || ') t' into r;
    return jsonb_build_object('rows', r);
  end if;
  execute q;
  notify pgrst, 'reload schema';
  return jsonb_build_object('rows', null);
end $$;
revoke execute on function admin_sql(text) from public, anon, authenticated;
grant execute on function admin_sql(text) to service_role;

alter table if exists applications enable row level security;
alter table if exists payments enable row level security;
alter table if exists tickets enable row level security;
alter table if exists otps enable row level security;
alter table if exists settings enable row level security;
revoke execute on function request_bed, set_booking, sync_beds from public, anon, authenticated;
notify pgrst, 'reload schema';
"""


def install(g):
    sb, rest, Fail, num, throttle, kv_get, kv_put = (g[k] for k in ('sb', 'rest', 'Fail', 'num', 'throttle', 'kv_get', 'kv_put'))
    KEY = os.environ.get('DB_CONSOLE_KEY', '')
    m = re.match(r'https://([a-z0-9]+)\.supabase\.co', g['URL'])
    ref = m[1] if m else ''

    def count(t):
        try:
            h = rest('HEAD', f'{t}?select=*', prefer='count=exact')[1]
            return int((h.get('Content-Range') or '*/0').rsplit('/', 1)[1])
        except Exception:
            return None  # missing table (or unreachable)
    g['count'] = count

    def console():
        if len(KEY) < 12:
            return 'off'
        try:
            sb('POST', 'rpc/admin_sql', {'q': 'select 1 as ok'}, raw=True)
            return 'on'
        except Fail:
            return 'no_function'

    def has_rent():
        try:
            sb('GET', 'applications?select=rent&limit=1')
            return True
        except Fail:
            return False

    def db_status(d):
        tables = {t: g['count'](t) for t in TABLES}
        return {'tables': tables, 'rent': has_rent(), 'console': console(), 'ref': ref, 'sql': UPDATE_SQL,
                'editor': f'https://supabase.com/dashboard/project/{ref}/sql/new' if ref else 'https://supabase.com/dashboard',
                'ok': all(tables[t] is not None for t in ('applications', 'payments', 'tickets', 'otps', 'settings')) and has_rent()}

    def db_rows(d):
        t = d.get('table')
        if t not in BROWSE:
            raise Fail('Choose a table.')
        off = max(num(d.get('offset')), 0)
        rows = sb('GET', f'{t}?select=*&order={BROWSE[t]}&limit=100&offset={off}')
        if t == 'floors':  # plans can be large; show their size instead
            for r in rows:
                r['layout'] = f"{len((r.get('layout') or {}).get('objs') or [])} objects"
        return {'rows': rows, 'offset': off, 'more': len(rows) == 100}

    def audit(d, sql, ok, msg=''):
        try:
            log = kv_get('audit:sql').get('runs') or []
            log.insert(0, {'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'ip': d.get('_ip'), 'sql': sql[:400], 'ok': ok, 'msg': msg[:200]})
            kv_put('audit:sql', {'runs': log[:100]})
        except Fail:
            pass

    def bare(sql):  # without comments and quoted text, for spotting statements that change data
        return re.sub(r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", ' ', sql, flags=re.S)

    def db_sql(d):
        if len(KEY) < 12:
            raise Fail('The SQL console is off. Set DB_CONSOLE_KEY (12+ characters) in Vercel and redeploy to turn it on.', 403)
        throttle('sql:' + d['_ip'], 60, 600)
        if not hmac.compare_digest(str(d.get('key') or '').encode(), KEY.encode()):
            audit(d, '(wrong console key)', False)
            raise Fail('Wrong console key.', 403)
        sql = re.sub(r'[;\s]+$', '', str(d.get('sql') or '').strip())
        if not sql:
            raise Fail('Type some SQL first.')
        if len(sql) > 50_000:
            raise Fail('That script is too long. Run it in smaller parts.')
        if DANGER.search(bare(sql)) and not d.get('confirm'):
            raise Fail('This changes or deletes data. Tick "I understand" and run it again.', 428)
        t0 = time.time()
        try:
            r = sb('POST', 'rpc/admin_sql', {'q': sql}, raw=True) or {}
        except Fail as e:
            audit(d, sql, False, str(e))
            if 'admin_sql' in str(e) and ('schema cache' in str(e) or 'Could not find' in str(e)):
                raise Fail('The console is not installed in the database yet. Run the update SQL in Supabase first.', 503)
            raise
        audit(d, sql, True)
        rows = r.get('rows')
        return {'rows': rows[:1000] if rows else rows, 'total': len(rows) if rows is not None else None, 'ms': int((time.time() - t0) * 1000)}

    def db_audit(d):
        return kv_get('audit:sql').get('runs') or []

    g['ADM'].update(db_status=db_status, db_rows=db_rows, db_sql=db_sql, db_audit=db_audit)
