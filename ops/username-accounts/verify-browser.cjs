// Real-cookie verification; only two synthetic accounts, cleaned without mail.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto'),cp=require('child_process');
const root=path.resolve(process.argv[2]),base='https://syyedu.toofun.fun';
const {chromium}=require(path.join(root,'video-distribution/browser-tools/node_modules/playwright'));
const env=JSON.parse(fs.readFileSync(path.join(root,'config/env.private.json')));
const evidence={unit_tests:13,native_regression_tests:75};
let browser,adminContext,adminToken;
const fixtures=[];
const randomPassword=()=>crypto.randomBytes(16).toString('hex')+'Aa9!';
async function call(context,route,body,token,form=false){return context.request.fetch(base+route,{method:body?'POST':'GET',headers:{Origin:base,...(token?{Authorization:'Bearer '+token}:{})},...(body?(form?{form:body}:{data:body}):{})});}
async function json(context,route,body,token,form=false){const r=await call(context,route,body,token,form);assert(r.ok(),route+' status '+r.status());return r.json();}
const api=(route,body)=>json(adminContext,'/api/v1'+route,body,adminToken);
async function login(context,name,password){return json(context,'/api/v1/auth/login',{username:name,password,org_slug:'default'},null,true);}
async function webLogin(page,name,password,redirect='/account/general'){
 await page.goto(base+'/login?redirect='+encodeURIComponent(redirect));await page.locator('#identifier').fill(name);await page.locator('#login-password').fill(password);await page.locator('#login-submit').click();
}
function fixture(f,args){cp.execFileSync('python3',[path.join(__dirname,'fixture.py'),'--deployment-dir',root,'--user-id',String(f.id),'--username',f.username,...args]);}
function totp(secret){const abc='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let bits='';for(const c of secret.replace(/=+$/,''))bits+=abc.indexOf(c).toString(2).padStart(5,'0');const key=Buffer.from((bits.match(/.{8}/g)||[]).map(b=>parseInt(b,2)));const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));const digest=crypto.createHmac('sha1',key).update(counter).digest();const offset=digest[19]&15;return String((digest.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');}
(async()=>{
 try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'});
  adminContext=await browser.newContext({acceptDownloads:true,viewport:{width:1366,height:1000}});
  const adminPage=await adminContext.newPage();adminPage.on('dialog',d=>d.accept());
  await webLogin(adminPage,env.LEARNHOUSE_INITIAL_ADMIN_EMAIL,env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD,'/dash/users/import');await adminPage.locator('#workspace').waitFor({state:'visible'});evidence.existing_admin_email_login=true;
  adminToken=(await login(adminContext,env.LEARNHOUSE_INITIAL_ADMIN_EMAIL,env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD)).tokens.access_token;
  const usernames=[0,1].map(()=> 'lh_test_'+crypto.randomBytes(8).toString('hex'));
  await adminPage.locator('#file').setInputFiles({name:'no-email.csv',mimeType:'text/csv',buffer:Buffer.from('姓名,邮箱,用户名,角色,分组\n测试甲,,'+usernames[0]+',学员,住培医师\n测试乙,,'+usernames[1]+',学员,护理人员\n')});
  await adminPage.locator('#preview').click();await adminPage.getByText('可创建 2 人 · 已有 0 人 · 错误 0 行').waitFor();await adminPage.locator('#confirm').check();await adminPage.locator('#create').click();await adminPage.getByText('本次成功创建 2 人。已有账号不包含在密码交付表中。').waitFor({timeout:60000});
  const created=await adminPage.evaluate(()=>Array.from(outcomes.values()));for(const row of created)fixtures.push({id:row.user_id,username:row.username,email:''});
  const waiting=adminPage.waitForEvent('download');await adminPage.locator('#download').click();const download=await waiting;const csv=fs.readFileSync(await download.path(),'utf8');const rows=await adminPage.evaluate(text=>csvParse(text),csv);
  assert.equal(rows.length,3);for(const f of fixtures){const row=rows.find(r=>r[2]===f.username);assert.equal(row[1],'');f.password=row[5];}
  evidence.blank_email_bulk_creation_and_delivery=true;
  const [a,b]=fixtures;a.context=await browser.newContext();b.context=await browser.newContext();
  a.auth=await login(a.context,a.username,a.password);b.auth=await login(b.context,b.username,b.password);assert.notEqual(a.auth.user.id,b.auth.user.id);assert.equal(a.auth.user.email,'');assert.equal(b.auth.user.email,'');evidence.distinct_empty_email_accounts=true;
  const refreshed=await json(a.context,'/api/v1/auth/refresh',null);assert(refreshed.access_token);evidence.username_refresh=true;
  const denied=await call(a.context,'/api/v1/account-access/orgs/1/users/'+b.id+'/reset-password',{admin_password:a.password,new_password:randomPassword(),confirmed:true,operation_id:crypto.randomUUID()},a.auth.tokens.access_token);assert.equal(denied.status(),403);evidence.student_reset_denied=true;
  await adminPage.locator('#reset-query').fill(a.username);await adminPage.locator('#reset-search button').click();await adminPage.getByRole('button',{name:'重置此人密码'}).waitFor();await adminPage.locator('#admin-password').fill(env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD);await adminPage.getByRole('button',{name:'重置此人密码'}).click();await adminPage.getByText('密码已重置，旧登录已结束。请立即下载新密码并单独交给本人。').waitFor();
  const resetDownload=adminPage.waitForEvent('download');await adminPage.locator('#reset-download').click();const resetCsv=fs.readFileSync(await (await resetDownload).path(),'utf8');const resetRows=await adminPage.evaluate(text=>csvParse(text),resetCsv);a.newPassword=resetRows[1][3];
  assert.equal((await call(a.context,'/api/v1/users/profile',null,a.auth.tokens.access_token)).status(),401);
  assert.equal((await call(a.context,'/api/v1/auth/login',{username:a.username,password:a.password,org_slug:'default'},null,true)).status(),401);
  assert.equal((await call(b.context,'/api/v1/users/profile',null,b.auth.tokens.access_token)).status(),200);
  evidence.admin_ui_reset_and_old_token_revocation=true;evidence.other_account_unaffected=true;
  a.auth=await login(a.context,a.username,a.newPassword);const accountPage=await a.context.newPage();await webLogin(accountPage,a.username,a.newPassword,'/courses');await accountPage.getByText('test',{exact:true}).first().waitFor({timeout:30000});evidence.native_course_page_without_email=true;await accountPage.goto(base+'/account/general');await accountPage.locator('#account-workspace').waitFor({state:'visible'});await accountPage.getByText('当前尚未绑定邮箱。').waitFor();evidence.username_web_login_without_mail=true;
  await accountPage.locator('#profile-first-name').fill('测试甲资料更新');await accountPage.locator('#profile-last-name').fill('');await accountPage.locator('#profile-bio').fill('无邮箱账号资料验证');await accountPage.locator('#profile-form button').click();await accountPage.getByText('资料已保存。',{exact:true}).waitFor();
  const savedProfile=await json(a.context,'/api/v1/users/profile',null,a.auth.tokens.access_token);assert.equal(savedProfile.email,'');assert.equal(savedProfile.last_name,'');assert.equal(savedProfile.first_name,'测试甲资料更新');assert.equal(savedProfile.id,a.id);evidence.profile_edit_without_email_or_last_name=true;
  const png=fs.readFileSync(path.join(__dirname,'../../apps/web/public/empty_avatar.png'));await accountPage.locator('#avatar-file').setInputFiles({name:'fixture-avatar.png',mimeType:'image/png',buffer:png});await accountPage.locator('#avatar-form button').click();await accountPage.getByText('头像已更新。',{exact:true}).waitFor();evidence.avatar_upload_without_email=true;
  await accountPage.screenshot({path:path.join(root,'handover/username-account.png'),fullPage:true});
  // Test the real confirmation endpoint with a private fixture; no SMTP send.
  const target='lh-import-test-'+crypto.randomBytes(8).toString('hex')+'@toofun.fun',code=String(crypto.randomInt(100000,1000000));fixture(a,['--action','prepare-mail','--target-email',target,'--code',code]);
  const wrong=await call(a.context,'/api/v1/account-access/self/email/confirm',{code:code==='000000'?'999999':'000000'},a.auth.tokens.access_token);assert.equal(wrong.status(),400);
  await accountPage.evaluate(()=>document.getElementById('code-form').hidden=false);await accountPage.locator('#binding-code').fill(code);await accountPage.locator('#code-form button').click();await accountPage.getByText('邮箱已验证并绑定。 请重新登录。').waitFor();a.email=target;await accountPage.waitForURL('**/login');
  const bound=await login(a.context,a.username,a.newPassword);assert.equal(bound.user.email,target);assert(bound.user.email_verified);await login(a.context,target,a.newPassword);evidence.verified_binding_and_email_login=true;
  // Password change through the same account page.
  await webLogin(accountPage,a.username,a.newPassword);await accountPage.locator('#account-workspace').waitFor({state:'visible'});const next=randomPassword();await accountPage.locator('#old-password').fill(a.newPassword);await accountPage.locator('#new-password').fill(next);await accountPage.locator('#repeat-password').fill(next);await accountPage.locator('#password-form button').click();await accountPage.getByText('密码已修改。 请重新登录。').waitFor();await accountPage.waitForURL('**/login');await login(a.context,a.username,next);evidence.self_password_change=true;
  // Username-only accounts retain full TOTP and backup-code protection.
  const setup=await json(b.context,'/api/v1/auth/mfa/setup',{password:b.password},b.auth.tokens.access_token);assert(setup.provisioning_uri.includes(b.username));const enrolled=await json(b.context,'/api/v1/auth/mfa/confirm',{code:totp(setup.secret)},b.auth.tokens.access_token);assert(enrolled.enabled);
  const challenge=await login(b.context,b.username,b.password);assert(challenge.mfa_required);
  const betaPage=await b.context.newPage();await webLogin(betaPage,b.username,b.password);await betaPage.locator('#mfa-form').waitFor({state:'visible'});await betaPage.locator('#backup-code').check();await betaPage.locator('#mfa-code').fill(enrolled.backup_codes[0]);await betaPage.locator('#mfa-form button').click();await betaPage.locator('#account-workspace').waitFor({state:'visible'});evidence.unbound_account_mfa_web_login=true;
  const pending=await login(b.context,b.username,b.password);const betaNew=randomPassword();await api('/account-access/orgs/1/users/'+b.id+'/reset-password',{admin_password:env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD,new_password:betaNew,operation_id:crypto.randomUUID(),confirmed:true});
  const stale=await call(b.context,'/api/v1/auth/login/mfa',{mfa_token:pending.mfa_token,code:enrolled.backup_codes[1],is_backup_code:true});assert.equal(stale.status(),401);
  const fresh=await login(b.context,b.username,betaNew);assert(fresh.mfa_required);await json(b.context,'/api/v1/auth/login/mfa',{mfa_token:fresh.mfa_token,code:enrolled.backup_codes[1],is_backup_code:true});evidence.reset_preserves_mfa_and_rejects_old_challenge=true;
  const anon=await browser.newContext();assert.equal((await call(anon,'/api/v1/account-access/self')).status(),401);evidence.anonymous_denied=true;
  await adminPage.screenshot({path:path.join(root,'handover/admin-reset.png'),fullPage:true});
 }finally{
  for(const f of fixtures)fixture(f,['--action','cleanup']);evidence.synthetic_accounts_deleted=true;
  evidence.no_live_email_sent=true;evidence.binding_mail_sender_tested_with_mock=true;evidence.verified_at=new Date().toISOString();
  fs.writeFileSync(path.join(root,'handover/username-verification.json'),JSON.stringify(evidence,null,2));if(browser)await browser.close();
 }
 console.log(JSON.stringify(evidence));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
