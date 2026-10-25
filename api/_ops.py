"""HostelAtlas step 2: bed selection/assignment, payment, verification, check-in, maintenance tickets.
Enable in api/index.py inside the same try block, after _flow:
    import _ops; _ops.install(globals())"""
import time

LIVE = 'status=in.(assigned,paid,verified,resident)'


def install(g):
    sb, Fail, q, authed, PUB, ADM, H = g['sb'], g['Fail'], g['q'], g['authed'], g['PUB'], g['ADM'], g['_h']
    mail, uread, cfg, old_plan, old_me = H['mail'], H['uread'], H['cfg'], PUB['plan'], PUB['me']
    now = lambda: time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    def own(d, need_full=True):
        e, lvl = uread(d['_a'])
        if not e:
            raise Fail('Please log in again.', 401)
        if need_full and lvl != 'full':
            raise Fail('Please verify with the email code first.', 403)
        r = sb('GET', f"applications?id=eq.{q(d.get('app_id'))}&email=eq.{q(e)}&select=*")
        if not r:
            raise Fail('Application not found.', 404)
        return r[0]

    def taken(bed, skip=None):
        return any(x['id'] != skip for x in sb('GET', f'applications?bed_id=eq.{q(bed)}&{LIVE}&select=id'))

    def tell_admin(subj, body):
        mail(cfg().get('admin_email'), subj, body)

    def plan(d):  # overlay new bed assignments on the availability map
        r = old_plan(d)
        m = {a['bed_id']: a['status'] for a in sb('GET', f"applications?hostel_id=eq.{q(d.get('hostel_id'))}&bed_id=not.is.null&{LIVE}&select=bed_id,status")}
        for b in r['beds']:
            if b['id'] in m:
                b['live'] = 'occupied' if m[b['id']] == 'resident' else 'reserved'
        return r

    def me(d):
        r = old_me(d)
        ids = ','.join(a['id'] for a in r['apps']) or 'none'
        codes = {b['id']: b['code'] for b in sb('GET', 'beds?select=id,code&limit=5000')}
        for a in r['apps']:
            a['bed_code'] = codes.get(a.get('bed_id'))
        r['tickets'] = sb('GET', f'tickets?app_id=in.({ids})&order=created_at.desc')
        return r

    # ---- user actions ----
    def pick_bed(d):
        a = own(d)
        if a['status'] != 'approved':
            raise Fail('You can choose a bed only once, after approval. Ask the hostel to change it.')
        b = sb('GET', f"beds?id=eq.{q(d.get('bed_id'))}&hostel_id=eq.{q(a['hostel_id'])}&select=id,code,price")
        if not b or taken(b[0]['id']):
            raise Fail('That bed is no longer available. Please pick another.')
        sb('PATCH', f"applications?id=eq.{q(a['id'])}", {'bed_id': b[0]['id'], 'status': 'assigned', 'amount_due': b[0]['price'] or 0})
        tell_admin('Bed chosen', f"{a['name']} chose bed {b[0]['code']}. Set the payment due time in the admin portal.")
        return {'ok': 1}

    def pay(d):
        a = own(d)
        ref = str(d.get('ref') or '').strip()
        if a['status'] != 'assigned' or len(ref) < 4:
            raise Fail('Enter your payment reference (UPI transaction ID) after a bed is assigned.')
        sb('PATCH', f"applications?id=eq.{q(a['id'])}", {'paid_ref': ref, 'status': 'paid'})
        tell_admin('Payment submitted', f"{a['name']} submitted payment reference {ref}. Please verify it.")
        return {'ok': 1}

    def ticket_new(d):
        a = own(d)
        t = str(d.get('title') or '').strip()
        if a['status'] != 'resident' or len(t) < 3:
            raise Fail('Tickets can be raised by residents. Please describe the problem.')
        sb('POST', 'tickets', {'app_id': a['id'], 'hostel_id': a['hostel_id'], 'title': t[:120], 'detail': str(d.get('detail') or '')[:1000]})
        tell_admin('New maintenance ticket', f"{a['name']}: {t}")
        return {'ok': 1}

    # ---- admin actions ----
    def residents(d):
        return sb('GET', 'applications?status=in.(approved,assigned,paid,verified,resident)&select=*,beds(code),hostels(name)&order=created_at.desc&limit=500')

    def upd(d, f, subj=None, body=None):
        r = sb('PATCH', f"applications?id=eq.{q(d.get('id'))}", f)
        if r and subj:
            mail(r[0]['email'], subj, body)
        return {'ok': 1}

    def assign(d):
        bed = d.get('bed_id')
        if taken(bed, d.get('id')):
            raise Fail('That bed is already assigned to someone else.')
        return upd(d, {'bed_id': bed, 'status': 'assigned', 'amount_due': int(d.get('amount') or 0), 'due_at': d.get('due_at') or None},
                   'Your bed is assigned', 'A bed has been assigned. Log in to see the amount and pay by the due time.')

    def set_fee(d):
        return upd(d, {'amount_due': int(d.get('amount') or 0), 'due_at': d.get('due_at') or None, 'plan': d.get('plan') if d.get('plan') in ('full', 'bed_only') else 'full'})

    def verify(d):
        r = sb('GET', f"applications?id=eq.{q(d.get('id'))}&select=amount_due")
        paid = int(d.get('paid') or (r[0]['amount_due'] if r else 0))
        return upd(d, {'status': 'verified', 'paid_amount': paid, 'verified_at': now()}, 'Payment verified', 'Your payment is verified. The hostel will check you in.')

    def checkin(d):
        return upd(d, {'status': 'resident', 'checkin_date': time.strftime('%Y-%m-%d')}, 'Welcome!', 'You are checked in. Log in to see fees and raise maintenance tickets.')

    def checkout(d):
        return upd(d, {'status': 'left', 'bed_id': None})

    def tickets(d):
        return sb('GET', 'tickets?select=*,applications(name),hostels(name)&order=created_at.desc&limit=300')

    def set_ticket(d):
        r = sb('PATCH', f"tickets?id=eq.{q(d.get('id'))}", {'status': d.get('status') if d.get('status') in ('open', 'in_progress', 'done') else 'open', 'reply': str(d.get('reply') or '')[:500] or None})
        return {'ok': 1}

    PUB.update(plan=plan, me=me, pick_bed=pick_bed, pay=pay, ticket_new=ticket_new)
    ADM.update(residents=residents, assign=assign, set_fee=set_fee, verify=verify, checkin=checkin, checkout=checkout, tickets=tickets, set_ticket=set_ticket)
