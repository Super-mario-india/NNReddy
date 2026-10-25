"""N.N Reddy Hostels (HostelAtlas) - single serverless API for Vercel.
Standard library only, so no requirements.txt is needed. All calls: POST /api/index {"a": "<action>", ...}
Environment variables: SUPABASE_URL, SUPABASE_SERVICE_KEY, ADMIN_PASSWORD, SESSION_SECRET (optional), HOLD_HOURS (optional)."""
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
            m = 'This item has bookings and cannot be deleted. Cancel or check out its bookings first.'
        raise Fail(m or 'Database error')


# ---- admin session tokens (HMAC signed, 24h) ----
sign = lambda p: hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()


def mint():
    p = str(int(time.time()) + 86400)
    return p + '.' + sign(p)


def authed(header):
    p, _, s = header.replace('Bearer ', '').strip().partition('.')
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
        if re.search(r'goo\.gl|maps\.app', u):  # short link: follow redirect
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
    i = q(d.get('id'))
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
    try:
        months = min(max(int(d.get('months') or 1), 1), 24)
    except ValueError:
        months = 1
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
    sb('POST', 'rpc/set_booking', {'p_id': d.get('id'), 'p_status': d.get('status'), 'p_verif': d.get('verification')})
    return {'ok': 1}


def save_hostel(d):
    f = {k: (str(d.get(k) or '').strip() or None)
         for k in ('name', 'city', 'phone', 'address', 'description', 'image_url', 'amenities', 'maps_url')}
    if not f['name']:
        raise Fail('Hostel name is required.')
    f['maps_url'] = clean_map(f['maps_url']) or None
    f['lat'], f['lng'] = geo(f['maps_url'])
    hid = d.get('id')
    r = sb('PATCH', f'hostels?id=eq.{q(hid)}', f) if hid else sb('POST', 'hostels', f)
    return r[0]


def del_hostel(d):
    sb('DELETE', f"hostels?id=eq.{q(d.get('id'))}")
    return {'ok': 1}


def save_floor(d):
    name = str(d.get('name') or '').strip()
    if not name:
        raise Fail('Floor name is required.')
    f = {'name': name, 'level': int(d.get('level') or 0)}
    if d.get('id'):
        return sb('PATCH', f"floors?id=eq.{q(d['id'])}", f)[0]
    return sb('POST', 'floors', {**f, 'hostel_id': d.get('hostel_id'), 'layout': {'objs': []}})[0]


def del_floor(d):
    sb('DELETE', f"floors?id=eq.{q(d.get('id'))}")
    return {'ok': 1}


def save_layout(d):
    L = d.get('layout') or {}
    objs = L.get('objs') or []
    if len(objs) > 1000:
        raise Fail('Too many objects on one floor (limit 1000).')
    fl = sb('GET', f"floors?id=eq.{q(d.get('floor_id'))}&select=hostel_id")
    if not fl:
        raise Fail('Floor not found.', 404)
    beds = {}
    for o in objs:
        if o.get('t') == 'bed':
            c = str(o.get('code') or '').strip()
            if not c:
                raise Fail('Every bed needs a bed code.')
            beds[c] = {'code': c, 'price': max(int(o.get('price') or 0), 0)}
    sb('PATCH', f"floors?id=eq.{q(d['floor_id'])}", {'layout': {'objs': objs}})
    sb('POST', 'rpc/sync_beds', {'p_floor': d['floor_id'], 'p_hostel': fl[0]['hostel_id'], 'p_beds': list(beds.values())})
    return {'ok': 1, 'beds': len(beds)}


PUB = {'hostels': hostels, 'hostel': hostel, 'book': book, 'track': track}
ADM = {'bookings': bookings, 'set_booking': set_booking, 'save_hostel': save_hostel, 'del_hostel': del_hostel,
       'save_floor': save_floor, 'del_floor': del_floor, 'save_layout': save_layout}


def route(d, auth):
    a = d.get('a')
    if a == 'login':
        if PW and hmac.compare_digest(str(d.get('password', '')).encode(), PW.encode()):
            return {'token': mint()}
        raise Fail('Incorrect password.', 401)
    if a in PUB:
        return PUB[a](d)
    if a in ADM:
        if not authed(auth):
            raise Fail('Session expired. Please sign in again.', 401)
        return ADM[a](d)
    raise Fail('Unknown action.', 404)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = int(self.headers.get('content-length') or 0)
            if n > 2_000_000:
                raise Fail('Request too large.', 413)
            out, code = route(json.loads(self.rfile.read(n) or b'{}'), self.headers.get('authorization', '')), 200
        except Fail as e:
            out, code = {'error': str(e)}, e.code
        except Exception:
            out, code = {'error': 'Unexpected server error.'}, 500
        b = json.dumps(out, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)


import _flow; _flow.install(globals())
