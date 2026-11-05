// Verify real native pages, ordinary-member access, protected downloads and tools.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto'),cp=require('child_process');
const root=path.resolve(process.argv[2]),base='https://syyedu.toofun.fun';
const {chromium}=require(path.join(root,'video-distribution/browser-tools/node_modules/playwright'));
const state=JSON.parse(fs.readFileSync(path.join(root,'handover/icu-examples-state.json')));
const env=JSON.parse(fs.readFileSync(path.join(root,'config/env.private.json')));
const report=JSON.parse(fs.readFileSync(path.join(__dirname,'verification.json')));
const evidenceDir=path.join(root,'handover/icu-examples-qa');fs.mkdirSync(evidenceDir,{recursive:true});
const clean=(uuid,prefix)=>uuid.replace(prefix+'_','');
let browser,fixture;
async function request(ctx,route,body,token,form=false){return ctx.request.fetch(base+route,{method:body?'POST':'GET',headers:{Origin:base,...(token?{Authorization:'Bearer '+token}:{})},...(body?(form?{form:body}:{data:body}):{})});}
async function json(ctx,route,body,token,form=false){const r=await request(ctx,route,body,token,form);assert(r.ok(),route+' '+r.status()+' '+(await r.text()).slice(0,180));return r.json();}
async function login(ctx,name,password){return json(ctx,'/api/v1/auth/login',{username:name,password,org_slug:'default'},null,true);}
async function webLogin(ctx,name,password){const r=await request(ctx,'/api/auth/login',{username:name,password,org_slug:'default'},null,true);assert(r.ok(),'web login '+r.status());}
async function verifyAccess(ctx,token){
 const result={};
 for(const [name,f] of Object.entries(state.folders)){
  const data=await json(ctx,'/api/v1/folders/'+f.folder_uuid,null,token);assert(data.items.length>=2);result[name]={items:data.items.length,subfolders:data.subfolders.length};
 }
 for(const c of Object.values(state.communities)){
  await json(ctx,'/api/v1/communities/'+c.community_uuid,null,token);
  const posts=await json(ctx,'/api/v1/communities/'+c.community_uuid+'/discussions?sort_by=recent&page=1&limit=100',null,token);assert.equal(posts.length,3);assert(posts[0].is_pinned);assert(posts.every(p=>JSON.parse(p.content).content.length>=8));
 }
 const course=await json(ctx,'/api/v1/courses/'+state.course.course_uuid+'/meta',null,token);assert(course.published);assert(!course.public);
 for(const a of Object.values(state.lessons)){const data=await json(ctx,'/api/v1/activities/'+a.activity_uuid,null,token);assert(data.published);assert(data.content.content.length>8);}
 for(const p of Object.values(state.playgrounds)){const data=await json(ctx,'/api/v1/playgrounds/'+p.playground_uuid,null,token);assert(data.published);assert(data.html_content.includes('生成练习稿'));}
 const pdf=await request(ctx,'/api/v1/media/'+state.workbook.media_uuid+'/file',null,token);assert(pdf.ok(),'PDF '+pdf.status()+' '+(pdf.ok()?'':await pdf.text()));assert.equal(crypto.createHash('sha256').update(await pdf.body()).digest('hex'),state.workbook_sha256);
 return result;
}
(async()=>{
 try{
  browser=await chromium.launch({headless:true,executablePath:'/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'});
  const admin=await browser.newContext();const adminAuth=await login(admin,env.LEARNHOUSE_INITIAL_ADMIN_EMAIL,env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD);
  const username='lh_test_'+crypto.randomBytes(8).toString('hex'),password=crypto.randomBytes(16).toString('hex')+'Aa9!';
  const created=await json(admin,'/api/v1/orgs/1/users/import/create',{rows:[{name:'ICU示例验收临时学员',username,email:'',role:'学员',groups:[],password}],import_id:crypto.randomUUID(),confirmed:true},adminAuth.tokens.access_token);
  assert.equal(created.rows[0].status,'created');fixture={id:created.rows[0].user_id,username};
  const member=await browser.newContext({viewport:{width:1366,height:1000},acceptDownloads:true});const memberAuth=await login(member,username,password);
  report.ordinary_member_access=await verifyAccess(member,memberAuth.tokens.access_token);report.ordinary_member_without_groups=true;
  await webLogin(member,username,password);const page=await member.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(report.root_url);await page.getByRole('heading',{name:'ICU教学示例馆',exact:true}).waitFor({timeout:30000});await page.getByText('01 入科与交接班',{exact:true}).waitFor();await page.getByText(state.workbook.name,{exact:true}).waitFor();await page.screenshot({path:path.join(evidenceDir,'library-desktop.png'),fullPage:true});report.library_native_ui=true;
  const community=Object.values(state.communities)[0];await page.goto(base+'/community/'+clean(community.community_uuid,'community'));await page.getByText('【虚构病例 A】交班时只说“呼吸变快了”够不够？',{exact:true}).waitFor();await page.screenshot({path:path.join(evidenceDir,'community-desktop.png'),fullPage:true});
  const first=Object.values(state.posts).find(p=>p.title.includes('虚构病例 A'));await page.goto(base+'/community/'+clean(community.community_uuid,'community')+'/discussion/'+clean(first.discussion_uuid,'discussion'));await page.getByText('情景',{exact:true}).waitFor();await page.getByText('请试着回答',{exact:true}).waitFor();report.rich_discussion_readable=true;await page.screenshot({path:path.join(evidenceDir,'discussion-desktop.png'),fullPage:true});
  await page.goto(report.course_url);await page.getByText(state.course.name,{exact:true}).first().waitFor();await page.screenshot({path:path.join(evidenceDir,'course-desktop.png'),fullPage:true});report.course_native_ui=true;
  report.interactive_tools={};
  for(const [key,p] of Object.entries(state.playgrounds)){
   await page.goto(base+'/playground/'+p.playground_uuid);const frame=page.frameLocator('iframe');await frame.getByRole('button',{name:'填入虚构示例'}).waitFor({timeout:30000});await frame.getByRole('button',{name:'填入虚构示例'}).click();assert((await frame.locator('#output').innerText()).includes(key==='sbar'?'病例 A':'ICU 轮转医师'));await frame.getByRole('button',{name:'复制练习稿'}).click();assert((await frame.locator('#status').innerText()).match(/已复制|已选中/));await page.screenshot({path:path.join(evidenceDir,key+'-desktop.png'),fullPage:true});await frame.getByRole('button',{name:'清空',exact:true}).click();assert.equal(await frame.locator('#f0').inputValue(),'');report.interactive_tools[key]={example:true,generate:true,copy_or_selection:true,clear:true};
   await page.setViewportSize({width:390,height:844});await frame.getByRole('button',{name:'填入虚构示例'}).click();assert(await frame.locator('body').evaluate(el=>el.scrollWidth<=window.innerWidth+1));await page.screenshot({path:path.join(evidenceDir,key+'-mobile.png'),fullPage:true});await page.setViewportSize({width:1366,height:1000});
  }
  await page.setViewportSize({width:390,height:844});await page.goto(report.root_url);await page.getByRole('heading',{name:'ICU教学示例馆',exact:true}).waitFor();await page.screenshot({path:path.join(evidenceDir,'library-mobile.png'),fullPage:true});report.mobile_layout_checked=true;
  if(process.env.LQY_TEST_PASSWORD){const maintainer=await browser.newContext();const auth=await login(maintainer,'lqy',process.env.LQY_TEST_PASSWORD);await verifyAccess(maintainer,auth.tokens.access_token);report.lqy_access=true;}
  const anon=await browser.newContext();report.anonymous_denied={};
  const protectedRoutes={folder:'/api/v1/folders/'+state.folders['ICU教学示例馆'].folder_uuid,community:'/api/v1/communities/'+community.community_uuid,course:'/api/v1/courses/'+state.course.course_uuid+'/meta',playground:'/api/v1/playgrounds/'+state.playgrounds.sbar.playground_uuid,media:'/api/v1/media/'+state.workbook.media_uuid+'/file'};
  for(const [key,route] of Object.entries(protectedRoutes)){const r=await request(anon,route);assert([401,403,404].includes(r.status()),key+' unexpected anonymous '+r.status());report.anonymous_denied[key]=r.status();}
  report.pdf_download_sha256_verified=true;report.browser_errors=errors;assert.equal(errors.length,0);
 }finally{
  if(fixture){cp.execFileSync('python3',[path.join(__dirname,'../username-accounts/fixture.py'),'--deployment-dir',root,'--user-id',String(fixture.id),'--username',fixture.username,'--action','cleanup']);report.synthetic_account_deleted=true;}
  if(browser)await browser.close();report.verified_at=new Date().toISOString();fs.writeFileSync(path.join(__dirname,'verification.json'),JSON.stringify(report,null,2));
 }
 console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
