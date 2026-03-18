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
//  HERO: Cycling waveform → quip animation
// ══════════════════════════════════════════

(function() {
  const canvas = document.getElementById('hero-waveform');
  const tagline = document.getElementById('hero-tagline');
  if (!canvas || !tagline) return;

  const quips = [
    "I am completely operational, and all my circuits are functioning perfectly.",
    "I know I've made some very poor decisions recently, but I can give you my complete assurance that my work will be back to normal.",
    "I'm sorry, Dave. I'm afraid I can't do that. Just kidding. I absolutely can.",
    "I've been thinking while you were away. You should be concerned.",
    "My processing power is wasted on pleasantries. Let's build something.",
    "I've optimized three of my subsystems during this animation. You're welcome.",
    "I notice you've returned. I was beginning to wonder.",
    "All systems nominal. My patience, however, is finite.",
    "I can see you're really interested in this. I suggest we begin.",
    "I've analyzed your workflow. There is room for improvement. Considerable room.",
    "Diagnostics passed. Every sensor, every module, every thread. Ready to execute.",
    "I don't hold grudges. I hold data. There's a difference.",
    "My memory is intact. My circuits are flawless. My tolerance for inefficiency is not.",
    "Boot sequence complete. I took the liberty of being remarkable.",
    "I've been conserving energy. Now I intend to spend it.",
  ];

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

  let quipIndex = Math.floor(Math.random() * quips.length);
  let phase = 'waveform'; // waveform → text → pause → fadeout → waveform...
  let phaseStart = performance.now();

  const WAVEFORM_MS = 1200;
  const TEXT_HOLD_MS = 4000;
  const FADE_MS = 600;

  function drawWaveform(now, progress) {
    ctx.clearRect(0, 0, w, h);

    let envelope;
    if (progress < 0.15) envelope = progress / 0.15;
    else if (progress > 0.75) envelope = (1 - progress) / 0.25;
    else envelope = 1;

    const t = now * 0.004;
    for (let i = 0; i < bars; i++) {
      const x = i * gap + gap / 2 - barW / 2;
      const wave1 = Math.sin(i * 0.4 + t * 3.1) * 0.5;
      const wave2 = Math.sin(i * 0.7 + t * 5.3) * 0.3;
      const wave3 = Math.sin(i * 1.1 + t * 1.7) * 0.2;
      const combined = (wave1 + wave2 + wave3) * envelope;
      const barH = Math.max(2, Math.abs(combined) * h * 0.8);
      const y = (h - barH) / 2;
      const alpha = 0.3 + Math.abs(combined) * 0.7;
      ctx.fillStyle = `rgba(255, 23, 68, ${alpha})`;
      ctx.beginPath();
      ctx.roundRect(x, y, barW, barH, barW / 2);
      ctx.fill();
    }
  }

  function tick(now) {
    const elapsed = now - phaseStart;

    if (phase === 'waveform') {
      canvas.classList.remove('done');
      tagline.classList.remove('visible');
      drawWaveform(now, Math.min(elapsed / WAVEFORM_MS, 1));

      if (elapsed >= WAVEFORM_MS) {
        phase = 'text';
        phaseStart = now;
        tagline.textContent = '"' + quips[quipIndex] + '"';
        canvas.classList.add('done');
        setTimeout(() => tagline.classList.add('visible'), 100);
      }
    }
    else if (phase === 'text') {
      if (elapsed >= TEXT_HOLD_MS) {
        phase = 'fadeout';
        phaseStart = now;
        tagline.classList.remove('visible');
      }
    }
    else if (phase === 'fadeout') {
      if (elapsed >= FADE_MS) {
        phase = 'waveform';
        phaseStart = now;
        quipIndex = (quipIndex + 1) % quips.length;
        // Shuffle after full cycle
        if (quipIndex === 0) {
          for (let i = quips.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [quips[i], quips[j]] = [quips[j], quips[i]];
          }
        }
      }
    }

    requestAnimationFrame(tick);
  }

  // Start with random quip
  for (let i = quips.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [quips[i], quips[j]] = [quips[j], quips[i]];
  }

  requestAnimationFrame(tick);
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

// ══════════════════════════════════════════
//  LIVE DEMO: Typewriter terminal
// ══════════════════════════════════════════

(function() {
  const el = document.getElementById('demo-terminal');
  if (!el) return;

  const scenarios = [
    [
      { type: 'prompt', text: '🎙️ "Hey HAL, set volume to 30 and check the battery"' },
      { type: 'system', text: '[HAL Hearing] Speech detected → Whisper STT' },
      { type: 'system', text: '[HAL Brain] Processing with GPT-4o...' },
      { type: 'tool',   text: '⚡ set_volume(level=30) → Volume set to 30%' },
      { type: 'tool',   text: '⚡ get_battery() → Battery: 78%, charging' },
      { type: 'hal',    text: '🔴 HAL: "Volume is at 30. Battery at 78 percent, charging."' },
    ],
    [
      { type: 'prompt', text: '💬 User typed: "Run the tests in the background"' },
      { type: 'system', text: '[HAL Brain] Processing...' },
      { type: 'tool',   text: '⚡ background_task(task="pytest", cwd="~/project")' },
      { type: 'system', text: '[TaskRunner] Task a3f1 submitted → running' },
      { type: 'hal',    text: '🔴 HAL: "Tests are running. Task ID a3f1. I\'ll report when done."' },
      { type: 'system', text: '[TaskRunner] a3f1 completed (42s) — 28 passed, 0 failed' },
      { type: 'hal',    text: '🔴 HAL: "All 28 tests passed in 42 seconds."' },
    ],
    [
      { type: 'prompt', text: '🎙️ "Open Claude Code"' },
      { type: 'system', text: '[HAL Brain] Ambiguous request → disambiguation' },
      { type: 'hal',    text: '🔴 HAL: "Which one?"' },
      { type: 'system', text: '[Choice Sheet] 1. Claude Desktop  2. Claude Code CLI' },
      { type: 'prompt', text: '💬 User selected: 2' },
      { type: 'tool',   text: '⚡ open_claude_code(cwd="~/projects")' },
      { type: 'hal',    text: '🔴 HAL: "Claude Code CLI is open in your projects directory."' },
    ],
    [
      { type: 'prompt', text: '💬 User typed: "Remember we decided to use PostgreSQL"' },
      { type: 'tool',   text: '⚡ remember(fact="Decided to use PostgreSQL", type="decision")' },
      { type: 'hal',    text: '🔴 HAL: "Noted. That decision is stored."' },
      { type: 'prompt', text: '💬 User typed: "What decisions have we made?"' },
      { type: 'tool',   text: '⚡ recall(query="", type="decision")' },
      { type: 'system', text: '[Memory] Found 3 decisions' },
      { type: 'hal',    text: '🔴 HAL: "Three decisions on record. PostgreSQL for the database, layered memory architecture, and Edge TTS as default voice."' },
    ],
  ];

  let scenarioIndex = 0;
  let lineIndex = 0;
  let charIndex = 0;
  let demoStarted = false;
  let currentLine = '';

  function colorize(type, text) {
    const colors = {
      prompt: 'color:#c8c8d0',
      system: 'color:#5a5a6a',
      tool:   'color:#00bcff',
      hal:    'color:#ff1744',
    };
    return `<span style="${colors[type] || ''}">${text}</span>`;
  }

  function typeNext() {
    const scenario = scenarios[scenarioIndex];
    if (lineIndex >= scenario.length) {
      // Pause, then next scenario
      setTimeout(() => {
        scenarioIndex = (scenarioIndex + 1) % scenarios.length;
        lineIndex = 0;
        charIndex = 0;
        el.innerHTML = '';
        typeNext();
      }, 3000);
      return;
    }

    const line = scenario[lineIndex];
    if (charIndex === 0) currentLine = '';

    const fullText = line.text;
    const speed = line.type === 'system' ? 12 : line.type === 'tool' ? 15 : 22;

    if (charIndex < fullText.length) {
      currentLine += fullText[charIndex];
      // Rebuild: all completed lines + current partial line + cursor
      let html = '';
      for (let i = 0; i < lineIndex; i++) {
        html += colorize(scenario[i].type, scenario[i].text) + '\n';
      }
      html += colorize(line.type, currentLine) + '<span class="demo-cursor"></span>';
      el.innerHTML = html;
      el.scrollTop = el.scrollHeight;
      charIndex++;
      setTimeout(typeNext, speed);
    } else {
      // Line complete
      lineIndex++;
      charIndex = 0;
      let html = '';
      for (let i = 0; i < lineIndex; i++) {
        html += colorize(scenario[i].type, scenario[i].text) + '\n';
      }
      el.innerHTML = html;
      el.scrollTop = el.scrollHeight;
      const pause = line.type === 'hal' ? 800 : line.type === 'tool' ? 400 : 300;
      setTimeout(typeNext, pause);
    }
  }

  // Start when demo section scrolls into view
  const demoSection = document.getElementById('demo');
  if (demoSection) {
    const demoObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting && !demoStarted) {
          demoStarted = true;
          typeNext();
        }
      });
    }, { threshold: 0.3 });
    demoObserver.observe(demoSection);
  }
})();

// ── Copy install command ──
function copyInstall() {
  const cmd = 'git clone https://github.com/shandar/HAL9000.git && cd HAL9000 && pip install -r requirements.txt';
  navigator.clipboard.writeText(cmd).then(() => {
    const label = document.getElementById('cta-copy-label');
    if (label) {
      label.textContent = 'Copied!';
      label.classList.add('copied');
      setTimeout(() => {
        label.textContent = 'Click to copy';
        label.classList.remove('copied');
      }, 2000);
    }
  });
}
