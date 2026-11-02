from playwright.sync_api import expect, sync_playwright

from tests.test_doctor_itemized_approval_playwright import RunningServer, _login, _prepare_review_fixture


def test_late_task_steps_preserve_active_editor_after_committed_save() -> None:
    server = RunningServer()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            _login(page, server.base_url)
            task_id = _prepare_review_fixture(page)
            reviews = []
            page.on("request", lambda request: reviews.append(request.url)
                    if request.method == "POST" and request.url.endswith(f"/tasks/{task_id}/review") else None)
            page.click('[data-record-edit-field="past_history"]')
            editor = page.locator('[data-record-field-input="past_history"]')
            editor.fill("首次提交的既往史")
            page.evaluate("""() => {
              const state = window.__lateStepsTest = {seen: false, inputEvents: []};
              const gate = new Promise(resolve => { state.release = resolve; });
              const realFetch = window.fetch.bind(window);
              window.fetch = async (...args) => {
                const response = await realFetch(...args);
                if (String(args[0]).endsWith('/steps')) { state.seen = true; await gate; }
                return response;
              };
            }""")
            page.route("**/export-readiness", lambda route: route.abort())
            page.click("#saveDraftButton")
            expect(page.locator(".record-version")).to_contain_text("服务器已接受保存", timeout=15000)
            page.wait_for_function("window.__lateStepsTest.seen")
            page.evaluate("""() => {
              const state = window.__lateStepsTest, selector = '[data-record-field-input="past_history"]';
              const onFocus = event => {
                if (!event.target.matches(selector)) return;
                document.removeEventListener('focusin', onFocus, true);
                state.node = event.target;
                state.release();
              };
              document.addEventListener('focusin', onFocus, true);
              document.addEventListener('input', event => {
                if (event.target.matches(selector)) state.inputEvents.push(event.target.value);
              }, true);
            }""")
            editor.fill("失败提示后的追加文字")
            expect(editor).to_be_focused()
            assert page.evaluate("window.__lateStepsTest.node.isConnected")
            assert page.evaluate("window.__lateStepsTest.inputEvents") == ["失败提示后的追加文字"]
            expect(editor).to_have_value("失败提示后的追加文字")
            page.unroute("**/export-readiness")
            page.click("[data-record-reload-latest]")
            page.wait_for_function("!appState.recordEditMode", timeout=15000)
            page.locator(".record-recovery summary").click()
            expect(page.locator(".record-recovery")).to_contain_text("失败提示后的追加文字")
            assert page.evaluate("async id => (await api('/api/tasks/' + id)).result_json.fields.past_history.value", task_id) == "首次提交的既往史"
            assert len(reviews) == 1
            browser.close()
    finally:
        server.close()
