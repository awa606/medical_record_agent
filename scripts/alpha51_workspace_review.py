"""Local-only visual review using the actual doctor page and synthetic data.

No production API registration is changed. Stop this process to remove review routes.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8791)
    parser.add_argument('--runtime', default='.artifacts/alpha51-clinical-review')
    parser.add_argument('--baseline-static', help='optional read-only archived static files inside .artifacts')
    args = parser.parse_args()
    runtime = (ROOT / args.runtime).resolve()
    if not runtime.is_relative_to((ROOT / '.artifacts').resolve()):
        parser.error('review runtime must be inside the ignored .artifacts directory')
    runtime.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.update({
        'MEDICAL_RECORD_AGENT_DB': str(runtime / 'review.sqlite3'),
        'MEDICAL_RECORD_AGENT_UPLOAD_DIR': str(runtime / 'uploads'),
        'MEDICAL_RECORD_AGENT_OUTPUT_DIR': str(runtime / 'outputs'),
        'MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR': str(runtime / 'speakers'),
        'RECORD_PROVIDER_MODE': 'demo', 'LLM_PROVIDER': 'mock',
        'ASR_ENGINE': 'mock', 'MEDICAL_RECORD_AGENT_ASR_ENGINE': 'mock',
        'ASR_PREWARM_ENABLED': '0',
    })
    static_root = ROOT / 'static'
    if args.baseline_static:
        static_root = (ROOT / args.baseline_static).resolve()
        if not static_root.is_relative_to((ROOT / '.artifacts').resolve()) or not (static_root / 'doctor.html').is_file():
            parser.error('baseline must be an existing static archive inside .artifacts')
    from fastapi.responses import HTMLResponse, Response
    from fastapi.staticfiles import StaticFiles
    from app.main import app
    import uvicorn

    app.mount('/review-assets', StaticFiles(directory=static_root), name='review-assets')

    @app.get('/workspace-review', include_in_schema=False)
    def review():
        html = (static_root / 'doctor.html').read_text(encoding='utf-8')
        html = html.replace('<head>', '<head><base href="/review-assets/">', 1)
        html = html.replace('</body>', '<script src="/__workspace_review.js"></script></body>')
        return HTMLResponse(html, headers={'Cache-Control': 'no-store'})

    @app.get('/__workspace_review.js', include_in_schema=False)
    def fixture():
        bootstrap = """(async () => {
          const wait = async predicate => {
            const deadline = Date.now() + 120000;
            while (!predicate()) {
              if (Date.now() > deadline) throw Error('Please sign in and reload the review page');
              await new Promise(r => setTimeout(r, 200));
            }
          };
          await wait(() => window.__MRA_APP_STATE__?.authUser);
          await createRecordTask('患者发热伴咳嗽咽痛2天，最高体温38.2℃。没有胸痛，也没有药物过敏史。');
          await wait(() => window.__MRA_APP_STATE__.currentRecordFields && window.__MRA_APP_STATE__.eventSource === null);
        """
        js = (ROOT / 'tests/fixtures/alpha51_workspace_review.js').read_text(encoding='utf-8')
        return Response(bootstrap + js + "\n})().catch(e => console.error('Visual review fixture:', e));", media_type='text/javascript', headers={'Cache-Control': 'no-store'})

    uvicorn.run(app, host='127.0.0.1', port=args.port)

if __name__ == '__main__':
    main()
