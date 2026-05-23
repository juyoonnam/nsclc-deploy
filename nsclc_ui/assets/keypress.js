/* NSCLC Insight Engine — Enter key to submit chat.
 *
 * Behavior:
 * - Enter (without Shift) → trigger chat-submit-btn click
 * - Shift+Enter → newline (default behavior)
 * - 한글 IME composition 중엔 무시 (자연스러운 한글 입력)
 *
 * Dash가 assets/ 폴더의 .js를 자동 로드. 별도 import 불필요.
 */

(function () {
  function isChatInputTextarea(el) {
    if (!el || el.tagName !== "TEXTAREA") return false;
    if (el.id === "chat-input") return true;
    // dmc.Textarea가 wrapper로 id를 박는 경우, 자손 textarea를 잡기 위해 ancestor 체크
    if (el.closest && el.closest("#chat-input")) return true;
    return false;
  }

  document.addEventListener(
    "keydown",
    function (e) {
      if (!isChatInputTextarea(e.target)) return;
      if (e.key !== "Enter") return;
      if (e.shiftKey) return; // Shift+Enter → newline (기본 동작)
      if (e.isComposing || e.keyCode === 229) return; // 한글 IME composition

      e.preventDefault();
      const btn = document.getElementById("chat-submit-btn");
      if (btn && !btn.disabled) {
        btn.click();
      }
    },
    true
  );
})();
