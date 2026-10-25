"""HostelAtlas step 1 backend: email settings, application form, user login (email / email+OTP),
gated floor plan. Enable by adding ONE line at the bottom of api/index.py (after `class handler`):
    import _flow; _flow.install(globals())
Everything works without email configured; mail is best-effort."""
import time, hmac, secrets, smtplib, ssl, re
from email.message import EmailMessage

MASK = ('phone', 'parent_phone', 'aadhaar', 'id_proof', 'address', 'photo_url', 'office')


def install(g):
    sb, Fail, q, sign, authed = g['sb'], g['Fail'], g['q'], g['sign'], g['authed']
    PUB, ADM, old_route = g['PUB'], g['ADM'], g['route']
    old_hostel, old_hostels = PUB['hostel'], PUB['hostels']

    def cfg():
        r = sb('GET', 'settings?key=eq.mail&select=value')
        return r[0]['value'] if r else {}

    def mail(to, subj, body):
        c = cfg()
        if not (c.get('user') and c.get('pass') and to):
            return False
        try:
            m = EmailMessage()
            m['From'], m['To'], m['Subject'] = c.get('from') or c['user'], to, subj
            m.set_content(body)
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context(), timeout=10) as s:
                s.login(c['user'], c['pass'].replace(' ', ''))
                s.send_message(m)
            return True
        except Exception:
            return False

    # ---- user tokens: u.<hex payload>.<sig>, level = basic (email only) or full (OTP verified) ----
    def umint(email, lvl):
        p = f'{email}|{lvl}|{int(time.time()) + 7 * 86400}'
        return 'u.' + p.encode().hex() + '.' + sign(p)

    def uread(h):
        try:
            _, x, s = h.replace('Bearer ', '').strip().split('.')
            p = bytes.fromhex(x).decode()
            e, l, t = p.split('|')
            if int(t) > time.time() and hmac.compare_digest(s, sign(p)):
                return e, l
        except Exception:
            pass
        return None, None

    def apps_of(email):
        return sb('GET', f'applications?email=eq.{q(email)}&select=*,hostels(name,phone)&order=created_at.desc')

    # ---- public ----
    def hostels(d):
        hs = old_hostels(d)
        if not authed(d['_a']):  # visitors see hostels only, never availability
            for h in hs:
                h['stat'], h['from'], h['free'] = {}, None, None
        return hs

    def hostel(d):
        if authed(d['_a']):
            return old_hostel(d)
        h = sb('GET', f"hostels?id=eq.{q(d.get('id'))}&select=*")
        if not h:
            raise Fail('Hostel not found', 404)
        return {'hostel': h[0], 'floors': [], 'beds': []}

    def apply(d):
        v = {k: str(d.get(k) or '').strip() for k in ('hostel_id', 'name', 'email', 'phone', 'aadhaar', 'parent_name', 'parent_phone',
                                                      'id_proof', 'address', 'purpose', 'college', 'office', 'join_date', 'photo_url')}
        v['email'] = v['email'].lower()
        if len(v['name']) < 2 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v['email']) \
                or not re.fullmatch(r'\+?\d[\d\s-]{8,14}', v['phone']) or not v['address']:
            raise Fail('Please enter your name, a valid email, mobile number and permanent address.')
        if v['aadhaar'] and not re.fullmatch(r'\d{12}', v['aadhaar'].replace(' ', '')):
            raise Fail('Aadhaar number must be 12 digits.')
        v['join_date'] = v['join_date'] if re.fullmatch(r'\d{4}-\d\d-\d\d', v['join_date']) else None
        row = {k: (x or None) for k, x in v.items()}
        sb('POST', 'applications', row)
        c = cfg()
        mail(c.get('admin_email'), f"New hostel application: {v['name']}", f"{v['name']} ({v['phone']}, {v['email']}) applied. Review it in the admin portal.")
        mail(v['email'], 'We received your hostel application', 'Thank you. The hostel team will review your application. '
             'Log in with this email address on the website to check your status.')
        return {'ok': 1, 'emailed': bool(c.get('user'))}

    def login_email(d):  # basic access: email only
        e = str(d.get('email') or '').strip().lower()
        if not apps_of(e):
            raise Fail('No application found for this email. Please apply first.', 404)
        return {'token': umint(e, 'basic'), 'level': 'basic'}

    def otp_send(d):
        e = str(d.get('email') or '').strip().lower()
        if not apps_of(e):
            raise Fail('No application found for this email.', 404)
        code = f'{secrets.randbelow(10**6):06d}'
        sb('DELETE', f'otps?email=eq.{q(e)}')
        sb('POST', 'otps', {'email': e, 'h': sign(e + code), 'exp': int(time.time()) + 600})
        if not mail(e, 'Your hostel login code', f'Your code is {code}. It expires in 10 minutes.'):
            sb('DELETE', f'otps?email=eq.{q(e)}')
            raise Fail('Email is not set up yet, so a code cannot be sent. You can still continue with basic access.')
        return {'ok': 1}

    def otp_verify(d):
        e, code = str(d.get('email') or '').strip().lower(), str(d.get('code') or '').strip()
        r = sb('GET', f'otps?email=eq.{q(e)}&select=*')
        if not r or r[0]['exp'] < time.time() or r[0]['tries'] >= 5:
            raise Fail('Code expired. Please request a new one.', 401)
        if not hmac.compare_digest(r[0]['h'], sign(e + code)):
            sb('PATCH', f'otps?email=eq.{q(e)}', {'tries': r[0]['tries'] + 1})
            raise Fail('Incorrect code.', 401)
        sb('DELETE', f'otps?email=eq.{q(e)}')
        return {'token': umint(e, 'full'), 'level': 'full'}

    def me(d):
        e, lvl = uread(d['_a'])
        if not e:
            raise Fail('Please log in again.', 401)
        out = apps_of(e)
        if lvl != 'full':  # personal details hidden without OTP
            for a in out:
                for k in MASK:
                    a[k] = None
        return {'level': lvl, 'email': e, 'apps': out}

    def plan(d):  # floor map + availability: only for approved applicants (or admin)
        hid = str(d.get('hostel_id') or '')
        e, _ = uread(d['_a'])
        if not authed(d['_a']) and not (e and any(a['status'] == 'approved' and a['hostel_id'] == hid for a in apps_of(e))):
            raise Fail('The floor plan is available after the hostel approves your application.', 403)
        return old_hostel({'id': hid})

    # ---- admin ----
    def get_settings(d):
        c = dict(cfg())
        c['pass'] = '********' if c.get('pass') else ''
        return c

    def save_settings(d):
        old = cfg()
        new = {k: str(d.get(k) or '').strip() for k in ('user', 'pass', 'from', 'admin_email', 'site_url')}
        if new['pass'] in ('', '********'):
            new['pass'] = old.get('pass', '')
        sb('POST', 'settings?on_conflict=key', {'key': 'mail', 'value': new}) if not old else sb('PATCH', 'settings?key=eq.mail', {'value': new})
        return {'ok': 1}

    def test_mail(d):
        c = cfg()
        if not mail(c.get('admin_email') or c.get('user'), 'HostelAtlas test email', 'Email is working.'):
            raise Fail('Could not send. Check the Gmail address and app password (2-step verification must be on).')
        return {'ok': 1}

    def applications(d):
        return sb('GET', 'applications?select=*,hostels(name)&order=created_at.desc&limit=300')

    def decide(d):
        st = d.get('status')
        if st not in ('approved', 'rejected'):
            raise Fail('Invalid status.')
        a = sb('PATCH', f"applications?id=eq.{q(d.get('id'))}", {'status': st})
        if a:
            site = cfg().get('site_url', '')
            mail(a[0]['email'], 'Your hostel application', ('Approved! Log in with this email on ' + site + ' to view the floor plan and choose a bed.')
                 if st == 'approved' else 'Sorry, the hostel could not approve your application.')
        return {'ok': 1}

    g['_h'] = dict(mail=mail, uread=uread, apps_of=apps_of, cfg=cfg)
    PUB.update(hostels=hostels, hostel=hostel, apply=apply, login_email=login_email, otp_send=otp_send,
               otp_verify=otp_verify, me=me, plan=plan)
    ADM.update(get_settings=get_settings, save_settings=save_settings, test_mail=test_mail,
               applications=applications, decide=decide)

    def route(d, auth):
        d['_a'] = auth
        return old_route(d, auth)
    g['route'] = route
