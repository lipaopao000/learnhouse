"""Observe the existing scheduled prefetch; never trigger a warm request."""
import argparse, datetime, json, subprocess, time
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--deployment-dir',required=True,type=Path);p.add_argument('--wait-seconds',type=int,default=900);args=p.parse_args()
    work=args.deployment_dir/'handover/icu-video-courses';state=json.loads((work/'state.json').read_text())
    expected={a['activity_uuid']:key for key,a in state['activities'].items() if a['activity_type']=='TYPE_VIDEO'}
    assert len(expected)==8,'Finish importing all videos before verification'
    started=time.monotonic();observations=[]
    while True:
        command='powershell -NoProfile -Command "Get-Content D:\\deploy\\LearnHouseVideo\\prefetch-state.json -Raw"'
        r=subprocess.run(['ssh','-o','ConnectTimeout=10','icu-jump',command],capture_output=True,text=True,timeout=30);r.check_returncode();cache=json.loads(r.stdout)
        rows=[]
        for activity,key in expected.items():
            found=[(uri,e) for uri,e in cache.items() if '/'+activity+'/' in uri]
            rows.append({'key':key,'uri':found[0][0] if found else None,'entry':found[0][1] if found else None})
        complete=sum(bool(row['entry'] and row['entry']['complete']) for row in rows)
        observation={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'completed':complete,'videos':rows}
        observations.append(observation)
        report={'automatic_schedule_only':True,'no_manual_video_stream_requests_before_this_check':True,'expected':len(expected),'completed':complete,'observations':observations}
        (work/'prefetch-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('Automatic prefetch:',str(complete)+'/'+str(len(expected)),flush=True)
        if complete==len(expected):break
        if time.monotonic()-started>args.wait_seconds:raise RuntimeError('Automatic prefetch not complete; inspect scheduled task status')
        time.sleep(30)
