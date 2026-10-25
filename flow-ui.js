/* flow-ui.js - step 1 screens for HostelAtlas. Add after floorplan-pro.js:
   <script src="/flow-ui.js"></script>   (needs api/_flow.py + schema-step1.sql installed) */
(()=>{
let ut=sessionStorage.getItem('ut'),ME=null;
const load=()=>view('<div class="wrap"><div class="empty">Loading...</div></div>'),
 F=(id,l,t='text',c='')=>`<div class="${c}"><label for="${id}">${l}</label><input id="${id}" type="${t}"></div>`,
 V=id=>($('#'+id)?.value||'').trim(),
 hid='<i style="color:var(--mut)">Hidden - verify with email code</i>';

window.api=async(a,d={})=>{const t=tok||ut,r=await fetch('/api/index',{method:'POST',headers:{'Content-Type':'application/json',...(t?{Authorization:'Bearer '+t}:{})},body:JSON.stringify({a,...d})});
 const j=await r.json().catch(()=>({error:'Network error'}));
 if(!r.ok){if(r.status===401&&!/^(login|otp_)/.test(a)){if(tok){tok=null;sessionStorage.removeItem('t');go('#/admin')}else{ut=null;sessionStorage.removeItem('ut');go('#/track')}}throw new Error(j.error||'Request failed')}return j};
$('#tk').innerHTML=I('user')+'<span>Login</span>';

/* ---- routes ---- */
const oh=window.home;window.home=()=>{const h=location.hash;return h.startsWith('#/apply/')?applyPage(h.slice(8)):h==='#/me'?mePage():oh()};
const od=window.drawHome;window.drawHome=q=>{od(q);document.querySelectorAll('.hc .row').forEach(r=>r.innerHTML='<span class="chip s">Apply to join</span>')};
window.drawHostel=()=>{const h=CUR.d.hostel,am=(h.amenities||'').split(',').map(s=>s.trim()).filter(Boolean);
 view(`<div class="wrap"><div class="ph" ${bg(h.image_url)}><div><h1>${esc(h.name)}</h1><div class="meta">${I('pin',15)}${esc([h.address,h.city].filter(Boolean).join(', '))}</div></div></div>
 <div class="two"><div class="card pad"><h3>About this hostel</h3><p style="color:var(--mut);white-space:pre-line">${esc(h.description||'Details coming soon.')}</p>${am.length?`<div class="tags">${am.map(a=>`<span class="chip s">${esc(a)}</span>`).join('')}</div>`:''}
 <div class="acts" style="margin-top:20px"><a class="btn g" href="#/apply/${h.id}">Apply for a bed</a><a class="btn o" href="#/track">Already applied? Login</a></div>
 <div class="note" style="margin-top:18px">${I('lock')}<div>The floor plan and bed availability are shown after the hostel approves your application.</div></div>${h.phone?`<p style="margin-top:14px"><a class="btn o" href="tel:${esc(h.phone)}">${I('phone',16)} ${esc(h.phone)}</a></p>`:''}</div>
 ${h.maps_url||h.address?`<div class="card map"><iframe loading="lazy" title="Map of ${esc(h.name)}" src="${mapSrc(h)}"></iframe><div class="mapbar"><span>${esc(h.address||h.city||'')}</span><a class="btn sm g" target="_blank" rel="noopener" href="${esc(openUrl(h))}">${I('ext',15)} Open in Google Maps</a></div></div>`:'<div></div>'}</div></div>`)};

/* ---- application form ---- */
const TERMS=['Advance is not refundable or transferable under any circumstances.','Management is not responsible for theft or loss of belongings such as cell phones, gold ornaments, cash and dress material.','Guests are not allowed into the hostel at any time.','Candidates must inform the manager 15 days in advance if they are leaving the hostel.','Laptop charges are Rs 200 per month.','Computers, water heaters, iron boxes and unused electrical items are not allowed. Breaking the rules carries a fine of Rs 1000.','Hostel timings: 6:00 am to 9:30 pm.'];
async function applyPage(id){load();const{hostel:h}=await api('hostel',{id});CUR={h};
 view(`<div class="wrap" style="max-width:720px;padding:50px 22px"><h1 style="font-size:44px">Apply to ${esc(h.name)}</h1><p style="color:var(--mut);margin:8px 0 22px">Fill in your details. The hostel team reviews them and emails you the decision.</p>
 <div class="card pad"><div class="f2">${F('a_name','Name of the candidate','text','full')}${F('a_email','Email','email')}${F('a_phone','Mobile','tel')}${F('a_aad','Aadhaar card no')}${F('a_idp','ID proof (type and number)')}${F('a_par',"Father's / Mother's name")}${F('a_pp','Parent mobile','tel')}
 <div class="full"><label for="a_addr">Permanent address</label><textarea id="a_addr"></textarea></div>${F('a_pur','Purpose of stay')}${F('a_col','College / coaching centre')}${F('a_off','Office address and phone','text','full')}${F('a_join','Date of joining','date')}${F('a_photo','Photo URL (optional)','url')}</div></div>
 <div class="card pad" style="margin-top:18px"><h3>Terms and conditions</h3><ol style="color:var(--mut);padding-left:20px;display:grid;gap:6px">${TERMS.map(t=>`<li>${t}</li>`).join('')}</ol>
 <label style="display:flex;gap:8px;align-items:center;margin-top:14px;font-weight:500"><input id="a_ok" type="checkbox" style="width:auto"> I have read the rules and regulations and shall abide by them.</label></div>
 <button class="btn g" style="margin-top:18px;width:100%;justify-content:center" data-act="apSend">Submit application</button></div>`)}
A.apSend=async(d,b)=>{if(!$('#a_ok').checked)return toast('Please accept the terms first',1);b.disabled=true;
 const r=await api('apply',{hostel_id:CUR.h.id,name:V('a_name'),email:V('a_email'),phone:V('a_phone'),aadhaar:V('a_aad'),id_proof:V('a_idp'),parent_name:V('a_par'),parent_phone:V('a_pp'),address:V('a_addr'),purpose:V('a_pur'),college:V('a_col'),office:V('a_off'),join_date:V('a_join'),photo_url:V('a_photo')});
 view(`<div class="wrap" style="max-width:560px;padding:70px 22px"><div class="card pad"><h1 style="font-size:38px;margin-bottom:10px">Application received</h1><p style="color:var(--mut)">The hostel team will review it${r.emailed?' and email you the decision':''}. Come back and log in with <b>${esc(V('a_email')||'your email')}</b> to check your status. Keep your email address handy - you do not need a reference number.</p><a class="btn g" style="margin-top:18px" href="#/track">Login</a></div></div>`)};

/* ---- user login ---- */
window.trackPage=()=>{if(ut){mePage().catch(e=>toast(e.message,1));return}
 view(`<div class="wrap" style="max-width:480px;padding:70px 22px"><h1 style="font-size:44px;margin-bottom:8px">Login</h1><p style="color:var(--mut);margin-bottom:20px">Enter the email you applied with.</p><div class="card pad" id="lg2"><label for="l_e">Email</label><input id="l_e" type="email" autocomplete="email">
 <div class="acts" style="margin-top:16px"><button class="btn g" data-act="lgSend">${I('lock',16)} Login with email code</button><button class="btn" data-act="lgBasic">Continue without code</button></div>
 <p class="meta" style="margin-top:12px;font-size:12.5px">Without a code you can see fees and ticket progress, but personal details stay hidden.</p></div></div>`)};
const done=(r)=>{ut=r.token;sessionStorage.setItem('ut',ut);A.close();go('#/me');mePage().catch(e=>toast(e.message,1))};
A.lgBasic=async()=>done(await api('login_email',{email:V('l_e')}));
A.lgSend=async(d,b)=>{const e=V('l_e')||ME?.email;await api('otp_send',{email:e});ME=ME||{};ME.email=e;
 modal(`${mh('Enter your code')}<p class="meta" style="margin:-6px 0 14px">We emailed a 6-digit code to ${esc(e)}.</p><input id="l_c" inputmode="numeric" maxlength="6" autocomplete="one-time-code" style="font-size:22px;letter-spacing:.3em"><button class="btn g" style="margin-top:16px;width:100%;justify-content:center" data-act="lgVer">Verify</button>`)};
A.lgVer=async()=>done(await api('otp_verify',{email:ME.email,code:V('l_c')}));
A.lgOut=()=>{ut=null;ME=null;sessionStorage.removeItem('ut');go('#/');toast('Logged out')};

/* ---- user account ---- */
async function mePage(){load();const r=await api('me');ME=r;const full=r.level==='full',R=(l,v)=>`<div><span class="meta">${l}</span><div>${v?esc(v):full?'-':hid}</div></div>`;
 view(`<div class="wrap" style="padding:50px 22px;max-width:900px"><h1 style="font-size:44px">Your hostel account</h1><div class="meta" style="margin:10px 0 22px;flex-wrap:wrap">${esc(r.email)} ${chip(full?'ok':'w',full?'Full access':'Basic access')}
 ${full?'':'<button class="btn sm g" data-act="lgSend">Verify with email code</button>'}<button class="btn sm o" data-act="lgOut">${I('out',14)} Log out</button></div>
 ${r.apps.map((a,i)=>{const s=stChip(a.status);return`<div class="card pad" style="margin-bottom:16px"><div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><h3 style="margin:0">${esc(a.hostels?.name)}</h3>${chip(s[0],s[1])}</div>
 <div class="f2" style="margin-top:14px">${R('Name',a.name)}${R('Mobile',a.phone)}${R('Aadhaar',a.aadhaar)}${R('Address',a.address)}${R('Purpose of stay',a.purpose)}${R('Date of joining',a.join_date)}</div>
 ${a.status==='approved'?`<button class="btn g" style="margin-top:16px" data-act="mePlan" data-h="${a.hostel_id}">View floor plan</button><div id="pv"></div>`:a.status==='pending'?'<div class="note" style="margin-top:14px">'+I('clock')+'<div>Your application is under review.</div></div>':''}</div>`}).join('')}
 <div class="mods">${[['wallet','Fee details','Dues, due dates and payment history.'],['wrench','Maintenance tickets','Track progress; raise tickets with a verified login.']].map(m=>`<div class="card">${I(m[0],24)}<h3>${m[1]}</h3><p>${m[2]}</p>${chip('s','Coming next')}</div>`).join('')}</div></div>`)}
function showPlan(){const{floors,beds}=CUR.d,f=floors[CUR.fi],bm={};if(f)beds.filter(b=>b.floor_id===f.id).forEach(b=>bm[b.code]=b);
 $('#pv').innerHTML=f?`<div class="tabs" style="margin-top:16px">${floors.map((x,i)=>`<button class="btn ${i===CUR.fi?'on':''}" data-act="mePf" data-i="${i}">${esc(x.name)}</button>`).join('')}</div><div class="card pl">${plan(f.layout||{},{bm})}${legend()}</div>`:'<div class="card empty" style="margin-top:14px">The floor plan will be published soon.</div>'}
A.mePlan=async d=>{CUR={d:await api('plan',{hostel_id:d.h}),fi:0};showPlan()};
A.mePf=d=>{CUR.fi=+d.i;showPlan()};
A.bed=()=>toast('Bed selection opens in the next update. The hostel can also assign your bed.');

/* ---- admin: applications + email settings ---- */
window.adminView=()=>{if(!AD.ap){Promise.all([api('applications').catch(()=>[]),api('get_settings').catch(()=>({}))]).then(([a,s])=>{AD.ap=a;AD.set=s;adminView()});return}
 const T=[['overview','Overview','grid'],['apps','Applications','users'],['bookings','Old bookings','cal'],['hostels','Hostels','building'],['plans','Floor plans','bed'],['mail','Email settings','wrench']],n=AD.ap.filter(a=>a.status==='pending').length;
 view(`<div class="wrap"><div class="adm"><aside>${T.map(t=>`<button class="btn ${AD.tab===t[0]?'on':''}" data-act="tab" data-t="${t[0]}">${I(t[2])} ${t[1]}${t[0]==='apps'&&n?' '+chip('w',n):''}</button>`).join('')}<button class="btn" data-act="logout">${I('out')} Sign out</button></aside><section id="pane"></section></div></div>`);
 $('#pane').innerHTML=({overview:ovw,apps:apTab,bookings:bkTab,hostels:hsTab,plans:plansTab,mail:mailTab})[AD.tab]();if(AD.tab==='plans')edInit()};
function apTab(){return`<div class="bar"><h2>Applications</h2></div><div class="card tw"><table><thead><tr><th>Applicant</th><th>Hostel</th><th>Details</th><th>Status</th><th>Actions</th></tr></thead><tbody>${AD.ap.map(a=>{const s=stChip(a.status);
 return`<tr><td><b>${esc(a.name)}</b><div class="meta">${esc(a.phone)}<br>${esc(a.email)}</div></td><td>${esc(a.hostels?.name)}<div class="meta">Joins ${esc(a.join_date||'-')}</div></td><td><div class="meta">${esc(a.purpose||'')}<br>${esc(a.college||'')}<br>Aadhaar ${esc(a.aadhaar||'-')}</div></td><td>${chip(s[0],s[1])}</td>
 <td><div class="acts">${a.status==='pending'?`<button class="btn sm g" data-act="apDec" data-id="${a.id}" data-s="approved">Approve</button><button class="btn sm o" data-act="apDec" data-id="${a.id}" data-s="rejected">Reject</button>`:''}</div></td></tr>`}).join('')||'<tr><td colspan="5" class="empty">No applications yet.</td></tr>'}</tbody></table></div>`}
A.apDec=async d=>{await api('decide',{id:d.id,status:d.s});AD.ap=await api('applications');toast('Application '+d.s);adminView()};
function mailTab(){const s=AD.set||{},F2=(k,l,t='text',c='')=>`<div class="${c}"><label>${l}</label><input id="m_${k}" type="${t}" value="${esc(s[k])}"></div>`;
 return`<div class="bar"><h2>Email settings</h2></div><div class="card pad"><p class="meta" style="margin-bottom:14px">Optional. The app works without email. Use a Gmail address with 2-step verification and an app password (Google Account > Security > App passwords).</p>
 <div class="f2">${F2('user','Gmail address','email')}${F2('pass','Gmail app password','password')}${F2('from','Sender name and address (optional)')}${F2('admin_email','Send new-application alerts to','email')}${F2('site_url','Website address','url','full')}</div>
 <div class="acts" style="margin-top:16px"><button class="btn g" data-act="mailSave">${I('save',16)} Save</button><button class="btn" data-act="mailTest">Send test email</button></div></div>`}
A.mailSave=async()=>{await api('save_settings',Object.fromEntries(['user','pass','from','admin_email','site_url'].map(k=>[k,V('m_'+k)])));AD.set=await api('get_settings');toast('Email settings saved')};
A.mailTest=async()=>{await A.mailSave();await api('test_mail');toast('Test email sent')};
})();
