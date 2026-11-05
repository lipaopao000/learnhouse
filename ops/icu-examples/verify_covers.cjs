const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto');
const root=path.resolve(process.argv[2]),base='https://syyedu.toofun.fun';
const {chromium}=require(path.join(root,'video-distribution/browser-tools/node_modules/playwright'));
const env=JSON.parse(fs.readFileSync(path.join(root,'config/env.private.json'))),state=JSON.parse(fs.readFileSync(path.join(root,'handover/icu-examples-state.json'))),covers=JSON.parse(fs.readFileSync(path.join(root,'handover/icu-covers-state.json')));
const reportPath=path.join(__dirname,'verification.json'),report=JSON.parse(fs.readFileSync(reportPath));
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'});try{
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
 const r=await ctx.request.post(base+'/api/auth/login',{headers:{Origin:base},form:{username:env.LEARNHOUSE_INITIAL_ADMIN_EMAIL,password:env.LEARNHOUSE_INITIAL_ADMIN_PASSWORD,org_slug:'default'}});assert(r.ok());
 const page=await ctx.newPage();
 const mediaBase=env.NEXT_PUBLIC_LEARNHOUSE_MEDIA_URL||env.NEXT_PUBLIC_LEARNHOUSE_BACKEND_URL||base+'/';
 const org='org_32e55dad-43ad-4eb4-ac0d-ecd1af125ddc';
 for(const record of Object.values(covers)){
  const response=await ctx.request.get(mediaBase.replace(/\/$/,'')+'/content/orgs/'+org+'/courses/'+record.course_uuid+'/thumbnails/'+record.thumbnail_image);assert(response.ok(),'Cover download '+record.title+' '+response.status());
  const data=await response.body();assert.equal(crypto.createHash('sha256').update(data).digest('hex'),record.asset_sha256,'Cover bytes '+record.title);
 }
 const dir=path.join(root,'handover/icu-examples-qa');
 const originalSeed=JSON.parse(fs.readFileSync(path.join(root,'handover/seed-state.json')));
 const overview=base+'/library/folder/'+originalSeed.folders['核心临床专题'].folder_uuid.replace('folder_','');
 for(const [key,target] of [['core-course-overview',overview],['library',base+'/library/folder/'+state.folders['ICU教学示例馆'].folder_uuid.replace('folder_','')],['example-course',base+'/course/'+state.course.course_uuid.replace('course_','')],['ventilation-course',base+'/course/'+covers.ventilation.course_uuid.replace('course_','')]]){
  await page.goto(target);await page.waitForFunction(()=>Array.from(document.images).some(img=>img.src.includes('/thumbnails/')&&img.complete&&img.naturalWidth>0)||Array.from(document.querySelectorAll('[style]')).some(el=>getComputedStyle(el).backgroundImage.includes('/thumbnails/')));
  await page.waitForTimeout(700);await page.screenshot({path:path.join(dir,key+'-with-cover.png'),fullPage:true});
 }
 await page.setViewportSize({width:390,height:844});await page.goto(base+'/library/folder/'+state.folders['ICU教学示例馆'].folder_uuid.replace('folder_',''));await page.waitForFunction(()=>Array.from(document.images).some(img=>img.src.includes('/thumbnails/')&&img.complete&&img.naturalWidth>0)||Array.from(document.querySelectorAll('[style]')).some(el=>getComputedStyle(el).backgroundImage.includes('/thumbnails/')));await page.screenshot({path:path.join(dir,'library-with-cover-mobile.png'),fullPage:true});
 report.course_covers.bytes_verified=Object.keys(covers).length;report.course_covers.native_desktop_and_mobile=true;report.course_covers.verified_at=new Date().toISOString();fs.writeFileSync(reportPath,JSON.stringify(report,null,2));console.log('Verified native cover images:',Object.keys(covers).length);
}finally{await browser.close()}})().catch(e=>{console.error(e.stack);process.exitCode=1});
