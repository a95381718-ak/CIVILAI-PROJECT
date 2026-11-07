document.addEventListener('DOMContentLoaded', () => {
  const assistantForm = document.getElementById('assistant-form');
  const assistantInput = document.getElementById('assistant-message');
  const assistantResponse = document.getElementById('assistant-response');
  if (assistantForm && assistantInput && assistantResponse && window.CIVILAI_ASSISTANT_URL) {
    const renderAssistant = (data) => {
      const action = data.needs_complaint && data.complaint_url
        ? `<a class="btn btn-small-outline" href="${data.complaint_url}">Register this issue <i class="bi bi-arrow-up-right"></i></a>`
        : '';
      const route = data.suggested_category
        ? `<span class="assistant-route"><i class="bi bi-signpost-2"></i> ${data.suggested_category}${data.department ? ` · ${data.department}` : ''}</span>`
        : '';
      assistantResponse.className = 'assistant-response assistant-response-ready';
      assistantResponse.innerHTML = `<span class="assistant-response-icon"><i class="bi bi-stars"></i></span><div><strong>${data.reply}</strong><p>${data.solution}</p>${data.complaint_prompt ? `<p class="assistant-prompt">${data.complaint_prompt}</p>` : ''}${route}<div class="assistant-action">${action}</div></div>`;
    };
    document.querySelectorAll('[data-assistant-prompt]').forEach((button) => button.addEventListener('click', () => {
      assistantInput.value = button.dataset.assistantPrompt;
      assistantInput.focus();
    }));
    assistantForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const message = assistantInput.value.trim();
      if (!message) { assistantInput.focus(); return; }
      const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
      assistantResponse.className = 'assistant-response assistant-response-loading';
      assistantResponse.innerHTML = '<span class="assistant-response-icon"><i class="bi bi-arrow-repeat"></i></span><div><strong>Reading the civic signal…</strong><small>Checking the issue against CIVILAI’s public-service guide.</small></div>';
      try {
        const response = await fetch(window.CIVILAI_ASSISTANT_URL, { method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify({message}) });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message || 'The assistant could not answer.');
        renderAssistant(data);
      } catch (error) {
        assistantResponse.className = 'assistant-response assistant-response-error';
        assistantResponse.innerHTML = `<span class="assistant-response-icon"><i class="bi bi-exclamation-circle"></i></span><div><strong>Try again in a moment.</strong><small>${error.message}</small></div>`;
      }
    });
  }

  document.querySelectorAll('[data-toggle-password]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const visible = input.type === 'text';
      input.type = visible ? 'password' : 'text';
      button.innerHTML = visible ? '<i class="bi bi-eye"></i>' : '<i class="bi bi-eye-slash"></i>';
    });
  });

  const description = document.getElementById('description');
  const counter = document.getElementById('char-count');
  const title = document.getElementById('title');
  const analyzeButton = document.getElementById('analyze-btn');
  const card = document.getElementById('classification-card');
  const category = document.getElementById('category_id');
  if (description && counter) {
    const updateCount = () => { counter.textContent = `${description.value.length} / 1200`; };
    description.addEventListener('input', updateCount); updateCount();
  }
  if (analyzeButton && card && window.CIVILAI_CLASSIFY_URL) {
    analyzeButton.addEventListener('click', async () => {
      const text = description?.value.trim() || '';
      if (text.length < 10) {
        card.innerHTML = '<div class="classify-result"><span class="classify-icon"><i class="bi bi-pencil"></i></span><div><strong>Add a little more context first.</strong><small>At least a sentence or two gives the offline rules something useful to match.</small></div></div>';
        return;
      }
      analyzeButton.disabled = true;
      analyzeButton.textContent = 'Reading signal…';
      try {
        const response = await fetch(window.CIVILAI_CLASSIFY_URL, { method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content}, body: JSON.stringify({title: title?.value || '', description: text}) });
        const result = await response.json();
        if (result.matched && category) {
          [...category.options].find(option => option.textContent.startsWith(result.category))?.setAttribute('selected', 'selected');
          const match = [...category.options].find(option => option.textContent.startsWith(result.category));
          if (match) category.value = match.value;
        }
        const percent = Math.round((result.strength || 0) * 100);
        card.innerHTML = `<div class="classify-result"><span class="classify-icon"><i class="bi bi-stars"></i></span><div><strong>${result.category} <span style="color:#70887b;font-weight:500">· ${result.department}</span></strong><small>${result.explanation} ${result.matched ? 'Suggested route selected below.' : ''}</small>${result.matched ? `<div class="match-meter"><span style="width:${percent}%"></span></div>` : ''}</div><button type="button" class="btn btn-small-outline" id="reanalyze-btn">Run again</button></div>`;
        document.getElementById('reanalyze-btn')?.addEventListener('click', () => analyzeButton.click());
      } catch (error) {
        card.innerHTML = '<div class="classify-result"><span class="classify-icon"><i class="bi bi-wifi-off"></i></span><div><strong>Manual routing still works.</strong><small>The classifier is unavailable right now. Choose a category below and continue.</small></div></div>';
      } finally { analyzeButton.disabled = false; analyzeButton.textContent = 'Request classification'; }
    });
  }
});
