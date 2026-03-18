// ══════════════════════════════════════════
//  NAV: Sticky background + active section tracking
// ══════════════════════════════════════════

const nav = document.getElementById('nav');
const navLinks = document.querySelectorAll('.nav-link[data-section]');
const navSections = [];

// Build section list for active tracking
navLinks.forEach(link => {
  const id = link.dataset.section;
  const section = document.getElementById(id);
  if (section) navSections.push({ id, el: section, link });
});

// Scroll handler: background + active state
let navTicking = false;

function updateNav() {
  const scrollY = window.scrollY;

  // Toggle scrolled class (background appearance)
  if (scrollY > 80) {
    nav.classList.add('scrolled');
  } else {
    nav.classList.remove('scrolled');
  }

  // FAB: show after scrolling past first viewport
  if (fabTop) {
    if (scrollY > window.innerHeight * 0.8) {
      fabTop.classList.add('visible');
    } else {
      fabTop.classList.remove('visible');
    }
  }

  // Determine active section
  let activeId = '';
  for (let i = navSections.length - 1; i >= 0; i--) {
    const { id, el } = navSections[i];
    const top = el.getBoundingClientRect().top + scrollY - 120;
    if (scrollY >= top) {
      activeId = id;
      break;
    }
  }

  // Update active link
  navLinks.forEach(link => {
    if (link.dataset.section === activeId) {
      link.classList.add('active');
    } else {
      link.classList.remove('active');
    }
  });

  navTicking = false;
}

window.addEventListener('scroll', () => {
  if (!navTicking) {
    requestAnimationFrame(updateNav);
    navTicking = true;
  }
}, { passive: true });

// Close mobile menu on link click
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', () => {
    const navLinksEl = document.getElementById('nav-links');
    if (navLinksEl) navLinksEl.classList.remove('open');
  });
});

// ── Scroll-to-top FAB ──
const fabTop = document.getElementById('fab-top');

// Initial state
updateNav();

// ══════════════════════════════════════════
//  HERO: Waveform → text animation
// ══════════════════════════════════════════

(function() {
  const canvas = document.getElementById('hero-waveform');
  const tagline = document.getElementById('hero-tagline');
  if (!canvas || !tagline) return;

  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.offsetWidth;
  const h = canvas.offsetHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);

  const bars = 48;
  const barW = Math.max(2, (w / bars) * 0.5);
  const gap = w / bars;
  const startTime = performance.now();
  const duration = 2400; // ms of waveform animation
  let animId;

  function draw(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);

    ctx.clearRect(0, 0, w, h);

    // Envelope: ramp up, sustain, ramp down
    let envelope;
    if (progress < 0.15) {
      envelope = progress / 0.15; // ramp up
    } else if (progress > 0.75) {
      envelope = (1 - progress) / 0.25; // ramp down
    } else {
      envelope = 1; // sustain
    }

    for (let i = 0; i < bars; i++) {
      const x = i * gap + gap / 2 - barW / 2;

      // Multiple sine waves for organic speech-like pattern
      const t = elapsed * 0.004;
      const wave1 = Math.sin(i * 0.4 + t * 3.1) * 0.5;
      const wave2 = Math.sin(i * 0.7 + t * 5.3) * 0.3;
      const wave3 = Math.sin(i * 1.1 + t * 1.7) * 0.2;
      const combined = (wave1 + wave2 + wave3) * envelope;

      const barH = Math.max(2, Math.abs(combined) * h * 0.8);
      const y = (h - barH) / 2;

      // Red glow color with varying opacity
      const alpha = 0.3 + Math.abs(combined) * 0.7;
      ctx.fillStyle = `rgba(255, 23, 68, ${alpha})`;
      ctx.beginPath();
      ctx.roundRect(x, y, barW, barH, barW / 2);
      ctx.fill();
    }

    if (progress < 1) {
      animId = requestAnimationFrame(draw);
    } else {
      // Waveform done → crossfade to text
      canvas.classList.add('done');
      setTimeout(() => tagline.classList.add('visible'), 200);
    }
  }

  animId = requestAnimationFrame(draw);
})();

// ── Scroll reveal (IntersectionObserver) ──
const reveals = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-stagger');
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -60px 0px' });

reveals.forEach(el => revealObserver.observe(el));

// ── Parallax (hero + section content) ──
const parallaxElements = document.querySelectorAll('[data-parallax]');
const sectionParallax = document.querySelectorAll('[data-parallax-section]');
let ticking = false;

function updateParallax() {
  const scrollY = window.scrollY;
  const viewH = window.innerHeight;

  // Hero parallax
  parallaxElements.forEach(el => {
    const speed = parseFloat(el.dataset.parallax);
    const offset = scrollY * speed;
    el.style.transform = `translateY(${offset}px)`;
  });

  // Section content parallax — subtle Y shift based on scroll position relative to section
  sectionParallax.forEach(el => {
    const speed = parseFloat(el.dataset.parallaxSection) || 0.05;
    const rect = el.getBoundingClientRect();
    const center = rect.top + rect.height / 2;
    const offset = (center - viewH / 2) * speed;
    el.style.transform = `translateY(${offset}px)`;
  });

  ticking = false;
}

// Disable parallax on mobile / reduced motion
const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const isMobile = window.innerWidth < 768;

if (!prefersReduced && !isMobile) {
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(updateParallax);
      ticking = true;
    }
  }, { passive: true });
}

// ── Counter animation ──
const counters = document.querySelectorAll('.counter-val');
let countersDone = false;

const counterObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting && !countersDone) {
      countersDone = true;
      counters.forEach(c => {
        const target = parseInt(c.dataset.target);
        const duration = 1500;
        const start = performance.now();

        function animate(now) {
          const elapsed = now - start;
          const progress = Math.min(elapsed / duration, 1);
          // Ease out cubic
          const eased = 1 - Math.pow(1 - progress, 3);
          c.textContent = Math.round(target * eased);
          if (progress < 1) requestAnimationFrame(animate);
        }
        requestAnimationFrame(animate);
      });
    }
  });
}, { threshold: 0.5 });

const statsSection = document.querySelector('.stats');
if (statsSection) counterObserver.observe(statsSection);

// ── Smooth anchor scrolling ──
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    const target = document.querySelector(a.getAttribute('href'));
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

// ══════════════════════════════════════════
//  TUTORIAL: Interactive Scenarios
// ══════════════════════════════════════════

// ── Tab switching ──
function switchTutTab(btn) {
  document.querySelectorAll('.tut-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tut-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  const panelId = 'panel-' + btn.dataset.panel;
  const panel = document.getElementById(panelId);
  if (panel) {
    panel.classList.add('active');
    // Auto-play animations for newly shown panel
    animatePanel(panelId);
  }
}

// ── Animate a panel's elements ──
function animatePanel(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;

  // Animate flow nodes
  const flowId = panel.querySelector('.tut-flow')?.id;
  if (flowId) animateFlow(flowId);

  // Animate conversation
  const convoId = panel.querySelector('.tut-convo')?.id;
  if (convoId) animateConvo(convoId);

  // Animate timeline
  const timelineId = panel.querySelector('.tut-timeline')?.id;
  if (timelineId) animateTimeline(timelineId);
}

// ── Flow diagram animation ──
function animateFlow(flowId) {
  const flow = document.getElementById(flowId);
  if (!flow) return;
  const items = flow.querySelectorAll('.tut-flow-node, .tut-flow-arrow');
  items.forEach(item => {
    item.classList.remove('visible');
    const delay = parseInt(item.dataset.delay || 0);
    setTimeout(() => item.classList.add('visible'), delay);
  });
}

// ── Conversation animation ──
function animateConvo(convoId) {
  const convo = document.getElementById(convoId);
  if (!convo) return;
  const items = convo.querySelectorAll('.tut-msg, .tut-tool-call, .tut-choice-sheet');
  items.forEach(item => {
    item.classList.remove('visible');
    const delay = parseInt(item.dataset.delay || 0);
    setTimeout(() => item.classList.add('visible'), delay);
  });
}

// ── Timeline animation ──
function animateTimeline(timelineId) {
  const tl = document.getElementById(timelineId);
  if (!tl) return;
  const items = tl.querySelectorAll('.tut-tl-item');
  items.forEach(item => {
    item.classList.remove('visible');
    const delay = parseInt(item.dataset.delay || 0);
    setTimeout(() => item.classList.add('visible'), delay);
  });
}

// ── Replay button ──
function replayConvo(convoId, flowId) {
  if (flowId) animateFlow(flowId);
  if (convoId) animateConvo(convoId);
}

function replayTimeline(timelineId) {
  animateTimeline(timelineId);
}

// ── Use case card toggle ──
function toggleUseCase(card) {
  card.classList.toggle('open');
}

// ── Auto-play first panel when tutorial section scrolls into view ──
const tutSection = document.querySelector('.tutorial');
let tutPlayed = false;

if (tutSection) {
  const tutObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting && !tutPlayed) {
        tutPlayed = true;
        animatePanel('panel-voice');
      }
    });
  }, { threshold: 0.15 });
  tutObserver.observe(tutSection);
}
