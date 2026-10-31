/* floorplan-pro.js - floor-plan editor for Admin > Floor plans.
   Loaded by index.html after the main script and uses its shared helpers (api, sheet, toast, shape, PAL, DEF, I, esc).
   Exposes window.PE: html() renders the tab, init() loads the first hostel, dirty / reset() guard unsaved work. */
(()=>{
const U=10,sn=v=>Math.round(v/5)*5,num=v=>Math.round(v*U),ft=v=>+(v/U).toFixed(2),oid=()=>'o'+Math.random().toString(36).slice(2,9);
const K={toilet:'washroom',wc:'washroom',passage:'corridor',stair:'stairs',elevator:'lift'};
const P={sel:new Set(),hist:[],fut:[],z:1,px:0,py:0,objs:null,dirty:0,hid:null,fid:null,floors:[]};
const byId=id=>P.objs.find(o=>o.id===id),sel=()=>[...P.sel].map(byId).filter(Boolean),onTab=()=>!!$('#cv');

/* ---------- plan code (one object per line) ---------- */
function fillBeds(r,n,pre,price,used){const cols=Math.max(1,Math.floor((r.w-5)/35)),a=[];let k=1;
 for(let i=0;i<n;i++){while(used.has(pre+'-'+k))k++;const code=pre+'-'+k;used.add(code);a.push({id:oid(),t:'bed',x:r.x+5+(i%cols)*35,y:r.y+5+Math.floor(i/cols)*70,w:30,h:65,r:0,l:'',code,price:price||0})}return a}
function parse(src,used){const out=[],err=[];let ox=0,oy=0;
 src.split('\n').forEach((raw,i)=>{const ln=raw.replace(/#.*$/,'').trim();if(!ln)return;
  const tk=[...ln.matchAll(/"([^"]*)"|(\S+)/g)].map(m=>[m[1]??m[2],m[1]!==undefined]),kind=tk.shift()[0].toLowerCase();
  if(kind==='origin'){ox=+tk[0]?.[0]||0;oy=+tk[1]?.[0]||0;return}
  if(kind==='floor')return;
  const t=K[kind]||kind;if(!DEF[t]){err.push(`Line ${i+1}: unknown type "${kind}"`);return}
  const o={id:oid(),t,x:0,y:0,w:DEF[t][0],h:DEF[t][1],r:0,l:DEF[t][2]},ns=[];let name='',nb=0,pr=0,lab=0;
  tk.forEach(([v,q])=>{let m;
   if(q){o.l=v;lab=1}
   else if(m=v.match(/^([\d.]+)x([\d.]+)$/)){o.w=Math.max(5,num(m[1]));o.h=Math.max(5,num(m[2]))}
   else if(/^-?[\d.]+$/.test(v))ns.push(+v);
   else if(m=v.match(/^(\w+)=(.+)$/)){const k=m[1].toLowerCase();if(k==='beds')nb=Math.min(30,Math.max(0,+m[2]||0));else if(k==='price')pr=Math.max(0,+m[2]||0);else if(k==='r')o.r=+m[2]||0}
   else name=v});
  o.x=num((ns[0]||0)+ox);o.y=num((ns[1]||0)+oy);
  if(t==='bed'){o.code=name||'B'+(out.length+1);o.price=pr;o.l='';used.add(o.code)}else if(name&&!lab)o.l=name;
  out.push(o);if(nb)out.push(...fillBeds(o,nb,(name||o.l).replace(/\W/g,'')||'B',pr,used))});
 return{objs:out,err}}
const toCode=objs=>objs.map(o=>`${{washroom:'wc'}[o.t]||o.t}${o.t==='bed'?' '+o.code:''} ${ft(o.x)} ${ft(o.y)} ${ft(o.w)}x${ft(o.h)}${o.r?' r='+o.r:''}${o.t==='bed'?(o.price?' price='+o.price:''):(o.l?` "${o.l}"`:'')}`).join('\n');

/* ---------- history ---------- */
const push=()=>{P.hist.push(JSON.stringify(P.objs));if(P.hist.length>100)P.hist.shift();P.fut=[];P.dirty=1};
const restore=s=>{P.objs=JSON.parse(s);P.sel=new Set([...P.sel].filter(byId));P.dirty=1;render();panel()};
const undo=()=>{if(!P.hist.length)return toast('Nothing to undo');P.fut.push(JSON.stringify(P.objs));restore(P.hist.pop())};
const redo=()=>{if(!P.fut.length)return toast('Nothing to redo');P.hist.push(JSON.stringify(P.objs));restore(P.fut.pop())};

/* ---------- render ---------- */
function render(){const el=$('#cv');if(!el)return;
 const g=(P.objs||[]).map(o=>{const s=P.sel.has(o.id);return`<g data-o="${esc(o.id)}" transform="translate(${o.x} ${o.y}) rotate(${o.r||0} ${o.w/2} ${o.h/2})">${shape(o,'available')}${s?`<rect width="${o.w}" height="${o.h}" class="e-sel"/>`:''}${s&&P.sel.size===1?`<rect data-rs="1" x="${o.w-7}" y="${o.h-7}" width="14" height="14" rx="3" class="e-rs"/>`:''}</g>`}).join('');
 el.innerHTML=P.objs?`<svg viewBox="${P.px} ${P.py} ${1000/P.z} ${640/P.z}" class="plan edit" role="img" aria-label="Floor plan editor"><defs><pattern id="g1" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10 0H0V10" class="e-g1"/></pattern><pattern id="g5" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M50 0H0V50" class="e-g5"/></pattern></defs><rect x="-3000" y="-3000" width="7000" height="7000" fill="url(#g1)"/><rect x="-3000" y="-3000" width="7000" height="7000" fill="url(#g5)"/>${g}</svg>
 <div class="efoot"><span>1 small square = 1 ft · Zoom ${Math.round(P.z*100)}% · ${P.objs.filter(o=>o.t==='bed').length} beds</span>${P.dirty?chip('--hold','Unsaved changes'):''}</div>`:`<div class="empty">Add a floor to start drawing.</div>`}
const acts=`<div class="row8" style="margin-top:12px"><button class="btn bs bm" data-act="pDup">Duplicate</button><button class="btn bs bm" data-act="pRot">Rotate 90°</button><button class="btn bd2 bm" data-act="pDel">Delete</button></div>`;
function panel(){const el=$('#pn');if(!el)return;const n=P.sel.size,o=n===1?byId([...P.sel][0]):null;
 if(!n){el.innerHTML=`<h3>Editing tips</h3><p class="mu" style="font-size:13.5px">Click an object to edit it, Shift+click to select several. Drag empty space to pan; scroll to zoom. Draw rooms first, then add beds inside them.</p><div class="keys">${[['Ctrl Z','Undo'],['Ctrl Y','Redo'],['Ctrl D','Duplicate'],['Ctrl A','Select all'],['R','Rotate 90°'],['Delete','Remove'],['Arrows','Nudge (Shift = 5 ft)']].map(k=>`<div><kbd>${k[0]}</kbd><span>${k[1]}</span></div>`).join('')}</div>`;return}
 if(!o){el.innerHTML=`<h3>${n} selected</h3>${acts}`;return}
 const F=(k,l)=>`<div><label class="lb">${l}</label><input class="fi sm" data-pk="${k}" type="number" step="0.5" value="${ft(o[k]||0)}"></div>`;
 el.innerHTML=`<h3>${esc(PAL.find(p=>p[0]===o.t)?.[1]||o.t)}</h3>${o.t!=='bed'?`<label class="lb">Label</label><input class="fi sm" data-pk="l" value="${esc(o.l)}">`:`<div class="g2"><div><label class="lb">Bed code</label><input class="fi sm" data-pk="code" value="${esc(o.code)}"></div><div><label class="lb">Rent / month (₹)</label><input class="fi sm" data-pk="price" type="number" min="0" value="${o.price||0}"></div></div>`}
 <div class="g2">${F('x','X (ft)')}${F('y','Y (ft)')}${F('w','Width (ft)')}${F('h','Height (ft)')}</div><label class="lb">Rotation (°)</label><input class="fi sm" data-pk="r" type="number" step="90" value="${o.r||0}">
 ${o.t==='room'?`<div class="fillbox"><b>Fill with beds</b><div class="g2"><div><label class="lb">Beds</label><input class="fi sm" id="fb_n" type="number" min="1" max="30" value="4"></div><div><label class="lb">Rent (₹)</label><input class="fi sm" id="fb_p" type="number" min="0" value="6000"></div></div><button class="btn bs bm bw" data-act="pFill">${I('bed',15)}Add beds to room</button></div>`:''}${acts}`}

/* ---------- loading ---------- */
async function load(hid,fid){const r=await api('hostel',{id:hid});P.hid=hid;P.floors=r.floors;P.fid=r.floors.some(f=>f.id===fid)?fid:r.floors[0]?.id||null;floor()}
function floor(){if(!onTab())return;$('#pH').value=P.hid;$('#pF').innerHTML=P.floors.map(f=>`<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('')||'<option value="">No floors yet</option>';$('#pF').value=P.fid||'';
 const f=P.floors.find(x=>x.id===P.fid);P.objs=f?JSON.parse(JSON.stringify(f.layout?.objs||[])):null;P.sel=new Set();P.hist=[];P.fut=[];P.dirty=0;P.z=1;P.px=0;P.py=0;render();panel();bind();if(P.objs?.length)fit()}
function fit(){if(!P.objs?.length){P.z=1;P.px=P.py=0;return render()}
 const x1=Math.min(...P.objs.map(o=>o.x)),y1=Math.min(...P.objs.map(o=>o.y)),x2=Math.max(...P.objs.map(o=>o.x+o.w)),y2=Math.max(...P.objs.map(o=>o.y+o.h));
 P.z=Math.min(3,Math.max(.3,Math.min(940/(x2-x1||1),580/(y2-y1||1))));P.px=x1-(1000/P.z-(x2-x1))/2;P.py=y1-(640/P.z-(y2-y1))/2;render()}
const guard=()=>!P.dirty||confirm('Discard unsaved changes on this floor?');

/* ---------- pointer interaction ---------- */
function bind(){const cv=$('#cv');if(!cv)return;let d=null;
 const pt=e=>{const s=cv.querySelector('svg'),p=s.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(s.getScreenCTM().inverse())};
 cv.onpointerdown=e=>{if(!P.objs||!e.target.closest('svg'))return;const g=e.target.closest('[data-o]');
  if(!g){if(!e.shiftKey)P.sel.clear();d={pan:1,cx:e.clientX,cy:e.clientY,px:P.px,py:P.py};cv.setPointerCapture(e.pointerId);render();panel();return}
  const o=byId(g.dataset.o);if(!o)return;
  if(e.shiftKey){P.sel.has(o.id)?P.sel.delete(o.id):P.sel.add(o.id);render();panel();return}
  if(!P.sel.has(o.id))P.sel=new Set([o.id]);const wd=P.dirty,fut=P.fut;push();
  d={wd,fut,p:pt(e),o,rs:!!e.target.closest('[data-rs]'),moved:0,items:sel().map(q=>({q,x:q.x,y:q.y,w:q.w,h:q.h}))};cv.setPointerCapture(e.pointerId);render();panel()};
 cv.onpointermove=e=>{if(!d)return;
  if(d.pan){const k=1000/P.z/cv.querySelector('svg').getBoundingClientRect().width;P.px=d.px-(e.clientX-d.cx)*k;P.py=d.py-(e.clientY-d.cy)*k;render();return}
  const p=pt(e),dx=p.x-d.p.x,dy=p.y-d.p.y,it=d.items.find(i=>i.q===d.o);d.moved=1;
  if(d.rs){const r=(d.o.r||0)*Math.PI/180,c=Math.cos(r),s=Math.sin(r);d.o.w=Math.max(10,sn(it.w+dx*c+dy*s));d.o.h=Math.max(10,sn(it.h-dx*s+dy*c))}
  else{let nx=sn(it.x+dx),ny=sn(it.y+dy);const ids=new Set(d.items.map(i=>i.q.id));
   for(const q of P.objs){if(ids.has(q.id))continue;for(const a of[q.x,q.x+q.w])for(const b of[nx,nx+it.w])if(Math.abs(a-b)<6){nx+=a-b;break}
    for(const a of[q.y,q.y+q.h])for(const b of[ny,ny+it.h])if(Math.abs(a-b)<6){ny+=a-b;break}}
   d.items.forEach(i=>{i.q.x=i.x+nx-it.x;i.q.y=i.y+ny-it.y})}
  P.dirty=1;render()};
 cv.onpointerup=cv.onpointercancel=()=>{if(d&&!d.pan&&!d.moved){P.hist.pop();P.fut=d.fut;P.dirty=d.wd}d=null;render();panel()};
 cv.onwheel=e=>{if(!P.objs||!e.target.closest('svg'))return;e.preventDefault();const s=cv.querySelector('svg'),r=s.getBoundingClientRect(),p=pt(e),z=Math.min(4,Math.max(.3,P.z*(e.deltaY<0?1.15:.87)));
  P.px=p.x-((e.clientX-r.left)/r.width)*1000/z;P.py=p.y-((e.clientY-r.top)/r.height)*640/z;P.z=z;render()}}

/* ---------- actions ---------- */
const zoom=f=>{P.z=Math.min(4,Math.max(.3,P.z*f));render()};
A.pUndo=undo;A.pRedo=redo;A.pFit=fit;A.pZi=()=>zoom(1.25);A.pZo=()=>zoom(.8);
A.pAdd=d=>{if(!P.objs)return toast('Add a floor first',1);push();const[w,h,l]=DEF[d.t],o={id:oid(),t:d.t,x:sn(P.px+500/P.z-w/2),y:sn(P.py+320/P.z-h/2),w,h,r:0,l};
 if(d.t==='bed'){const f=P.floors.find(x=>x.id===P.fid),pre=(f.name.replace(/[^a-z0-9]/gi,'').slice(0,4)||'B').toUpperCase(),used=new Set(P.objs.map(x=>x.code));let n=1;while(used.has(pre+'-'+String(n).padStart(2,'0')))n++;o.code=pre+'-'+String(n).padStart(2,'0');o.price=0}
 P.objs.push(o);P.sel=new Set([o.id]);render();panel()};
A.pDup=()=>{if(!P.sel.size)return;push();const ns=new Set(),used=new Set(P.objs.map(x=>x.code));sel().forEach(o=>{const c={...o,id:oid(),x:o.x+20,y:o.y+20};if(c.t==='bed'){let n=2;while(used.has(o.code+'-'+n))n++;c.code=o.code+'-'+n;used.add(c.code)}P.objs.push(c);ns.add(c.id)});P.sel=ns;render();panel()};
A.pRot=()=>{if(!P.sel.size)return;push();sel().forEach(o=>o.r=((o.r||0)+90)%360);render();panel()};
A.pDel=()=>{if(!P.sel.size)return;push();P.objs=P.objs.filter(o=>!P.sel.has(o.id));P.sel.clear();render();panel()};
A.pFill=()=>{const r=sel()[0];if(!r)return;const n=Math.min(30,Math.max(1,+$('#fb_n').value||1));push();P.objs.push(...fillBeds(r,n,(r.l||'R').replace(/\W/g,'')||'R',Math.max(0,+$('#fb_p').value||0),new Set(P.objs.map(o=>o.code))));render();panel();toast(n+' beds added. Drag them to adjust.')};
A.pSave=async()=>{if(!P.objs)return;P.objs.forEach(o=>{if(o.t==='bed')o.code=String(o.code||'').trim()});const c=P.objs.filter(o=>o.t==='bed').map(o=>o.code),dup=c.find((x,i)=>c.indexOf(x)!==i);
 if(c.some(x=>!x))throw new Error('Every bed needs a bed code');if(dup)throw new Error(`Bed code ${dup} is used twice. Bed codes must be unique on a floor.`);
 const r=await api('save_layout',{floor_id:P.fid,layout:{objs:P.objs}}),f=P.floors.find(x=>x.id===P.fid);if(f)f.layout={objs:JSON.parse(JSON.stringify(P.objs))};P.dirty=0;render();
 toast(`Saved. ${r.beds} bed${r.beds===1?'':'s'} published.`);api('hostels').then(h=>{if(S.AD)S.AD.hs=h}).catch(()=>{})};
A.pNF=()=>sheet('Add a floor',S.AD.hs.find(h=>h.id===P.hid)?.name||'',`<div class="g2">${FL('nf_n','Floor name, e.g. First floor')}${FL('nf_l','Level number','number',String(P.floors.length))}</div><button class="btn bp bw" data-act="pMk">${I('plus',16)}Add floor</button>`);
A.pMk=async()=>{if(!val('nf_n'))fail('nf_n','Enter a floor name');if(!guard())return;const r=await api('save_floor',{hostel_id:P.hid,name:val('nf_n'),level:+val('nf_l')||0});closeSheet();await load(P.hid,r.id);toast('Floor added')};
A.pDF=async()=>{if(!P.fid)return;const f=P.floors.find(x=>x.id===P.fid);if(!await confirmUI(`Delete ${f?.name||'this floor'}?`,'Its plan and beds are removed. Floors with bookings or applications cannot be deleted.','Delete floor','danger'))return;await api('del_floor',{id:P.fid});P.dirty=0;await load(P.hid);toast('Floor deleted')};
A.pCode=()=>{if(!P.objs)return toast('Add a floor first',1);sheet('Plan code','Type or paste a whole floor at once',`<p class="fine" style="margin:0 0 10px">One object per line: <b>type [name] x y WxH "label" beds=N price=N r=90</b>. Sizes and positions are in feet. Types: room, corridor, wc, stairs, lift, door, window, bed, balcony, fan, light, rack. Use <b>origin x y</b> to shift everything after it.</p>
 <textarea class="fi mono" id="pc" spellcheck="false" aria-label="Plan code" placeholder='room R1 0 0 14.25x9.5 "Room 1" beds=4 price=6000'>${esc(toCode(P.objs))}</textarea><div id="pe" class="fine" style="color:var(--occ);margin:0 0 10px"></div>
 <div class="ft2"><button class="btn bs" data-act="pRun" data-m="a">Add to plan</button><button class="btn bp" data-act="pRun" data-m="r">Replace plan</button></div>`)};
A.pRun=d=>{const used=new Set(d.m==='a'?P.objs.map(o=>o.code):[]),r=parse($('#pc').value,used);if(r.err.length){$('#pe').innerHTML=r.err.map(esc).join('<br>');return}
 if(d.m==='r'&&P.objs.length&&!confirm('Replace everything on this floor? You can still undo.'))return;
 push();P.objs=d.m==='r'?r.objs:P.objs.concat(r.objs);P.sel=new Set();closeSheet();fit();panel();toast(r.objs.length+' objects placed. Press Save layout when you are happy.')};

/* ---------- admin tab ---------- */
window.PE={
 html:()=>!S.AD.hs.length?`<div class="ph"><h1>Floor plans</h1></div><div class="card empty">Add a hostel first.</div>`:
 `<div class="ph"><h1>Floor plans</h1><p>Draw rooms and beds. Saving publishes the plan and updates the bed inventory; moving a bed never loses its history.</p></div>
 <div class="tbar"><select class="fi sm" id="pH" aria-label="Hostel">${S.AD.hs.map(h=>`<option value="${esc(h.id)}">${esc(h.name)}</option>`).join('')}</select><select class="fi sm" id="pF" aria-label="Floor"></select><button class="btn bs bm" data-act="pNF">${I('plus',15)}Floor</button><button class="btn bd2 bm" data-act="pDF" aria-label="Delete floor" title="Delete floor">${I('trash',15)}</button></div>
 <div class="etool"><div class="row8"><button class="ib sm" data-act="pUndo" aria-label="Undo" title="Undo (Ctrl+Z)">${I('undo',17)}</button><button class="ib sm" data-act="pRedo" aria-label="Redo" title="Redo (Ctrl+Y)">${I('redo',17)}</button><button class="ib sm" data-act="pZo" aria-label="Zoom out" title="Zoom out">${I('zout',17)}</button><button class="ib sm" data-act="pZi" aria-label="Zoom in" title="Zoom in">${I('zin',17)}</button><button class="ib sm" data-act="pFit" aria-label="Fit to screen" title="Fit to screen">${I('fit',17)}</button><button class="btn bs bm" data-act="pCode">${I('code',15)}Plan code</button></div><button class="btn bp bm" data-act="pSave">${I('save',15)}Save layout</button></div>
 <div class="ed"><div class="pal">${PAL.map(p=>`<button class="btn bs bm" data-act="pAdd" data-t="${p[0]}">${I(p[2],16)}${p[1]}</button>`).join('')}</div><div class="card pw ecv" id="cv"></div><div class="card pd panel" id="pn"></div></div>`,
 init:async()=>{if(!S.AD.hs.length||!onTab())return;const h=S.AD.hs.some(x=>x.id===P.hid)?P.hid:S.AD.hs.some(x=>x.id===S.scope)?S.scope:S.AD.hs[0].id;await load(h,h===P.hid?P.fid:null)},
 get dirty(){return!!P.dirty&&onTab()},
 reset(){P.dirty=0}};

document.addEventListener('focusin',e=>{P.snap=e.target.dataset?.pk&&P.sel.size===1?JSON.stringify(P.objs):null});
document.addEventListener('input',e=>{const k=e.target.dataset?.pk;if(!k||P.sel.size!==1)return;const o=byId([...P.sel][0]),v=e.target.value;if(!o)return;
 if(P.snap){P.hist.push(P.snap);P.fut=[];P.snap=null}
 o[k]=['l','code'].includes(k)?v:['x','y','w','h'].includes(k)?num(+v||0):+v||0;if(k==='w'||k==='h')o[k]=Math.max(5,o[k]);if(k==='price')o[k]=Math.max(0,o[k]);P.dirty=1;render()});
document.addEventListener('change',async e=>{try{
 if(e.target.id==='pH'){if(!guard()){e.target.value=P.hid;return}await load(e.target.value)}
 if(e.target.id==='pF'){if(!guard()){e.target.value=P.fid;return}P.fid=e.target.value;floor()}}catch(x){toast(x.message,1)}});
addEventListener('beforeunload',e=>{if(PE.dirty){e.preventDefault();e.returnValue=''}});
addEventListener('keydown',e=>{if(!onTab()||!P.objs||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||$('#ov').classList.contains('on'))return;const k=e.key.toLowerCase(),m=e.ctrlKey||e.metaKey;
 if(m&&k==='z'){e.preventDefault();e.shiftKey?redo():undo()}else if(m&&k==='y'){e.preventDefault();redo()}else if(m&&k==='d'){e.preventDefault();A.pDup()}
 else if(m&&k==='a'){e.preventDefault();P.sel=new Set(P.objs.map(o=>o.id));render();panel()}else if((k==='delete'||k==='backspace')&&P.sel.size){e.preventDefault();A.pDel()}
 else if(k==='r'&&!m&&P.sel.size)A.pRot();else if(k.startsWith('arrow')&&P.sel.size){e.preventDefault();push();const s=e.shiftKey?50:5,[dx,dy]={arrowleft:[-s,0],arrowright:[s,0],arrowup:[0,-s],arrowdown:[0,s]}[k];sel().forEach(o=>{o.x+=dx;o.y+=dy});render();panel()}},true);
})();
