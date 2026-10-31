"""HostelAtlas resident operations: bed choice and assignment, payment reference and verification,
check-in / check-out, maintenance tickets. Loaded automatically by api/index.py after _flow.
Every status change is conditional on the current status, so double clicks and stale screens cannot skip steps."""
import re, time

LIVE = 'status=in.(assigned,paid,verified,resident)'
IST = 19800  # India Standard Time offset in seconds, so check-in dates follow the hostel's calendar


def install(g):
    sb, Fail, q, authed, num, uid, PUB, ADM, H = (g[k] for k in ('sb', 'Fail', 'q', 'authed', 'num', 'uid', 'PUB', 'ADM', '_h'))
    mail, uread, cfg = H['mail'], H['uread'], H['cfg']
    old_plan, old_me, old_hostels = PUB['plan'], PUB['me'], PUB['hostels']
    now = lambda: time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    when = lambda v: v if re.match(r'\d{4}-\d\d-\d\dT\d\d:\d\d', str(v or '')) else None

    def own(d):
        e, _ = uread(d['_a'])
        if not e:
            raise Fail('Please sign in again.', 401)
        r = sb('GET', f"applications?id=eq.{uid(d.get('app_id'), 'Application')}&email=eq.{q(e)}&select=*")
        if not r:
            raise Fail('Application not found.', 404)
        return r[0]

    def app(i):
        r = sb('GET', f"applications?id=eq.{uid(i, 'Application')}&select=*")
        if not r:
            raise Fail('Application not found.', 404)
        return r[0]

    def taken(bed, skip=None):
        return any(x['id'] != skip for x in sb('GET', f'applications?bed_id=eq.{q(bed)}&{LIVE}&select=id'))

    def free_bed(bed, hostel_id, skip=None):
        b = sb('GET', f"bed_live?id=eq.{uid(bed, 'Bed')}&hostel_id=eq.{q(hostel_id)}&select=id,code,price,live")
        if not b or b[0]['live'] != 'available' or taken(b[0]['id'], skip):
            raise Fail('That bed is no longer available. Please pick another.', 409)
        return b[0]

    def move(i, states, f):
        """Update an application only while it is still in one of `states`."""
        r = sb('PATCH', f"applications?id=eq.{uid(i, 'Application')}&status=in.({','.join(states)})", f)
        if not r:
            raise Fail('This application changed since the page loaded. Refresh and try again.', 409)
        return r[0]

    def tell_admin(subj, body):
        mail(cfg().get('admin_email'), subj, body)

    def hostels(d):  # admin overview: beds held by applications count as reserved / occupied
        hs = old_hostels(d)
        if authed(d['_a']):
            by = {h['id']: h for h in hs}
            for a in sb('GET', f'applications?bed_id=not.is.null&{LIVE}&select=hostel_id,status&limit=5000'):
                h = by.get(a['hostel_id'])
                if h and h['stat'].get('available'):
                    k = 'occupied' if a['status'] == 'resident' else 'reserved'
                    h['stat']['available'] -= 1
                    h['stat'][k] = h['stat'].get(k, 0) + 1
                    h['free'] = h['stat']['available']
        return hs

    def plan(d):  # overlay application bed assignments on the availability map
        r = old_plan(d)
        m = {a['bed_id']: a['status'] for a in sb('GET', f"applications?hostel_id=eq.{q(d.get('hostel_id'))}&bed_id=not.is.null&{LIVE}&select=bed_id,status")}
        for b in r['beds']:
            if b['id'] in m and b['live'] == 'available':
                b['live'] = 'occupied' if m[b['id']] == 'resident' else 'reserved'
        return r

    def me(d):
        r = old_me(d)
        ids = [a['id'] for a in r['apps']]
        bids = [a['bed_id'] for a in r['apps'] if a.get('bed_id')]
        codes = {b['id']: b['code'] for b in sb('GET', f"beds?id=in.({','.join(bids)})&select=id,code")} if bids else {}
        for a in r['apps']:
            a['bed_code'] = codes.get(a.get('bed_id'))
        r['tickets'] = sb('GET', f"tickets?app_id=in.({','.join(ids)})&order=created_at.desc") if ids else []
        return r

    # ---- applicant actions ----
    def pick_bed(d):
        a = own(d)
        if a['status'] != 'approved':
            raise Fail('You can choose a bed only once, after approval. Ask the hostel to change it.')
        b = free_bed(d.get('bed_id'), a['hostel_id'])
        move(a['id'], ('approved',), {'bed_id': b['id'], 'status': 'assigned', 'amount_due': b['price'] or 0})
        tell_admin('Bed chosen', f"{a['name']} chose bed {b['code']}. Set the payment due time in the admin portal.")
        return {'ok': 1}

    def pay(d):
        a = own(d)
        ref = str(d.get('ref') or '').strip()[:60]
        if a['status'] != 'assigned' or len(ref) < 4:
            raise Fail('Enter your payment reference (UPI transaction ID) after a bed is assigned.')
        move(a['id'], ('assigned',), {'paid_ref': ref, 'status': 'paid'})
        tell_admin('Payment submitted', f"{a['name']} submitted payment reference {ref}. Please verify it.")
        return {'ok': 1}

    def ticket_new(d):
        a = own(d)
        t = str(d.get('title') or '').strip()
        if a['status'] != 'resident' or len(t) < 3:
            raise Fail('Requests can be raised by residents. Please describe the problem.')
        if len(sb('GET', f"tickets?app_id=eq.{a['id']}&status=in.(open,in_progress)&select=id")) >= 5:
            raise Fail('You already have 5 open requests. Please wait for the hostel to close one.')
        sb('POST', 'tickets', {'app_id': a['id'], 'hostel_id': a['hostel_id'], 'title': t[:120], 'detail': str(d.get('detail') or '').strip()[:1000] or None})
        tell_admin('New maintenance request', f"{a['name']}: {t}")
        return {'ok': 1}

    # ---- admin actions ----
    def residents(d):
        return sb('GET', 'applications?status=in.(approved,assigned,paid,verified,resident)&select=*,beds(code),hostels(name)&order=created_at.desc&limit=500')

    def assign(d):
        a = app(d.get('id'))
        b = free_bed(d.get('bed_id'), a['hostel_id'], a['id'])
        r = move(a['id'], ('approved', 'assigned'), {'bed_id': b['id'], 'status': 'assigned',
                                                    'amount_due': max(num(d.get('amount')), 0), 'due_at': when(d.get('due_at'))})
        mail(r['email'], 'Your bed is assigned', f"Bed {b['code']} has been assigned to you. Sign in to see the amount and pay by the due time.")
        return {'ok': 1}

    def set_fee(d):
        move(d.get('id'), ('assigned', 'paid', 'verified', 'resident'),
             {'amount_due': max(num(d.get('amount')), 0), 'due_at': when(d.get('due_at')),
              'plan': d.get('plan') if d.get('plan') in ('full', 'bed_only') else 'full'})
        return {'ok': 1}

    def verify(d):  # also from 'assigned', for residents who paid in cash without submitting a reference
        a = app(d.get('id'))
        paid = max(num(d.get('paid'), a['amount_due'] or 0), 0)
        r = move(a['id'], ('assigned', 'paid'), {'status': 'verified', 'paid_amount': paid, 'verified_at': now()})
        mail(r['email'], 'Payment verified', 'Your payment is verified. The hostel will check you in.')
        return {'ok': 1}

    def checkin(d):
        r = move(d.get('id'), ('verified',), {'status': 'resident', 'checkin_date': time.strftime('%Y-%m-%d', time.gmtime(time.time() + IST))})
        mail(r['email'], 'Welcome!', 'You are checked in. Sign in to see fees and raise maintenance requests.')
        return {'ok': 1}

    def checkout(d):  # also releases a bed held by someone who never moved in
        move(d.get('id'), ('assigned', 'paid', 'verified', 'resident'), {'status': 'left', 'bed_id': None})
        return {'ok': 1}

    def tickets(d):
        return sb('GET', 'tickets?select=*,applications(name),hostels(name)&order=created_at.desc&limit=300')

    def set_ticket(d):
        st = d.get('status') if d.get('status') in ('open', 'in_progress', 'done') else 'open'
        if not sb('PATCH', f"tickets?id=eq.{uid(d.get('id'), 'Request')}", {'status': st, 'reply': str(d.get('reply') or '').strip()[:500] or None}):
            raise Fail('Request not found.', 404)
        return {'ok': 1}

    PUB.update(hostels=hostels, plan=plan, me=me, pick_bed=pick_bed, pay=pay, ticket_new=ticket_new)
    ADM.update(residents=residents, assign=assign, set_fee=set_fee, verify=verify, checkin=checkin, checkout=checkout, tickets=tickets, set_ticket=set_ticket)
