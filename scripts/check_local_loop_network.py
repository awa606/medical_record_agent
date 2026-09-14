"""Record actual internal connectivity and external TCP denial for the test stack."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite network evidence')
    network=json.loads(subprocess.check_output(['docker','network','inspect',args.project+'_local_only']))[0]
    report={'time':datetime.now(timezone.utc).isoformat(),'network_internal':network['Internal'],'checks':[]}
    for service in ('app','ollama'):
        container=f'{args.project}-{service}-1'
        for host,port,expect in [('ollama',11434,True),('1.1.1.1',443,False),('example.com',443,False)]:
            # Fixed destinations only. timeout distinguishes a blocked route from a hung probe.
            run=subprocess.run(['docker','exec',container,'timeout','5','bash','-c',f'echo > /dev/tcp/{host}/{port}'],capture_output=True,text=True,timeout=12)
            reachable=run.returncode==0
            report['checks'].append({'service':service,'host':host,'port':port,'expected_reachable':expect,
                                     'reachable':reachable,'exit_code':run.returncode,'pass':reachable==expect})
    report['passed']=report['network_internal'] and all(r['pass'] for r in report['checks'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
