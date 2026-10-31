"""N.N Reddy Hostels (HostelAtlas) - single serverless API for Vercel.
Standard library only, so no requirements.txt is needed. All calls: POST /api/index {"a": "<action>", ...}
Environment variables: SUPABASE_URL, SUPABASE_SERVICE_KEY, ADMIN_PASSWORD, SESSION_SECRET, HOLD_HOURS (optional).
Access: PUB actions are open (catalogue, applying, signing in); applicant actions check a signed applicant token
issued only after an emailed code is verified; ADM actions check a signed admin token. Sign-in actions are rate limited."""
import json, os, re, hmac, time, hashlib, urllib.request, urllib.parse, urllib.error
from http.server import BaseHTTPRequestHandler

URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
PW = os.environ.get('ADMIN_PASSWORD', '')
SECRET = (os.environ.get('SESSION_SECRET') or PW).encode()
HOLD = int(os.environ.get('HOLD_HOURS', '48'))
q = lambda v: urllib.parse.quote(str(v), safe='')


class Fail(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def sb(method, path, body=None):
    if not URL or not KEY:
        raise Fail('Server is not configured: set SUPABASE_URL and SUPABASE_SERVICE_KEY', 500)
    h = {'apikey': KEY, 'Content-Type': 'application/json', 'Prefer': 'return=representation'}
    if KEY.startswith('eyJ'):
        h['Authorization'] = 'Bearer ' + KEY
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f'{URL}/rest/v1/{path}', data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            t = r.read()
            return json.loads(t) if t else None
    except urllib.error.HTTPError as e:
        try:
            m = json.loads(e.read()).get('message')
        except Exception:
            m = None
        if m and 'violates foreign key' in m:
            m = 'This item has bookings or applications and cannot be deleted. Close them first.'
        elif m and 'applications_one_live_bed' in m:
            m = 'That bed was just taken by someone else. Please pick another.'
        raise Fail(m or 'Database error')


def num(v, default=0):
    """Lenient integer parse for amounts and levels typed by people ("6,000", "6000.0")."""
    try:
        return int(float(re.sub(r'[,\s]', '', str(v))))
    except (TypeError, ValueError, OverflowError):
        return default


def uid(v, what='Record'):
    """Validate a row id before it reaches a query, so bad input gets a clean 404 instead of a database error."""
    v = str(v or '').strip()
    if not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', v):
        raise Fail(f'{what} not found.', 404)
    return v


def throttle(key, limit, window):
    """Allow `limit` calls per `window` seconds for a key (rows 'rl:<key>' in the otps table).
    Fails open if that table is missing, so a database problem never locks everyone out."""
    k, now = 'rl:' + key, int(time.time())
    try:
        r = sb('GET', f'otps?email=eq.{q(k)}&select=exp,tries')
        if not r or r[0]['exp'] < now:
            sb('DELETE', f'otps?email=eq.{q(k)}')
            sb('POST', 'otps', {'email': k, 'h': '-', 'exp': now + window, 'tries': 1})
        elif (r[0]['tries'] or 0) >= limit:
            raise Fail('Too many attempts. Please wait a few minutes and try again.', 429)
        else:
            sb('PATCH', f'otps?email=eq.{q(k)}', {'tries': (r[0]['tries'] or 0) + 1})
    except Fail as e:
        if e.code == 429:
            raise


# ---- admin session tokens (HMAC signed, 24h) ----
sign = lambda p: hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()


def mint():
    p = str(int(time.time()) + 86400)
    return p + '.' + sign(p)


def authed(header):
    p, _, s = (header or '').replace('Bearer ', '').strip().partition('.')
    return bool(PW) and p.isdigit() and int(p) > time.time() and hmac.compare_digest(s, sign(p))


# ---- Google Maps link -> coordinates (used for the embedded map card) ----
def clean_map(u):
    u = (u or '').strip()
    m = re.search(r'src="([^"]+)"', u)  # pasted <iframe> embed code
    return m.group(1) if m else u


def geo(u):
    if not u:
        return None, None
    try:
        host = urllib.parse.urlparse(u).hostname or ''
        if host == 'goo.gl' or host.endswith('.goo.gl'):  # short link: follow redirect (only to Google)
            u = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=6).geturl()
    except Exception:
        pass
    for p in (r'@(-?\d+\.\d+),(-?\d+\.\d+)', r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)',
              r'[?&](?:q|ll|query|destination)=(-?\d+\.\d+)(?:,|%2C)(-?\d+\.\d+)'):
        m = re.search(p, u)
        if m:
            return float(m[1]), float(m[2])
    m = re.search(r'!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)', u)  # embed format: lng first
    return (float(m[2]), float(m[1])) if m else (None, None)


# ---- public actions ----
def hostels(d):
    hs = sb('GET', 'hostels?select=*&order=created_at')
    agg = {}
    for b in sb('GET', 'bed_live?select=hostel_id,live,price&limit=5000'):
        a = agg.setdefault(b['hostel_id'], {'stat': {}, 'from': None})
        a['stat'][b['live']] = a['stat'].get(b['live'], 0) + 1
        if b['live'] == 'available' and b['price']:
            a['from'] = min(a['from'] or b['price'], b['price'])
    for h in hs:
        a = agg.get(h['id'], {'stat': {}, 'from': None})
        h['stat'], h['from'], h['free'] = a['stat'], a['from'], a['stat'].get('available', 0)
    return hs


def hostel(d):
    i = uid(d.get('id'), 'Hostel')
    h = sb('GET', f'hostels?id=eq.{i}&select=*')
    if not h:
        raise Fail('Hostel not found', 404)
    return {'hostel': h[0],
            'floors': sb('GET', f'floors?hostel_id=eq.{i}&order=level,name'),
            'beds': sb('GET', f'bed_live?hostel_id=eq.{i}&select=id,floor_id,code,price,live&limit=5000')}


def book(d):
    n, e, p = (str(d.get(k) or '').strip() for k in ('name', 'email', 'phone'))
    if len(n) < 2 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', e) or not re.fullmatch(r'\+?\d[\d\s-]{8,14}', p):
        raise Fail('Please enter a valid name, email address and mobile number.')
    mi = str(d.get('move_in') or '')
    if not re.fullmatch(r'\d{4}-\d\d-\d\d', mi):
        raise Fail('Please choose a move-in date.')
    months = min(max(num(d.get('months'), 1), 1), 24)
    ref = sb('POST', 'rpc/request_bed', {'p_bed': d.get('bed_id'), 'p_name': n, 'p_email': e.lower(), 'p_phone': p,
                                         'p_move_in': mi, 'p_months': months, 'p_hold_hours': HOLD})
    x = sb('GET', f'bookings?id=eq.{q(ref)}&select=hostels(name,phone)')
    return {'ref': ref, 'hold_hours': HOLD, 'hostel': x[0]['hostels'] if x else None}


def track(d):
    r = sb('GET', f"bookings?id=eq.{q(d.get('ref', '').strip())}&email=eq.{q(d.get('email', '').strip().lower())}"
                  '&select=status,verification,move_in,months,beds(code),hostels(name,phone)')
    if not r:
        raise Fail('No booking found for that reference and email.', 404)
    return r[0]


# ---- admin actions ----
def bookings(d):
    return sb('GET', 'bookings?select=*,beds(code),hostels(name)&order=created_at.desc&limit=300')


def set_booking(d):
    sb('POST', 'rpc/set_booking', {'p_id': uid(d.get('id'), 'Booking'), 'p_status': d.get('status'), 'p_verif': d.get('verification')})
    return {'ok': 1}


def save_hostel(d):
    f = {k: (str(d.get(k) or '').strip()[:2000] or None)
         for k in ('name', 'city', 'phone', 'address', 'description', 'image_url', 'amenities', 'maps_url')}
    if not f['name']:
        raise Fail('Hostel name is required.')
    if f['image_url'] and not re.match(r'https?://', f['image_url'], re.I):
        raise Fail('Cover image link must start with https://')
    f['maps_url'] = clean_map(f['maps_url']) or None
    f['lat'], f['lng'] = geo(f['maps_url'])
    hid = d.get('id')
    r = sb('PATCH', f"hostels?id=eq.{uid(hid, 'Hostel')}", f) if hid else sb('POST', 'hostels', f)
    if not r:
        raise Fail('Hostel not found.', 404)
    return r[0]


def del_hostel(d):
    sb('DELETE', f"hostels?id=eq.{uid(d.get('id'), 'Hostel')}")
    return {'ok': 1}


def save_floor(d):
    name = str(d.get('name') or '').strip()
    if not name:
        raise Fail('Floor name is required.')
    f = {'name': name[:60], 'level': num(d.get('level'))}
    if d.get('id'):
        r = sb('PATCH', f"floors?id=eq.{uid(d['id'], 'Floor')}", f)
        if not r:
            raise Fail('Floor not found.', 404)
        return r[0]
    return sb('POST', 'floors', {**f, 'hostel_id': uid(d.get('hostel_id'), 'Hostel'), 'layout': {'objs': []}})[0]


def del_floor(d):
    sb('DELETE', f"floors?id=eq.{uid(d.get('id'), 'Floor')}")
    return {'ok': 1}


TYPES = {'room', 'corridor', 'bed', 'washroom', 'door', 'window', 'stairs', 'lift', 'fan', 'light', 'rack', 'balcony'}


def coord(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return round(min(max(f, -1e5), 1e5), 2) if f == f else 0  # f != f only for NaN


def save_layout(d):
    L = d.get('layout') or {}
    objs = L.get('objs') or [] if isinstance(L, dict) else None
    if not isinstance(objs, list):
        raise Fail('Invalid layout.')
    if len(objs) > 1000:
        raise Fail('Too many objects on one floor (limit 1000).')
    fid = uid(d.get('floor_id'), 'Floor')
    fl = sb('GET', f'floors?id=eq.{fid}&select=hostel_id')
    if not fl:
        raise Fail('Floor not found.', 404)
    # Plans are shown to applicants, so store only known fields with clean values (no markup can ride along).
    clean, beds = [], {}
    for i, o in enumerate(objs):
        if not isinstance(o, dict) or o.get('t') not in TYPES:
            raise Fail('The plan contains an unknown object type.')
        c = {'id': re.sub(r'[^\w-]', '', str(o.get('id') or ''))[:40] or f'o{i}', 't': o['t'],
             'x': coord(o.get('x')), 'y': coord(o.get('y')), 'w': max(coord(o.get('w')), 1), 'h': max(coord(o.get('h')), 1),
             'r': coord(o.get('r')), 'l': str(o.get('l') or '')[:80]}
        if c['t'] == 'bed':
            code = str(o.get('code') or '').strip()[:40]
            if not code:
                raise Fail('Every bed needs a bed code.')
            if code in beds:
                raise Fail(f'Bed code {code} is used more than once on this floor.')
            c['code'], c['price'] = code, max(num(o.get('price')), 0)
            beds[code] = {'code': code, 'price': c['price']}
        clean.append(c)
    sb('PATCH', f'floors?id=eq.{fid}', {'layout': {'objs': clean}})
    sb('POST', 'rpc/sync_beds', {'p_floor': fid, 'p_hostel': fl[0]['hostel_id'], 'p_beds': list(beds.values())})
    return {'ok': 1, 'beds': len(beds)}


PUB = {'hostels': hostels, 'hostel': hostel}  # book/track are kept for the legacy bookings table but no longer public
ADM = {'bookings': bookings, 'set_booking': set_booking, 'save_hostel': save_hostel, 'del_hostel': del_hostel,
       'save_floor': save_floor, 'del_floor': del_floor, 'save_layout': save_layout}


def route(d, auth):
    if not isinstance(d, dict):
        raise Fail('Bad request.')
    a = d.get('a')
    if a == 'login':
        throttle('admin:' + d.get('_ip', ''), 10, 900)
        if PW and hmac.compare_digest(str(d.get('password', '')).encode(), PW.encode()):
            return {'token': mint()}
        raise Fail('Incorrect password.', 401)
    if a in PUB:
        if LOAD_ERR:  # fail closed: without the access rules in _flow/_ops, public calls could expose too much
            raise Fail('The server is updating. Please try again in a few minutes.', 503)
        return PUB[a](d)
    if a in ADM:
        if not authed(auth):
            raise Fail('Session expired. Please sign in again.', 401)
        return ADM[a](d)
    raise Fail('Unknown action.', 404)


def client_ip(h):
    return (h.get('x-real-ip') or h.get('x-forwarded-for') or '').split(',')[0].strip() or 'unknown'


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = int(self.headers.get('content-length') or 0)
            if n > 2_000_000:
                raise Fail('Request too large.', 413)
            try:
                d, auth = json.loads(self.rfile.read(n) or b'{}'), self.headers.get('authorization', '')
            except ValueError:
                raise Fail('Bad request.')
            if isinstance(d, dict):  # set server-side, so a client can never supply its own
                d['_a'], d['_ip'] = auth, client_ip(self.headers)
            out, code = route(d, auth), 200
        except Fail as e:
            out, code = {'error': str(e)}, e.code
        except Exception:
            out, code = {'error': 'Unexpected server error.'}, 500
        b = json.dumps(out, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)


import importlib.util, traceback
LOAD_ERR = []
HERE = os.path.dirname(os.path.abspath(__file__))

def _load(name):
    try:
        spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.install(globals())
    except Exception:
        LOAD_ERR.append(name + ': ' + traceback.format_exc()[-1500:])

_load('_flow')
_load('_ops')
ADM['diag'] = lambda d: {'errors': LOAD_ERR, 'files': sorted(os.listdir(HERE))}  # admin only: tracebacks are internal
