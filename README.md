# N.N Reddy Hostels (HostelAtlas)

Fee tracking and maintenance for the N.N Reddy girls and boys hostels, plus online applications. Visitors see only the two hostels: photos, facilities, timings, rules and location. Applicants apply to one hostel at a time. Once approved, they sign in with a one-time email code, pick their bed on the floor plan, and from then on track their fees and maintenance requests. Staff manage everything from the admin portal, which works on a phone.

**Stack:** static pages (no build step) + one Python serverless function (standard library only) + Supabase Postgres, hosted on Vercel.

## Project layout

```
nn-reddy-hostels/
  index.html         the website, applicant account and admin portal (light and dark themes)
  floorplan-pro.js   the floor-plan editor used in Admin > Floor plans
  api/index.py       backend entry point (Vercel Python function): hostels, floors, layouts, admin login
  api/_flow.py       applications, email-code sign-in, email settings, approvals
  api/_ops.py        bed choice and assignment, fee history and payments, check-in / check-out, maintenance requests
  api/_db.py         Admin > Database: table health, the database update script, table browser, SQL console
  README.md          this guide
```

There is no `requirements.txt` and no `vercel.json` on purpose: the backend uses only the Python standard library and talks to Supabase over its REST API.

## What works today

| Area | Status |
|---|---|
| Girls and boys hostels kept separate: badges, eligibility check, one open application per person, admin filter | Working |
| Hostel photos uploaded from the admin panel (up to 8, resized on the phone, swipe gallery with full-screen viewer) | Working |
| Per-hostel timings, house rules, monthly fee, deposit and notice banner | Working |
| Google Maps link to embedded map card with directions | Working |
| Fee tracking: joining fee, monthly rent for everyone in one tap, extra charges, payments from residents, office receipts, full history | Working (needs the database update in Admin > Database) |
| Admin Database tab: table health, update script, table browser with CSV export, optional SQL console | Working (SQL console needs `DB_CONSOLE_KEY`) |
| Floors, drag-and-drop floor-plan editor with undo, zoom, multi-select and "plan code" (rooms, corridors, beds, washrooms, doors, windows, stairs, lifts, fans, lights, racks, balconies) | Working |
| Bed inventory created from the layout, with live status (available, reserved, occupied, unavailable) | Working |
| Four-step online application with house rules | Working |
| Applicant sign-in with a one-time email code | Working (needs Admin > Email set up) |
| Floor plan and bed choice, shown only after approval; two people can never get one bed | Working |
| Check in, check out, release a held bed | Working |
| Maintenance requests with categories, status and replies; residents are emailed on every update | Working |
| Admin overview with dues, payments to confirm, occupancy and new requests; every name and row opens its details | Working |
| Card or UPI checkout inside the app, visitor register, waitlists | Under development (applicants pay the hostel owner directly) |
| Document upload and e-agreements | Under development (staff check documents in person) |

## Step 1. Create the Supabase project

1. Go to https://supabase.com and sign in (GitHub login is easiest).
2. Click **New project**. Choose an organization, name it `nn-reddy-hostels`, set a strong **database password** and save it in a password manager.
3. For **Region** choose the closest to your users (for Hyderabad, `Asia-Pacific (Mumbai)`).
4. Click **Create new project** and wait about two minutes until the dashboard loads.

## Step 2. Create the database

1. In Supabase, open **SQL Editor** in the left menu and click **New query**.
2. Paste the entire script below and click **Run**. It should end with "Success. No rows returned".

```sql
create extension if not exists pgcrypto;

create table hostels (
  id uuid primary key default gen_random_uuid(),
  name text not null, city text, address text, phone text, description text,
  image_url text, amenities text, maps_url text, lat float8, lng float8,
  created_at timestamptz default now()
);
create table floors (
  id uuid primary key default gen_random_uuid(),
  hostel_id uuid not null references hostels on delete cascade,
  name text not null, level int default 0,
  layout jsonb default '{"objs":[]}'
);
create table beds (
  id uuid primary key default gen_random_uuid(),
  hostel_id uuid not null references hostels on delete cascade,
  floor_id uuid not null references floors on delete cascade,
  code text not null, price int default 0,
  status text default 'available' check (status in ('available','unavailable')),
  unique (floor_id, code)
);
create table bookings (
  id uuid primary key default gen_random_uuid(),
  bed_id uuid not null references beds,
  hostel_id uuid not null references hostels,
  name text, email text, phone text, move_in date, months int default 1,
  status text default 'pending',
  verification text default 'pending',
  hold_expires_at timestamptz,
  created_at timestamptz default now()
);
create index on bookings (bed_id, status);

-- Live bed status = physical state + booking state (expired holds free the bed automatically)
create view bed_live as
select b.*,
  case
    when b.status <> 'available' then 'unavailable'
    when exists (select 1 from bookings k where k.bed_id = b.id and k.status = 'checked_in') then 'occupied'
    when exists (select 1 from bookings k where k.bed_id = b.id and k.status in ('approved','confirmed')) then 'reserved'
    when exists (select 1 from bookings k where k.bed_id = b.id and k.status = 'pending' and k.hold_expires_at > now()) then 'hold'
    else 'available'
  end as live
from beds b;

-- Applications: the main way people join a hostel
create table applications (
  id uuid primary key default gen_random_uuid(),
  hostel_id uuid not null references hostels,
  name text not null, email text not null, phone text,
  aadhaar text, parent_name text, parent_phone text, id_proof text, address text,
  purpose text, college text, office text, join_date date, photo_url text,
  status text not null default 'pending'
    check (status in ('pending','approved','rejected','assigned','paid','verified','resident','left')),
  bed_id uuid references beds,
  amount_due int default 0, paid_amount int default 0, plan text default 'full',
  due_at timestamptz, paid_ref text, verified_at timestamptz, checkin_date date,
  created_at timestamptz default now()
);
create index on applications (email);
-- One live application per bed: the database itself refuses a double booking, even if two requests race
create unique index applications_one_live_bed on applications (bed_id)
  where status in ('assigned','paid','verified','resident');

-- Sign-in codes (also used for sign-in rate limits), email settings, maintenance requests
create table otps (email text primary key, h text not null, exp bigint not null, tries int not null default 0);
create table settings (key text primary key, value jsonb not null default '{}');
create table tickets (
  id uuid primary key default gen_random_uuid(),
  app_id uuid not null references applications on delete cascade,
  hostel_id uuid not null references hostels,
  title text not null, detail text, reply text,
  status text not null default 'open' check (status in ('open','in_progress','done')),
  created_at timestamptz default now()
);

-- Race-safe booking for the earlier self-service flow (kept so old bookings still work)
create function request_bed(p_bed uuid, p_name text, p_email text, p_phone text, p_move_in date, p_months int, p_hold_hours int)
returns uuid language plpgsql as $$
declare v_h uuid; v_id uuid;
begin
  select hostel_id into v_h from beds where id = p_bed and status = 'available' for update;
  if not found then raise exception 'This bed is not available.'; end if;
  if exists (select 1 from bookings x where x.bed_id = p_bed and (x.status in ('approved','confirmed','checked_in')
     or (x.status = 'pending' and x.hold_expires_at > now()))) then
    raise exception 'Someone else just requested this bed. Please pick another.';
  end if;
  insert into bookings (bed_id, hostel_id, name, email, phone, move_in, months, hold_expires_at)
  values (p_bed, v_h, p_name, p_email, p_phone, p_move_in, p_months, now() + make_interval(hours => p_hold_hours))
  returning id into v_id;
  return v_id;
end $$;

-- Booking lifecycle with validated transitions; admission needs verified identity
create function set_booking(p_id uuid, p_status text, p_verif text)
returns void language plpgsql as $$
declare b bookings;
begin
  select * into b from bookings where id = p_id for update;
  if not found then raise exception 'Booking not found.'; end if;
  perform 1 from beds where id = b.bed_id for update;
  if p_verif is not null then
    update bookings set verification = p_verif where id = p_id; b.verification := p_verif;
  end if;
  if p_status is null then return; end if;
  if not ((b.status = 'pending' and p_status in ('approved','rejected','cancelled'))
       or (b.status = 'approved' and p_status in ('confirmed','cancelled'))
       or (b.status = 'confirmed' and p_status in ('checked_in','cancelled'))
       or (b.status = 'checked_in' and p_status = 'checked_out')) then
    raise exception 'Cannot move a % booking to %.', b.status, p_status;
  end if;
  if p_status = 'approved' and exists (select 1 from bookings x where x.bed_id = b.bed_id and x.id <> b.id
     and (x.status in ('approved','confirmed','checked_in') or (x.status = 'pending' and x.hold_expires_at > now()))) then
    raise exception 'This bed was taken by another request.';
  end if;
  if p_status = 'confirmed' and b.verification <> 'verified' then
    raise exception 'Complete identity verification before confirming admission.';
  end if;
  update bookings set status = p_status, hold_expires_at = null where id = p_id;
end $$;

-- Saving a floor layout creates, updates and retires beds without touching booking or application history
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

-- Lock everything: only the server (service key) may touch data
alter table hostels enable row level security;
alter table floors enable row level security;
alter table beds enable row level security;
alter table bookings enable row level security;
alter table applications enable row level security;
alter table otps enable row level security;
alter table settings enable row level security;
alter table tickets enable row level security;
revoke all on bed_live from anon, authenticated;
revoke execute on function request_bed, set_booking, sync_beds from public, anon, authenticated;
```

3. Open **Table Editor**. You should see `hostels`, `floors`, `beds`, `bookings`, `applications`, `otps`, `settings` and `tickets`.
4. After you deploy (Step 5), sign in to the admin portal, open **Database** (under **More** on a phone), click **Copy SQL**, paste it in a new Supabase SQL query and click **Run**. This adds the fee history table, the monthly rent column and the SQL console function.

### Updating an existing database

Every new version that needs database changes shows them in **Admin > Database**: missing tables are marked in red, and the **Update SQL** box holds the exact script (also in `api/_db.py`). It is safe to run more than once and never changes your data. Click **Copy SQL**, then **Open Supabase SQL editor**, paste, and click **Run**. Once the SQL console is switched on (Step 5), **Run it here** does the same without leaving the app.

If the update stops at `applications_one_live_bed`, two live applications share a bed. Release one of them in **Admin > Residents** and run it again.

## Step 3. Copy your Supabase keys

1. In Supabase open **Project Settings** (gear icon), then **Data API**. Copy the **Project URL**, for example `https://abcdxyz.supabase.co`.
2. Open **Project Settings**, then **API Keys**. Open the **Legacy API keys** tab and copy the **`service_role`** key (a long text beginning `eyJ`).
3. Treat the `service_role` key like a password. It bypasses all database protections. It must only ever live in Vercel environment variables, never in `index.html` or GitHub.

## Step 4. Put the code on GitHub

1. Create a **private** repository on https://github.com named `nn-reddy-hostels`.
2. Put the files in the repository exactly as in **Project layout** above: `index.html`, `floorplan-pro.js` and `README.md` in the root, and the four Python files inside a folder named `api`.
3. From the project folder:

```bash
git init
git add .
git commit -m "N.N Reddy Hostels"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/nn-reddy-hostels.git
git push -u origin main
```

## Step 5. Deploy on Vercel

1. Go to https://vercel.com, sign in with GitHub and click **Add New**, then **Project**.
2. Import `nn-reddy-hostels`.
3. Set **Framework Preset** to **Other**. Leave **Build Command**, **Output Directory** and **Install Command** empty.
4. Expand **Environment Variables** and add these (apply to Production, Preview and Development):

| Name | Value |
|---|---|
| `SUPABASE_URL` | Project URL from Step 3 |
| `SUPABASE_SERVICE_KEY` | `service_role` key from Step 3 |
| `ADMIN_PASSWORD` | A long, unique password for the admin portal (16+ characters) |
| `SESSION_SECRET` | A long random string, at least 16 characters (40 is better). It signs every session. Applicant sign-in will not work without it unless `ADMIN_PASSWORD` is 16+ characters. Changing it signs everyone out |
| `DB_CONSOLE_KEY` | Optional. Turns on the SQL console in **Admin > Database**. Use a long secret (12+ characters) that is different from the admin password; it must be typed every time the console is used. Leave it out to keep the console off |
| `HOLD_HOURS` | Optional, only used by the old self-service bookings. Default `48`. You can leave it out |

5. Click **Deploy**. After about a minute Vercel shows your live URL such as `https://nn-reddy-hostels.vercel.app`.
6. If you change an environment variable later, go to **Deployments**, open the latest one, and choose **Redeploy** so the change takes effect.

## Step 6. First-use walkthrough

1. Open your site and click the lock icon at the top right (or go to `/#/admin`). Sign in with `ADMIN_PASSWORD`.
2. **Email** tab: enter a Gmail address and a Gmail **app password** (Google Account, Security, turn on 2-Step Verification, then App passwords), the address that should get new-application alerts, and your website address. Click **Send test email**. **Applicants cannot sign in until this works**, because sign-in is by emailed code.
3. **Hostels** (under **More** on a phone): tap a hostel or **Add hostel**. Choose **Girls** or **Boys**, then enter the name, area, warden phone, address, monthly fee, deposit, facilities, timings (one per line, like `Breakfast | 7:30 to 9:00 AM`), house rules (one per line) and an optional notice. Save, then **Add photos**: up to 8 per hostel, the first is the cover, and the star makes another photo the cover.
4. **Google Maps link:** open the hostel in Google Maps, click **Share**, then **Copy link**, and paste it in the form. Short links (`maps.app.goo.gl`), long links and pasted embed code all work. If you leave the link empty, the map is drawn from the address.
5. **Floor plans** tab: choose the hostel, click **Floor**, name it (for example "Ground floor") and set its level number.
6. Click objects in the left palette to add them. Drag to move, drag the gold corner handle to resize, and use the panel on the right for exact position (in feet), size and rotation. Select a room and use **Fill with beds** to place several beds at once, or use **Plan code** to type a whole floor. Ctrl+Z undoes.
7. Give every bed a **unique code** and a monthly rent, then click **Save layout**. This publishes the plan and creates or updates the bed inventory. Moving a bed on the plan never loses its history.
8. Test the applicant side in a private window: open a hostel, click **Apply to this hostel**, then **Verify email and track** to sign in with the emailed code.
9. Back in **Applications**, open the application and **Approve** it. The applicant now sees the floor plan under **My stay** and reserves a bed (or you use **Residents > Assign bed**).
10. In **Residents**, tap the person: **Verify joining payment** once the money arrives (a submitted UPI reference is shown), then **Check in**. **Release bed** frees a bed held by someone who never moved in; **Check out** ends a stay and keeps the fee history.
11. **Fees** each month: **Charge monthly rent** adds one month of rent to every resident (their own rent from **Fee settings**, else the bed price, else the hostel's monthly fee). Running it twice for the same month is safe. Residents send a UPI reference with **I have paid**; you **Confirm received** or mark **Not received**. Money paid at the office: open the resident and **Record payment**. Mistakes can be deleted from the history.
12. Residents report problems under **Requests**. Tap one in the admin **Requests** tab to set its status and reply; the resident is emailed every update.
13. Use **All / Girls / Boys** at the top of the admin pages to work on one hostel at a time. The admin portal signs itself out after 30 minutes without activity.

## How an application moves

`pending` (applied) → `approved` or `rejected` → `assigned` (bed reserved, fee due) → `paid` (UPI reference submitted) → `verified` (staff confirmed the money) → `resident` (checked in) → `left` (checked out or bed released).

1. Visitors see hostels, facilities, rules and the map, but never bed availability.
2. A person can have one open application at a time, across both hostels. The hostel is emailed when someone applies.
3. After approval, the applicant signs in with an emailed code and sees the floor plan with live availability. They can reserve one bed, once; staff can change it.
4. Every step only moves forward from the state it expects. A double click, a stale screen or two staff members acting at once cannot skip or repeat a step.
5. Two people can never get the same bed. The server checks availability, and the `applications_one_live_bed` index makes the database refuse a second claim on the same bed.

Payment is not processed online. Applicants pay the hostel owner directly and submit the UPI transaction ID; staff verify it. Staff can also verify cash payments that have no reference. Bookings from the earlier self-service flow still appear under **Admin > Old bookings** until you close them, but new self-service holds are no longer possible.

## Run it locally (optional)

```bash
npm i -g vercel
cd nn-reddy-hostels
vercel link
vercel env pull .env.local
vercel dev
```

Open http://localhost:3000. Never commit `.env.local`.

## Custom domain

In Vercel, open **Settings**, then **Domains**, add your domain and follow the DNS instructions at your registrar.

## Security notes

- All database tables are locked by Row Level Security. The browser never talks to Supabase directly; only the Python function does, using the service key.
- Every API call is checked on the server. Public calls are limited to the hostel catalogue, applying and signing in. Applicant calls need a signed applicant session, which is issued only after the emailed 6-digit code is verified, and each call is checked against that applicant's own application. Admin calls need a signed admin session. The two kinds of session cannot be swapped for each other.
- Sign-in codes expire after 10 minutes, work once and lock after 5 wrong tries. Admin login, code requests, code checks and new applications are rate limited per IP address. The code-request form never reveals whether an email has applied.
- Admin sessions expire after 24 hours and applicant sessions after 7 days; both are kept only for the browser tab. Use a strong `ADMIN_PASSWORD` and set `SESSION_SECRET`.
- The page sets a Content Security Policy and escapes everything it displays, and the server cleans floor-plan data before saving it. Uploaded photos are checked to be real JPG, PNG or WebP images and limited in size and number.
- The SQL console can change or delete anything in the database, so it is off unless `DB_CONSOLE_KEY` is set. Every run needs that key (kept only in the open tab), statements that change or delete data need an extra tick, runs are rate limited, and the last 100 runs are logged (shown in **Admin > Database**). Leave `DB_CONSOLE_KEY` unset if you prefer to use the Supabase SQL editor.
- Applicant name, email and phone are personal data. Share admin access only with trusted staff and delete old rejected or cancelled records you no longer need. Review India's Digital Personal Data Protection requirements before collecting identity documents online.
- Floor plans here are operational maps, not fire-safety certification.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Server is not configured" | `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` is missing in Vercel, or `SESSION_SECRET` is missing or too short. Add it, then redeploy |
| "Email sign-in is not set up yet" | Fill in **Admin > Email** and click **Send test email** |
| Every page says "The server is updating" | `api/_flow.py` or `api/_ops.py` failed to load, so the server refuses public calls rather than run without its access rules. Check the Vercel function logs, or sign in as admin and call the `diag` action |
| "Too many attempts" | Rate limit. Wait 15 minutes (an hour for repeated applications) |
| "Incorrect password" | `ADMIN_PASSWORD` is missing or was changed after the last deploy. Redeploy |
| "Database update needed" | Open **Admin > Database**, copy the update SQL and run it in Supabase |
| "Could not find the function ... in the schema cache" | Re-run the update SQL from **Admin > Database**, then wait a few seconds |
| Site shows 404 at `/` | The Framework Preset must be **Other** and `index.html` must be in the repository root |
| `/api/index` returns 404 | The file must be at `api/index.py` |
| Map card shows the wrong place | Paste a fuller Google Maps link, or make sure the address field is complete |
| Cannot delete a hostel or floor | It has bookings or applications. Close those first (reject, release or check out). Layout edits only retire beds that have history |
| Supabase project paused | Free projects pause after about a week of inactivity. Click **Restore** in the Supabase dashboard |
