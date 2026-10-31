"""HostelAtlas applicant flow: email settings, application form, email-code sign-in, gated floor plan.
Loaded automatically by api/index.py. Applicants prove they own their email with a one-time code before
any of their data is shown, so Gmail (Admin > Email) must be set up for applicants to sign in.
Mail for notifications is best-effort: the app keeps working if a message cannot be sent."""
import time, hmac, secrets, smtplib, ssl, re
from email.message import EmailMessage

FIELDS = ('hostel_id', 'name', 'email', 'phone', 'aadhaar', 'parent_name', 'parent_phone', 'id_proof', 'address',
          'purpose', 'college', 'office', 'join_date', 'photo_url')
OPEN = 'status=in.(pending,approved,assigned,paid,verified,resident)'
EMAIL = r'[^@\s|]+@[^@\s|]+\.[^@\s|]+'
PHONE = r'\+?\d[\d\s-]{8,14}'
TTL = 600  # seconds an emailed code stays valid


def install(g):
    sb, Fail, q, sign, authed, throttle, uid = g['sb'], g['Fail'], g['q'], g['sign'], g['authed'], g['throttle'], g['uid']
    PUB, ADM = g['PUB'], g['ADM']
    old_hostel, old_hostels = PUB['hostel'], PUB['hostels']
    usign = lambda p: sign('u|' + p)  # domain-separated from admin tokens and code hashes
    csign = lambda e, c: sign('otp|' + e + '|' + c)

    def cfg():
        r = sb('GET', 'settings?key=eq.mail&select=value')
        return (r[0]['value'] or {}) if r else {}

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

    def strong():
        return len(g['SECRET']) >= 16

    # ---- applicant tokens: u.<hex payload>.<sig>, issued only after the emailed code is verified ----
    def umint(email):
        if not strong():
            raise Fail('Server is not configured: set SESSION_SECRET to a long random string.', 500)
        p = f'{email}|full|{int(time.time()) + 7 * 86400}'
        return 'u.' + p.encode().hex() + '.' + usign(p)

    def uread(h):
        try:
            tag, x, s = (h or '').replace('Bearer ', '').strip().split('.')
            p = bytes.fromhex(x).decode()
            e, lvl, t = p.split('|')
            if strong() and tag == 'u' and lvl == 'full' and int(t) > time.time() and hmac.compare_digest(s, usign(p)):
                return e, lvl
        except Exception:
            pass
        return None, None

    def apps_of(email):
        return sb('GET', f'applications?email=eq.{q(email)}&select=*,hostels(name,phone)&order=created_at.desc')

    def email_of(d):
        e = str(d.get('email') or '').strip().lower()
        if not re.fullmatch(EMAIL, e):
            raise Fail('Please enter a valid email address.')
        return e

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
        h = sb('GET', f"hostels?id=eq.{uid(d.get('id'), 'Hostel')}&select=*")
        if not h:
            raise Fail('Hostel not found', 404)
        return {'hostel': h[0], 'floors': [], 'beds': []}

    def apply(d):
        throttle('apply:' + d['_ip'], 5, 3600)
        v = {k: str(d.get(k) or '').strip()[:300] for k in FIELDS}
        v['email'], v['aadhaar'] = v['email'].lower(), re.sub(r'\s', '', v['aadhaar'])
        if len(v['name']) < 2 or not re.fullmatch(EMAIL, v['email']) \
                or not re.fullmatch(PHONE, v['phone']) or not v['address']:
            raise Fail('Please enter your name, a valid email, mobile number and permanent address.')
        if v['aadhaar'] and not re.fullmatch(r'\d{12}', v['aadhaar']):
            raise Fail('Aadhaar number must be 12 digits.')
        if v['parent_phone'] and not re.fullmatch(PHONE, v['parent_phone']):
            raise Fail('Please enter a valid parent mobile number.')
        if v['photo_url'] and not re.match(r'https?://', v['photo_url'], re.I):
            raise Fail('Photo link must start with https://')
        v['join_date'] = v['join_date'] if re.fullmatch(r'\d{4}-\d\d-\d\d', v['join_date']) else None
        v['hostel_id'] = uid(v['hostel_id'], 'Hostel')
        if not sb('GET', f"hostels?id=eq.{v['hostel_id']}&select=id"):
            raise Fail('Hostel not found.', 404)
        if sb('GET', f"applications?email=eq.{q(v['email'])}&hostel_id=eq.{v['hostel_id']}&{OPEN}&select=id"):
            raise Fail('You already have an open application for this hostel. Sign in with your email to see it.')
        sb('POST', 'applications', {k: (x or None) for k, x in v.items()})
        c = cfg()
        mail(c.get('admin_email'), f"New hostel application: {v['name']}",
             f"{v['name']} ({v['phone']}, {v['email']}) applied. Review it in the admin portal.")
        mail(v['email'], 'We received your hostel application', 'Thank you. The hostel team will review your application. '
             'Sign in on the website with this email address to check your status.')
        return {'ok': 1, 'emailed': bool(c.get('user'))}

    def otp_send(d):
        e = email_of(d)
        c = cfg()
        if not (c.get('user') and c.get('pass')):
            raise Fail('Email sign-in is not set up yet. Please contact the hostel.', 503)
        if not strong():
            raise Fail('Server is not configured: set SESSION_SECRET to a long random string.', 500)
        throttle('otp:' + d['_ip'], 10, 900)
        r = sb('GET', f'otps?email=eq.{q(e)}&select=exp')
        if r and r[0]['exp'] - TTL + 60 > time.time():
            raise Fail('A code was sent less than a minute ago. Check your inbox and spam folder.', 429)
        if not sb('GET', f'applications?email=eq.{q(e)}&select=id&limit=1'):
            return {'ok': 1}  # same answer as success, so the form never reveals who has applied
        code = f'{secrets.randbelow(10**6):06d}'
        sb('DELETE', f'otps?email=eq.{q(e)}')
        sb('POST', 'otps', {'email': e, 'h': csign(e, code), 'exp': int(time.time()) + TTL, 'tries': 0})
        if not mail(e, f'{code} is your hostel sign-in code', f'Your code is {code}. It expires in 10 minutes.\n'
                    'If you did not ask for it, you can ignore this email.'):
            sb('DELETE', f'otps?email=eq.{q(e)}')
            raise Fail('The code could not be emailed right now. Please try again shortly.', 502)
        return {'ok': 1}

    def otp_verify(d):
        e, code = email_of(d), str(d.get('code') or '').strip()
        throttle('otpv:' + d['_ip'], 30, 900)
        r = sb('GET', f'otps?email=eq.{q(e)}&select=*')
        n = r[0]['tries'] if r else None
        if not r or r[0]['exp'] < time.time() or (n or 0) >= 5:
            raise Fail('This code has expired. Please request a new one.', 401)
        # claim the attempt first (compare-and-set on tries), so parallel guesses cannot beat the limit
        cas = 'tries=is.null' if n is None else f'tries=eq.{n}'
        if not sb('PATCH', f'otps?email=eq.{q(e)}&{cas}', {'tries': (n or 0) + 1}):
            raise Fail('Please try again.', 409)
        if not re.fullmatch(r'\d{6}', code) or not hmac.compare_digest(r[0]['h'], csign(e, code)):
            raise Fail('Incorrect code.', 401)
        sb('DELETE', f'otps?email=eq.{q(e)}')
        return {'token': umint(e), 'email': e}

    def me(d):
        e, _ = uread(d['_a'])
        if not e:
            raise Fail('Please sign in again.', 401)
        return {'email': e, 'apps': apps_of(e)}

    def plan(d):  # floor map + availability: only for approved applicants (or admin)
        hid = uid(d.get('hostel_id'), 'Hostel')
        if not authed(d['_a']):
            e, _ = uread(d['_a'])
            if not e:
                raise Fail('Please sign in again.', 401)
            if not any(a['status'] == 'approved' and a['hostel_id'] == hid for a in apps_of(e)):
                raise Fail('The floor plan is available after the hostel approves your application.', 403)
        return old_hostel({'id': hid})

    # ---- admin ----
    def get_settings(d):
        c = dict(cfg())
        c['pass'] = '********' if c.get('pass') else ''
        return c

    def save_settings(d):
        old = cfg()
        new = {k: str(d.get(k) or '').strip()[:200] for k in ('user', 'pass', 'from', 'admin_email', 'site_url')}
        for k in ('user', 'admin_email'):
            if new[k] and not re.fullmatch(EMAIL, new[k]):
                raise Fail('Please enter valid email addresses.')
        if new['pass'] in ('', '********'):
            new['pass'] = old.get('pass', '')
        if sb('GET', 'settings?key=eq.mail&select=key'):
            sb('PATCH', 'settings?key=eq.mail', {'value': new})
        else:
            sb('POST', 'settings', {'key': 'mail', 'value': new})
        return {'ok': 1}

    def test_mail(d):
        c = cfg()
        if not mail(c.get('admin_email') or c.get('user'), 'HostelAtlas test email', 'Email is working.'):
            raise Fail('Could not send. Check the Gmail address and app password (2-step verification must be on).')
        return {'ok': 1}

    def applications(d):
        return sb('GET', 'applications?select=*,hostels(name)&order=created_at.desc&limit=500')

    def decide(d):
        st = d.get('status')
        if st not in ('approved', 'rejected'):
            raise Fail('Invalid status.')
        a = sb('PATCH', f"applications?id=eq.{uid(d.get('id'), 'Application')}&status=eq.pending", {'status': st})
        if not a:
            raise Fail('This application was already decided. Refresh to see its status.', 409)
        site = cfg().get('site_url') or 'the hostel website'
        mail(a[0]['email'], 'Your hostel application',
             f'Approved! Sign in with this email on {site} to view the floor plan and choose your bed.'
             if st == 'approved' else 'Sorry, the hostel could not approve your application.')
        return {'ok': 1}

    g['_h'] = dict(mail=mail, uread=uread, apps_of=apps_of, cfg=cfg)
    for k in ('book', 'track', 'login_email'):  # replaced by applications and email-code sign-in
        PUB.pop(k, None)
    PUB.update(hostels=hostels, hostel=hostel, apply=apply, otp_send=otp_send, otp_verify=otp_verify, me=me, plan=plan)
    ADM.update(get_settings=get_settings, save_settings=save_settings, test_mail=test_mail,
               applications=applications, decide=decide)
