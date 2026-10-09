// Actual embedded UI handlers, deferred synthetic replies; no browser/network.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../photopicker/webui.py'), 'utf8');
function extract(name) {
  const marker = new RegExp('(?:async )?function '+name+'\\(');
  const at = source.search(marker);
  return at < 0 ? '' : source.slice(at, source.indexOf('\n}', at)+2);
}
function fixture() {
  const nodes=new Map(), pending=[], notices=[];
  function $(id) {
    if(!nodes.has(id)) {const classes=new Set(); nodes.set(id,{value:'synthetic/output', checked:false,style:{},textContent:'',classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x)},querySelector:()=>null});}
    return nodes.get(id);
  }
  const session=()=>({source_folder:'synthetic',candidates:[{idx:0,decision:''},{idx:1,decision:''}],counts:{}});
  const state={session:session(),focus:0,swapping:false,mutating:false,needsSync:false,epoch:0};
  const sandbox={state,$,toast:x=>notices.push(x),renderLeds(){},updateFilterCounts(){},renderGrid(){},updatePos(){},scrollFocusIntoView(){},openFocus(){},renderSimilar(){},
    advanceToUndecided(){state.focus++},
    postJSON:(path,body)=>new Promise((resolve,reject)=>pending.push({path,body,resolve,reject})),
    fetchState:async()=>session()};
  vm.createContext(sandbox);
  vm.runInContext(['applySession','reconcileSession','runMutation','decide','undo','swapFrame','runExport'].map(extract).join('\n'),sandbox);
  return {sandbox,state,pending,notices,$,session};
}
test('pending decision blocks undo, swap, export and second decision',async()=>{
 const f=fixture(), job=f.sandbox.decide('keep');
 const others=[f.sandbox.undo(),f.sandbox.swapFrame(0,0),f.sandbox.runExport(),f.sandbox.decide('reject')];
 const count=f.pending.length;
 for(const p of f.pending) p.resolve({ok:true,json:{state:f.session(),exported:0,target:'synthetic'}});
 await Promise.all([job,...others]); assert.equal(count,1);
});
test('decision completion preserves focus moved while request pending',async()=>{
 const f=fixture(),job=f.sandbox.decide('keep'); f.state.focus=1;
 f.pending[0].resolve({ok:true,json:{state:f.session()}}); await job;
 assert.equal(f.state.focus,1);
});
test('uncertain decision reconciles without replay',async()=>{
 const f=fixture(); let reads=0; f.sandbox.fetchState=async()=>{reads++; return f.session()};
 const job=f.sandbox.decide('keep'); f.pending[0].reject(new Error('connection lost')); await job;
 assert.equal(reads,1); assert.equal(f.pending.length,1); assert.equal(f.state.mutating,false);
 assert.ok(f.notices.some(x=>/review/i.test(x)));
});
test('failed reconciliation blocks next write and only refreshes',async()=>{
 const f=fixture(); f.sandbox.fetchState=async()=>{throw Error('offline')};
 const job=f.sandbox.undo(); f.pending[0].reject(Error('offline')); await job;
 await f.sandbox.decide('keep'); assert.equal(f.pending.length,1); assert.equal(f.state.needsSync,true);
 f.sandbox.fetchState=async()=>f.session(); await f.sandbox.decide('keep');
 assert.equal(f.pending.length,1); assert.equal(f.state.needsSync,false);
});
test('export renders successful copies alongside missing manifest and file failures',async()=>{
 const f=fixture(),job=f.sandbox.runExport();
 f.pending[0].resolve({ok:true,json:{exported:1,requested:2,target:'synthetic/output',complete:false,failures:[{file:'bad.jpg',stage:'copy',error:'unreadable'}],manifest_error:'disk full'}}); await job;
 assert.match(f.$('export-result').textContent,/bad.jpg/); assert.match(f.$('export-result').textContent,/disk full/);
 assert.match(f.$('export-result').textContent,/1/); assert.ok(f.$('export-result').classList.contains('err'));
});
test('export rejection reports uncertain output without replay',async()=>{
 const f=fixture(),job=f.sandbox.runExport(); f.pending[0].reject(Error('offline')); await job;
 assert.match(f.$('export-result').textContent,/unconfirmed/i); assert.equal(f.pending.length,1); assert.equal(f.state.mutating,false);
});
