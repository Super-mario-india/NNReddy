# N.N Reddy Hostels (HostelAtlas)

A multi-hostel management and bed-booking platform. Admins add hostels, paste a Google Maps link, draw floor plans and publish bookable beds. Applicants browse a hostel, pick an exact bed on the plan and submit a request. Staff review, verify and admit.

**Stack:** one static `index.html` (no build step) + one Python serverless function (`api/index.py`, standard library only) + Supabase Postgres, hosted on Vercel.

## Project layout

```
nn-reddy-hostels/
  index.html      the whole website, admin portal and floor-plan editor
  api/index.py    the backend (Vercel Python function)
  README.md       this guide
```

There is no `requirements.txt` and no `vercel.json` on purpose: the backend uses only the Python standard library and talks to Supabase over its REST API.

## What works today

| Area | Status |
|---|---|
| Multiple hostels (name, address, phone, cover image, amenities, description) | Working |
| Google Maps link to embedded map card with "Open in Google Maps" | Working |
| Floors, drag-and-drop floor-plan editor (rooms, corridors, beds, washrooms, doors, windows, stairs, lifts, fans, lights, racks, balconies) | Working |
| Bed inventory created from the layout, with live status (available, on hold, reserved, occupied, unavailable) | Working |
| Bed request with automatic hold expiry and race-safe booking | Working |
| Admin review: approve or reject, verification, confirm, check in, check out, cancel | Working |
| Applicant status tracking by reference and email | Working |
| Online payments, visitor register, maintenance tickets, waitlists | Under development (the app tells applicants to pay the hostel owner directly) |
| Document upload and e-agreements | Under development (verification is recorded by staff after checking documents in person) |

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

-- Race-safe booking: the bed row is locked, so two people can never take the same bed
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

-- Saving a floor layout creates, updates and retires beds without touching booking history
create function sync_beds(p_floor uuid, p_hostel uuid, p_beds jsonb)
returns void language plpgsql as $$
begin
  insert into beds (hostel_id, floor_id, code, price)
  select p_hostel, p_floor, x->>'code', coalesce((x->>'price')::int, 0) from jsonb_array_elements(p_beds) x
  on conflict (floor_id, code) do update set price = excluded.price, status = 'available';
  delete from beds where floor_id = p_floor and code not in (select x->>'code' from jsonb_array_elements(p_beds) x)
    and not exists (select 1 from bookings where bed_id = beds.id);
  update beds set status = 'unavailable' where floor_id = p_floor and code not in (select x->>'code' from jsonb_array_elements(p_beds) x);
end $$;

-- Lock everything: only the server (service key) may touch data
alter table hostels enable row level security;
alter table floors enable row level security;
alter table beds enable row level security;
alter table bookings enable row level security;
revoke all on bed_live from anon, authenticated;
revoke execute on function request_bed, set_booking, sync_beds from public, anon, authenticated;
```

3. Open **Table Editor**. You should see `hostels`, `floors`, `beds` and `bookings`.

## Step 3. Copy your Supabase keys

1. In Supabase open **Project Settings** (gear icon), then **Data API**. Copy the **Project URL**, for example `https://abcdxyz.supabase.co`.
2. Open **Project Settings**, then **API Keys**. Open the **Legacy API keys** tab and copy the **`service_role`** key (a long text beginning `eyJ`).
3. Treat the `service_role` key like a password. It bypasses all database protections. It must only ever live in Vercel environment variables, never in `index.html` or GitHub.

## Step 4. Put the code on GitHub

1. Create a **private** repository on https://github.com named `nn-reddy-hostels`.
2. Put the three files in the repository exactly like this: `index.html` and `README.md` in the root, and `index.py` inside a folder named `api`.
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
| `SESSION_SECRET` | Any long random string (for example, 40 random characters) |
| `HOLD_HOURS` | Optional. Hours a requested bed is held before it frees up. Default `48` |

5. Click **Deploy**. After about a minute Vercel shows your live URL such as `https://nn-reddy-hostels.vercel.app`.
6. If you change an environment variable later, go to **Deployments**, open the latest one, and choose **Redeploy** so the change takes effect.

## Step 6. First-use walkthrough

1. Open your site and click **Admin**. Sign in with `ADMIN_PASSWORD`.
2. **Hostels** tab, **Add hostel**. Enter the name, area, phone, full address, cover image URL, amenities and description.
3. **Google Maps link:** open the hostel in Google Maps, click **Share**, then **Copy link**, and paste it in the form. Short links (`maps.app.goo.gl`), long links and pasted embed code all work. The hostel page now shows a live map card with an **Open in Google Maps** button. If you leave the link empty, the map is drawn from the address.
4. **Floor plans** tab: choose the hostel, click **Floor**, name it (for example "Ground floor") and set its level number.
5. Click objects in the left palette to add them. Drag to move, drag the gold corner handle to resize, and use the panel on the right for exact position, size and rotation. One grid square is one metre. Draw rooms first, then place beds, doors and fixtures inside them.
6. Give every bed a **unique code** and a monthly rent, then click **Save layout**. This publishes the plan and creates or updates the bed inventory. Moving a bed on the plan never loses its booking history.
7. Open the public site, pick the hostel and click a green bed to test a booking.
8. Back in **Bookings** run the flow: **Approve**, **Mark verified** (after you have checked the applicant's identity documents in person), **Confirm admission**, **Check in**, and later **Check out**.

## How booking works

1. An applicant requests a bed. The bed is held for `HOLD_HOURS` and shows as "On hold" to everyone else. Expired holds free the bed automatically, with no scheduled job.
2. Staff approve or reject. Approving re-checks that nobody else took the bed.
3. Verification status is separate from booking status. A booking cannot be confirmed until verification is marked verified.
4. Check in marks the bed occupied. Check out frees it.
5. Two people can never get the same bed: the database locks the bed row during every request and approval.

Payment is not processed online. Applicants see a clear message to pay the hostel owner directly, using the phone number you saved for that hostel.

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
- Admin sessions are signed tokens that expire after 24 hours. Use a strong `ADMIN_PASSWORD`.
- Applicant name, email and phone are personal data. Share admin access only with trusted staff and delete old rejected or cancelled records you no longer need. Review India's Digital Personal Data Protection requirements before collecting identity documents online.
- Floor plans here are operational maps, not fire-safety certification.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Server is not configured" | `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` is missing in Vercel. Add it, then redeploy |
| "Incorrect password" | `ADMIN_PASSWORD` is missing or was changed after the last deploy. Redeploy |
| "Could not find the function ... in the schema cache" | Re-run the SQL from Step 2, then wait a few seconds |
| Site shows 404 at `/` | The Framework Preset must be **Other** and `index.html` must be in the repository root |
| `/api/index` returns 404 | The file must be at `api/index.py` |
| Map card shows the wrong place | Paste a fuller Google Maps link, or make sure the address field is complete |
| Cannot delete a hostel or floor | It has bookings. Cancel or check out those bookings first. Layout edits only retire beds that have history |
| Supabase project paused | Free projects pause after about a week of inactivity. Click **Restore** in the Supabase dashboard |
