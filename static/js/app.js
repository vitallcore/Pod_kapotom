(() => {
  const modal = document.getElementById('feedbackModal');
  const serviceSelect = modal ? modal.querySelector('select[name="service_id"]') : null;
  const searchInput = document.getElementById('searchInput');
  const openers = [
    document.getElementById('openFeedback'),
    document.getElementById('openFeedback2'),
    document.getElementById('openFeedback3'),
  ].filter(Boolean);
  const closeBtn = document.getElementById('closeFeedback');
  const cancelBtn = document.getElementById('cancelFeedback');
  const backdrop = document.getElementById('modalBackdrop');

  function inferCurrentServiceId() {
    const meta = document.querySelector('article h1');
    const linkActive = document.querySelector('a.nav-active');
    const urlMatch = location.pathname.match(/^\/services\/(\d+)/);
    if (urlMatch) return urlMatch[1];
    return null;
  }

  function openModal() {
    if (!modal) return;
    // Try to preselect current service based on URL like /services/{id}
    const currentId = inferCurrentServiceId();
    if (serviceSelect && currentId) {
      const opt = Array.from(serviceSelect.options).find(o => String(o.value) === String(currentId));
      if (opt) serviceSelect.value = String(currentId);
    }
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }
  function closeModal() {
    if (!modal) return;
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }

  openers.forEach((btn) => btn.addEventListener('click', openModal));
  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
  if (backdrop) backdrop.addEventListener('click', closeModal);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  // Search functionality
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const query = searchInput.value.trim();
        if (query) {
          window.location.href = `/services?search=${encodeURIComponent(query)}`;
        }
      }
    });
  }
})();


