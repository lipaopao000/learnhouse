"""Convert legacy WMV/large MP4 to browser-compatible H.264/AAC, without cuts."""
import argparse, concurrent.futures, hashlib, json, shutil, subprocess
from pathlib import Path
from catalog import COURSES

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--work-dir',required=True,type=Path);args=parser.parse_args()
    work=args.work_dir;ready=work/'ready';ready.mkdir(exist_ok=True)
    def prepare(item):
        course,lesson=item;key=lesson['key'];target=ready/(key+'.mp4')
        if 'parts' in lesson:
            extracted=work/'extracted'/key
            # unar handles multi-volume RAR; libarchive's partial extraction does not.
            if not extracted.exists():
                extracted.mkdir(parents=True)
                subprocess.run(['unar','-f','-D','-o',str(extracted),str(work/'downloads'/(key+'.part1.rar'))],check=True,stdout=subprocess.DEVNULL)
            candidates=[p for p in extracted.rglob('*') if p.suffix.lower() in {'.wmv','.mp4'}]
            assert len(candidates)==1, candidates
            original=candidates[0]
        else: original=work/'downloads'/(key+'.mp4')
        before=probe(original)
        if not target.exists():
            temp=target.with_suffix('.partial.mp4')
            if course['key']=='critical-care-en':
                # Remux the original H.264/AAC stream, preserving all frames/audio.
                command=['ffmpeg','-v','error','-y','-i',str(original),'-map','0:v:0','-map','0:a:0','-c','copy','-movflags','+faststart',str(temp)]
            else:
                command=['ffmpeg','-v','error','-y','-i',str(original),'-map','0:v:0','-map','0:a:0','-vf',"scale='min(1280,iw)':-2",'-c:v','libx264','-threads','3','-preset','fast','-crf','25','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-movflags','+faststart',str(temp)]
            converted=subprocess.run(command,capture_output=True)
            (work/(key+'-conversion.log')).write_bytes(converted.stderr)
            converted.check_returncode()
            after=probe(temp)
            assert abs(float(before['format']['duration'])-float(after['format']['duration']))<1
            temp.replace(target)
        after=probe(target)
        # Full decode catches corruption beyond the first playable frame.
        decoded=subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','null','-'],capture_output=True)
        decoded.check_returncode()
        assert not decoded.stderr.strip(), 'Output decode warning: '+key
        video=next(s for s in after['streams'] if s['codec_type']=='video')
        audio=next(s for s in after['streams'] if s['codec_type']=='audio')
        with target.open('rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
        result=dict(key=key,file=target.name,bytes=target.stat().st_size,sha256=digest,duration=float(after['format']['duration']),original_duration=float(before['format']['duration']),width=video['width'],height=video['height'],video_codec=video['codec_name'],audio_codec=audio['codec_name'],full_decode_passed=True,changes='Full-length format conversion to H.264/AAC MP4; no cuts, crop, added captions or branding.' if course['key']!='critical-care-en' else 'Lossless remux to fast-start MP4; no cuts, added captions or branding.')
        print('Ready',key,result['duration'],result['bytes'],flush=True)
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(prepare,[(c,l) for c in COURSES for l in c['lessons']]))
    (work/'media-manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
