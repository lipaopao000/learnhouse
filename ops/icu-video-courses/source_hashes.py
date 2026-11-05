"""Verify persisted server originals without requesting/priming media caches."""
import argparse, json, re, shlex, sys
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--deployment-dir',type=Path,required=True);args=p.parse_args();root=args.deployment_dir.resolve()
    sys.path.insert(0,str(root));from remote import bash
    work=root/'handover/icu-video-courses';state=json.loads((work/'state.json').read_text());manifest={m['key']:m for m in json.loads((work/'media-manifest.json').read_text())}
    rows=[]
    for key,activity in state['activities'].items():
        if activity['activity_type']!='TYPE_VIDEO':continue
        course=state['courses'][key.split('/')[0]]
        org='org_32e55dad-43ad-4eb4-ac0d-ecd1af125ddc'
        components=[org,course['course_uuid'],activity['activity_uuid'],activity['content']['filename']]
        assert all(re.fullmatch(r'[A-Za-z0-9_.-]+',v) for v in components)
        filename=f'/app/api/content/orgs/{org}/courses/{components[1]}/activities/{components[2]}/video/{components[3]}'
        output=bash('docker exec learnhouse-app sha256sum '+shlex.quote(filename),timeout=60)
        digest=output.strip().split()[0];expected=manifest[key.split('/')[1]]['sha256'];assert digest==expected,'Persisted source mismatch: '+key
        rows.append({'key':key,'sha256':digest,'source_matches_uploaded_file':True})
        print('Persisted source verified:',key,flush=True)
    assert len(rows)==8
    (work/'source-verification.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
