// Run with LEARNHOUSE_PLAYWRIGHT_MODULE set to an installed Playwright module.
const { chromium } = require(process.env.LEARNHOUSE_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const output = process.argv[2];
if (!output) throw new Error('Provide an evidence directory');
(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    headless: true, args: ['--autoplay-policy=no-user-gesture-required']
  });
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const evidence = {consoleErrors: [], failedRequests: [], videoResponses: []};
  page.on('pageerror', e => evidence.consoleErrors.push(e.message));
  page.on('requestfailed', req => evidence.failedRequests.push({url: req.url().split('?')[0], error: req.failure()?.errorText}));
  page.on('response', async response => {
    if (response.url().includes('/api/v1/stream/')) {
      evidence.videoResponses.push({status: response.status(), url: response.url().split('?')[0], cache: (await response.allHeaders())['x-learnhouse-video-cache']});
    }
  });
  try {
    const response = await page.goto('https://syyedu.toofun.fun/course/6b149f36-be4b-48df-9ba8-a9d7d52499ae/activity/563cb760-4725-40e0-8d9a-1f9d525686c4', {waitUntil: 'domcontentloaded', timeout: 60000});
    evidence.pageStatus = response.status();
    await page.locator('video').first().waitFor({timeout: 60000});
    await page.waitForFunction(() => document.querySelector('video')?.readyState >= 1, {timeout: 60000});
    evidence.metadata = await page.locator('video').first().evaluate(v => ({duration:v.duration, width:v.videoWidth, height:v.videoHeight, error:v.error?.message || null}));
    await page.locator('video').first().evaluate(async v => {v.muted = true; await v.play();});
    await page.waitForFunction(() => document.querySelector('video')?.currentTime > 2, {timeout: 60000});
    evidence.playbackTime = await page.locator('video').first().evaluate(v => v.currentTime);
    await page.locator('video').first().evaluate(v => {v.currentTime = 1800;});
    await page.waitForFunction(() => {const v=document.querySelector('video'); return v?.currentTime > 1801 && !v.seeking && v.readyState >= 2;}, {timeout: 60000});
    evidence.seekTime = await page.locator('video').first().evaluate(v => v.currentTime);
    await page.screenshot({path: path.join(output, 'lesson-playback.png'), fullPage: true});
    evidence.passed = true;
  } finally {
    fs.writeFileSync(path.join(output, 'browser-verification.json'), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify(evidence, null, 2));
    await browser.close();
  }
})().catch(e => {console.error(e.message); process.exitCode=1;});
