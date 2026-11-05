// Read-only native UI/playback acceptance; the temporary learner is removed.
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto'),cp=require('child_process');
const root=path.resolve(process.argv[2]),work=path.join(root,'handover/icu-video-courses'),base='https://syyedu.toofun.fun';
const {chromium}=require(path.join(root,'video-distribution/browser-tools/node_modules/playwright'));
const state=JSON.parse(fs.readFileSync(path.join(work,'state.json'))),manifest=JSON.parse(fs.readFileSync(path.join(work,'media-manifest.json'))),env=JSON.parse(fs.readFileSync(path.join(root,'config/env.private.json')));
const report={courses:[],videos:[],anonymous_denied:[],ordinary_member_without_groups:true};
let browser,fixture;
async function json(ctx,route,body,token,form=false){const r=await ctx.request.fetch(base+route,{method:body?'POST':'GET',headers:{Origin:base,...(token?{Authorization:'Bearer '+token}:{})},...(body?(form?{form:body}:{data:body}):{})});assert(r.ok(),route+' '+r.status()+' '+(await r.text()).slice(0,120));return r.json();}
async function login(ctx,name,password){return json(ctx,'/api/v1/auth/login',{username:name,password,org_slug:'default'},null,true);}
async function onboard(page){for(const label of ['开始','开始吧']){const button=page.getByRole('button',{name:label,exact:true});if(await button.isVisible().catch(()=>false))await button.click();}}
async function coversLoaded(page){
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('[style]')).some(e=>getComputedStyle(e).backgroundImage.includes('/thumbnails/'))||Array.from(document.images).some(i=>i.src.includes('/thumbnails/')&&i.complete&&i.naturalWidth>0));
 await page.evaluate(async()=>{const urls=Array.from(document.querySelectorAll('[style]')).map(e=>getComputedStyle(e).backgroundImage).filter(v=>v.includes('/thumbnails/')).map(v=>v.match(/url\(["']?(.*?)["']?\)/)?.[1]).filter(Boolean);await Promise.all(urls.map(src=>new Promise((resolve,reject)=>{const image=new Image();image.onload=resolve;image.onerror=reject;image.src=src;})));});
}
(async()=>{try{
 browser=await chromium.launch({headless:true,executablePath:'/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'});
 const admin=await browser.newContext(),auth=await login(admin,env.LEARNHOUSE_INITIAL_ADMIN_EMAIL,env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD);
 const username='lh_test_'+crypto.randomBytes(8).toString('hex'),password=crypto.randomBytes(16).toString('hex')+'Aa9!';
 const imported=await json(admin,'/api/v1/orgs/1/users/import/create',{rows:[{name:'视频课程验收临时学员',username,email:'',role:'学员',groups:[],password}],import_id:crypto.randomUUID(),confirmed:true},auth.tokens.access_token);
 assert.equal(imported.rows[0].status,'created');fixture={id:imported.rows[0].user_id,username};
 const member=await browser.newContext({viewport:{width:1440,height:1000}}),student=await login(member,username,password),anon=await browser.newContext();
 const web=await member.request.post(base+'/api/auth/login',{headers:{Origin:base},form:{username,password,org_slug:'default'}});assert(web.ok());
 const page=await member.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const folder=await json(member,'/api/v1/folders/'+state.folder.folder_uuid,null,student.tokens.access_token);assert.equal(folder.items.length,3);
 report.library_url=base+'/library/folder/'+state.folder.folder_uuid.replace('folder_','');
 await page.goto(report.library_url);await page.getByRole('heading',{name:'ICU视频课堂',exact:true}).waitFor({timeout:30000});await onboard(page);await coversLoaded(page);await page.screenshot({path:path.join(work,'qa/library-desktop.png'),fullPage:true});
 if(process.env.WAIT_FOR_AUTOCACHE){
  const deadline=Date.now()+15*60*1000;
  while(true){let done=false;try{const cache=JSON.parse(fs.readFileSync(path.join(work,'prefetch-verification.json')));done=cache.completed===8;}catch{}
   if(done)break;assert(Date.now()<deadline,'Automatic prefetch timed out before media acceptance');await new Promise(resolve=>setTimeout(resolve,10000));}
 }
 for(const [key,course] of Object.entries(state.courses)){
  const meta=await json(member,'/api/v1/courses/'+course.course_uuid+'/meta',null,student.tokens.access_token);assert(meta.published&&!meta.public&&meta.thumbnail_image);const videos=meta.chapters.flatMap(c=>c.activities).filter(a=>a.activity_type==='TYPE_VIDEO');assert.equal(videos.length,key==='cvc'?2:3);assert(meta.chapters.flatMap(c=>c.activities).every(a=>a.published));
  const courseUrl=base+'/course/'+course.course_uuid.replace('course_','');report.courses.push({key,name:course.name,url:courseUrl,videos:videos.length,published:true,public:false,thumbnail:meta.thumbnail_image});
  await page.goto(courseUrl);await page.getByText(course.name,{exact:true}).first().waitFor({timeout:30000});await onboard(page);await coversLoaded(page);await page.screenshot({path:path.join(work,'qa/'+key+'-course.png'),fullPage:true});
  for(const video of videos){
   const media=manifest.find(m=>state.activities[key+'/'+m.key]?.activity_uuid===video.activity_uuid);assert(media);
   const stream='/api/v1/stream/video/'+[meta.org_uuid,meta.course_uuid,video.activity_uuid,video.content.filename].map(encodeURIComponent).join('/');
   const head=await member.request.head(base+stream);assert.equal(head.status(),200);assert.equal(Number(head.headers()['content-length']),media.bytes);
   const ranges=[];
   for(const [start,end] of [[0,1023],[media.bytes-1024,media.bytes-1]]){
    const response=await member.request.get(base+stream,{headers:{Range:`bytes=${start}-${end}`}});assert.equal(response.status(),206);assert.equal(response.headers()['content-range'],`bytes ${start}-${end}/${media.bytes}`);
    const expected=Buffer.alloc(1024),fd=fs.openSync(path.join(work,'ready',media.file),'r');try{fs.readSync(fd,expected,0,1024,start);}finally{fs.closeSync(fd);}assert((await response.body()).equals(expected));ranges.push({start,end,status:response.status(),cache:response.headers()['x-learnhouse-video-cache']});
   }
   const denied=await anon.request.get(base+stream,{headers:{Range:'bytes=0-1023'}});assert([401,403,404].includes(denied.status()));report.anonymous_denied.push({key:media.key,status:denied.status()});
   const url=courseUrl+'/activity/'+video.activity_uuid.replace('activity_','');await page.goto(url);await onboard(page);const player=page.locator('video').first();await player.waitFor({timeout:30000});
   await player.evaluate(v=>{v.muted=true;return v.play();});await page.waitForFunction(()=>{const v=document.querySelector('video');return v&&v.currentTime>1&&!v.paused},null,{timeout:45000});
   const initial=await player.evaluate(v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,error:v.error?.message||null}));assert(!initial.error&&Math.abs(initial.duration-media.duration)<1&&initial.width===media.width&&initial.height===media.height);
   const seekTo=Math.min(Math.floor(media.duration*0.65),media.duration-10);await player.evaluate((v,t)=>{v.currentTime=t;return v.play();},seekTo);await page.waitForFunction(t=>{const v=document.querySelector('video');return v&&!v.seeking&&v.currentTime>t+1&&!v.paused},seekTo,{timeout:45000});await player.evaluate(v=>v.pause());
   await page.screenshot({path:path.join(work,'qa/'+media.key+'-playback.png'),fullPage:true});report.videos.push({key:media.key,url,duration:initial.duration,width:initial.width,height:initial.height,playback_advanced:true,seek_to:seekTo,seek_advanced:true,ranges,source_bytes_match:true});console.log('Verified native playback:',media.key);
  }
 }
 if(process.env.LQY_TEST_PASSWORD){const maintainer=await browser.newContext(),m=await login(maintainer,'lqy',process.env.LQY_TEST_PASSWORD);for(const c of Object.values(state.courses))await json(maintainer,'/api/v1/courses/'+c.course_uuid+'/meta',null,m.tokens.access_token);report.lqy_access=true;}
 await page.setViewportSize({width:390,height:844});await page.goto(report.library_url);await page.getByRole('heading',{name:'ICU视频课堂',exact:true}).waitFor();await page.screenshot({path:path.join(work,'qa/library-mobile.png'),fullPage:true});report.mobile_library=true;
 report.browser_errors=errors;assert.equal(errors.length,0);
}finally{
 if(fixture){cp.execFileSync('python3',[path.join(__dirname,'../username-accounts/fixture.py'),'--deployment-dir',root,'--user-id',String(fixture.id),'--username',fixture.username,'--action','cleanup']);report.synthetic_account_deleted=true;}
 if(browser)await browser.close();report.verified_at=new Date().toISOString();fs.writeFileSync(path.join(work,'browser-verification.json'),JSON.stringify(report,null,2));
}
console.log(JSON.stringify({courses:report.courses.length,videos:report.videos.length,synthetic_account_deleted:report.synthetic_account_deleted}));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
