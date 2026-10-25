/* floorplan-pro.js - Floor plan editor v2 for HostelAtlas.
   Add <script src="/floorplan-pro.js"></script> right after the main <script> in index.html.
   Replaces the Admin > Floor plans tab. No backend changes needed. */
(()=>{
const S=10, sn=v=>Math.round(v/5)*5, num=v=>Math.round(v*S), ft=v=>+(v/S).toFixed(2);
const K={toilet:'washroom',wc:'washroom',passage:'corridor',stair:'stairs',elevator:'lift'};
const P={sel:new Set(),hist:[],fut:[],z:1,px:0,py:0,objs:null};
const byId=id=>P.objs.find(o=>o.id===id), $$=s=>document.querySelector(s);

/* ---------- plan code (DSL) ---------- */
function fillBeds(r,n,pre,price){const cols=Math.max(1,Math.floor((r.w-5)/35)),a=[];
 for(let i=0;i<n;i++)a.push({id:uid(),t:'bed',x:r.x+5+(i%cols)*35,y:r.y+5+Math.floor(i/cols)*70,w:30,h:65,r:0,l:'',code:pre+'-'+(i+1),price:price||0});return a}
function parse(src){const out=[],err=[];let ox=0,oy=0;
 src.split('\n').forEach((raw,i)=>{const ln=raw.replace(/#.*$/,'').trim();if(!ln)return;
  const tk=[...ln.matchAll(/"([^"]*)"|(\S+)/g)].map(m=>[m[1]??m[2],m[1]!==undefined]),kind=tk.shift()[0].toLowerCase();
  if(kind==='origin'){ox=+tk[0]?.[0]||0;oy=+tk[1]?.[0]||0;return}
  if(kind==='floor')return;
  const t=K[kind]||kind;if(!DEF[t]){err.push(`Line ${i+1}: unknown type "${kind}"`);return}
  const o={id:uid(),t,x:0,y:0,w:DEF[t][0],h:DEF[t][1],r:0,l:DEF[t][2]},ns=[];let name='',nb=0,pr=0,lab=0;
  tk.forEach(([v,q])=>{let m;
   if(q){o.l=v;lab=1}
   else if(m=v.match(/^([\d.]+)x([\d.]+)$/)){o.w=num(m[1]);o.h=num(m[2])}
   else if(/^-?[\d.]+$/.test(v))ns.push(+v);
   else if(m=v.match(/^(\w+)=(.+)$/)){const k=m[1].toLowerCase();if(k==='beds')nb=+m[2];else if(k==='price')pr=+m[2];else if(k==='r')o.r=+m[2]}
   else name=v});
  o.x=num((ns[0]||0)+ox);o.y=num((ns[1]||0)+oy);
  if(t==='bed'){o.code=name||'B'+(out.length+1);o.price=pr;o.l=''}else if(name&&!lab)o.l=name;
  out.push(o);if(nb)out.push(...fillBeds(o,nb,(name||o.l).replace(/\W/g,'')||'B',pr))});
 return{objs:out,err}}
const toCode=objs=>objs.map(o=>`${{washroom:'wc'}[o.t]||o.t}${o.t==='bed'?' '+o.code:''} ${ft(o.x)} ${ft(o.y)} ${ft(o.w)}x${ft(o.h)}${o.r?' r='+o.r:''}${o.t==='bed'?(o.price?' price='+o.price:''):(o.l?` "${o.l}"`:'')}`).join('\n');

/* ---------- history ---------- */
const push=()=>{P.hist.push(JSON.stringify(P.objs));if(P.hist.length>100)P.hist.shift();P.fut=[];P.dirty=1};
const restore=s=>{P.objs=JSON.parse(s);P.sel=new Set([...P.sel].filter(byId));P.dirty=1;render();panel()};
const undo=()=>{if(!P.hist.length)return toast('Nothing to undo');P.fut.push(JSON.stringify(P.objs));restore(P.hist.pop())};
const redo=()=>{if(!P.fut.length)return toast('Nothing to redo');P.hist.push(JSON.stringify(P.objs));restore(P.fut.pop())};

/* ---------- render ---------- */
function render(){const el=$$('#cv');if(!el)return;
 const g=(P.objs||[]).map(o=>{const s=P.sel.has(o.id);return`<g data-o="${o.id}" transform="translate(${o.x} ${o.y}) rotate(${o.r||0} ${o.w/2} ${o.h/2})">${shape(o,'available')}${s?`<rect width="${o.w}" height="${o.h}" fill="rgba(216,185,138,.1)" stroke="#d8b98a" stroke-width="2" stroke-dasharray="5 4"/>`:''}${s&&P.sel.size===1?`<rect data-rs="1" x="${o.w-7}" y="${o.h-7}" width="14" height="14" rx="3" fill="#d8b98a" style="cursor:nwse-resize"/>`:''}</g>`}).join('');
 el.innerHTML=P.objs?`<svg viewBox="${P.px} ${P.py} ${1000/P.z} ${640/P.z}" class="plan" style="cursor:grab" role="img" aria-label="Floor plan editor"><defs><pattern id="g1" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10 0H0V10" fill="none" stroke="#fff" stroke-opacity=".04"/></pattern><pattern id="g5" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M50 0H0V50" fill="none" stroke="#fff" stroke-opacity=".1"/></pattern></defs><rect x="-3000" y="-3000" width="7000" height="7000" fill="url(#g1)"/><rect x="-3000" y="-3000" width="7000" height="7000" fill="url(#g5)"/>${g}</svg><div class="meta" style="margin-top:8px;font-size:12px">1 square = 1 ft. Zoom ${Math.round(P.z*100)}%${P.dirty?' - unsaved changes':''}</div>`:'<div class="empty">Add a floor to start drawing.</div>'}
function panel(){const el=$$('#pn');if(!el)return;const n=P.sel.size,o=n===1?byId([...P.sel][0]):null;
 if(!n){el.innerHTML='<div class="meta">Click an object to edit it. Shift+click to select several. Drag empty space to pan, scroll to zoom.</div><div class="meta" style="font-size:12px">Ctrl+Z undo, Ctrl+Y redo, Ctrl+D duplicate, Ctrl+A select all, R rotate, Delete remove, arrows nudge (Shift = 5 ft).</div>';return}
 if(!o){el.innerHTML=`<b style="font:500 20px Fraunces">${n} selected</b><div class="acts"><button class="btn sm" data-act="pDup">Duplicate</button><button class="btn sm" data-act="pRot">Rotate 90</button><button class="btn sm o" data-act="pDel">Delete</button></div>`;return}
 const F=(k,l)=>`<div><label>${l}</label><input data-pk="${k}" type="number" step="0.5" value="${ft(o[k]||0)}"></div>`;
 el.innerHTML=`<b style="font:500 20px Fraunces">${PAL.find(p=>p[0]===o.t)[1]}</b><div class="f2">${o.t!=='bed'?`<div class="full"><label>Label</label><input data-pk="l" value="${esc(o.l)}"></div>`:`<div><label>Bed code</label><input data-pk="code" value="${esc(o.code)}"></div><div><label>Rent / month</label><input data-pk="price" type="number" value="${o.price||0}"></div>`}
 ${F('x','X (ft)')}${F('y','Y (ft)')}${F('w','Width (ft)')}${F('h','Height (ft)')}<div><label>Rotation</label><input data-pk="r" type="number" step="90" value="${o.r||0}"></div></div>
 ${o.t==='room'?`<div class="f2"><div><label>Beds to add</label><input id="fb_n" type="number" min="1" max="30" value="4"></div><div><label>Rent / month</label><input id="fb_p" type="number" value="6000"></div></div><button class="btn sm g" data-act="pFill">Fill room with beds</button>`:''}
 <div class="acts"><button class="btn sm" data-act="pDup">Duplicate</button><button class="btn sm" data-act="pRot">Rotate 90</button><button class="btn sm o" data-act="pDel">Delete</button></div>`}

/* ---------- loading ---------- */
async function load(hid,fid){const r=await api('hostel',{id:hid});P.hid=hid;P.floors=r.floors;P.fid=fid||r.floors[0]?.id;floor()}
function floor(){$$('#pH').value=P.hid;$$('#pF').innerHTML=P.floors.map(f=>`<option value="${f.id}">${esc(f.name)}</option>`).join('')||'<option value="">No floors yet</option>';$$('#pF').value=P.fid||'';
 const f=P.floors.find(x=>x.id===P.fid);P.objs=f?JSON.parse(JSON.stringify(f.layout?.objs||[])):null;P.sel=new Set();P.hist=[];P.fut=[];P.dirty=0;P.z=1;P.px=0;P.py=0;render();panel();bind()}
const fit=()=>{if(!P.objs?.length){P.z=1;P.px=P.py=0;return render()}
 const x1=Math.min(...P.objs.map(o=>o.x)),y1=Math.min(...P.objs.map(o=>o.y)),x2=Math.max(...P.objs.map(o=>o.x+o.w)),y2=Math.max(...P.objs.map(o=>o.y+o.h));
 P.z=Math.min(3,Math.max(.4,Math.min(940/(x2-x1||1),580/(y2-y1||1))));P.px=x1-(1000/P.z-(x2-x1))/2;P.py=y1-(640/P.z-(y2-y1))/2;render()};
const guard=()=>!P.dirty||confirm('Discard unsaved changes on this floor?');

/* ---------- pointer interaction ---------- */
function bind(){const cv=$$('#cv');if(!cv)return;let d=null;
 const pt=e=>{const s=cv.querySelector('svg'),p=s.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(s.getScreenCTM().inverse())};
 cv.onpointerdown=e=>{if(!P.objs)return;const g=e.target.closest('[data-o]');
  if(!g){if(!e.shiftKey)P.sel.clear();d={pan:1,cx:e.clientX,cy:e.clientY,px:P.px,py:P.py};cv.setPointerCapture(e.pointerId);render();panel();return}
  const o=byId(g.dataset.o);
  if(e.shiftKey){P.sel.has(o.id)?P.sel.delete(o.id):P.sel.add(o.id);render();panel();return}
  if(!P.sel.has(o.id))P.sel=new Set([o.id]);push();
  d={p:pt(e),o,rs:!!e.target.closest('[data-rs]'),moved:0,items:[...P.sel].map(id=>{const q=byId(id);return{q,x:q.x,y:q.y,w:q.w,h:q.h}})};cv.setPointerCapture(e.pointerId);render();panel()};
 cv.onpointermove=e=>{if(!d)return;
  if(d.pan){const k=1000/P.z/cv.querySelector('svg').getBoundingClientRect().width;P.px=d.px-(e.clientX-d.cx)*k;P.py=d.py-(e.clientY-d.cy)*k;render();return}
  const p=pt(e),dx=p.x-d.p.x,dy=p.y-d.p.y,it=d.items.find(i=>i.q===d.o);d.moved=1;
  if(d.rs){const r=(d.o.r||0)*Math.PI/180,c=Math.cos(r),s=Math.sin(r);d.o.w=Math.max(10,sn(it.w+dx*c+dy*s));d.o.h=Math.max(10,sn(it.h-dx*s+dy*c))}
  else{let nx=sn(it.x+dx),ny=sn(it.y+dy);const ids=new Set(d.items.map(i=>i.q.id));
   for(const q of P.objs){if(ids.has(q.id))continue;for(const a of[q.x,q.x+q.w])for(const b of[nx,nx+it.w])if(Math.abs(a-b)<6){nx+=a-b;break}
    for(const a of[q.y,q.y+q.h])for(const b of[ny,ny+it.h])if(Math.abs(a-b)<6){ny+=a-b;break}}
   d.items.forEach(i=>{i.q.x=i.x+nx-it.x;i.q.y=i.y+ny-it.y})}
  P.dirty=1;render()};
 cv.onpointerup=()=>{if(d&&!d.pan&&!d.moved){P.hist.pop()}d=null;render();panel()};
 cv.onwheel=e=>{if(!P.objs)return;e.preventDefault();const s=cv.querySelector('svg'),r=s.getBoundingClientRect(),p=pt(e),z=Math.min(4,Math.max(.3,P.z*(e.deltaY<0?1.15:.87)));
  P.px=p.x-((e.clientX-r.left)/r.width)*1000/z;P.py=p.y-((e.clientY-r.top)/r.height)*640/z;P.z=z;render()}}

/* ---------- actions ---------- */
const sel=()=>[...P.sel].map(byId);
const zoom=f=>{P.z=Math.min(4,Math.max(.3,P.z*f));render()};
A.pUndo=undo;A.pRedo=redo;A.pFit=fit;A.pZi=()=>zoom(1.25);A.pZo=()=>zoom(.8);
A.pAdd=d=>{if(!P.objs)return toast('Add a floor first',1);push();const[w,h,l]=DEF[d.t],o={id:uid(),t:d.t,x:sn(P.px+500/P.z-w/2),y:sn(P.py+320/P.z-h/2),w,h,r:0,l};
 if(d.t==='bed'){const f=P.floors.find(x=>x.id===P.fid),pre=(f.name.replace(/[^a-z0-9]/gi,'').slice(0,4)||'B').toUpperCase(),used=new Set(P.objs.map(x=>x.code));let n=1;while(used.has(pre+'-'+String(n).padStart(2,'0')))n++;o.code=pre+'-'+String(n).padStart(2,'0');o.price=0}
 P.objs.push(o);P.sel=new Set([o.id]);render();panel()};
A.pDup=()=>{if(!P.sel.size)return;push();const ns=new Set();sel().forEach(o=>{const c={...o,id:uid(),x:o.x+20,y:o.y+20};if(c.t==='bed'){let n=2;while(P.objs.some(x=>x.code===o.code+'-'+n))n++;c.code=o.code+'-'+n}P.objs.push(c);ns.add(c.id)});P.sel=ns;render();panel()};
A.pRot=()=>{if(!P.sel.size)return;push();sel().forEach(o=>o.r=((o.r||0)+90)%360);render();panel()};
A.pDel=()=>{if(!P.sel.size)return;push();P.objs=P.objs.filter(o=>!P.sel.has(o.id));P.sel.clear();render();panel()};
A.pFill=()=>{const r=sel()[0],n=Math.min(30,+$$('#fb_n').value||1);push();const pre=(r.l||'R').replace(/\W/g,'');P.objs.push(...fillBeds(r,n,pre,+$$('#fb_p').value||0));render();panel();toast(n+' beds added - drag them to adjust')};
A.pSave=async()=>{if(!P.objs)return;const c=P.objs.filter(o=>o.t==='bed').map(o=>(o.code||'').trim());if(c.some(x=>!x)||new Set(c).size!==c.length)return toast('Every bed needs a unique code',1);
 await api('save_layout',{floor_id:P.fid,layout:{objs:P.objs}});P.floors.find(f=>f.id===P.fid).layout={objs:JSON.parse(JSON.stringify(P.objs))};P.dirty=0;render();toast('Layout saved and bed inventory updated')};
A.pNF=()=>modal(`${mh('Add floor')}<div class="f2"><div><label>Floor name</label><input id="nf_n" placeholder="First floor"></div><div><label>Level number</label><input id="nf_l" type="number" value="1"></div></div><button class="btn g" style="margin-top:18px" data-act="pMk">Add floor</button>`);
A.pMk=async()=>{const r=await api('save_floor',{hostel_id:P.hid,name:$$('#nf_n').value,level:+$$('#nf_l').value||0});A.close();await load(P.hid,r.id)};
A.pDF=async()=>{if(!P.fid||!confirm('Delete this floor and its beds? Floors with bookings cannot be deleted.'))return;await api('del_floor',{id:P.fid});await load(P.hid)};
A.pCode=()=>modal(`${mh('Plan code')}<p class="meta" style="margin:-6px 0 10px">One line per object: <b>type [name] x y WxH "label" beds=N price=N r=90</b>. Sizes and positions are in feet. Types: room, corridor, wc, stairs, lift, door, window, bed, balcony, fan, light, rack. Use <b>origin x y</b> to shift everything.</p>
 <textarea id="pc" style="min-height:260px;font:12.5px/1.5 ui-monospace,Menlo,monospace" spellcheck="false" placeholder='room R1 0 0 14.25x9.5 "Room 1" beds=4 price=6000'>${esc(toCode(P.objs||[]))}</textarea><div id="pe" class="meta" style="color:var(--occ);margin-top:8px"></div>
 <div class="acts" style="margin-top:14px"><button class="btn g" data-act="pRun" data-m="r">Replace plan</button><button class="btn" data-act="pRun" data-m="a">Add to plan</button></div>`);
A.pRun=d=>{if(!P.objs)return toast('Add a floor first',1);const r=parse($$('#pc').value);if(r.err.length){$$('#pe').innerHTML=r.err.map(esc).join('<br>');return}
 if(d.m==='r'&&P.objs.length&&!confirm('Replace everything on this floor? You can still undo.'))return;
 push();P.objs=d.m==='r'?r.objs:P.objs.concat(r.objs);P.sel=new Set();A.close();fit();panel();toast(r.objs.length+' objects placed - press Save when happy')};

/* ---------- admin tab ---------- */
window.plansTab=()=>!AD.hs.length?'<div class="bar"><h2>Floor plans</h2></div><div class="card empty">Add a hostel first.</div>':
 `<div class="bar"><h2>Floor plans</h2></div><div class="tool"><select id="pH" aria-label="Hostel">${AD.hs.map(h=>`<option value="${h.id}">${esc(h.name)}</option>`).join('')}</select><select id="pF" aria-label="Floor"></select><button class="btn" data-act="pNF">${I('plus',16)} Floor</button><button class="btn o" data-act="pDF" aria-label="Delete floor">${I('trash',16)}</button></div>
 <div class="tool" style="position:sticky;top:76px;z-index:5"><button class="btn" data-act="pUndo">Undo</button><button class="btn" data-act="pRedo">Redo</button><button class="btn" data-act="pZo" aria-label="Zoom out">-</button><button class="btn" data-act="pZi" aria-label="Zoom in">+</button><button class="btn" data-act="pFit">Fit</button><button class="btn" data-act="pCode">Plan code</button><button class="btn g" data-act="pSave">${I('save',16)} Save layout</button></div>
 <div class="ed"><div class="pal">${PAL.map(p=>`<button class="btn sm" data-act="pAdd" data-t="${p[0]}">${I(p[2],16)} ${p[1]}</button>`).join('')}</div><div class="card pl" id="cv"></div><div class="card panel" id="pn"></div></div>`;
window.edInit=async()=>{if(AD.hs.length)await load(AD.hs[0].id)};

document.addEventListener('focusin',e=>{if(e.target.dataset?.pk&&P.sel.size===1)push()});
document.addEventListener('input',e=>{const k=e.target.dataset?.pk;if(!k||P.sel.size!==1)return;const o=byId([...P.sel][0]),v=e.target.value;
 o[k]=['l','code'].includes(k)?v:['x','y','w','h'].includes(k)?num(+v||0):+v||0;if(k==='w'||k==='h')o[k]=Math.max(5,o[k]);P.dirty=1;render()});
document.addEventListener('change',async e=>{try{
 if(e.target.id==='pH'){if(!guard()){e.target.value=P.hid;return}await load(e.target.value)}
 if(e.target.id==='pF'){if(!guard()){e.target.value=P.fid;return}P.fid=e.target.value;floor()}}catch(x){toast(x.message,1)}});
addEventListener('beforeunload',e=>{if(P.dirty&&$$('#cv')){e.preventDefault();e.returnValue=''}});
addEventListener('keydown',e=>{if(!$$('#cv')||!P.objs||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||$$('#modal .ov'))return;const k=e.key.toLowerCase(),m=e.ctrlKey||e.metaKey;
 if(m&&k==='z'){e.preventDefault();e.shiftKey?redo():undo()}else if(m&&k==='y'){e.preventDefault();redo()}else if(m&&k==='d'){e.preventDefault();A.pDup()}
 else if(m&&k==='a'){e.preventDefault();P.sel=new Set(P.objs.map(o=>o.id));render();panel()}else if(k==='delete'||k==='backspace'){e.preventDefault();A.pDel()}
 else if(k==='r'&&!m)A.pRot();else if(k.startsWith('arrow')&&P.sel.size){e.preventDefault();push();const s=e.shiftKey?50:5,[dx,dy]={arrowleft:[-s,0],arrowright:[s,0],arrowup:[0,-s],arrowdown:[0,s]}[k];sel().forEach(o=>{o.x+=dx;o.y+=dy});render();panel()}},true);
})();
