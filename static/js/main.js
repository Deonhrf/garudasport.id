// ---------------------------------------------------------------
// GarudaSport — interaksi sisi klien (menu mobile + filter kategori)
// ---------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  // Toggle menu mobile
  const menuToggle = document.getElementById('menuToggle');
  const mobileMenu = document.getElementById('mobileMenu');

  if (menuToggle && mobileMenu) {
    menuToggle.addEventListener('click', () => {
      mobileMenu.classList.toggle('hidden');
    });
  }

  // Filter kategori produk
  const filterButtons = document.querySelectorAll('.filter-btn');
  const productCards = document.querySelectorAll('.product-card');
  const emptyState = document.getElementById('emptyState');

  filterButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const selected = btn.dataset.filter;

      filterButtons.forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');

      let visibleCount = 0;

      productCards.forEach((card) => {
        const tags = (card.dataset.tags || '').split(' ');
        const matches = selected === 'all' || tags.includes(selected);
        card.style.display = matches ? '' : 'none';
        if (matches) visibleCount += 1;
      });

      if (emptyState) {
        emptyState.classList.toggle('hidden', visibleCount > 0);
      }
    });
  });
});
