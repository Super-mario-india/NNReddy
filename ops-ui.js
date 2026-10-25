/* ops-ui.js - step 2 screens. Add AFTER flow-ui.js: <script src="/ops-ui.js"></script> */
(()=>{
const SC={pending:['w','Under review'],approved:['i','Approved'],assigned:['w','Bed assigned'],paid:['i','Payment submitted'],verified:['ok','Verified'],resident:['ok','Resident'],rejected:['b','Rejected'],left:['','Checked out']},
 TC={open:['w','Open'],in_progress:['i','In progress'],done:['ok','Done']},
 money=n=>'Rs '+(n||0).toLocaleString('en-IN'),dt=s=>s?new Date(s).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'}):'-',
 V=id=>($('#'+id)?.value||'').trim(),sc=s=>{const c=SC[s]||['',s];return chip(c[0],c[1])},
 hid='<i style="color:var(--mut)">Hidden - verify with email code</i>';
let OP={};

/* ---------- user account ---------- */
window.mePage2=async()=>{view('<div class="wrap"><div class="empty">Loading...</div></div>');const r=await api('me');OP.me=r;const full=r.level==='full',R=(l,v)=>`<div><span class="meta">${l}</span><div>${v?esc(v):full?'-':hid}</div></div>`;
 view(`<div class="wrap" style="padding:50px 22px;max-width:900px"><h1 style="font-size:44px">Your hostel account</h1><div class="meta" style="margin:10px 0 22px;flex-wrap:wrap">${esc(r.email)} ${chip(full?'ok':'w',full?'Full access':'Basic access')}
 ${full?'':'<button class="btn sm g" data-act="lgSend">Verify with email code</button>'}<button class="btn sm o" data-act="lgOut">${I('out',14)} Log out</button></div>
 ${r.apps.map(a=>{const bal=Math.max(0,(a.amount_due||0)-(a.paid_amount||0)),tk=r.tickets.filter(t=>t.app_id===a.id),live=['assigned','paid','verified','resident'].includes(a.status);return`<div class="card pad" style="margin-bottom:18px">
 <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><h3 style="margin:0">${esc(a.hostels?.name)}${a.bed_code?' - bed '+esc(a.bed_code):''}</h3>${sc(a.status)}</div>
 <div class="f2" style="margin-top:14px">${R('Name',a.name)}${R('Mobile',a.phone)}${R('Aadhaar',a.aadhaar)}${R('Address',a.address)}${R('Purpose of stay',a.purpose)}${R('Date of joining',a.join_date)}</div>
 ${a.status==='pending'?`<div class="note">${I('clock')}<div>Your application is under review. You will be emailed once it is decided.</div></div>`:''}
 ${a.status==='approved'?`<button class="btn g" style="margin-top:16px" data-act="opPlan" data-id="${a.id}" data-h="${a.hostel_id}">Choose your bed</button><div id="pv"></div>`:''}
 ${live?`<div class="stats" style="margin-top:18px"><div class="card stat"><b>${money(a.amount_due)}</b><span>Fee</span></div><div class="card stat"><b>${money(a.paid_amount)}</b><span>Paid</span></div><div class="card stat"><b>${money(bal)}</b><span>Balance</span></div><div class="card stat" style="font-size:14px"><b style="font-size:20px">${dt(a.due_at)}</b><span>Pay before</span></div></div>`:''}
 ${a.status==='assigned'?(full?`<div class="note w">${I('wallet')}<div>Pay ${money(a.amount_due)} to the hostel owner${a.hostels?.phone?` (<a href="tel:${esc(a.hostels.phone)}">${esc(a.hostels.phone)}</a>)`:''} before the time above, then enter your payment reference (UPI transaction ID).</div></div>
 <div class="srch" style="max-width:none"><input id="p_ref" placeholder="Payment reference"><button class="btn g" data-act="opPay" data-id="${a.id}">Submit payment</button></div>`:`<div class="note w">${I('lock')}<div>Verify with the email code to submit your payment.</div></div>`):''}
 ${a.status==='paid'?`<div class="note">${I('clock')}<div>Payment submitted (${esc(a.paid_ref||'')}). Waiting for the hostel to verify it.</div></div>`:''}
 ${a.status==='verified'?`<div class="note">${I('check')}<div>Payment verified. The hostel will mark your check-in.</div></div>`:''}
 ${a.status==='resident'||tk.length?`<h3 style="margin:22px 0 10px;font-size:20px">Maintenance tickets</h3>${tk.map(t=>{const c=TC[t.status];return`<div class="card pad" style="margin-bottom:8px;padding:12px 16px"><div style="display:flex;justify-content:space-between;gap:8px"><b>${esc(t.title)}</b>${chip(c[0],c[1])}</div>${t.reply?`<div class="meta">Hostel: ${esc(t.reply)}</div>`:''}</div>`}).join('')||'<div class="meta">No tickets yet.</div>'}
 ${a.status==='resident'?(full?`<div class="f2" style="margin-top:12px"><div><label>Problem</label><input id="t_t" placeholder="Fan not working"></div><div><label>Details (optional)</label><input id="t_d"></div></div><button class="btn sm g" style="margin-top:10px" data-act="opTicket" data-id="${a.id}">Raise ticket</button>`:'<div class="meta" style="margin-top:10px">Verify with the email code to raise a ticket.</div>'):''}`:''}</div>`}).join('')}</div>`)};
A.opPlan=async d=>{OP.app=d.id;OP.d=await api('plan',{hostel_id:d.h});OP.fi=0;showPlan()};
function showPlan(){const{floors,beds}=OP.d,f=floors[OP.fi],bm={};if(f)beds.filter(b=>b.floor_id===f.id).forEach(b=>bm[b.code]=b);
 $('#pv').innerHTML=f?`<div class="tabs" style="margin-top:16px">${floors.map((x,i)=>`<button class="btn ${i===OP.fi?'on':''}" data-act="opFl" data-i="${i}">${esc(x.name)}</button>`).join('')}</div><div class="card pl">${plan(f.layout||{},{bm})}${legend()}</div><p class="meta" style="margin-top:8px">Tap a green bed to choose it.</p>`:'<div class="card empty">The floor plan will be published soon.</div>'}
A.opFl=d=>{OP.fi=+d.i;showPlan()};
A.bed=async d=>{if(!OP.app)return;const b=OP.d.beds.find(x=>x.id===d.id);if(!confirm(`Choose bed ${b.code}${b.price?' at '+money(b.price)+' per month':''}?`))return;await api('pick_bed',{app_id:OP.app,bed_id:d.id});toast('Bed chosen');mePage2()};
A.opPay=async d=>{await api('pay',{app_id:d.id,ref:V('p_ref')});toast('Payment submitted');mePage2()};
A.opTicket=async d=>{await api('ticket_new',{app_id:d.id,title:V('t_t'),detail:V('t_d')});toast('Ticket raised');mePage2()};

/* ---------- admin: Residents + Tickets tabs ---------- */
const ova=window.adminView;
window.adminView=()=>{const t=AD.tab,mine=t==='res'||t==='tix';if(mine)AD.tab='overview';ova();AD.tab=t;const as=$('aside');if(!as)return;
 const add=(k,l,ic)=>as.querySelector('[data-act=logout]').insertAdjacentHTML('beforebegin',`<button class="btn ${t===k?'on':''}" data-act="tab" data-t="${k}">${I(ic)} ${l}</button>`);
 add('res','Residents & payments','users');add('tix','Maintenance','wrench');
 if(!mine)return;as.querySelectorAll('.btn.on').forEach(b=>b.dataset.t!==t&&b.classList.remove('on'));
 (t==='res'?resTab:tixTab)().catch(e=>toast(e.message,1))};
async function resTab(){const rs=AD.rs=await api('residents'),h=AD.hs.find(x=>x.id===AD.rh)||null,L=rs.filter(a=>!AD.rh||a.hostel_id===AD.rh);
 const act=a=>({approved:[['Assign bed','opAsg','g']],assigned:[['Fee / due time','opFee','']],paid:[['Verify payment','opVer','g'],['Fee / due time','opFee','']],verified:[['Check in','opIn','g']],resident:[['Fee / due time','opFee',''],['Check out','opOut','o']]}[a.status]||[]).map(x=>`<button class="btn sm ${x[2]}" data-act="${x[1]}" data-id="${a.id}">${x[0]}</button>`).join('');
 $('#pane').innerHTML=`<div class="bar"><h2>Residents & payments</h2><select id="rh" style="width:auto"><option value="">All hostels</option>${AD.hs.map(x=>`<option value="${x.id}" ${x.id===AD.rh?'selected':''}>${esc(x.name)}</option>`).join('')}</select></div>
 <div class="card tw"><table><thead><tr><th>Person</th><th>Bed / plan</th><th>Status</th><th>Fee</th><th>Paid / due</th><th>Actions</th></tr></thead><tbody>${L.map(a=>{const bal=Math.max(0,a.amount_due-a.paid_amount);
 return`<tr><td style="display:flex;gap:10px;align-items:center">${safe(a.photo_url)?`<img src="${esc(a.photo_url)}" alt="" width="44" height="44" style="border-radius:50%;object-fit:cover">`:`<span style="width:44px;height:44px;border-radius:50%;background:var(--s2);display:grid;place-items:center">${I('user',18)}</span>`}<div><b>${esc(a.name)}</b><div class="meta">${esc(a.phone)}<br>${esc(a.hostels?.name)}</div></div></td>
 <td>${esc(a.beds?.code||'-')}<div class="meta">${a.plan==='bed_only'?'Bed only':'With food'}</div></td><td>${sc(a.status)}${a.paid_ref?`<div class="meta">Ref ${esc(a.paid_ref)}</div>`:''}</td><td>${money(a.amount_due)}<div class="meta">Due ${dt(a.due_at)}</div></td>
 <td>${money(a.paid_amount)}<div class="meta" style="color:${bal?'var(--occ)':'var(--ok)'}">${bal?'Balance '+money(bal):'No dues'}</div></td><td><div class="acts">${act(a)}</div></td></tr>`}).join('')||'<tr><td colspan="6" class="empty">Nobody here yet. Approve applications first.</td></tr>'}</tbody></table></div>`;
 $('#rh').onchange=e=>{AD.rh=e.target.value;resTab()}}
const R_=id=>AD.rs.find(a=>a.id===id),loc=s=>s?new Date(new Date(s)-new Date(s).getTimezoneOffset()*6e4).toISOString().slice(0,16):'';
const done=async m=>{A.close();toast(m);await resTab()};
A.opAsg=async d=>{const a=R_(d.id),p=await api('plan',{hostel_id:a.hostel_id}),fl=Object.fromEntries(p.floors.map(f=>[f.id,f.name])),bs=p.beds.filter(b=>b.live==='available');OP.beds=bs;
 modal(`${mh('Assign bed to '+esc(a.name))}<div class="f2"><div class="full"><label>Bed</label><select id="o_b">${bs.map(b=>`<option value="${b.id}">${esc(fl[b.floor_id])} - ${esc(b.code)}${b.price?' ('+money(b.price)+')':''}</option>`).join('')||'<option value="">No free beds</option>'}</select></div>
 <div><label>Fee (Rs)</label><input id="o_a" type="number" value="${bs[0]?.price||6000}"></div><div><label>Pay before</label><input id="o_d" type="datetime-local"></div></div><button class="btn g" style="margin-top:16px" data-act="opAsgGo" data-id="${a.id}">Assign and notify</button>`);
 $('#o_b').onchange=e=>{$('#o_a').value=OP.beds.find(b=>b.id===e.target.value)?.price||6000}};
A.opAsgGo=async d=>{await api('assign',{id:d.id,bed_id:V('o_b'),amount:V('o_a'),due_at:V('o_d')?new Date(V('o_d')).toISOString():null});done('Bed assigned')};
A.opFee=d=>{const a=R_(d.id);modal(`${mh('Fee for '+esc(a.name))}<div class="f2"><div><label>Fee (Rs)</label><input id="o_a" type="number" value="${a.amount_due}"></div><div><label>Pay before</label><input id="o_d" type="datetime-local" value="${loc(a.due_at)}"></div>
 <div class="full"><label>Plan</label><select id="o_p"><option value="full" ${a.plan==='full'?'selected':''}>With food</option><option value="bed_only" ${a.plan==='bed_only'?'selected':''}>Bed only (no food)</option></select></div></div><button class="btn g" style="margin-top:16px" data-act="opFeeGo" data-id="${a.id}">Save</button>`)};
A.opFeeGo=async d=>{await api('set_fee',{id:d.id,amount:V('o_a'),plan:V('o_p'),due_at:V('o_d')?new Date(V('o_d')).toISOString():null});done('Fee updated')};
A.opVer=async d=>{const a=R_(d.id),v=prompt(`Payment reference: ${a.paid_ref||'-'}\nAmount received (Rs):`,a.amount_due);if(v===null)return;await api('verify',{id:d.id,paid:v});done('Payment verified')};
A.opIn=async d=>{await api('checkin',{id:d.id});done('Checked in')};
A.opOut=async d=>{if(!confirm('Check this resident out and free the bed?'))return;await api('checkout',{id:d.id});done('Checked out')};
async function tixTab(){const ts=AD.ts=await api('tickets');
 $('#pane').innerHTML=`<div class="bar"><h2>Maintenance</h2></div><div style="display:grid;gap:12px">${ts.map(t=>{const c=TC[t.status];return`<div class="card pad"><div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><div><b>${esc(t.title)}</b><div class="meta">${esc(t.applications?.name)} - ${esc(t.hostels?.name)} - ${dt(t.created_at)}</div></div>${chip(c[0],c[1])}</div>${t.detail?`<p style="color:var(--mut);margin-top:8px">${esc(t.detail)}</p>`:''}
 <div class="tool" style="margin:12px 0 0"><select id="ts_${t.id}">${Object.keys(TC).map(k=>`<option value="${k}" ${k===t.status?'selected':''}>${TC[k][1]}</option>`).join('')}</select><input id="tr_${t.id}" placeholder="Reply to resident" value="${esc(t.reply)}" style="flex:1;min-width:200px"><button class="btn sm g" data-act="opTk" data-id="${t.id}">Save</button></div></div>`}).join('')||'<div class="card empty">No tickets.</div>'}</div>`}
A.opTk=async d=>{await api('set_ticket',{id:d.id,status:V('ts_'+d.id),reply:V('tr_'+d.id)});toast('Ticket updated');tixTab()};
})();
