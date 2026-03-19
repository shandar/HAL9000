let isRunning = false;
let eventSource = null;
let videoActive = false;
let chatSending = false;

// ── DOM refs ───────────────────────────────────
const halPanel = document.getElementById('hal-panel');
const halImage = document.getElementById('hal-image');
const halStatusLabel = document.getElementById('hal-status-label');
const powerBtn = document.getElementById('power-img-btn');
// subsystems now live on HAL image (halControls)
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const chatMicBtn = document.getElementById('chat-mic-btn');
const typingIndicator = document.getElementById('typing-indicator');
// Terminal removed — logs integrated into chat
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const camPanel = document.getElementById('cam-panel');
const camVideo = document.getElementById('cam-video');
const camHud = document.getElementById('cam-hud');
const camOfflineLabel = document.getElementById('cam-offline-label');
const camSpeaking = document.getElementById('cam-speaking');
const camTimestamp = document.getElementById('cam-timestamp');
const bottomTime = document.getElementById('bottom-time');
const voiceSelector = document.getElementById('voice-selector');
const waveformWrap = document.getElementById('waveform-wrap');
const waveformCanvas = document.getElementById('waveform-canvas');
const halControls = document.getElementById('hal-controls');
const wfCtx = waveformCanvas.getContext('2d');

// ── Toast Notifications ─────────────────────
const toastContainer = document.getElementById('toastContainer');

function showToast(type, title, message, duration = 5000) {
  const icons = { error: '\u26A0', warn: '\u26A0', info: '\u24D8' };
  const toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.innerHTML =
    '<span class="toast-icon">' + (icons[type] || '\u24D8') + '</span>' +
    '<div class="toast-body">' +
      '<div class="toast-title">' + escapeHtml(title) + '</div>' +
      '<div>' + escapeHtml(message) + '</div>' +
    '</div>' +
    '<button class="toast-close" onclick="dismissToast(this.parentElement)">\u2715</button>';
  toastContainer.appendChild(toast);

  // Auto-dismiss
  if (duration > 0) {
    setTimeout(() => dismissToast(toast), duration);
  }

  // Keep max 5 toasts
  while (toastContainer.children.length > 5) {
    toastContainer.removeChild(toastContainer.firstChild);
  }
}

function dismissToast(el) {
  if (!el || !el.parentElement) return;
  el.classList.add('removing');
  setTimeout(() => { if (el.parentElement) el.parentElement.removeChild(el); }, 300);
}

// Detect errors from log entries and show toasts
function checkForErrors(entries) {
  entries.forEach(entry => {
    const text = (entry.text || '').toLowerCase();
    if (entry.role === 'system' && (text.includes('error') || text.includes('failed'))) {
      showToast('error', 'System Error', entry.text);
    } else if (entry.role === 'tool' && text.startsWith('[error]')) {
      showToast('warn', 'Tool Failed', entry.text);
    }
  });
}

// ── Web Audio API for real waveform ──────────
let audioCtx = null;
let analyser = null;
let freqData = null;
let lastSpeechId = 0;

// ── API helper ─────────────────────────────────
async function api(path, method = 'GET', body = null) {
  const opts = { method };
  if (body) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api/' + path, opts);
  return res.json();
}

// ── Power / subsystem controls ─────────────────
async function togglePower() {
  if (powerBtn) {
    powerBtn.style.opacity = '0.4';
    powerBtn.style.pointerEvents = 'none';
  }
  const action = isRunning ? 'stop' : 'start';
  showToast('info', action === 'start' ? 'Booting' : 'Shutting Down',
    action === 'start' ? 'Initializing subsystems...' : 'Saving session...', 3000);
  const status = await api(action, 'POST');
  applyStatus(status);
  if (powerBtn) {
    powerBtn.style.opacity = '';
    powerBtn.style.pointerEvents = '';
  }
}

async function toggleSub(name) {
  if (!isRunning) return;
  const status = await api('toggle/' + name, 'POST');
  applyStatus(status);
}

async function toggleBlur() {
  if (!isRunning) return;
  try {
    const result = await api('blur', 'POST');
    const btn = document.getElementById('blur-toggle');
    const label = document.getElementById('blur-label');
    if (result.blur) {
      btn.classList.add('active');
      label.textContent = 'Blur On';
    } else {
      btn.classList.remove('active');
      label.textContent = 'Blur';
    }
  } catch(e) { console.error('Blur toggle failed:', e); }
}

async function switchVoice(provider) {
  if (!isRunning) return;
  voiceSelector.querySelectorAll('.tb-voice-opt').forEach(o => o.classList.add('switching'));
  const result = await api('voice_provider', 'POST', { provider });
  voiceSelector.querySelectorAll('.tb-voice-opt').forEach(o => {
    o.classList.remove('switching');
    o.classList.toggle('active', o.dataset.provider === result.provider);
  });
}

// ── Claude Code — open embedded terminal (fallback: external terminal) ─────
async function openClaudeCode() {
  if (!isRunning) return;
  const claudeBtn = document.querySelector('.claude-btn');
  claudeBtn.style.opacity = '0.4';
  claudeBtn.style.pointerEvents = 'none';
  try {
    // Try embedded terminal first (macOS/Linux)
    openTerminal();
    showToast('info', 'Terminal', 'Terminal opened', 2000);
  } catch (err) {
    // Fallback: open external terminal (Windows or if WebSocket fails)
    try {
      const result = await fetch('/api/open_claude', { method: 'POST' });
      const data = await result.json();
      if (data.error) {
        showToast('error', 'Claude Code', data.error);
      } else {
        showToast('info', 'Claude Code', 'External terminal opened', 2000);
      }
    } catch (err2) {
      showToast('error', 'Claude Code', err2.message);
    }
  } finally {
    setTimeout(() => {
      claudeBtn.style.opacity = '';
      claudeBtn.style.pointerEvents = '';
    }, 3000);
  }
}

// ── Chat — send typed message with token streaming ──
async function sendChat() {
  const text = chatInput.value.trim();
  if (!text || chatSending) return;
  if (!isRunning) {
    addChatMsg('system', 'Activate HAL first');
    return;
  }

  chatInput.value = '';
  chatInput.style.height = 'auto';
  chatSending = true;
  setStatus('thinking', 'HAL is thinking...');

  // Block SSE from rendering duplicates during streaming
  streamingUntil = (Date.now() / 1000) + 300; // 5 min — refined in finally block

  // Add user message immediately
  addChatMsg('user', text);

  // Create streaming HAL message bubble with blinking cursor
  const halDiv = document.createElement('div');
  halDiv.className = 'msg hal';
  halDiv.innerHTML = '<span class="msg-label">HAL</span><span class="msg-stream-text"></span><span class="msg-cursor"></span>';
  // Remove cursor from any previous HAL message
  chatMessages.querySelectorAll('.msg-cursor').forEach(c => c.remove());
  chatMessages.appendChild(halDiv);
  const streamSpan = halDiv.querySelector('.msg-stream-text');
  const streamCursor = halDiv.querySelector('.msg-cursor');
  chatMessages.scrollTop = chatMessages.scrollHeight;


  try {
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));

          if (event.type === 'token') {
            fullText += event.text;
            streamSpan.textContent = fullText;
            chatMessages.scrollTop = chatMessages.scrollHeight;
            setStatus('speaking', 'HAL is responding...');

          } else if (event.type === 'tool') {
            const name = event.name;
            const summary = (event.result?.result || event.result?.error || '').substring(0, 150);
            addChatMsg('tool', `[${name}] ${summary}`);
            setStatus('thinking', `Running ${name}...`);
          } else if (event.type === 'done') {
            // Final — replace stream content with final text
            const finalText = fullText || event.text || '';
            if (event.text && !fullText) {
              streamSpan.textContent = event.text;
            }
            // Check for choices in the final text
            const parsed = parseChoices(finalText);
            if (parsed && parsed.choices.length >= 2 && parsed.choices.length <= 10) {
              showChoiceSheet(parsed.title, parsed.choices);
              streamSpan.textContent = parsed.title || finalText.split(/\n/)[0] || '';
            }
          }
        } catch (e) { /* skip malformed events */ }
      }
    }

  } catch (err) {
    showToast('error', 'Connection Error', err.message);
  } finally {
    // Fade out the streaming cursor
    if (streamCursor && streamCursor.parentElement) {
      streamCursor.classList.add('fade-out');
      setTimeout(() => streamCursor.remove(), 500);
    }
    // Mark: skip SSE entries up to 2 seconds from now (covers server log delay)
    streamingUntil = (Date.now() / 1000) + 2;
    chatSending = false;
    setStatus(null);
    chatInput.focus();
  }
}

// ── Status pill — unified feedback for all actions ──
const statusPill = document.getElementById('chat-status-pill');
const statusPillText = document.getElementById('chat-status-text');

function setStatus(phase, text) {
  // phase: null (hide), 'recording', 'transcribing', 'thinking', 'speaking', 'sending'
  if (!phase) {
    statusPill.classList.remove('active', 'recording', 'transcribing', 'thinking', 'speaking');
    chatInput.placeholder = 'Message HAL...';
    chatInput.disabled = false;
    chatSendBtn.disabled = false;
    chatMicBtn.disabled = false;
    chatMicBtn.style.opacity = '';
    chatMicBtn.style.pointerEvents = '';
    chatMicBtn.classList.remove('listening', 'transcribing');
    return;
  }

  statusPill.className = 'chat-status-pill active ' + phase;
  statusPillText.textContent = text || phase;
  chatInput.placeholder = text || phase;
  chatInput.disabled = true;
  chatSendBtn.disabled = true;
  chatMicBtn.disabled = true;
  chatMicBtn.style.opacity = phase === 'recording' ? '' : '0.3';
  chatMicBtn.style.pointerEvents = 'none';
}

// ── Browser-side mic recording ─────────────────
let micRecording = false;
let micStream = null;
let micProcessor = null;
let micSource = null;
let micAnalyser = null;
let micChunks = [];
let micSilenceStart = 0;
let micSampleRate = 16000;
let wfMicActive = false;
const MIC_SILENCE_THRESHOLD = 0.015;  // normalized RMS
const MIC_SILENCE_DURATION = 1500;    // ms before auto-stop
const MIC_MAX_DURATION = 30000;       // 30s max recording
let micTimeout = null;

async function voiceInput() {
  if (chatSending) return;
  if (!isRunning) {
    addChatMsg('system', 'Activate HAL first');
    return;
  }

  // Stop HAL speaking if currently playing audio
  if (currentSource || wfSpeaking) {
    if (currentSource) { try { currentSource.stop(); } catch(e) {} currentSource = null; }
    wfSpeaking = false;
    waveformWrap.classList.remove('active');
    fetch('/api/speech_done', { method: 'POST' }).catch(() => {});
  }

  // Toggle: if already recording, stop
  if (micRecording) {
    stopMicRecording();
    return;
  }

  // Start recording
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000 }
    });
  } catch (err) {
    if (err.name === 'NotAllowedError') {
      showToast('error', 'Mic Denied', 'Please allow microphone access in your browser settings', 4000);
    } else if (err.name === 'NotFoundError') {
      showToast('error', 'No Mic', 'No microphone found on this device', 3000);
    } else {
      showToast('error', 'Mic Error', err.message, 3000);
    }
    return;
  }

  micRecording = true;
  micChunks = [];
  micSilenceStart = 0;

  // Create audio context for recording
  ensureAudioCtx();
  if (audioCtx.state === 'suspended') await audioCtx.resume();
  micSampleRate = audioCtx.sampleRate;

  micSource = audioCtx.createMediaStreamSource(micStream);
  micAnalyser = audioCtx.createAnalyser();
  micAnalyser.fftSize = 128;
  micAnalyser.smoothingTimeConstant = 0.75;

  // Use ScriptProcessorNode for PCM capture
  micProcessor = audioCtx.createScriptProcessor(4096, 1, 1);
  micProcessor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    micChunks.push(new Float32Array(input));

    // Silence detection
    let sum = 0;
    for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
    const rms = Math.sqrt(sum / input.length);

    if (rms < MIC_SILENCE_THRESHOLD) {
      if (!micSilenceStart) micSilenceStart = Date.now();
      else if (Date.now() - micSilenceStart > MIC_SILENCE_DURATION && micChunks.length > 3) {
        stopMicRecording(); // auto-stop after 1.5s silence
      }
    } else {
      micSilenceStart = 0;
    }
  };

  micSource.connect(micAnalyser);
  micSource.connect(micProcessor);
  micProcessor.connect(audioCtx.destination);

  // Drive waveform from mic input
  wfMicActive = true;
  waveformWrap.classList.add('active');

  // UI feedback
  chatMicBtn.classList.add('listening');
  setStatus('recording', 'Recording... click mic to stop');

  // Safety timeout
  micTimeout = setTimeout(() => {
    if (micRecording) stopMicRecording();
  }, MIC_MAX_DURATION);
}

async function stopMicRecording() {
  if (!micRecording) return;
  micRecording = false;
  clearTimeout(micTimeout);

  // Disconnect audio nodes
  if (micProcessor) { micProcessor.disconnect(); micProcessor = null; }
  if (micSource) { micSource.disconnect(); micSource = null; }
  if (micStream) {
    micStream.getTracks().forEach(t => t.stop());
    micStream = null;
  }

  // Stop waveform and clear residual bars
  wfMicActive = false;
  micAnalyser = null;
  waveformWrap.classList.remove('active');
  const _cvs = document.getElementById('waveformCanvas');
  if (_cvs) {
    const _ctx = _cvs.getContext('2d');
    _ctx.clearRect(0, 0, _cvs.width, _cvs.height);
  }
  chatMicBtn.classList.remove('listening');

  if (micChunks.length < 2) {
    setStatus(null);
    showToast('info', 'Too Short', 'Recording was too short — try again', 2000);
    return;
  }

  // Encode to WAV
  setStatus('transcribing', 'Transcribing...');
  chatMicBtn.classList.add('transcribing');

  const wavBlob = encodeWAV(micChunks, micSampleRate);
  micChunks = [];

  // Send to server for transcription
  try {
    const formData = new FormData();
    formData.append('audio', wavBlob, 'recording.wav');

    const resp = await fetch('/api/transcribe', { method: 'POST', body: formData });
    const data = await resp.json();

    chatMicBtn.classList.remove('transcribing');

    if (!data.text) {
      setStatus(null);
      showToast('info', 'No Speech', 'Nothing heard — try speaking more clearly', 3000);
      return;
    }

    // Show what was heard
    setStatus('thinking', 'Heard: ' + data.text.substring(0, 50));

    // Send transcription as chat text
    chatInput.value = data.text;
    setStatus(null);
    await sendChat();

  } catch (err) {
    chatMicBtn.classList.remove('transcribing');
    setStatus(null);
    showToast('error', 'Transcription Failed', err.message, 3000);
  }
}

// ── WAV encoder (pure JS, no dependencies) ──────
function encodeWAV(chunks, sampleRate) {
  // Concatenate all Float32 chunks
  let totalLength = 0;
  for (const c of chunks) totalLength += c.length;
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (const c of chunks) { merged.set(c, offset); offset += c.length; }

  // Convert Float32 [-1,1] to Int16
  const numSamples = merged.length;
  const buffer = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buffer);

  // WAV header
  const writeStr = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + numSamples * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);          // chunk size
  view.setUint16(20, 1, true);           // PCM format
  view.setUint16(22, 1, true);           // mono
  view.setUint32(24, sampleRate, true);   // sample rate
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true);           // block align
  view.setUint16(34, 16, true);          // bits per sample
  writeStr(36, 'data');
  view.setUint32(40, numSamples * 2, true);

  // PCM data
  let p = 44;
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, merged[i]));
    view.setInt16(p, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    p += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

// ── Slash Commands ──────────────────────────────
const cmdMenu = document.getElementById('cmd-menu');
let cmdSelectedIdx = -1;
let cmdVisible = false;

const COMMANDS = [
  // System
  { cmd: '/help',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>', desc: 'Show all available commands', cat: 'System' },
  { cmd: '/status',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>', desc: 'Show system status (vision, voice, provider)', cat: 'System' },
  { cmd: '/reset',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>', desc: 'Clear conversation history', cat: 'System' },
  { cmd: '/clear',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>', desc: 'Clear chat display (keeps memory)', cat: 'System' },
  { cmd: '/tools',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>', desc: 'List all 40 available tools', cat: 'System' },
  // Memory
  { cmd: '/memory',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>', desc: 'Show all stored memories', cat: 'Memory' },
  { cmd: '/remember',   icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>', desc: 'Remember something: /remember [fact]', cat: 'Memory' },
  { cmd: '/forget',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>', desc: 'Forget a memory: /forget [keyword]', cat: 'Memory' },
  { cmd: '/save',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/></svg>', desc: 'Save current session context', cat: 'Memory' },
  // Voice & Vision
  { cmd: '/voice',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 010 14.14"/></svg>', desc: 'Switch voice: /voice edge | elevenlabs | local', cat: 'Voice' },
  { cmd: '/mute',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>', desc: 'Mute HAL voice output', cat: 'Voice' },
  { cmd: '/unmute',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/></svg>', desc: 'Unmute HAL voice output', cat: 'Voice' },
  { cmd: '/vision',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>', desc: 'Toggle camera on/off', cat: 'Vision' },
  { cmd: '/screenshot',icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="13" r="3"/><path d="M12 7v.01"/></svg>', desc: 'Take a screenshot of your screen', cat: 'Vision' },
  // Apps & System Control
  { cmd: '/open',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 3l14 9-14 9V3z"/></svg>', desc: 'Open an app: /open Safari', cat: 'Apps' },
  { cmd: '/quit',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>', desc: 'Quit an app: /quit Safari', cat: 'Apps' },
  { cmd: '/apps',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>', desc: 'List running applications', cat: 'Apps' },
  { cmd: '/volume',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/></svg>', desc: 'Get or set volume: /volume 50', cat: 'Control' },
  { cmd: '/brightness', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/></svg>', desc: 'Get or set brightness: /brightness 80', cat: 'Control' },
  { cmd: '/battery',    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="6" width="18" height="12" rx="2"/><line x1="23" y1="13" x2="23" y2="11"/></svg>', desc: 'Show battery status', cat: 'Control' },
  { cmd: '/wifi',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.55a11 11 0 0114.08 0"/><path d="M1.42 9a16 16 0 0121.16 0"/><path d="M8.53 16.11a6 6 0 016.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>', desc: 'Show current WiFi network', cat: 'Control' },
  { cmd: '/time',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>', desc: 'Show current date and time', cat: 'Control' },
  { cmd: '/notify',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>', desc: 'Send notification: /notify [message]', cat: 'Control' },
  { cmd: '/clipboard',  icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/></svg>', desc: 'Read clipboard contents', cat: 'Control' },
  // Claude Code & Tasks
  { cmd: '/claude',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>', desc: 'Open Claude Code terminal', cat: 'Claude' },
  { cmd: '/delegate',   icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>', desc: 'Delegate task: /delegate [task description]', cat: 'Claude' },
  { cmd: '/task',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>', desc: 'Run background task: /task [description]', cat: 'Claude' },
  { cmd: '/tasks',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/></svg>', desc: 'Show background tasks status', cat: 'Claude' },
  // Files & Web
  { cmd: '/files',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>', desc: 'List files: /files [path]', cat: 'Files' },
  { cmd: '/read',       icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>', desc: 'Read a file: /read [path]', cat: 'Files' },
  { cmd: '/search',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>', desc: 'Web search: /search [query]', cat: 'Web' },
  { cmd: '/fetch',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9"/></svg>', desc: 'Fetch webpage: /fetch [url]', cat: 'Web' },
  // Workspace
  { cmd: '/artifact',   icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>', desc: 'Create artifact: /artifact [code|html|mermaid] [title]', cat: 'Workspace' },
  { cmd: '/agents',     icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>', desc: 'Show orchestrated agents and conflicts', cat: 'Workspace' },
];

function showCmdMenu(filter) {
  const q = (filter || '').toLowerCase();
  const filtered = q === '/'
    ? COMMANDS
    : COMMANDS.filter(c => c.cmd.includes(q) || c.desc.toLowerCase().includes(q.replace('/', '')));

  if (filtered.length === 0) { hideCmdMenu(); return; }

  cmdSelectedIdx = 0;
  cmdVisible = true;

  // Group by category
  let html = '<div class="cmd-menu-header">Commands — type to filter</div>';
  let lastCat = '';
  let idx = 0;
  filtered.forEach((c) => {
    if (c.cat !== lastCat) {
      html += '<div style="padding:4px 12px 2px;font-size:0.55rem;font-weight:700;letter-spacing:0.15em;text-transform:uppercase;color:#555;border-top:1px solid #1a1a24;margin-top:2px;">' + (c.cat || '') + '</div>';
      lastCat = c.cat;
    }
    html += '<div class="cmd-item ' + (idx === 0 ? 'selected' : '') + '" data-idx="' + idx + '" onclick="execCmd(\'' + c.cmd + '\')" onmouseenter="cmdSelect(' + idx + ')">' +
      '<div class="cmd-item-icon">' + c.icon + '</div>' +
      '<div class="cmd-item-text">' +
        '<div class="cmd-item-name"><span>/</span>' + c.cmd.slice(1) + '</div>' +
        '<div class="cmd-item-desc">' + c.desc + '</div>' +
      '</div>' +
    '</div>';
    idx++;
  });
  cmdMenu.innerHTML = html;

  cmdMenu.classList.add('active');
}

function hideCmdMenu() {
  cmdMenu.classList.remove('active');
  cmdVisible = false;
  cmdSelectedIdx = -1;
}

function cmdSelect(idx) {
  cmdSelectedIdx = idx;
  cmdMenu.querySelectorAll('.cmd-item').forEach((el, i) => {
    el.classList.toggle('selected', i === idx);
  });
}

async function execCmd(cmd) {
  hideCmdMenu();
  chatInput.value = '';
  chatInput.style.height = 'auto';

  const parts = cmd.trim().split(/\s+/);
  const base = parts[0].toLowerCase();
  const arg = parts.slice(1).join(' ');

  // Route to chat for commands that need HAL's brain
  const chatCmds = {
    '/memory':    'list all my memories',
    '/save':      'save session',
    '/screenshot':'take a screenshot',
    '/battery':   'what is my battery status',
    '/wifi':      'what wifi am I connected to',
    '/time':      'what time is it',
    '/clipboard': 'read my clipboard',
    '/apps':      'list running applications',
    '/agents':    'list agents and check conflicts',
  };

  // Commands with arguments → send to chat
  const argChatCmds = {
    '/remember':  'remember that ',
    '/forget':    'forget ',
    '/open':      'open application ',
    '/quit':      'quit application ',
    '/delegate':  'delegate to claude code: ',
    '/task':      'run this in the background: ',
    '/files':     'list files in ',
    '/read':      'read file ',
    '/search':    'search the web for ',
    '/fetch':     'fetch the webpage ',
    '/notify':    'send a notification saying ',
    '/artifact':  'create a code artifact titled ',
  };

  if (chatCmds[base]) {
    chatInput.value = chatCmds[base];
    await sendChat();
  } else if (argChatCmds[base]) {
    if (arg) {
      chatInput.value = argChatCmds[base] + arg;
      await sendChat();
    } else {
      addChatMsg('system', 'Usage: ' + base + ' [argument]. Example: ' + base + ' test');
    }
  } else {
    // Direct commands (no brain needed)
    switch (base) {
      case '/help': {
        let cats = {};
        COMMANDS.forEach(c => { (cats[c.cat] = cats[c.cat] || []).push(c); });
        let helpText = '';
        for (const [cat, cmds] of Object.entries(cats)) {
          helpText += '\n' + cat + ':\n';
          cmds.forEach(c => { helpText += '  ' + c.cmd + ' — ' + c.desc + '\n'; });
        }
        addChatMsg('system', helpText);
        break;
      }
      case '/status': {
        const st = await api('status');
        addChatMsg('system',
          'Running: ' + st.running + ' | Vision: ' + st.vision + ' | Voice: ' + st.voice + ' (' + st.voice_provider + ') | Processing: ' + st.processing
        );
        break;
      }
      case '/reset':
        await api('chat', 'POST', { text: 'reset' });
        chatMessages.innerHTML = '';
        chatInitialized = false;
        lastLogTime = 0;
        addChatMsg('system', 'Conversation cleared.');
        break;
      case '/clear':
        chatMessages.innerHTML = '';
        chatInitialized = false;
        addChatMsg('system', 'Chat display cleared.');
        break;
      case '/claude':
        openClaudeCode();
        break;
      case '/tools': {
        try {
          const data = await api('tools');
          if (data && data.tools) {
            const grouped = {};
            data.tools.forEach(t => {
              const cat = t.name.startsWith('get_') || t.name.startsWith('set_') ? 'System' :
                t.name.includes('file') || t.name.includes('search_files') ? 'Files' :
                t.name.includes('app') || t.name.includes('open_') || t.name.includes('quit_') ? 'Apps' :
                t.name.includes('web') || t.name.includes('fetch') ? 'Web' :
                t.name.includes('remember') || t.name.includes('recall') || t.name.includes('forget') || t.name.includes('memory') || t.name.includes('session') ? 'Memory' :
                t.name.includes('claude') || t.name.includes('delegate') || t.name.includes('task') || t.name.includes('agent') || t.name.includes('orchestrate') || t.name.includes('conflict') ? 'Claude & Tasks' :
                t.name.includes('artifact') ? 'Workspace' :
                t.name.includes('shell') ? 'Shell' :
                t.name.includes('screenshot') ? 'System' :
                'Other';
              if (!grouped[cat]) grouped[cat] = [];
              grouped[cat].push(t);
            });
            let output = `${data.count} tools registered:\n`;
            Object.keys(grouped).sort().forEach(cat => {
              output += `\n${cat}:\n`;
              grouped[cat].forEach(t => {
                output += `  ${t.name} — ${t.description}\n`;
              });
            });
            addChatMsg('system', output);
          }
        } catch(e) { addChatMsg('system', 'Failed to fetch tools: ' + e.message); }
        break;
      }
      case '/tasks': {
        const tasks = await api('tasks');
        if (!tasks || tasks.length === 0) {
          addChatMsg('system', 'No background tasks.');
        } else {
          let taskText = tasks.length + ' task(s):\n';
          tasks.forEach(t => { taskText += '  [' + t.status + '] ' + t.id + ': ' + t.description.substring(0, 60) + '\n'; });
          addChatMsg('system', taskText);
        }
        break;
      }
      case '/voice':
        if (arg && ['edge', 'elevenlabs', 'local'].includes(arg)) {
          await switchVoice(arg);
          addChatMsg('system', 'Voice switched to ' + arg);
        } else {
          addChatMsg('system', 'Usage: /voice edge | /voice elevenlabs | /voice local');
        }
        break;
      case '/mute':
        if (isRunning) { await toggleSub('voice'); addChatMsg('system', 'Voice muted.'); }
        break;
      case '/unmute':
        if (isRunning) { await toggleSub('voice'); addChatMsg('system', 'Voice unmuted.'); }
        break;
      case '/vision':
        await toggleSub('vision');
        break;
      case '/volume':
        if (arg) {
          chatInput.value = 'set volume to ' + arg;
          await sendChat();
        } else {
          chatInput.value = 'what is my current volume';
          await sendChat();
        }
        break;
      case '/brightness':
        if (arg) {
          chatInput.value = 'set brightness to ' + arg;
          await sendChat();
        } else {
          chatInput.value = 'what is my current brightness';
          await sendChat();
        }
        break;
      default:
        addChatMsg('system', 'Unknown command: ' + base + '. Type /help for available commands.');
    }
  }
}

// Chat input: Enter to send, Shift+Enter for newline, / for commands
chatInput.addEventListener('keydown', (e) => {
  // Command menu navigation
  if (cmdVisible) {
    const items = cmdMenu.querySelectorAll('.cmd-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      cmdSelect(Math.min(cmdSelectedIdx + 1, items.length - 1));
      items[cmdSelectedIdx]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      cmdSelect(Math.max(cmdSelectedIdx - 1, 0));
      items[cmdSelectedIdx]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (items[cmdSelectedIdx]) {
        let name = items[cmdSelectedIdx].querySelector('.cmd-item-name').textContent.trim();
        if (name.startsWith('/')) name = name.slice(1);
        execCmd('/' + name + (chatInput.value.includes(' ') ? ' ' + chatInput.value.split(' ').slice(1).join(' ') : ''));
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      hideCmdMenu();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      if (items[cmdSelectedIdx]) {
        let tname = items[cmdSelectedIdx].querySelector('.cmd-item-name').textContent.trim();
        if (tname.startsWith('/')) tname = tname.slice(1);
        chatInput.value = '/' + tname + ' ';
        chatInput.dispatchEvent(new Event('input'));
      }
    }
    return;
  }

  // Normal chat
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    const val = chatInput.value.trim();
    if (val.startsWith('/')) {
      execCmd(val);
    } else {
      sendChat();
    }
  }
});

chatInput.addEventListener('input', () => {
  chatInput.style.overflow = 'hidden';
  chatInput.style.height = 'auto';
  const h = Math.min(chatInput.scrollHeight, 80);
  chatInput.style.height = h + 'px';
  // Only allow scroll when content exceeds max-height
  if (chatInput.scrollHeight > 80) chatInput.style.overflowY = 'auto';

  // Show/hide command menu
  const val = chatInput.value;
  if (val.startsWith('/') && val.length <= 25) {
    showCmdMenu(val);
  } else {
    hideCmdMenu();
  }
});

// ── Choice Sheet ─────────────────────────────────
const choiceBackdrop = document.getElementById('choice-backdrop');
const choiceSheet = document.getElementById('choice-sheet');
const choiceTitle = document.getElementById('choice-title');
const choiceItems = document.getElementById('choice-items');

function showChoiceSheet(title, choices) {
  choiceTitle.textContent = title || 'Select an option';
  choiceItems.innerHTML = '';

  choices.forEach((choice, i) => {
    const item = document.createElement('div');
    item.className = 'choice-item';
    item.innerHTML =
      '<span class="choice-item-num">' + (i + 1) + '</span>' +
      '<div><div class="choice-item-text">' + escapeHtml(choice.label) + '</div>' +
      (choice.desc ? '<div class="choice-item-desc">' + escapeHtml(choice.desc) + '</div>' : '') +
      '</div>';
    item.onclick = () => selectChoice(choice.label, i + 1);
    choiceItems.appendChild(item);
  });

  // Animate in
  requestAnimationFrame(() => {
    choiceBackdrop.classList.add('active');
    choiceSheet.classList.add('active');
  });
}

function dismissChoiceSheet() {
  choiceSheet.classList.remove('active');
  choiceBackdrop.classList.remove('active');
}

// Auto-dismiss on page load (in case stale from previous session)
dismissChoiceSheet();

function selectChoice(label, num) {
  dismissChoiceSheet();
  // Send the choice as a user message
  chatInput.value = String(num);
  sendChat();
}

/**
 * Detect if HAL's message contains numbered choices.
 * Patterns detected:
 *   - "1. Option text" / "2. Option text" (numbered list)
 *   - "One, Option text" / "Two, Option text" (spoken numbers)
 *   - Lines starting with a number followed by period/colon/comma
 * Returns { title, choices[] } or null.
 */
function parseChoices(text) {
  /*
   * Detect DISAMBIGUATION choices only — not informational lists.
   * Heuristics:
   *  - Items must be SHORT labels (< 80 chars each)
   *  - 2–6 items (disambiguation, not educational)
   *  - Numbers must start at 1 and be sequential
   *  - Title (text before list) should be brief (< 120 chars)
   *  - Items should NOT contain multiple sentences
   */

  function isDisambiguation(title, items) {
    // Too many items → probably informational content
    if (items.length > 6) return false;
    // Every item must be a short label (not a paragraph)
    const allShort = items.every(label => label.length < 80 && !label.includes('. '));
    if (!allShort) return false;
    // Title should be brief (a question or prompt, not a paragraph)
    if (title && title.length > 120) return false;
    return true;
  }

  // Try numbered list first (most common)
  const numMatches = [...text.matchAll(/(?:^|\n)\s*(\d+)[.):\-]\s+(.+)/g)];
  if (numMatches.length >= 2) {
    // Numbers must start at 1 and be sequential
    const nums = numMatches.map(m => parseInt(m[1]));
    if (nums[0] !== 1 || !nums.every((n, i) => n === i + 1)) return null;

    const firstIdx = text.indexOf(numMatches[0][0].trim());
    let title = text.substring(0, firstIdx).trim();
    title = title.replace(/[:\-]+$/, '').trim();

    const labels = numMatches.map(m => m[2].trim().replace(/[.?!]$/, ''));
    if (!isDisambiguation(title, labels)) return null;

    if (!title) title = 'Choose an option';
    const choices = labels.map(l => ({ label: l, desc: '' }));
    return { title, choices };
  }

  // Try spoken numbers: "One, ..." "Two, ..."
  const spokenMatches = [...text.matchAll(/(?:^|\n)\s*(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)[,.:]\s+(.+)/gi)];
  if (spokenMatches.length >= 2) {
    const firstIdx = text.indexOf(spokenMatches[0][0].trim());
    let title = text.substring(0, firstIdx).trim();
    title = title.replace(/[:\-]+$/, '').trim();

    const labels = spokenMatches.map(m => m[2].trim().replace(/[.?!]$/, ''));
    if (!isDisambiguation(title, labels)) return null;

    if (!title) title = 'Choose an option';
    const choices = labels.map(l => ({ label: l, desc: '' }));
    return { title, choices };
  }

  return null;
}

// ── Chat message rendering ─────────────────────
let chatInitialized = false;

function addChatMsg(role, text) {
  if (!chatInitialized) { chatMessages.innerHTML = ''; chatInitialized = true; }


  let displayText = text;

  // Check if HAL's message contains choices → show choice sheet + strip from bubble
  // Only for new messages, not initial page load replay
  if (role === 'hal' && lastLogTime > 0) {
    const parsed = parseChoices(text);
    if (parsed && parsed.choices.length >= 2 && parsed.choices.length <= 10) {
      showChoiceSheet(parsed.title, parsed.choices);
      // Strip the numbered list from the chat bubble — show only the title/question
      displayText = parsed.title || '';
      if (!displayText) displayText = text.split(/\n/)[0]; // fallback: first line
    }
  }

  const div = document.createElement('div');
  div.className = 'msg ' + role;

  const roleLabel = role === 'hal' ? 'HAL'
    : role === 'user' ? (window._halUserName || 'YOU')
    : role === 'tool' ? 'TOOL'
    : 'SYS';

  if (role === 'tool' || role === 'system') {
    div.innerHTML = '<span class="msg-label">' + roleLabel + '</span>' + escapeHtml(displayText);
  } else {
    div.innerHTML = '<span class="msg-label">' + roleLabel + '</span>' + formatMessage(displayText);
  }

  // Add blinking terminal cursor to HAL messages
  if (role === 'hal') {
    // Remove cursor from any previous HAL message
    const oldCursors = chatMessages.querySelectorAll('.msg-cursor');
    oldCursors.forEach(c => c.remove());
    // Add cursor to this message
    const cursor = document.createElement('span');
    cursor.className = 'msg-cursor';
    div.appendChild(cursor);
    // Fade out cursor after a delay
    setTimeout(() => { cursor.classList.add('fade-out'); }, 2000);
    setTimeout(() => { cursor.remove(); }, 2500);
  }

  chatMessages.appendChild(div);

  // Keep last 150 messages
  while (chatMessages.children.length > 150) {
    chatMessages.removeChild(chatMessages.firstChild);
  }
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

let lastLogTime = 0;
let streamingUntil = 0; // timestamp — skip SSE user/hal/tool entries until this time

function appendLogEntries(entries) {
  if (!entries.length) return;
  const now = Date.now() / 1000;
  entries.forEach(entry => {
    // Skip entries already rendered (dedup by timestamp)
    if (entry.time && entry.time <= lastLogTime) return;
    // During/after streaming, skip user+hal+tool entries (they were rendered by sendChat)
    if (entry.time && entry.time <= streamingUntil && (entry.role === 'user' || entry.role === 'hal' || entry.role === 'tool')) {
      if (entry.time) lastLogTime = entry.time; // advance time but don't render
      return;
    }
    addChatMsg(entry.role, entry.text);
  });
  const latest = entries[entries.length - 1];
  if (latest && latest.time) lastLogTime = latest.time;
}

const _escDiv = document.createElement('div');
function escapeHtml(str) {
  _escDiv.textContent = str;
  return _escDiv.innerHTML;
}

function formatMessage(text) {
  // Pre-process: split inline numbered lists into separate lines
  // Matches patterns like ". 2. " or ". 3) " mid-sentence
  text = text.replace(/\.\s+(\d+)[.):\-]\s+/g, '.\n$1. ');
  // Also handle start of text: "1. Item 2. Item"
  text = text.replace(/^(\d+)[.):\-]\s+/gm, '\n$1. ');

  const lines = text.split('\n');
  let html = '';
  let inList = false;

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed) {
      if (inList) { html += '</div>'; inList = false; }
      if (i > 0 && i < lines.length - 1) html += '<div style="height:6px"></div>';
      continue;
    }

    // Numbered list: "1. Item" or "1) Item"
    const numMatch = trimmed.match(/^(\d+)[.):\-]\s+(.+)/);
    // Bullet list: "- Item" or "* Item" or "• Item"
    const bulletMatch = trimmed.match(/^[-*•]\s+(.+)/);

    if (numMatch || bulletMatch) {
      if (!inList) { html += '<div class="msg-list">'; inList = true; }
      const itemText = numMatch ? numMatch[2] : bulletMatch[1];
      const num = numMatch ? numMatch[1] : '';
      html += '<div class="msg-list-item">';
      if (num) html += '<span class="msg-list-num">' + escapeHtml(num) + '</span>';
      else html += '<span class="msg-list-bullet"></span>';
      html += '<span>' + escapeHtml(itemText) + '</span></div>';
    } else {
      if (inList) { html += '</div>'; inList = false; }
      html += '<div>' + escapeHtml(trimmed) + '</div>';
    }
  }
  if (inList) html += '</div>';
  return html;
}

// ── Status application ─────────────────────────
function applyStatus(s) {
  isRunning = s.running;

  // Set user name for chat labels
  if (s.user_name) {
    window._halUserName = s.user_name.split(' ')[0].toUpperCase();
  }

  halImage.classList.toggle('off', !s.running);
  halImage.classList.toggle('active', s.running);
  halPanel.classList.toggle('active', s.running);
  halStatusLabel.textContent = s.running ? 'Online' : 'Offline';

  // Power button state is managed by the HAL image button handler below

  // Camera
  const shouldShowVideo = s.running && s.vision && s.has_camera;
  if (shouldShowVideo && !videoActive) {
    camVideo.src = '/api/video?' + Date.now();
    camVideo.style.display = 'block';
    camHud.style.display = 'block';
    camOfflineLabel.style.display = 'none';
    camPanel.classList.remove('inactive');
    videoActive = true;
    wfResize();
  } else if (!shouldShowVideo && videoActive) {
    camVideo.src = '';
    camVideo.style.display = 'none';
    camHud.style.display = 'none';
    camOfflineLabel.style.display = '';
    camPanel.classList.add('inactive');
    videoActive = false;
    wfResize();
  }

  camSpeaking.classList.toggle('active', !!s.speaking);

  // Blur button state
  const blurBtn = document.getElementById('blur-toggle');
  const blurLabel = document.getElementById('blur-label');
  if (blurBtn) {
    blurBtn.classList.toggle('active', !!s.blur);
    blurLabel.textContent = s.blur ? 'Blur On' : 'Blur';
  }

  // Trigger real audio playback when new speech arrives
  if (s.speech_id && s.speech_id > lastSpeechId) {
    playSpeechAudio(s.speech_id);
  }

  // Voice provider selector (toolbar)
  voiceSelector.classList.toggle('disabled', !s.running);
  if (s.voice_provider) {
    voiceSelector.querySelectorAll('.tb-voice-opt').forEach(o => {
      o.classList.toggle('active', o.dataset.provider === s.voice_provider);
    });
  }

  // Subsystem buttons (HAL image)
  const isBusy = !!s.processing;
  halControls.querySelectorAll('.hal-ctrl-btn').forEach(btn => {
    // Power button — always enabled, toggle on/off state
    if (btn.classList.contains('power-img-btn')) {
      btn.classList.toggle('on', s.running);
      btn.title = s.running ? 'Deactivate HAL' : 'Activate HAL';
      return;
    }
    // Claude button: disabled when not running OR when processing
    if (btn.classList.contains('claude-btn')) {
      btn.classList.toggle('disabled', !s.running || isBusy);
      return;
    }
    // Subsystem toggles: disabled when not running
    const sub = btn.dataset.sub;
    const enabled = s[sub];
    btn.classList.toggle('disabled', !s.running);
    btn.classList.toggle('on', enabled && s.running);
  });

  // Show processing state via unified status pill
  if (isBusy && !micRecording && !chatSending) {
    setStatus('thinking', 'HAL is processing...');
  } else if (!isBusy && !micRecording && !chatSending) {
    setStatus(null);
  }

}

// Terminal removed — all logs go to chat window

// ── Timestamps ─────────────────────────────────
const topBarDate = document.getElementById('top-bar-date');
function updateTimestamps() {
  const now = new Date();
  const ts = now.toISOString().replace('T', ' ').substring(0, 19);
  camTimestamp.textContent = ts;
  bottomTime.textContent = ts;
  // Top bar: day and date
  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  topBarDate.textContent = days[now.getDay()] + ' ' + now.getDate() + ' ' + months[now.getMonth()] + ' ' + now.getFullYear();
}
setInterval(updateTimestamps, 1000);
updateTimestamps();

// ── SSE ─────────────────────────────────────────
function connectSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource('/api/stream');

  eventSource.onopen = () => {
    statusDot.classList.add('connected');
    statusDot.classList.remove('disconnected');
    statusText.textContent = 'Connected';
  };

  // On first SSE message, skip audio playback for existing speech
  let sseFirstMessage = true;

  eventSource.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (e) { return; } // skip malformed SSE

    // On first message, sync lastSpeechId to avoid replaying old audio
    if (sseFirstMessage) {
      sseFirstMessage = false;
      lastSpeechId = data.status.speech_id || 0;
    }

    applyStatus(data.status);
    appendLogEntries(data.log);
    checkForErrors(data.log);
    if (data.tasks) updateTaskPanel(data.tasks);
    if (data.agents) updateAgentPanel(data.agents);
    if (data.artifact_version !== undefined) checkArtifacts(data.artifact_version);
  };

  eventSource.onerror = () => {
    statusDot.classList.remove('connected');
    statusDot.classList.add('disconnected');
    statusText.textContent = 'Reconnecting';
    showToast('warn', 'Connection Lost', 'Attempting to reconnect to HAL...', 3000);
  };
}

connectSSE();

// ── Task Queue Panel ─────────────────────────
const taskPanel = document.getElementById('task-panel');
const taskList = document.getElementById('task-list');
const taskBadge = document.getElementById('task-badge');

function updateTaskPanel(tasks) {
  if (!tasks || tasks.length === 0) {
    taskPanel.classList.remove('visible');
    return;
  }
  taskPanel.classList.add('visible');

  const active = tasks.filter(t => t.status === 'running' || t.status === 'queued').length;
  taskBadge.textContent = active || tasks.length;

  taskList.innerHTML = tasks.map(t => {
    let elapsed = '';
    if (t.started_at) {
      const end = t.completed_at || (Date.now() / 1000);
      elapsed = Math.round(end - t.started_at) + 's';
    }
    const cancelBtn = (t.status === 'running' || t.status === 'queued')
      ? `<button class="task-cancel" onclick="cancelTask('${t.id}')">×</button>`
      : '';
    return `<div class="task-card">
      <span class="task-dot ${t.status}"></span>
      <span class="task-desc" title="${escapeHtml(t.description)}">${escapeHtml(t.description.substring(0, 50))}</span>
      <span class="task-time">${elapsed}</span>
      ${cancelBtn}
    </div>`;
  }).join('');
}

async function cancelTask(id) {
  await fetch(`/api/tasks/${id}/cancel`, { method: 'POST' });
}

// ── Agent Panel ─────────────────────────────
const agentSection = document.getElementById('agent-section');

function updateAgentPanel(agents) {
  if (!agents || agents.length === 0) {
    agentSection.innerHTML = '';
    return;
  }
  agentSection.innerHTML = agents.map(a => {
    let elapsed = '';
    if (a.started_at) {
      const end = a.completed_at || (Date.now() / 1000);
      elapsed = Math.round(end - a.started_at) + 's';
    }
    const cancelBtn = a.status === 'working'
      ? `<button class="task-cancel" onclick="cancelAgent('${a.id}')">×</button>`
      : '';
    const files = a.files_touched && a.files_touched.length
      ? `<span class="task-time">${a.files_touched.length} files</span>`
      : '';
    return `<div class="agent-card">
      <span class="task-dot ${a.status === 'working' ? 'running' : a.status}"></span>
      <span class="agent-name">${escapeHtml(a.name)}</span>
      <span class="task-desc" title="${escapeHtml(a.task)}">${escapeHtml(a.task.substring(0, 40))}</span>
      ${files}
      <span class="task-time">${elapsed}</span>
      ${cancelBtn}
    </div>`;
  }).join('');

  // Show task panel if agents exist
  if (agents.length > 0) taskPanel.classList.add('visible');
}

async function cancelAgent(id) {
  await fetch(`/api/agents/${id}/cancel`, { method: 'POST' });
}

// ── Workspace / Artifacts Panel ──────────────
const dashboard = document.querySelector('.dashboard');
const workspacePanel = document.getElementById('workspace-panel');
const workspaceTabs = document.getElementById('workspace-tabs');
const workspaceActions = document.getElementById('workspace-actions');
const workspaceContent = document.getElementById('workspace-content');
let currentArtifacts = [];
let activeArtifactId = null;
let lastArtifactVersion = -1;

function checkArtifacts(version) {
  if (version === lastArtifactVersion) return;
  const prevCount = currentArtifacts.length;
  lastArtifactVersion = version;
  fetch('/api/artifacts').then(r => r.json()).then(artifacts => {
    currentArtifacts = artifacts;
    if (artifacts.length > 0) {
      dashboard.classList.add('has-artifacts');
      const rh2 = document.getElementById('resize-handle-2');
      if (rh2) rh2.style.display = '';
      // Always activate the newest artifact when a new one is added
      const isNew = artifacts.length > prevCount;
      if (isNew || !activeArtifactId || !artifacts.find(a => a.id === activeArtifactId)) {
        activeArtifactId = artifacts[artifacts.length - 1].id;
      }
      renderWorkspaceTabs();
      renderArtifact();
    } else {
      dashboard.classList.remove('has-artifacts');
      const rh2 = document.getElementById('resize-handle-2');
      if (rh2) rh2.style.display = 'none';
      activeArtifactId = null;
    }
  }).catch(() => {});
}

function renderWorkspaceTabs() {
  workspaceTabs.innerHTML = currentArtifacts.map(a => {
    const active = a.id === activeArtifactId ? 'active' : '';
    return `<div class="workspace-tab ${active}" onclick="selectArtifact('${a.id}')">
      ${a.title.substring(0, 20)}
      <span class="workspace-tab-close" onclick="event.stopPropagation(); closeArtifact('${a.id}')">×</span>
    </div>`;
  }).join('');
}

function selectArtifact(id) {
  activeArtifactId = id;
  renderWorkspaceTabs();
  renderArtifact();
}

function renderArtifact() {
  editingArtifact = false;
  workspaceContent.classList.remove('editing');
  closeRunOutput();

  const a = currentArtifacts.find(x => x.id === activeArtifactId);
  if (!a) {
    if (workspaceContent) workspaceContent.innerHTML = '';
    if (workspaceActions) workspaceActions.innerHTML = '';
    return;
  }

  renderArtifactActions(a);

  // Content
  let content = '';
  if (a.type === 'html') {
    content = `<iframe class="artifact-html" sandbox="allow-scripts" srcdoc="${a.content.replace(/"/g, '&quot;')}"></iframe>`;
  } else if (a.type === 'mermaid') {
    content = `<div class="mermaid">${a.content}</div>`;
  } else {
    content = `<pre><code>${escapeHtml(a.content)}</code></pre>`;
  }

  workspaceContent.innerHTML = content;

  // Render mermaid diagrams if present
  if (a.type === 'mermaid' && window.mermaid) {
    window.mermaid.run({ querySelector: '.mermaid' });
  }
}

function renderArtifactActions(a) {
  const isRunnable = a.type === 'code' || a.type === 'html';
  const editLabel = editingArtifact ? 'Save' : 'Edit';
  const editCls = editingArtifact ? 'active' : '';

  const actions = [
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>', label: 'Run', onclick: 'runArtifact()', cls: 'accent-green', show: isRunnable },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>', label: editLabel, onclick: 'editArtifact()', cls: editCls, show: true },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>', label: 'Copy', onclick: 'copyArtifact()', cls: '', show: true },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>', label: 'Send to Claude', onclick: 'sendArtifactToClaude()', cls: '', show: true },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>', label: 'Download', onclick: 'downloadArtifact()', cls: '', show: true },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>', label: 'Regenerate', onclick: 'regenerateArtifact()', cls: 'accent-red', show: true },
  ];

  if (workspaceActions) {
    workspaceActions.innerHTML = actions
      .filter(a => a.show)
      .map(a => `<button class="workspace-action-btn ${a.cls}" onclick="${a.onclick}">${a.icon} ${a.label}</button>`)
      .join('');
  }
}

function closeArtifact(id) {
  // Remove from server (best-effort)
  currentArtifacts = currentArtifacts.filter(a => a.id !== id);
  if (activeArtifactId === id) {
    activeArtifactId = currentArtifacts.length ? currentArtifacts[0].id : null;
  }
  if (currentArtifacts.length === 0) {
    dashboard.classList.remove('has-artifacts');
    const rh2 = document.getElementById('resize-handle-2');
    if (rh2) rh2.style.display = 'none';
  }
  renderWorkspaceTabs();
  renderArtifact();
}

function copyArtifact() {
  const a = currentArtifacts.find(x => x.id === activeArtifactId);
  if (a) {
    navigator.clipboard.writeText(a.content).then(() => {
      showToast('info', 'Copied', 'Artifact copied to clipboard', 2000);
    });
  }
}

let editingArtifact = false;

function editArtifact() {
  const a = currentArtifacts.find(x => x.id === activeArtifactId);
  if (!a) return;

  if (editingArtifact) {
    // Save and exit edit mode
    const editor = document.getElementById('artifact-editor');
    if (editor) {
      const newContent = editor.value;
      a.content = newContent;
      // Persist to server
      fetch(`/api/artifacts/${a.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newContent })
      }).catch(() => {});
      showToast('info', 'Saved', 'Artifact updated', 2000);
    }
    editingArtifact = false;
    renderArtifact();
    return;
  }

  // Enter edit mode
  editingArtifact = true;
  workspaceContent.classList.add('editing');
  workspaceContent.innerHTML = `<textarea id="artifact-editor" class="workspace-editor" spellcheck="false">${escapeHtml(a.content)}</textarea>`;

  // Support Tab key for indentation
  const editor = document.getElementById('artifact-editor');
  editor.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      editor.value = editor.value.substring(0, start) + '  ' + editor.value.substring(end);
      editor.selectionStart = editor.selectionEnd = start + 2;
    }
  });

  // Update button states
  renderArtifactActions(a);
}

// ── Claude Output Viewer (in camera panel) ──────────
let claudeOutputInterval = null;

async function sendArtifactToClaude() {
  const a = currentArtifacts.find(x => x.id === activeArtifactId);
  if (!a) return;

  showToast('info', 'Sending', 'Opening terminal with code review...', 2000);

  // Save artifact to temp file via API, then open terminal with claude reviewing it
  try {
    const resp = await fetch('/api/send_to_claude', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: a.content,
        language: a.language || a.type,
        title: a.title,
      })
    });
    const data = await resp.json();
    if (data.error) {
      showToast('error', 'Failed', data.error, 3000);
      return;
    }

    // Open interactive terminal with claude command
    const claudeBin = data.claude_bin || 'claude';
    const tmpFile = data.tmp_file || '';
    const lang = a.language || a.type || 'code';
    const cmd = `cd ~ && ${claudeBin} "Review and improve the code in ${tmpFile} — it is a ${lang} ${a.title}. Read the file first."`;
    openTerminal(cmd);
  } catch (e) {
    showToast('error', 'Failed', 'Could not send to Claude Code: ' + e.message, 3000);
  }
}

function openClaudeOutput(taskId) {
  // Use read-only mode for background task output
  terminalMode = false;
  const viewer = document.getElementById('claude-output-viewer');
  const container = document.getElementById('terminal-container');
  const body = document.getElementById('claude-output-body');
  const dot = document.getElementById('terminal-dot');
  const title = document.getElementById('terminal-title');
  const offlineLabel = document.getElementById('cam-offline-label');

  camPanel.classList.remove('inactive');
  if (offlineLabel) offlineLabel.style.display = 'none';
  viewer.style.display = 'flex';
  container.style.display = 'none';
  body.style.display = '';
  body.textContent = 'Connecting to Claude Code...\n';
  dot.className = 'claude-output-dot';
  title.textContent = 'CLAUDE CODE';

  // Poll for output every 1.5s
  if (claudeOutputInterval) clearInterval(claudeOutputInterval);
  claudeOutputInterval = setInterval(async () => {
    try {
      const resp = await fetch('/api/claude_output');
      const data = await resp.json();

      if (data.output) {
        body.textContent = data.output;
        body.scrollTop = body.scrollHeight;
      }

      if (data.status === 'completed') {
        dot.className = 'claude-output-dot done';
        title.textContent = 'CLAUDE CODE — DONE';
        clearInterval(claudeOutputInterval);
        claudeOutputInterval = null;
      } else if (data.status === 'failed') {
        dot.className = 'claude-output-dot error';
        title.textContent = 'CLAUDE CODE — FAILED';
        clearInterval(claudeOutputInterval);
        claudeOutputInterval = null;
      }
    } catch (e) {
      // silently retry
    }
  }, 1500);

  wfResize();
}

// ── Interactive Terminal (xterm.js + WebSocket) ─────
let halTerminal = null;
let halTermWs = null;
let halTermFit = null;
let halTermResizeObs = null;
let terminalMode = false; // true = interactive xterm, false = read-only output

function openTerminal(initialCmd) {
  terminalMode = true;
  const viewer = document.getElementById('claude-output-viewer');
  const container = document.getElementById('terminal-container');
  const body = document.getElementById('claude-output-body');
  const dot = document.getElementById('terminal-dot');
  const title = document.getElementById('terminal-title');
  const offlineLabel = document.getElementById('cam-offline-label');

  // Show panel
  camPanel.classList.remove('inactive');
  if (offlineLabel) offlineLabel.style.display = 'none';
  viewer.style.display = 'flex';
  container.style.display = '';
  body.style.display = 'none';
  dot.className = 'claude-output-dot';
  title.textContent = 'TERMINAL';

  // Dispose previous terminal
  if (halTerminal) {
    halTerminal.dispose();
    halTerminal = null;
  }
  if (halTermWs) {
    halTermWs.close();
    halTermWs = null;
  }

  // Create xterm.js instance
  halTerminal = new Terminal({
    theme: {
      background: '#0a0a10',
      foreground: '#c8c8d0',
      cursor: '#ff1744',
      cursorAccent: '#0a0a10',
      selectionBackground: 'rgba(255, 23, 68, 0.3)',
      black: '#0a0a10',
      red: '#ff1744',
      green: '#00e676',
      yellow: '#ffc107',
      blue: '#00bcff',
      magenta: '#e040fb',
      cyan: '#00bcff',
      white: '#c8c8d0',
    },
    fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace",
    fontSize: 13,
    cursorBlink: true,
    cursorStyle: 'block',
    scrollback: 5000,
    allowProposedApi: true,
  });

  // Load addons
  halTermFit = new FitAddon.FitAddon();
  halTerminal.loadAddon(halTermFit);
  halTerminal.loadAddon(new WebLinksAddon.WebLinksAddon());

  // Attach to DOM
  container.innerHTML = '';
  halTerminal.open(container);

  // Fit after layout settles, then send size to PTY
  function fitAndResize() {
    if (!halTermFit || !halTerminal) return;
    try {
      halTermFit.fit();
      halTerminal.focus();
      // Send resize to PTY via WebSocket
      if (halTermWs && halTermWs.readyState === WebSocket.OPEN) {
        halTermWs.send(`\x1b[8;${halTerminal.rows};${halTerminal.cols}t`);
      }
    } catch(e) {}
  }
  setTimeout(fitAndResize, 100);
  setTimeout(fitAndResize, 300);
  setTimeout(fitAndResize, 600);

  // Connect WebSocket to PTY server
  try {
    halTermWs = new WebSocket('ws://127.0.0.1:9001');

    halTermWs.onopen = () => {
      dot.className = 'claude-output-dot done';
      title.textContent = 'TERMINAL — CONNECTED';

      // Fit and send size after connection
      setTimeout(() => {
        fitAndResize();
        // Send initial command if provided
        if (initialCmd) {
          setTimeout(() => {
            halTermWs.send(initialCmd + '\n');
          }, 300);
        }
      }, 200);
    };

    halTermWs.onmessage = (e) => {
      halTerminal.write(e.data);
    };

    halTermWs.onclose = () => {
      dot.className = 'claude-output-dot error';
      title.textContent = 'TERMINAL — DISCONNECTED';
      halTerminal.write('\r\n\x1b[31m[Disconnected]\x1b[0m\r\n');
    };

    halTermWs.onerror = () => {
      dot.className = 'claude-output-dot error';
      title.textContent = 'TERMINAL — NOT AVAILABLE';
      halTerminal.write('\r\n\x1b[33mEmbedded terminal not available on this platform.\x1b[0m\r\n');
      halTerminal.write('\x1b[33mUse the external terminal instead.\x1b[0m\r\n');
    };

    // Send user input to PTY
    halTerminal.onData(data => {
      if (halTermWs && halTermWs.readyState === WebSocket.OPEN) {
        halTermWs.send(data);
      }
    });

    // Handle resize
    halTerminal.onResize(({ cols, rows }) => {
      if (halTermWs && halTermWs.readyState === WebSocket.OPEN) {
        halTermWs.send(`\x1b[8;${rows};${cols}t`);
      }
    });

  } catch (e) {
    halTerminal.write(`\r\n\x1b[31m[Failed to connect: ${e.message}]\x1b[0m\r\n`);
  }

  // Debounced resize — wait 300ms after last resize event before sending to PTY
  let _termResizeTimer = null;
  if (halTermResizeObs) { halTermResizeObs.disconnect(); halTermResizeObs = null; }
  halTermResizeObs = new ResizeObserver(() => {
    if (!halTermFit || !halTerminal) return;
    // Fit xterm locally (instant, no PTY signal)
    try { halTermFit.fit(); } catch(e) {}
    // Debounce the PTY resize signal
    clearTimeout(_termResizeTimer);
    _termResizeTimer = setTimeout(() => {
      if (halTermWs && halTermWs.readyState === WebSocket.OPEN && halTerminal) {
        halTermWs.send(`\x1b[8;${halTerminal.rows};${halTerminal.cols}t`);
      }
    }, 300);
  });
  halTermResizeObs.observe(container);

  wfResize();
}

function closeClaudeOutput() {
  if (claudeOutputInterval) {
    clearInterval(claudeOutputInterval);
    claudeOutputInterval = null;
  }

  // Clean up terminal
  if (halTermResizeObs) {
    halTermResizeObs.disconnect();
    halTermResizeObs = null;
  }
  if (halTermWs) {
    halTermWs.close();
    halTermWs = null;
  }
  if (halTerminal) {
    halTerminal.dispose();
    halTerminal = null;
  }
  halTermFit = null;
  terminalMode = false;

  const viewer = document.getElementById('claude-output-viewer');
  const offlineLabel = document.getElementById('cam-offline-label');
  viewer.style.display = 'none';
  if (offlineLabel) offlineLabel.style.display = '';

  // Collapse camera panel if vision is off
  const status = lastStatus || {};
  if (!status.vision) {
    camPanel.classList.add('inactive');
  }
  wfResize();
}

function downloadArtifact() {
  const a = currentArtifacts.find(x => x.id === activeArtifactId);
  if (!a) return;
  const ext = { code: a.language || 'txt', markdown: 'md', html: 'html', mermaid: 'mmd', json: 'json' };
  const filename = `${a.title.replace(/\s+/g, '_').toLowerCase()}.${ext[a.type] || 'txt'}`;
  const blob = new Blob([a.content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  showToast('info', 'Downloaded', filename, 2000);
}

async function regenerateArtifact() {
  const a = currentArtifacts.find(x => x.id === activeArtifactId);
  if (!a) return;
  showToast('info', 'Regenerating', 'Asking HAL to regenerate...', 2000);
  try {
    await api('chat', 'POST', { text: `regenerate the ${a.type} artifact "${a.title}" with improvements` });
  } catch (e) {
    showToast('error', 'Failed', 'Could not regenerate', 3000);
  }
}

async function runArtifact() {
  const a = currentArtifacts.find(x => x.id === activeArtifactId);
  if (!a) return;
  if (a.type !== 'code' && a.type !== 'html') return;

  // If in edit mode, use editor content
  let code = a.content;
  const editor = document.getElementById('artifact-editor');
  if (editor) code = editor.value;

  const lang = a.language || a.type || 'python';

  // JS/HTML runs in browser sandbox
  if (lang === 'javascript' || lang === 'js' || lang === 'html' || a.type === 'html') {
    showRunOutput('running', 'Running in browser...');
    try {
      const iframe = document.createElement('iframe');
      iframe.sandbox = 'allow-scripts';
      iframe.style.display = 'none';
      document.body.appendChild(iframe);

      // Capture console.log
      const logs = [];
      const script = `
        const _logs = [];
        const _origLog = console.log;
        console.log = (...args) => { _logs.push(args.map(String).join(' ')); _origLog(...args); };
        console.error = (...args) => { _logs.push('ERROR: ' + args.map(String).join(' ')); };
        try { ${code} } catch(e) { _logs.push('ERROR: ' + e.message); }
        parent.postMessage({ type: 'hal-run-result', logs: _logs }, '*');
      `;
      iframe.srcdoc = `<script>${script}<\/script>`;

      const result = await new Promise((resolve) => {
        const handler = (e) => {
          if (e.data && e.data.type === 'hal-run-result' && (e.origin === 'null' || e.origin === window.location.origin)) {
            window.removeEventListener('message', handler);
            resolve(e.data.logs.join('\n') || '(no output)');
          }
        };
        window.addEventListener('message', handler);
        setTimeout(() => { resolve('(timed out)'); }, 5000);
      });

      document.body.removeChild(iframe);
      showRunOutput('success', result);
    } catch (e) {
      showRunOutput('error', e.message);
    }
    return;
  }

  // Python/bash/node runs on server
  showRunOutput('running', `Running ${lang}...`);
  try {
    const resp = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, language: lang })
    });
    const data = await resp.json();

    if (data.error) {
      showRunOutput('error', data.error);
    } else {
      const output = (data.stdout || '') + (data.stderr ? '\n[stderr] ' + data.stderr : '');
      showRunOutput(data.returncode === 0 ? 'success' : 'error', output || '(no output)');
    }
  } catch (e) {
    showRunOutput('error', 'Failed to execute: ' + e.message);
  }
}

function showRunOutput(status, text) {
  if (!workspacePanel) return;

  let outputEl = document.getElementById('workspace-run-output');
  if (!outputEl) {
    outputEl = document.createElement('div');
    outputEl.id = 'workspace-run-output';
    outputEl.className = 'workspace-output';
    workspacePanel.appendChild(outputEl);
  }

  const dotCls = status === 'error' ? 'error' : status === 'running' ? 'running' : '';
  const bodyCls = status === 'error' ? 'error' : status === 'running' ? 'running' : '';
  const a = currentArtifacts.find(x => x.id === activeArtifactId);
  const lang = a ? (a.language || a.type) : 'code';
  const title = status === 'running' ? 'Running...' : status === 'error' ? 'Error' : 'Output';

  // Format output lines with prompt
  const lines = text.split('\n');
  let bodyHtml = '';

  if (status === 'running') {
    bodyHtml = `<div class="workspace-output-line"><span class="workspace-output-prompt">$ </span>${escapeHtml(lang)} running...</div>`;
  } else {
    bodyHtml = `<div class="workspace-output-line"><span class="workspace-output-prompt">$ </span>${escapeHtml(lang)} run</div>`;
    lines.forEach(line => {
      bodyHtml += `<div class="workspace-output-line">${escapeHtml(line)}</div>`;
    });
    if (status !== 'error') {
      bodyHtml += `<div class="workspace-output-line" style="color:var(--text-dim);margin-top:4px"><span class="workspace-output-prompt">$ </span>exit 0</div>`;
    } else {
      bodyHtml += `<div class="workspace-output-line" style="color:var(--red);margin-top:4px"><span class="workspace-output-prompt">$ </span>exit 1</div>`;
    }
  }

  outputEl.innerHTML = `
    <div class="workspace-output-header">
      <div class="workspace-output-header-left">
        <div class="workspace-output-dot ${dotCls}"></div>
        <span class="workspace-output-title">${title}</span>
      </div>
      <span class="workspace-output-close" onclick="closeRunOutput()">&#x2715;</span>
    </div>
    <div class="workspace-output-body ${bodyCls}">${bodyHtml}</div>
  `;

  // Auto-scroll to bottom
  const body = outputEl.querySelector('.workspace-output-body');
  if (body) body.scrollTop = body.scrollHeight;
}

function closeRunOutput() {
  const el = document.getElementById('workspace-run-output');
  if (el) el.remove();
}

// ── Waveform Visualizer (fits red block in HAL image) ──
let wfSpeaking = false;
const WF_BARS = 32;
let WF_W = 0, WF_H = 0, WF_GAP = 1;

// Positions within the original HAL.png (850x1236)
const IMG_W = 850, IMG_H = 1236;
// Red waveform block
const BLOCK_LEFT = 124 / IMG_W;
const BLOCK_TOP = 1016 / IMG_H;
const BLOCK_W = 605 / IMG_W;
const BLOCK_H = 144 / IMG_H;
// Blank strip (between eye and red block) — buttons go here
const STRIP_TOP = 860 / IMG_H;     // slightly higher to give more room
const STRIP_H = 150 / IMG_H;       // taller strip for bigger buttons

function wfResize() {
  // Calculate where the image actually renders inside the panel
  // (object-fit: contain causes letterboxing)
  const panelRect = halPanel.getBoundingClientRect();
  const pW = panelRect.width;
  const pH = panelRect.height;
  if (pW < 1 || pH < 1) return;

  const imgAspect = IMG_W / IMG_H;
  const panelAspect = pW / pH;

  let rendW, rendH, offX, offY;
  if (panelAspect > imgAspect) {
    // Panel is wider than image — image fits to height, centered horizontally
    rendH = pH;
    rendW = pH * imgAspect;
    offX = (pW - rendW) / 2;
    offY = 0;
  } else {
    // Panel is taller than image — image fits to width, centered vertically
    rendW = pW;
    rendH = pW / imgAspect;
    offX = 0;
    offY = (pH - rendH) / 2;
  }

  // Position the overlay exactly over the red block within the rendered image
  const oLeft = offX + BLOCK_LEFT * rendW;
  const oTop = offY + BLOCK_TOP * rendH;
  const oWidth = BLOCK_W * rendW;
  const oHeight = BLOCK_H * rendH;

  waveformWrap.style.left = oLeft + 'px';
  waveformWrap.style.top = oTop + 'px';
  waveformWrap.style.width = oWidth + 'px';
  waveformWrap.style.height = oHeight + 'px';

  // Position the control buttons on the blank strip
  const sTop = offY + STRIP_TOP * rendH;
  const sH = STRIP_H * rendH;
  halControls.style.left = offX + 'px';
  halControls.style.top = sTop + 'px';
  halControls.style.width = rendW + 'px';
  halControls.style.height = sH + 'px';

  // Scale buttons proportionally — 60% of strip height, max 42px
  const btnSize = Math.max(18, Math.min(42, Math.round(sH * 0.58)));
  const iconSize = Math.round(btnSize * 0.46);
  const btnGap = Math.round(btnSize * 0.22);
  halControls.style.gap = btnGap + 'px';
  halControls.querySelectorAll('.hal-ctrl-btn').forEach(btn => {
    btn.style.width = btnSize + 'px';
    btn.style.height = btnSize + 'px';
    btn.style.borderRadius = Math.round(btnSize * 0.12) + 'px';
    btn.querySelector('svg').style.width = iconSize + 'px';
    btn.querySelector('svg').style.height = iconSize + 'px';
  });

  // Set canvas resolution for crisp rendering
  const dpr = window.devicePixelRatio || 1;
  const cw = Math.round(oWidth * dpr);
  const ch = Math.round(oHeight * dpr);
  if (cw < 1 || ch < 1) return;
  waveformCanvas.width = cw;
  waveformCanvas.height = ch;
  WF_W = cw;
  WF_H = ch;
}

// Debounce only window resize; ResizeObserver runs live for smooth transitions
let wfWindowTimer;
function wfWindowResizeDebounced() {
  clearTimeout(wfWindowTimer);
  wfWindowTimer = setTimeout(wfResize, 50);
}

wfResize();
window.addEventListener('resize', wfWindowResizeDebounced);
new ResizeObserver(() => requestAnimationFrame(wfResize)).observe(halPanel);

function ensureAudioCtx() {
  if (audioCtx) return;
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 128;
  analyser.smoothingTimeConstant = 0.75;
  freqData = new Uint8Array(analyser.frequencyBinCount);
}

let currentSource = null; // track active audio source to prevent overlap

async function playSpeechAudio(speechId) {
  if (speechId <= lastSpeechId) return;
  lastSpeechId = speechId;

  // Stop any currently playing audio to prevent overlap
  if (currentSource) {
    try { currentSource.stop(); } catch (e) { /* already stopped */ }
    currentSource = null;
    wfSpeaking = false;
  }

  ensureAudioCtx();
  if (audioCtx.state === 'suspended') await audioCtx.resume();

  try {
    const resp = await fetch('/api/speech');
    if (!resp.ok || resp.status === 204) return;

    const arrayBuf = await resp.arrayBuffer();
    if (!arrayBuf.byteLength) return;

    const audioBuf = await audioCtx.decodeAudioData(arrayBuf);
    const source = audioCtx.createBufferSource();
    source.buffer = audioBuf;
    currentSource = source;

    source.connect(analyser);
    analyser.connect(audioCtx.destination);

    wfResize(); // ensure canvas matches current size
    waveformWrap.classList.add('active');
    wfSpeaking = true;

    source.onended = () => {
      currentSource = null;
      wfSpeaking = false;
      fetch('/api/speech_done', { method: 'POST' }).catch(() => {});
    };

    source.start();
  } catch (err) {
    console.error('[Waveform] Audio playback error:', err);
    currentSource = null;
    wfSpeaking = false;
    fetch('/api/speech_done', { method: 'POST' }).catch(() => {});
  }
}

function wfDraw() {
  // Skip rendering when idle — save CPU
  if (!wfSpeaking && !wfMicActive) {
    setTimeout(wfDraw, 200); // check again in 200ms instead of 16ms
    return;
  }
  if (WF_W < 1 || WF_H < 1) { requestAnimationFrame(wfDraw); return; }
  wfCtx.clearRect(0, 0, WF_W, WF_H);

  // Pick the active analyser: mic takes priority over speech
  const activeAnalyser = (wfMicActive && micAnalyser) ? micAnalyser : (wfSpeaking && analyser) ? analyser : null;
  const isMic = wfMicActive && micAnalyser;

  if (activeAnalyser) {
    if (!freqData || freqData.length !== activeAnalyser.frequencyBinCount) {
      freqData = new Uint8Array(activeAnalyser.frequencyBinCount);
    }
    activeAnalyser.getByteFrequencyData(freqData);
  }

  const padX = Math.round(WF_W * 0.03);
  const padY = Math.round(WF_H * 0.1);
  const drawW = WF_W - padX * 2;
  const drawH = WF_H - padY * 2;
  const barW = Math.max(1, Math.floor(drawW / WF_BARS) - WF_GAP);

  // Color: cyan for mic recording, red for speech output
  const r = isMic ? 0 : 255;
  const g = isMic ? 188 : 23;
  const b = isMic ? 255 : 68;

  for (let i = 0; i < WF_BARS; i++) {
    const val = activeAnalyser ? (freqData[i] || 0) : 0;
    const norm = val / 255;
    const h = norm * drawH;
    const x = padX + i * (barW + WF_GAP);
    const y = padY + (drawH - h) / 2;

    if (h < 1) continue;

    const alpha = 0.5 + norm * 0.5;
    wfCtx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
    wfCtx.fillRect(x, y, barW, h);

    if (h > 2) {
      wfCtx.fillStyle = `rgba(${r + 50}, ${g + 50}, ${b + 50}, ${alpha * 0.7})`;
      wfCtx.fillRect(x, y, barW, 1);
      wfCtx.fillRect(x, y + h - 1, barW, 1);
    }
  }

  // Keep waveform visible while mic or speech is active
  if (!wfSpeaking && !wfMicActive) {
    waveformWrap.classList.remove('active');
  }

  requestAnimationFrame(wfDraw);
}
requestAnimationFrame(wfDraw);

// PWA Service Worker — updateViaCache:'none' ensures SW file is always fetched fresh
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/assets/sw.js', { updateViaCache: 'none' })
    .then(reg => { if (reg.waiting) reg.waiting.postMessage({ type: 'SKIP_WAITING' }); })
    .catch(() => {});
}

// ── Column Resize Handles (overlay approach) ──────
(function() {
  const db = document.querySelector('.dashboard');
  const h1 = document.getElementById('resize-handle-1');
  const h2 = document.getElementById('resize-handle-2');
  const leftCol = document.querySelector('.left-col');
  const rightCol = document.querySelector('.right-col');
  const wsPanel = document.getElementById('workspace-panel');
  let dragging = null;
  let startX = 0;
  let startWidths = {};

  // Position handles at column boundaries
  function positionHandles() {
    if (!leftCol) return;
    const dbRect = db.getBoundingClientRect();
    const leftRect = leftCol.getBoundingClientRect();
    // h1 sits at the right edge of left-col
    h1.style.left = (leftRect.right - dbRect.left - 4) + 'px';
    h1.style.top = (leftRect.top - dbRect.top) + 'px';
    h1.style.height = leftRect.height + 'px';

    if (h2 && wsPanel && wsPanel.offsetParent !== null) {
      const wsRect = wsPanel.getBoundingClientRect();
      h2.style.left = (wsRect.right - dbRect.left - 4) + 'px';
      h2.style.top = (wsRect.top - dbRect.top) + 'px';
      h2.style.height = wsRect.height + 'px';
      h2.style.display = '';
    } else if (h2) {
      h2.style.display = 'none';
    }
  }

  // Reposition on resize
  const _posObs = new ResizeObserver(positionHandles);
  _posObs.observe(db);
  setTimeout(positionHandles, 100);

  function onDown(e, handle) {
    e.preventDefault();
    dragging = handle;
    startX = e.clientX || e.touches[0].clientX;
    // Capture current pixel widths from computed grid
    const cols = getComputedStyle(db).gridTemplateColumns.split(/\s+/).map(v => parseFloat(v));
    startWidths = { cols: cols };
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }

  h1.addEventListener('mousedown', e => onDown(e, h1));
  h1.addEventListener('touchstart', e => onDown(e, h1), { passive: false });
  h2.addEventListener('mousedown', e => onDown(e, h2));
  h2.addEventListener('touchstart', e => onDown(e, h2), { passive: false });

  function onMove(e) {
    if (!dragging) return;
    const x = e.clientX || (e.touches && e.touches[0].clientX) || 0;
    const dx = x - startX;
    const cols = [...startWidths.cols];
    const minCol = 200;
    const hasArtifacts = db.classList.contains('has-artifacts');

    if (dragging === h1) {
      // Resize left-col (col 0) vs next col (col 1 in 2-col, or col 1 in 3-col)
      const nextIdx = 1;
      const newLeft = Math.max(minCol, Math.min(cols[0] + dx, db.clientWidth * 0.5));
      const delta = newLeft - cols[0];
      cols[0] = newLeft;
      cols[nextIdx] = Math.max(minCol, cols[nextIdx] - delta);
    } else if (dragging === h2 && hasArtifacts && cols.length >= 3) {
      // Resize workspace (col 1) vs chat (col 2) in 3-col mode
      const newWs = Math.max(minCol, Math.min(cols[1] + dx, db.clientWidth * 0.6));
      const delta = newWs - cols[1];
      cols[1] = newWs;
      cols[2] = Math.max(minCol, cols[2] - delta);
    }

    db.style.gridTemplateColumns = cols.map(c => c + 'px').join(' ');
    positionHandles();
    if (typeof wfResize === 'function') wfResize();
  }

  function onUp() {
    if (!dragging) return;
    dragging.classList.remove('dragging');
    dragging = null;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }

  document.addEventListener('mousemove', onMove);
  document.addEventListener('touchmove', onMove, { passive: false });
  document.addEventListener('mouseup', onUp);
  document.addEventListener('touchend', onUp);
})();

// ── Footer ─────────────────────────────────────────
(function() {
  const _f0 = '32ca0d3e3831691d1e292841b54e7fc80eb8a4a71d6f7e40921c03cb683a9901';
  const _f1 = 'Built with <span class="heart">\u2665</span> and ' +
    '<img class="claude-icon" src="/assets/claude-color.svg" alt="Claude"> at ' +
    '<a href="https://affordance.design" target="_blank" rel="noopener">Affordance Design Studio</a> by ' +
    '<a href="https://shandarjunaid.com" target="_blank" rel="noopener">Shandar J</a>';
  let _busy = false;
  async function _v() {
    if (_busy) return;
    _busy = true;
    try {
      const el = document.querySelector('.bottom-bar');
      if (!el) return;
      const spans = el.querySelectorAll('span');
      const s = spans.length > 1 ? spans[1] : spans[0];
      if (!s) return;
      const buf = new TextEncoder().encode(s.innerHTML);
      const h = await crypto.subtle.digest('SHA-256', buf);
      const hex = Array.from(new Uint8Array(h)).map(b => b.toString(16).padStart(2,'0')).join('');
      if (hex !== _f0) { s.innerHTML = _f1; }
    } finally { _busy = false; }
  }
  _v();
  setInterval(_v, 8000);
  const bar = document.querySelector('.bottom-bar');
  if (bar) {
    new MutationObserver(() => _v()).observe(bar, { childList: true, subtree: true, characterData: true });
    Object.defineProperty(bar, 'hidden', { set: () => {}, get: () => false });
    new MutationObserver(() => {
      if (bar.style.display === 'none' || bar.style.visibility === 'hidden' || bar.style.opacity === '0') {
        bar.style.display = ''; bar.style.visibility = ''; bar.style.opacity = '';
      }
    }).observe(bar, { attributes: true, attributeFilter: ['style', 'class'] });
  }
})();

// ── Cycling Tips ────────────────────────────────────
(function() {
  const tips = [
    'Type <span class="tip-key">/</span> to see all slash commands',
    'Hold the <span style="color:#00e676;">mic button</span> to speak to HAL',
    'Drag & drop files onto chat to teach HAL new knowledge',
    'Say <span class="tip-key">remember</span> to store facts across restarts',
    'HAL can see you \u2014 toggle vision with the eye button',
    'Use <span class="tip-key">/tools</span> to see all 40+ available tools',
    'Ask HAL to <span class="tip-key">delegate to Claude Code</span> for coding tasks',
    'HAL supports 4 AI providers: OpenAI, Anthropic, Gemini, Ollama',
    'Upload PDFs, docs, code files \u2014 HAL will learn from them',
    'Use <span class="tip-key">/clear</span> to reset conversation history',
    'HAL can control your system: volume, brightness, apps, files',
    'Background tasks run silently \u2014 check the Tasks panel',
    'Create code artifacts with <span class="tip-key">/artifact</span>',
    'HAL remembers you across sessions via persistent memory',
    'Free mode: set <span class="tip-key">FREE_MODE=true</span> for zero API costs',
  ];

  const container = document.getElementById('chat-tips');
  // Create all tip elements
  tips.forEach((html, i) => {
    const div = document.createElement('div');
    div.className = 'tip' + (i === 0 ? ' active' : '');
    div.innerHTML = html;
    container.appendChild(div);
  });

  let current = 0;
  setInterval(() => {
    const els = container.querySelectorAll('.tip');
    els[current].classList.remove('active');
    current = (current + 1) % tips.length;
    els[current].classList.add('active');
  }, 5000);
})();

// ── Knowledge Upload System ─────────────────────────
(function() {
  const chatPanel = document.querySelector('.chat-panel');
  const dropOverlay = document.getElementById('chat-drop-overlay');
  const knowledgePanel = document.getElementById('knowledge-panel');
  const knowledgeBadge = document.getElementById('knowledge-badge');
  const knowledgeList = document.getElementById('knowledge-list');
  const knowledgeStorage = document.getElementById('knowledge-storage');
  const modeModal = document.getElementById('knowledge-mode-modal');
  const modeTitle = document.getElementById('knowledge-mode-title');
  const modeDesc = document.getElementById('knowledge-mode-desc');

  let pendingUpload = null; // deferred upload needing mode choice
  let knowledgeExpanded = true;

  // File type icons
  function fileIcon(name) {
    const ext = name.split('.').pop().toLowerCase();
    const icons = {
      pdf: '\u{1F4D5}', docx: '\u{1F4C4}', xlsx: '\u{1F4CA}', csv: '\u{1F4CA}',
      py: '\u{1F40D}', js: '\u{1F7E8}', ts: '\u{1F535}', json: '\u{1F4CB}',
      md: '\u{1F4DD}', txt: '\u{1F4C3}', html: '\u{1F310}', css: '\u{1F3A8}',
      png: '\u{1F5BC}', jpg: '\u{1F5BC}', jpeg: '\u{1F5BC}',
    };
    return icons[ext] || '\u{1F4C1}';
  }

  // ── Drag & Drop ──────────────────────────
  let dragCounter = 0;

  chatPanel.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragCounter++;
    dropOverlay.classList.add('active');
  });

  chatPanel.addEventListener('dragover', (e) => {
    e.preventDefault();
  });

  chatPanel.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter <= 0) {
      dragCounter = 0;
      dropOverlay.classList.remove('active');
    }
  });

  chatPanel.addEventListener('drop', (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropOverlay.classList.remove('active');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      uploadKnowledgeFile(files[0]);
    }
  });

  // ── File Input Handler ─────────────────────
  window.handleKnowledgeFileInput = function(event) {
    const file = event.target.files[0];
    if (file) uploadKnowledgeFile(file);
    event.target.value = ''; // reset so same file can be re-uploaded
  };

  // ── Upload File ────────────────────────────
  async function uploadKnowledgeFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', 'auto');

    try {
      const resp = await fetch('/api/knowledge/upload', { method: 'POST', body: formData });
      const data = await resp.json();

      if (data.error) {
        appendSystemMessage('Knowledge upload failed: ' + data.error);
        return;
      }

      if (data.needs_choice) {
        // Large file — ask user deep/skim
        pendingUpload = data;
        modeTitle.textContent = file.name;
        modeDesc.textContent = `${data.size_kb} KB — choose how HAL should process this file:`;
        modeModal.classList.add('active');
        return;
      }

      // Success
      const modeLabel = data.mode === 'always' ? 'always loaded' : `${data.chunks} chunks`;
      appendSystemMessage(`Learned from ${data.name} (${modeLabel})`);
      refreshKnowledgePanel();
    } catch (err) {
      appendSystemMessage('Upload error: ' + err.message);
    }
  }

  // ── Mode Choice (deep/skim) ─────────────────
  window.chooseKnowledgeMode = async function(mode) {
    modeModal.classList.remove('active');
    if (!pendingUpload) return;

    try {
      const resp = await fetch('/api/knowledge/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: pendingUpload.id,
          content: pendingUpload.content,
          name: pendingUpload.name,
          mode: mode,
        }),
      });
      const data = await resp.json();

      if (data.error) {
        appendSystemMessage('Processing failed: ' + data.error);
      } else {
        appendSystemMessage(`Learned from ${data.name} (${data.chunks} chunks, ${mode})`);
        refreshKnowledgePanel();
      }
    } catch (err) {
      appendSystemMessage('Processing error: ' + err.message);
    }
    pendingUpload = null;
  };

  // ── Panel Toggle ───────────────────────────
  window.toggleKnowledgePanel = function() {
    knowledgeExpanded = !knowledgeExpanded;
    knowledgeList.style.display = knowledgeExpanded ? '' : 'none';
    knowledgeStorage.style.display = knowledgeExpanded ? '' : 'none';
  };

  // ── Delete Knowledge File ──────────────────
  window.deleteKnowledge = async function(id, name) {
    if (!confirm('Delete knowledge: ' + name + '?')) return;
    try {
      await fetch('/api/knowledge/' + id, { method: 'DELETE' });
      refreshKnowledgePanel();
      appendSystemMessage('Forgot: ' + name);
    } catch (err) {
      appendSystemMessage('Delete failed: ' + err.message);
    }
  };

  // ── Refresh Panel ──────────────────────────
  async function refreshKnowledgePanel() {
    try {
      const resp = await fetch('/api/knowledge');
      const data = await resp.json();
      const files = data.files || [];
      const storage = data.storage || {};

      knowledgeBadge.textContent = files.length;
      knowledgePanel.classList.toggle('visible', files.length > 0);

      if (files.length === 0) {
        knowledgeList.innerHTML = '';
        knowledgeStorage.textContent = '';
        return;
      }

      let html = '';
      for (const f of files) {
        const tag = f.mode === 'always' ? 'always' : `${f.chunks || 0} chunks`;
        html += `<div class="knowledge-item">
          <span class="knowledge-icon">${fileIcon(f.name)}</span>
          <span class="knowledge-name" title="${f.name}">${f.name}</span>
          <span class="knowledge-tag">${tag}</span>
          <span class="knowledge-tag">${f.size_kb} KB</span>
          <button class="knowledge-del" onclick="deleteKnowledge('${f.id}','${f.name.replace(/'/g,"\\'")}')">x</button>
        </div>`;
      }
      knowledgeList.innerHTML = html;
      knowledgeStorage.textContent = `${storage.used_mb || 0} MB / ${storage.max_mb || 50} MB`;
    } catch (err) {
      // silent fail
    }
  }

  // Helper: add system message to chat
  function appendSystemMessage(text) {
    const chatMsgs = document.getElementById('chat-messages');
    const empty = chatMsgs.querySelector('.chat-empty');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = 'chat-msg system';
    div.innerHTML = '<span class="msg-prefix" style="color:var(--cyan);">&gt; SYSTEM</span> ' +
      '<span class="msg-text" style="color:var(--text-dim);">' + text + '</span>';
    chatMsgs.appendChild(div);
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
  }

  // Refresh on load + periodically
  refreshKnowledgePanel();
  setInterval(refreshKnowledgePanel, 30000); // refresh every 30s
})();
