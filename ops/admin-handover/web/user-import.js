'use strict';
// No credentials or passwords are persisted in browser storage.
const $ = id => document.getElementById(id);
let orgId, sourceRows = [], checkedRows = [], busy = false, importId;
const passwords = new Map(), outcomes = new Map();
const statusText = {ready:'可创建',existing:'已有账号，跳过',error:'错误',created:'已创建',recovered:'已创建，重试确认'};
function message(text, error=false){ $('status').textContent=text; $('status').className=error?'error':'success'; }
async function api(path, body){
 const response=await fetch('/api/v1'+path,{credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json'}:{},method:body?'POST':'GET',body:body?JSON.stringify(body):undefined});
 let data; try{data=await response.json();}catch{throw new Error('服务暂不可用，请稍后重试');}
 if(!response.ok){const detail=typeof data.detail==='string'?data.detail:('请求失败（'+response.status+'）');const error=new Error(detail);error.status=response.status;throw error;}
 return data;
}
function csvParse(text){
 text=text.replace(/^\uFEFF/,'');
 const rows=[];let row=[],value='',quoted=false,closed=false;
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(quoted){if(c==='"'){if(text[i+1]==='"'){value+='"';i++;}else{quoted=false;closed=true;}}else value+=c;continue;}
  if(c==='"'){if(value||closed)throw new Error('CSV 引号格式错误');quoted=true;continue;}
  if(c===','||c==='\n'||c==='\r'){row.push(value);value='';closed=false;if(c!==','){if(c==='\r'&&text[i+1]==='\n')i++;if(row.some(v=>v.trim()))rows.push(row);row=[];}continue;}
  if(closed&&c!==' '&&c!=='\t')throw new Error('CSV 引号后有多余字符');
  if(!closed)value+=c;
 }
 if(quoted)throw new Error('CSV 存在未闭合的引号');
 row.push(value);if(row.some(v=>v.trim()))rows.push(row);
 return rows;
}
function parsePeople(text){
 const matrix=csvParse(text);if(matrix.length<2)throw new Error('表格没有人员数据');
 const aliases={姓名:'name',name:'name',邮箱:'email',email:'email',用户名:'username',username:'username',角色:'role',role:'role',分组:'groups',groups:'groups'};
 const headers=matrix[0].map(v=>aliases[v.trim().toLowerCase()]);
 for(const required of ['name','email'])if(!headers.includes(required))throw new Error('缺少“姓名”或“邮箱”表头');
 if(new Set(headers.filter(Boolean)).size!==headers.filter(Boolean).length)throw new Error('表头重复');
 if(matrix.length-1>500)throw new Error('每次最多导入 500 人，请拆分文件');
 return matrix.slice(1).map((cells,index)=>{
  if(cells.length>headers.length)throw new Error('第 '+(index+2)+' 行列数超过表头，请检查逗号或引号');
  const item={name:'',email:'',username:'',role:'学员',groups:[]};
  headers.forEach((key,i)=>{if(!key)return;const value=(cells[i]||'').trim();item[key]=key==='groups'?value.split(/[;；]/).map(v=>v.trim()).filter(Boolean):(key==='role'&&!value?'学员':value);});
  return item;
 });
}
function safeCell(value){let s=String(value??'');if(/^[\s]*[=+\-@]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
function downloadCsv(name, rows){
 const blob=new Blob(['\uFEFF'+rows.map(row=>row.map(safeCell).join(',')).join('\r\n')+'\r\n'],{type:'text/csv;charset=utf-8'});
 const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function randomPassword(){
 const alphabet='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
 let result='Aa9!';
 while(result.length<24){const bytes=crypto.getRandomValues(new Uint8Array(32));for(const b of bytes)if(b<Math.floor(256/alphabet.length)*alphabet.length&&result.length<24)result+=alphabet[b%alphabet.length];}
 return result;
}
function renderRows(rows){
 $('rows').replaceChildren();
 rows.forEach(r=>{const tr=document.createElement('tr');for(const value of [r.row+1,r.name,r.email,r.username,r.role,r.groups.join('；'),r.errors.length?r.errors.join('；'):statusText[r.status]]){const td=document.createElement('td');td.textContent=value;tr.append(td);}if(r.status==='error')tr.className='error';$('rows').append(tr);});
}
function updateCreate(){ $('create').disabled=busy||!$('confirm').checked||!checkedRows.some(r=>r.status==='ready')||checkedRows.some(r=>r.status==='error'); }
function setBusy(value){busy=value;$('file').disabled=value;$('preview').disabled=value||!sourceRows.length;$('retry').disabled=value;updateCreate();}
$('template').addEventListener('click',()=>downloadCsv('ICU账号导入模板.csv',[['姓名','邮箱','用户名','角色','分组']]));
$('file').addEventListener('change',async()=>{
 if(passwords.size&&!confirm('重新选择文件会清除当前页面的初始密码。请先下载交付表。是否继续？')){$('file').value='';return;}
 sourceRows=[];checkedRows=[];passwords.clear();outcomes.clear();importId=crypto.randomUUID();$('review').hidden=true;$('delivery').hidden=true;$('preview').disabled=true;$('confirm').checked=false;
 const file=$('file').files[0];if(!file)return;
 try{if(file.size>2*1024*1024)throw new Error('文件过大，请限制在 2MB 内');if(!/\.csv$/i.test(file.name))throw new Error('请先把 Excel 表格另存为 CSV UTF-8');sourceRows=parsePeople(new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer()));$('filename').textContent=file.name+' · '+sourceRows.length+' 人';$('preview').disabled=false;message('文件已读取，请检查并预览。');}catch(e){message(e instanceof TypeError?'文件编码无法读取，请另存为 CSV UTF-8。':e.message,true);}
});
$('preview').addEventListener('click',async()=>{setBusy(true);try{const data=await api('/orgs/'+orgId+'/users/import/preview',{rows:sourceRows});checkedRows=data.rows;renderRows(checkedRows);$('counts').textContent='可创建 '+data.ready+' 人 · 已有 '+data.existing+' 人 · 错误 '+data.errors+' 行';$('review').hidden=false;message(data.errors?'请修正错误后重新上传。':'检查完成，请核对后确认创建。',data.errors>0);}catch(e){message(e.message,true);}finally{setBusy(false);}});
$('confirm').addEventListener('change',updateCreate);
async function execute(){
 setBusy(true);$('delivery').hidden=false;$('retry').hidden=true;
 const pending=checkedRows.filter(r=>r.status==='ready'&&!['created','recovered','existing'].includes(outcomes.get(r.email)?.status));
 for(const r of pending)if(!passwords.has(r.email))passwords.set(r.email,randomPassword());
 try{
  for(let i=0;i<pending.length;i+=25){
   message('正在创建 '+Math.min(i+25,pending.length)+' / '+pending.length+'，请保持页面打开…');
   const chunk=pending.slice(i,i+25).map(r=>({name:r.name,email:r.email,username:r.username,role:r.role,groups:r.groups,password:passwords.get(r.email)}));
   const data=await api('/orgs/'+orgId+'/users/import/create',{import_id:importId,confirmed:true,rows:chunk});
   for(const result of data.rows)outcomes.set(result.email,result);
   if(data.rows.some(r=>r.status==='error'))throw new Error('部分账号未创建，请查看结果。已完成的账号可立即下载。');
  }
  message('导入完成，请立即下载账号与初始密码交付表。');
 }catch(e){message(e.message+' 如网络中断，可在当前页面重试；已创建账号不会重置密码。',true);$('retry').hidden=false;}
 finally{
  const final=checkedRows.map(r=>outcomes.has(r.email)?{...outcomes.get(r.email),row:r.row}:r);renderRows(final);
  const completed=Array.from(outcomes.values()).filter(r=>['created','recovered'].includes(r.status));
  $('result').textContent='本次成功创建 '+completed.length+' 人。已有账号不包含在密码交付表中。';$('download').disabled=!completed.length;setBusy(false);$('create').disabled=true;
 }
}
$('create').addEventListener('click',execute);$('retry').addEventListener('click',execute);
$('download').addEventListener('click',()=>{const rows=Array.from(outcomes.values()).filter(r=>['created','recovered'].includes(r.status));downloadCsv('ICU账号交付-'+new Date().toISOString().slice(0,10)+'.csv',[['姓名','邮箱','用户名','角色','分组','初始密码'],...rows.map(r=>[r.name,r.email,r.username,r.role,r.groups.join(';'),passwords.get(r.email)])]);});
window.addEventListener('beforeunload',event=>{if(passwords.size){event.preventDefault();event.returnValue='';}});
(async()=>{try{const org=await api('/orgs/slug/default');orgId=org.id;const meta=await api('/orgs/'+orgId+'/users/import/meta');$('groups').textContent=meta.groups.join('、');$('access').hidden=true;$('workspace').hidden=false;}catch(e){$('access').textContent=e.status===401?'请先登录管理员账号。':e.message;if(e.status===401){const a=document.createElement('a');a.href='/login?callbackUrl=%2Fdash%2Fusers%2Fimport';a.textContent=' 前往登录';$('access').append(a);}}})();
