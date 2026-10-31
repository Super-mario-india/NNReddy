"""HostelAtlas resident operations: bed choice and assignment, joining payment, check-in / check-out,
monthly fee tracking (the payments ledger) and maintenance requests. Loaded automatically by api/index.py after _flow.
Every status change is conditional on the current status, so double clicks and stale screens cannot skip steps.

Fees: the joining charge and joining payment live on the application row (amount_due / paid_amount). Everything
after check-in is a row in `payments` (kind 'charge' or 'payment'), so each change is a single atomic insert or update
and the full history is kept. Without the payments table the app keeps working and reports ledger=False."""
import re, time, calendar
from datetime import datetime

LIVE = 'status=in.(assigned,paid,verified,resident)'
IST = 19800  # India Standard Time offset in seconds, so dates follow the hostel's calendar
MAX_AMOUNT = 10_00_000


def stamp(s):
    """Database timestamp text -> seconds since 1970 (0 when missing or unreadable)."""
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()
    except (TypeError, ValueError):
        return 0


def install(g):
    sb, Fail, q, authed, num, uid, PUB, ADM, H = (g[k] for k in ('sb', 'Fail', 'q', 'authed', 'num', 'uid', 'PUB', 'ADM', '_h'))
    mail, uread, cfg, profiles = H['mail'], H['uread'], H['cfg'], g['profiles']
    old_plan, old_me, old_hostels = PUB['plan'], PUB['me'], PUB['hostels']
    now = lambda: time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    today = lambda: time.strftime('%Y-%m-%d', time.gmtime(time.time() + IST))
    when = lambda v: v if re.match(r'\d{4}-\d\d-\d\dT\d\d:\d\d', str(v or '')) else None
    rs = lambda n: f"Rs {n:,}"

    def amount(v, default=None):
        n = num(v, default if default is not None else 0)
        if not 0 < n <= MAX_AMOUNT:
            raise Fail('Enter an amount in rupees.')
        return n

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

    # ---- fee ledger ----
    def ledger_rows(flt):
        """Payments rows for a filter, or None when the payments table has not been created yet."""
        try:
            return sb('GET', f'payments?{flt}&order=created_at.desc&limit=10000')
        except Fail as e:
            if e.code == 503:
                return None
            raise

    def fees(a, rows):
        mine = [r for r in rows or [] if r['app_id'] == a['id']]
        due = (a.get('amount_due') or 0) + sum(r['amount'] for r in mine if r['kind'] == 'charge')
        paid = (a.get('paid_amount') or 0) + sum(r['amount'] for r in mine if r['kind'] == 'payment' and r['status'] == 'verified')
        dues = [r['due_at'] for r in mine if r['kind'] == 'charge' and r.get('due_at')]
        pend = [r for r in mine if r['kind'] == 'payment' and r['status'] == 'submitted']
        if a['status'] == 'paid' and not pend and a.get('paid_ref'):
            pend = [{'amount': max((a.get('amount_due') or 0) - (a.get('paid_amount') or 0), 0)}]
        return {'due': due, 'paid': paid, 'balance': max(due - paid, 0), 'credit': max(paid - due, 0),
                'due_at': max(dues) if dues else a.get('due_at'), 'pending': sum(r['amount'] for r in pend)}

    def history(a, rows):
        """Ledger rows plus the joining charge / payment kept on the application, newest first."""
        h = [dict(r) for r in rows or [] if r['app_id'] == a['id']]
        if a.get('amount_due'):
            h.append({'id': None, 'kind': 'charge', 'amount': a['amount_due'], 'label': 'Joining charges', 'status': 'verified',
                      'created_at': a.get('created_at'), 'due_at': a.get('due_at'), 'fixed': True})
        if a.get('paid_amount'):
            h.append({'id': None, 'kind': 'payment', 'amount': a['paid_amount'], 'label': 'Joining payment', 'ref': a.get('paid_ref'),
                      'status': 'verified', 'created_at': a.get('verified_at') or a.get('created_at'), 'fixed': True})
        elif a['status'] == 'paid' and a.get('paid_ref'):
            h.append({'id': None, 'kind': 'payment', 'amount': a.get('amount_due') or 0, 'label': 'Joining payment', 'ref': a['paid_ref'],
                      'status': 'submitted', 'created_at': a.get('created_at'), 'fixed': True})
        return sorted(h, key=lambda r: r.get('created_at') or '', reverse=True)

    def entry(pid, **flt):
        r = sb('GET', '&'.join([f"payments?id=eq.{uid(pid, 'Payment')}", *(f'{k}=eq.{v}' for k, v in flt.items()), 'select=*,applications(name,email)']))
        if not r:
            raise Fail('This entry was already changed. Refresh to see the latest.', 409)
        return r[0]

    # ---- public / applicant ----
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
        rows = ledger_rows(f"app_id=in.({','.join(ids)})") if ids else []
        P = profiles()
        for a in r['apps']:
            a['bed_code'] = codes.get(a.get('bed_id'))
            a['fees'], a['history'] = fees(a, rows), history(a, rows)
            p = P.get(a['hostel_id']) or {}
            a['hostel_timings'], a['hostel_notice'] = p.get('timings') or [], p.get('notice') or ''
        r['ledger'] = rows is not None
        r['tickets'] = sb('GET', f"tickets?app_id=in.({','.join(ids)})&order=created_at.desc") if ids else []
        return r

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
        if len(ref) < 4:
            raise Fail('Enter the UPI transaction ID from your payment app.')
        if a['status'] == 'assigned':  # joining payment
            move(a['id'], ('assigned',), {'paid_ref': ref, 'status': 'paid'})
        elif a['status'] in ('verified', 'resident'):
            rows = ledger_rows(f"app_id=eq.{a['id']}")
            if rows is None:
                raise Fail('Paying from the app is not switched on yet. Please tell the hostel office you have paid.', 503)
            if sum(r['kind'] == 'payment' and r['status'] == 'submitted' for r in rows) >= 3:
                raise Fail('You already have payments waiting for the hostel to confirm.')
            amt = amount(d.get('amount'), fees(a, rows)['balance'])
            sb('POST', 'payments', {'app_id': a['id'], 'hostel_id': a['hostel_id'], 'kind': 'payment', 'amount': amt,
                                    'ref': ref, 'status': 'submitted', 'label': 'Payment'})
        else:
            raise Fail('Payments open once your bed is reserved.')
        tell_admin('Payment submitted', f"{a['name']} submitted payment reference {ref}. Please verify it in the admin portal.")
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

    # ---- admin: people ----
    def residents(d):
        L = sb('GET', 'applications?status=in.(approved,assigned,paid,verified,resident,left)&select=*,beds(code,price),hostels(name,phone)&order=created_at.desc&limit=1000')
        rows = ledger_rows('select=app_id,kind,amount,status,due_at,created_at')
        for a in L:
            a['fees'] = fees(a, rows)
        t = time.gmtime(time.time() + IST)
        m0 = calendar.timegm((t.tm_year, t.tm_mon, 1, 0, 0, 0)) - IST  # start of this month in India, as a UTC instant
        sub = ledger_rows('kind=eq.payment&status=eq.submitted&select=*,applications(name),hostels(name)') or []
        got = sum(r['amount'] for r in rows or [] if r['kind'] == 'payment' and r['status'] == 'verified' and stamp(r['created_at']) >= m0)
        got += sum(a.get('paid_amount') or 0 for a in L if stamp(a.get('verified_at')) >= m0)
        return {'list': L, 'ledger': rows is not None, 'submitted': sub, 'collected_month': got}

    def ledger(d):
        a = app(d.get('id'))
        rows = ledger_rows(f"app_id=eq.{a['id']}")
        return {'fees': fees(a, rows), 'history': history(a, rows), 'ledger': rows is not None}

    def assign(d):
        a = app(d.get('id'))
        b = free_bed(d.get('bed_id'), a['hostel_id'], a['id'])
        r = move(a['id'], ('approved', 'assigned'), {'bed_id': b['id'], 'status': 'assigned',
                                                    'amount_due': max(num(d.get('amount')), 0), 'due_at': when(d.get('due_at'))})
        mail(r['email'], 'Your bed is assigned', f"Bed {b['code']} has been assigned to you. Sign in to see the amount and pay by the due time.")
        return {'ok': 1}

    def set_fee(d):  # joining amount (before check-in), monthly rent, plan and due date
        f = {'due_at': when(d.get('due_at')), 'plan': d.get('plan') if d.get('plan') in ('full', 'bed_only') else 'full'}
        if d.get('amount') not in (None, ''):
            f['amount_due'] = max(num(d.get('amount')), 0)
        if d.get('rent') not in (None, ''):
            f['rent'] = max(num(d.get('rent')), 0) or None
        move(d.get('id'), ('assigned', 'paid', 'verified', 'resident'), f)
        return {'ok': 1}

    def verify(d):  # joining payment, also from 'assigned' for people who paid in cash without a reference
        a = app(d.get('id'))
        paid = max(num(d.get('paid'), a['amount_due'] or 0), 0)
        r = move(a['id'], ('assigned', 'paid'), {'status': 'verified', 'paid_amount': paid, 'verified_at': now()})
        mail(r['email'], 'Payment verified', 'Your payment is verified. The hostel will check you in.')
        return {'ok': 1}

    def charge(d):
        a = app(d.get('id'))
        if a['status'] not in ('verified', 'resident'):
            raise Fail('Add charges after the joining payment is verified. Before that, edit the joining amount instead.')
        amt, label = amount(d.get('amount')), str(d.get('label') or '').strip()[:80] or 'Charge'
        sb('POST', 'payments', {'app_id': a['id'], 'hostel_id': a['hostel_id'], 'kind': 'charge', 'amount': amt,
                                'label': label, 'due_at': when(d.get('due_at')), 'status': 'verified'})
        mail(a['email'], f'{label}: {rs(amt)} due', f"{label}: {rs(amt)} has been added to your hostel account. Sign in to see your balance.")
        return {'ok': 1}

    def bill_month(d):
        per = str(d.get('period') or '')
        if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', per):
            raise Fail('Choose the month to charge.')
        hf = f"&hostel_id=eq.{uid(d['hostel_id'], 'Hostel')}" if d.get('hostel_id') else ''
        people = sb('GET', f'applications?status=eq.resident{hf}&select=*&limit=2000')
        if ledger_rows('limit=1') is None:
            raise Fail(g['UPGRADE'], 503)
        done = {r['app_id'] for r in sb('GET', f'payments?kind=eq.charge&period=eq.{per}&select=app_id&limit=10000')}
        bids = [a['bed_id'] for a in people if a.get('bed_id')]
        price = {b['id']: b['price'] for b in sb('GET', f"beds?id=in.({','.join(bids)})&select=id,price")} if bids else {}
        fee = {k: v.get('fee') for k, v in profiles().items()}
        label, due = 'Rent for ' + time.strftime('%B %Y', time.strptime(per, '%Y-%m')), when(d.get('due_at'))
        rows, out = [], {'charged': 0, 'skipped': 0, 'no_rent': 0, 'total': 0}
        for a in people:
            amt = a.get('rent') or price.get(a.get('bed_id')) or fee.get(a['hostel_id']) or 0
            if a['id'] in done:
                out['skipped'] += 1
            elif amt <= 0:
                out['no_rent'] += 1
            else:
                rows.append({'app_id': a['id'], 'hostel_id': a['hostel_id'], 'kind': 'charge', 'amount': amt, 'label': label,
                             'period': per, 'due_at': due, 'status': 'verified'})
                out['charged'] += 1
                out['total'] += amt
        if rows:  # one insert: all residents are charged, or none are
            sb('POST', 'payments', rows)
        return out

    def record_payment(d):  # money received at the office
        a = app(d.get('id'))
        if a['status'] in ('assigned', 'paid'):
            return verify({'id': a['id'], 'paid': d.get('amount')})
        if a['status'] not in ('verified', 'resident', 'left'):
            raise Fail('Payments can be recorded once a bed is assigned.')
        amt = amount(d.get('amount'))
        sb('POST', 'payments', {'app_id': a['id'], 'hostel_id': a['hostel_id'], 'kind': 'payment', 'amount': amt, 'status': 'verified',
                                'ref': str(d.get('ref') or '').strip()[:60] or None, 'label': str(d.get('label') or '').strip()[:80] or 'Payment'})
        mail(a['email'], 'Payment received', f"We received your payment of {rs(amt)}. Thank you.")
        return {'ok': 1}

    def verify_payment(d):
        p = entry(d.get('payment_id'), kind='payment', status='submitted')
        f = {'status': 'verified'}
        if d.get('amount') not in (None, ''):
            f['amount'] = amount(d.get('amount'))
        if not sb('PATCH', f"payments?id=eq.{p['id']}&status=eq.submitted", f):
            raise Fail('This payment was already handled.', 409)
        mail((p.get('applications') or {}).get('email'), 'Payment confirmed', f"Your payment of {rs(f.get('amount', p['amount']))} (ref {p.get('ref') or '-'}) is confirmed. Thank you.")
        return {'ok': 1}

    def reject_payment(d):
        p = entry(d.get('payment_id'), kind='payment', status='submitted')
        if not sb('PATCH', f"payments?id=eq.{p['id']}&status=eq.submitted", {'status': 'rejected'}):
            raise Fail('This payment was already handled.', 409)
        mail((p.get('applications') or {}).get('email'), 'Payment not confirmed',
             f"We could not find your payment of {rs(p['amount'])} (ref {p.get('ref') or '-'}). Please contact the hostel office.")
        return {'ok': 1}

    def del_entry(d):  # undo a mistaken charge or payment
        p = entry(d.get('payment_id'))
        sb('DELETE', f"payments?id=eq.{p['id']}")
        return {'ok': 1}

    def checkin(d):
        r = move(d.get('id'), ('verified',), {'status': 'resident', 'checkin_date': today()})
        mail(r['email'], 'Welcome!', 'You are checked in. Sign in to see fees and raise maintenance requests.')
        return {'ok': 1}

    def checkout(d):  # also releases a bed held by someone who never moved in
        move(d.get('id'), ('assigned', 'paid', 'verified', 'resident'), {'status': 'left', 'bed_id': None})
        return {'ok': 1}

    # ---- admin: maintenance ----
    def tickets(d):
        return sb('GET', 'tickets?select=*,applications(name,phone,email,bed_id,beds(code)),hostels(name)&order=created_at.desc&limit=500')

    def set_ticket(d):
        st = d.get('status') if d.get('status') in ('open', 'in_progress', 'done') else 'open'
        reply = str(d.get('reply') or '').strip()[:500] or None
        r = sb('PATCH', f"tickets?id=eq.{uid(d.get('id'), 'Request')}", {'status': st, 'reply': reply})
        if not r:
            raise Fail('Request not found.', 404)
        a = sb('GET', f"applications?id=eq.{r[0]['app_id']}&select=email")
        words = {'open': 'is open', 'in_progress': 'is being worked on', 'done': 'is resolved'}[st]
        mail(a[0]['email'] if a else None, f"Request update: {r[0]['title']}",
             f"Your request \"{r[0]['title']}\" {words}." + (f"\n\nHostel: {reply}" if reply else ''))
        return {'ok': 1}

    PUB.update(hostels=hostels, plan=plan, me=me, pick_bed=pick_bed, pay=pay, ticket_new=ticket_new)
    ADM.update(residents=residents, ledger=ledger, assign=assign, set_fee=set_fee, verify=verify, charge=charge, bill_month=bill_month,
               record_payment=record_payment, verify_payment=verify_payment, reject_payment=reject_payment, del_entry=del_entry,
               checkin=checkin, checkout=checkout, tickets=tickets, set_ticket=set_ticket)
