'use strict';
const el=id=>document.getElementById(id);
function status(text,error=false){el('status').textContent=text;el('status').className=error?'error':'success';}
async function request(path,body,form=false){
 const res=await fetch(path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':form?'application/x-www-form-urlencoded':'application/json'}:{},body:body?(form?new URLSearchParams(body):JSON.stringify(body)):undefined});
 let data;try{data=await res.json();}catch{throw new Error('服务暂不可用，请稍后重试');}
 if(!res.ok){const detail=data.detail;let message=typeof detail==='string'?detail:detail?.message||'操作失败，请检查后重试';if(detail?.code==='EMAIL_NOT_VERIFIED')message='邮箱尚未验证，请使用注册邮件中的链接完成验证。';const error=new Error(message);error.status=res.status;throw error;}return data;
}
async function submit(form,action){const buttons=Array.from(form.querySelectorAll('button'));buttons.forEach(b=>b.disabled=true);try{await action();}catch(e){status(e.message,true);}finally{buttons.forEach(b=>b.disabled=false);}}
function destination(){const query=new URLSearchParams(location.search);const raw=query.get('redirect')||query.get('callbackUrl')||'/';try{const url=new URL(raw,location.origin);return url.origin===location.origin?url.pathname+url.search+url.hash:'/';}catch{return '/';}}
async function signOut(message){status(message+' 请重新登录。');try{await request('/api/auth/logout',{});}catch{}setTimeout(()=>location.assign('/login'),1200);}
if(document.body.dataset.page==='login'){
 let mfaToken;
 el('login-form').addEventListener('submit',event=>{event.preventDefault();submit(event.target,async()=>{status('正在登录…');const result=await request('/api/auth/login',{username:el('identifier').value.trim(),password:el('login-password').value,org_slug:'default'},true);el('login-password').value='';if(result.mfa_required){mfaToken=result.mfa_token;el('login-form').hidden=true;el('mfa-form').hidden=false;el('mfa-code').focus();status('请输入双重验证代码。');return;}location.assign(destination());});});
 el('mfa-form').addEventListener('submit',event=>{event.preventDefault();submit(event.target,async()=>{await request('/api/auth/login/mfa',{mfa_token:mfaToken,code:el('mfa-code').value.trim(),is_backup_code:el('backup-code').checked});location.assign(destination());});});
}else{
 (async()=>{try{const profile=await request('/api/v1/account-access/self');el('identity').textContent=profile.name.trim()||profile.username;el('handle').textContent='@'+profile.username;document.querySelectorAll('[data-current-name]').forEach(e=>e.textContent=profile.name.trim()||profile.username);el('current-email').textContent=profile.email?'当前邮箱：'+profile.email+(profile.email_verified?'（已验证）':'（未验证）'):'当前尚未绑定邮箱。';el('account-workspace').hidden=false;}catch(e){if(e.status===401){location.replace('/login?redirect=%2Faccount%2Fgeneral');}else status(e.message,true);}})();
 el('password-form').addEventListener('submit',event=>{event.preventDefault();submit(event.target,async()=>{if(el('new-password').value!==el('repeat-password').value)throw new Error('两次输入的新密码不一致');await request('/api/v1/account-access/self/password',{current_password:el('old-password').value,new_password:el('new-password').value});event.target.reset();await signOut('密码已修改。');});});
 el('email-form').addEventListener('submit',event=>{event.preventDefault();submit(event.target,async()=>{await request('/api/v1/account-access/self/email/request',{email:el('binding-email').value.trim(),current_password:el('binding-password').value});el('binding-password').value='';el('code-form').hidden=false;el('binding-code').focus();status('验证码已发送至填写的邮箱，10 分钟内有效。');});});
 el('code-form').addEventListener('submit',event=>{event.preventDefault();submit(event.target,async()=>{await request('/api/v1/account-access/self/email/confirm',{code:el('binding-code').value.trim()});event.target.reset();await signOut('邮箱已验证并绑定。');});});
}
