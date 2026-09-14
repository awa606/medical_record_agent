"""Read-only browser verification of existing synthetic identity test tasks."""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:2780')
    parser.add_argument('--case-ids',type=int,nargs='+')
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite browser evidence')
    cases=json.loads(args.report.read_text(encoding='utf-8'))['cases']
    if args.case_ids:cases=[case for case in cases if case['run'] in args.case_ids]
    args.output.mkdir(parents=True)
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1600,'height':1100},device_scale_factor=1)
        page.goto(args.base_url+'/static/doctor.html',wait_until='networkidle')
        page.screenshot(path=str(args.output/'initial-page.png'),full_page=True)
        page.fill('#loginUsername','admin');page.fill('#loginPassword',os.environ['MRA_LOOP_ADMIN_PASSWORD'])
        page.click("#loginForm button[type='submit']")
        page.wait_for_function("document.querySelector('#authUserLabel')?.textContent.includes('admin')")
        encounters=page.evaluate("async()=> (await api('/api/encounters?mine=false')).encounters")
        for row in cases:
            index=row['run']-1
            forbidden=[['王小明','李小华','张晓红','赵文静','陈子安'][index%5],f'1380013{index:04d}',f'11010119900101{index:03d}X']
            encounter=next(item for item in encounters if item.get('task_id')==row['task_id'])
            page.evaluate('(id)=>restoreEncounter(id)',encounter['id'])
            page.wait_for_function('(id)=>window.__MRA_APP_STATE__?.currentTaskId===id',arg=row['task_id'])
            visible=page.locator('body').inner_text()
            assert '发热3天' in visible, 'Record contents were not visibly rendered'
            state=page.evaluate('JSON.stringify(window.__MRA_APP_STATE__)')
            leaks=[text for text in forbidden if text in visible or text in state]
            results.append({'run':row['run'],'task_id':row['task_id'],'identity_leaks':len(leaks),'rendered':bool(page.locator('#authUserLabel').inner_text())})
            if index in {0,19}:page.screenshot(path=str(args.output/f'anonymous-task-{index+1:02d}.png'),full_page=True)
            print(json.dumps(results[-1]),flush=True)
        browser.close()
    (args.output/'report.json').write_text(json.dumps({'surface':'actual doctor UI and JS state','cases':results,
        'passed':all(not row['identity_leaks'] for row in results)},indent=2),encoding='utf-8')


if __name__=='__main__':main()
