// Live verification creates one synthetic account and deletes it in finally.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(process.argv[2]);
const {chromium}=require(path.join(root,'video-distribution/browser-tools/node_modules/playwright'));
const env=JSON.parse(fs.readFileSync(path.join(root,'config/env.private.json')));
const seed=JSON.parse(fs.readFileSync(path.join(root,'handover/seed-state.json')));
const base='https://syyedu.toofun.fun';
const coursesOnly=process.argv.includes("--courses-only");
const evidence=coursesOnly?JSON.parse(fs.readFileSync(path.join(root,"handover/browser-verification.json"))):{};let browser,context,adminToken,userId;
const suffix=require('crypto').randomUUID().replaceAll('-','').slice(0,16);
const email='lh-import-test-'+suffix+'@toofun.fun';
async function adminApi(route,body,method){
 const res=await context.request.fetch(base+'/api/v1'+route,{method:method||(body?'POST':'GET'),headers:{Authorization:'Bearer '+adminToken,Origin:base},...(body?{data:body}:{})});
 assert(res.ok(),'Admin API '+route+' returned '+res.status());return res.json();
}
(async()=>{
 try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'});
  context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  const page=await context.newPage();page.on('dialog',dialog=>dialog.accept());
  await page.goto(base+'/dash/users/import');
  await page.getByText('请先登录管理员账号。').waitFor();evidence.anonymous_denied=true;
  const login=await context.request.post(base+'/api/auth/login',{headers:{Origin:base},form:{username:env.LEARNHOUSE_INITIAL_ADMIN_EMAIL,password:env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD,org_slug:'default'}});
  assert(login.ok(),'Administrator browser login failed');
  const bearer=await context.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},form:{username:env.LEARNHOUSE_INITIAL_ADMIN_EMAIL,password:env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD,org_slug:'default'}});
  adminToken=(await bearer.json()).tokens.access_token;
  await page.goto(base+'/dash/users/import');await page.locator('#workspace').waitFor({state:'visible'});
  if(!coursesOnly){
  evidence.csv_parser=await page.evaluate(()=>{
   const rows=csvParse('\uFEFF姓名,邮箱\r\n"医生,甲","a@example.com"\r\n"多\n行","b@example.com"');
   return rows.length===3&&rows[1][0]==='医生,甲'&&rows[2][0]==='多\n行'&&safeCell('=1+1')==='"\'=1+1"';
  });assert(evidence.csv_parser);
  await page.locator('#file').setInputFiles({name:'temporary-staff.csv',mimeType:'text/csv',buffer:Buffer.from('\uFEFF姓名,邮箱,用户名,角色,分组\r\n导入测试,'+email+',testimport_'+suffix+',学员,住培医师\r\n')});
  await page.locator('#preview').click();await page.getByText('可创建 1 人 · 已有 0 人 · 错误 0 行').waitFor();
  await page.screenshot({path:path.join(root,'handover/import-preview.png'),fullPage:true});
  await page.locator('#confirm').check();await page.locator('#create').click();
  await page.getByText('本次成功创建 1 人。已有账号不包含在密码交付表中。').waitFor({timeout:60000});
  const current=await page.evaluate(()=>({importId,rows:Array.from(outcomes.values())}));userId=current.rows[0].user_id;
  const waiting=page.waitForEvent('download');await page.locator('#download').click();
  const download=await waiting;const csv=fs.readFileSync(await download.path(),'utf8');
  const delivery=await page.evaluate(text=>csvParse(text),csv);
  assert.equal(delivery.length,2);assert.equal(delivery[1][1],email);const password=delivery[1][5];assert(password.length>=24);evidence.download_passwords=true;
  const auth=await context.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},form:{username:email,password,org_slug:'default'}});
  assert(auth.ok(),'Imported account login failed');const studentToken=(await auth.json()).tokens.access_token;
  const profile=await context.request.get(base+'/api/v1/users/profile',{headers:{Authorization:'Bearer '+studentToken}});
  assert(profile.ok(),'Imported account token failed');assert.equal((await profile.json()).email,email);evidence.import_login=true;
  const groupUsers=await adminApi('/usergroups/'+seed.groups['住培医师'].id+'/users');assert(groupUsers.some(u=>u.id===userId));evidence.group_assignment=true;
  for(const route of ['/orgs/1/users/import/meta','/orgs/999999/users/import/meta']){
   const res=await context.request.get(base+'/api/v1'+route,{headers:{Authorization:'Bearer '+studentToken}});assert.equal(res.status(),403);
  }evidence.student_and_cross_org_denied=true;
  const row={name:'导入测试',email,username:'testimport_'+suffix,role:'学员',groups:['住培医师'],password};
  const retry=await adminApi('/orgs/1/users/import/create',{import_id:current.importId,confirmed:true,rows:[row]});assert.equal(retry.rows[0].status,'recovered');
  assert(!JSON.stringify(retry).includes(password));evidence.retry_idempotent=true;
  const duplicate=await adminApi('/orgs/1/users/import/create',{import_id:require('crypto').randomUUID(),confirmed:true,rows:[{...row,password:'OtherPassword77!'}]});assert.equal(duplicate.rows[0].status,'existing');evidence.existing_password_preserved=true;
  const invalid=await adminApi('/orgs/1/users/import/preview',{rows:[{name:'bad',email:'invalid',role:'管理员'},{name:'A',email:'duplicate@example.com'},{name:'B',email:'duplicate@example.com'}]});assert.equal(invalid.errors,2);evidence.invalid_roles_and_duplicates=true;
  const csrf=await context.request.post(base+'/api/v1/orgs/1/users/import/preview',{headers:{Authorization:'Bearer '+adminToken,Origin:'https://other.example'},data:{rows:[row]}});assert.equal(csrf.status(),403);evidence.cross_origin_denied=true;
  const malformed=await context.request.post(base+'/api/v1/orgs/1/users/import/create',{headers:{Authorization:'Bearer '+adminToken,Origin:base},data:{rows:[],import_id:'invalid',password}});assert.equal(malformed.status(),422);assert(!(await malformed.text()).includes(password));evidence.password_not_echoed=true;
  }
  const drafts=await adminApi('/courses/org_slug/default/page/1/limit/100?include_unpublished=true');
  evidence.draft_courses=Object.values(seed.courses).length;
  for(const saved of Object.values(seed.courses)){const live=drafts.find(c=>c.course_uuid===saved.course.course_uuid);assert(live&&!live.published&&!live.public);}
  const sample=Object.values(seed.courses)[0],activity=Object.values(sample.activities)[0];
  const hidden=await (await browser.newContext()).request.get(base+'/api/v1/courses/'+sample.course.course_uuid);assert([401,403,404].includes(hidden.status()));evidence.drafts_private=true;
  const courseContext=await browser.newContext({viewport:{width:1440,height:1000}});
  const courseLogin=await courseContext.request.post(base+'/api/auth/login',{headers:{Origin:base},form:{username:env.LEARNHOUSE_INITIAL_ADMIN_EMAIL,password:env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD,org_slug:'default'}});assert(courseLogin.ok());
  const coursePage=await courseContext.newPage();
  await coursePage.goto(base+'/course/'+sample.course.course_uuid.replace('course_','')+'/activity/'+activity.activity_uuid.replace('activity_','')+'/edit');
  await coursePage.waitForFunction(()=>document.body.innerText.includes('本平台用于科室教学与培训。请按分配的课程和培训安排完成学习。'),{timeout:30000});
  await coursePage.waitForFunction(()=>{let element=document.querySelector('.ProseMirror');if(!element)return false;while(element&&element!==document.body){const style=getComputedStyle(element);if(Number(style.opacity)<0.99||style.display==='none'||style.visibility==='hidden')return false;element=element.parentElement;}return true;});
  await coursePage.screenshot({path:path.join(root,'handover/course-draft.png'),fullPage:true});evidence.draft_page_rendered=true;
  await coursePage.setViewportSize({width:390,height:844});await coursePage.goto(base+'/dash/users/import');await coursePage.locator('#workspace').waitFor({state:'visible'});await coursePage.screenshot({path:path.join(root,'handover/import-mobile.png'),fullPage:true});evidence.mobile_import_rendered=true;
 }finally{
  if(userId){require('child_process').execFileSync('python3',[path.join(__dirname,'cleanup-test-user.py'),'--deployment-dir',root,'--user-id',String(userId),'--email',email]);evidence.test_account_deleted=true;evidence.test_cleanup_without_email=true;}
  evidence.verified_at=new Date().toISOString();
  fs.writeFileSync(path.join(root,'handover/browser-verification.json'),JSON.stringify(evidence,null,2));
  if(browser)await browser.close();
 }
 console.log(JSON.stringify(evidence));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
