// ==========================================
// GLOBAL STATE
// ==========================================
let socket = null;
let videoFile = null;
let autoSelectFile = null;  // filename from v_raw when auto-select is used
let isProcessing = false;
let charLockActive = true;  // Toggle default ON
let lockedCharCount = 0;    // The saved target char count
let audioGenerated = false; // Whether TTS audio has been generated

// ==========================================
// DOM ELEMENTS
// ==========================================
const elements = {
  uploadZone: document.getElementById('uploadZone'),
  uploadPlaceholder: document.getElementById('uploadPlaceholder'),
  videoInput: document.getElementById('videoInput'),
  videoPreview: document.getElementById('videoPreview'),
  filePreview: document.getElementById('filePreview'),
  removeVideoBtn: document.getElementById('removeVideoBtn'),
  videoTopic: document.getElementById('videoTopic'),

  // Dual preview
  dualPreviewContainer: document.getElementById('dualPreviewContainer'),
  completedThumbnail: document.getElementById('completedThumbnail'),
  completedOverlay: document.getElementById('completedOverlay'),
  completedVideoPreview: document.getElementById('completedVideoPreview'),

  // Mute toggle
  muteToggleLabel: document.getElementById('muteToggleLabel'),
  muteToggle: document.getElementById('muteToggle'),
  muteIcon: document.getElementById('muteIcon'),

  startBtn: document.getElementById('startBtn'),

  progressSection: document.getElementById('progressSection'),
  progressFill: document.getElementById('progressFill'),
  progressPercentage: document.getElementById('progressPercentage'),
  progressMessage: document.getElementById('progressMessage'),

  logsTerminal: document.getElementById('logsTerminal'),
  clearLogsBtn: document.getElementById('clearLogsBtn'),

  // Script Generator
  scriptTextarea: document.getElementById('scriptTextarea'),
  scriptOverlayText: document.getElementById('scriptOverlayText'),
  charCounter: document.getElementById('charCounter'),
  scriptActions: document.getElementById('scriptActions'),
  btnRegenerate: document.getElementById('btnRegenerate'),
  btnExtend: document.getElementById('btnExtend'),
  btnReduce: document.getElementById('btnReduce'),
  btnApprove: document.getElementById('btnApprove'),
  approveIcon: document.getElementById('approveIcon'),
  approveLabel: document.getElementById('approveLabel'),
  charLockToggle: document.getElementById('charLockToggle'),
  // Audio player
  audioPlayer: document.getElementById('audioPlayer'),
  apPlayBtn: document.getElementById('apPlayBtn'),
  apTime: document.getElementById('apTime'),
  apProgress: document.getElementById('apProgress'),
  apAudio: document.getElementById('apAudio'),
};

// ==========================================
// SOCKET.IO CONNECTION
// ==========================================
function initializeSocket() {
  socket = io();

  socket.on('connect', () => {
    addLog('🔌 Connected to server', 'success');
  });

  socket.on('disconnect', () => {
    addLog('🔌 Disconnected from server', 'error');
  });

  socket.on('progress_update', (data) => {
    updateProgress(data.percentage, data.message);
  });

  socket.on('step_update', (data) => {
    updateStepStatus(data.step_id, data.status, data.message);
  });

  socket.on('log_message', (data) => {
    addLog(data.message);
  });

  socket.on('processing_complete', (data) => {
    onProcessingComplete(data.files);
  });

  socket.on('processing_error', (data) => {
    onProcessingError(data.message);
  });

  socket.on('script_review', (data) => {
    showScriptForReview(data.script);
  });

  socket.on('audio_ready', (data) => {
    onAudioReady(data.url);
  });

  socket.on('title_generated', (data) => {
    const titleInput = document.getElementById('scriptTitle');
    if (titleInput) {
      titleInput.value = data.title;
    }
  });
}

// ==========================================
// FILE UPLOAD
// ==========================================
function setupFileUpload() {
  elements.uploadZone.addEventListener('click', (e) => {
    if (e.target.closest('video')) return;
    // Don't open file picker if clicking the auto-select side
    if (e.target.closest('#uploadSplitRight') || e.target.closest('.btn-autoselect')) return;
    if (!isProcessing) elements.videoInput.click();
  });

  elements.videoInput.addEventListener('change', (e) => {
    handleFileSelect(e.target.files[0]);
  });

  elements.uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (!isProcessing) elements.uploadZone.classList.add('dragover');
  });

  elements.uploadZone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    elements.uploadZone.classList.remove('dragover');
  });

  elements.uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    elements.uploadZone.classList.remove('dragover');
    if (!isProcessing) {
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith('video/')) {
        handleFileSelect(file);
      } else {
        alert('Please drop a valid video file (MP4, MOV)');
      }
    }
  });

  // Remove video button
  elements.removeVideoBtn.addEventListener('click', () => {
    if (isProcessing) return;
    videoFile = null;
    autoSelectFile = null;
    elements.videoPreview.src = '';
    elements.videoPreview.pause();
    elements.dualPreviewContainer.classList.add('hidden');
    elements.uploadPlaceholder.classList.remove('hidden');
    elements.filePreview.classList.add('hidden');
    elements.removeVideoBtn.classList.add('hidden');
    elements.muteToggleLabel.classList.add('hidden');
    elements.muteIcon.classList.add('hidden');
    elements.videoInput.value = '';

    // Reset auto-select info
    const autoInfo = document.getElementById('autoSelectInfo');
    if (autoInfo) autoInfo.classList.add('hidden');

    // Reset completed side
    resetCompletedPanel();

    // Reset dashed styling
    elements.uploadZone.style.borderStyle = 'dashed';
    elements.uploadZone.style.padding = 'var(--spacing-lg)';
  });

  // Mute toggle (controls whether raw video audio is stripped before generation)
  elements.muteToggle.addEventListener('change', () => {
    const muted = elements.muteToggle.checked;
    elements.muteIcon.textContent = muted ? '🔇' : '🔊';
  });

  // Auto-Select button
  const autoSelectBtn = document.getElementById('autoSelectBtn');
  if (autoSelectBtn) {
    autoSelectBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (isProcessing) return;
      try {
        const res = await fetch('/api/v_raw_oldest');
        const data = await res.json();
        if (!data.found) {
          alert('No video files found in v_raw folder');
          return;
        }
        autoSelectFile = data.filename;
        videoFile = { name: data.filename, size: data.size, type: 'video/mp4', _autoSelect: true };

        // Show the filename in the auto-select info area
        const autoInfo = document.getElementById('autoSelectInfo');
        const autoName = document.getElementById('autoSelectFilename');
        if (autoInfo && autoName) {
          autoName.textContent = `✓ ${data.filename} (${formatFileSize(data.size)})`;
          autoInfo.classList.remove('hidden');
        }

        // Load preview from server
        elements.videoPreview.src = `/files/v_raw/${encodeURIComponent(data.filename)}`;
        elements.dualPreviewContainer.classList.remove('hidden');
        elements.uploadPlaceholder.classList.add('hidden');
        elements.removeVideoBtn.classList.remove('hidden');
        elements.muteToggleLabel.classList.remove('hidden');
        elements.muteIcon.classList.remove('hidden');
        resetCompletedPanel();
        elements.videoPreview.addEventListener('loadeddata', captureFirstFrame, { once: true });

        elements.filePreview.textContent = `✓ [Auto] ${data.filename} (${formatFileSize(data.size)})`;
        elements.filePreview.classList.remove('hidden');

        elements.uploadZone.style.borderStyle = 'none';
        elements.uploadZone.style.padding = '0';
      } catch (err) {
        alert('Failed to fetch from v_raw: ' + err.message);
      }
    });
  }
}

function handleFileSelect(file) {
  if (!file || !file.type.startsWith('video/')) {
    alert('Please select a video file');
    return;
  }

  videoFile = file;
  autoSelectFile = null;  // Clear auto-select when user manually picks a file

  const url = URL.createObjectURL(file);
  elements.videoPreview.src = url;

  // Show dual preview, hide placeholder
  elements.dualPreviewContainer.classList.remove('hidden');
  elements.uploadPlaceholder.classList.add('hidden');
  elements.removeVideoBtn.classList.remove('hidden');
  elements.muteToggleLabel.classList.remove('hidden');
  elements.muteIcon.classList.remove('hidden');

  // Reset completed panel for new file
  resetCompletedPanel();

  // Capture first frame onto canvas once video metadata loads
  elements.videoPreview.addEventListener('loadeddata', captureFirstFrame, { once: true });

  elements.filePreview.textContent = `✓ ${file.name} (${formatFileSize(file.size)})`;
  elements.filePreview.classList.remove('hidden');

  // Hide border when video is shown
  elements.uploadZone.style.borderStyle = 'none';
  elements.uploadZone.style.padding = '0';
}

function captureFirstFrame() {
  const video = elements.videoPreview;
  const canvas = elements.completedThumbnail;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
}

function resetCompletedPanel() {
  // Show canvas + overlay, hide completed video
  elements.completedThumbnail.classList.remove('hidden');
  elements.completedOverlay.classList.remove('hidden');
  elements.completedVideoPreview.classList.add('hidden');
  elements.completedVideoPreview.src = '';
  elements.completedVideoPreview.pause();
  // Reset overlay text
  elements.completedOverlay.querySelector('.overlay-icon').textContent = '⏳';
  elements.completedOverlay.querySelector('.overlay-text').textContent = 'Waiting for generation...';
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// ==========================================
// START PROCESSING
// ==========================================
function setupStartButton() {
  elements.startBtn.addEventListener('click', async () => {
    // If button is in download mode, trigger the download
    if (finalVideoUrl) {
      window.open(finalVideoUrl, '_blank');

      // If auto-select was used, save the final video to v_fin and clean up v_raw
      if (autoSelectFile) {
        try {
          const finalFilename = finalVideoUrl.split('/').pop();
          await fetch('/api/move_to_v_fin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              raw_filename: autoSelectFile,
              final_filename: decodeURIComponent(finalFilename)
            })
          });
          addLog(`📦 Saved final video to v_fin and removed raw file`, 'success');
        } catch (err) {
          addLog(`⚠ Failed to move to v_fin: ${err.message}`, 'error');
        }
        autoSelectFile = null;
      }

      // Reset button back to Start Processing after download
      finalVideoUrl = null;
      elements.startBtn.querySelector('.btn-icon').textContent = '🚀';
      elements.startBtn.querySelector('.btn-text').textContent = 'Start Processing';
      elements.startBtn.classList.remove('btn-download-ready');
      return;
    }

    if (!videoFile) {
      alert('Please upload a video file first');
      return;
    }
    await startProcessing();
  });
}

async function startProcessing() {
  try {
    isProcessing = true;
    elements.startBtn.disabled = true;
    elements.startBtn.querySelector('.btn-text').textContent = 'Processing...';

    elements.progressSection.classList.remove('hidden');

    updateProgress(0, 'Initializing...');
    clearLogs();

    for (let i = 1; i <= 7; i++) {
      updateStepStatus(i, 'queued');
    }

    // Reset script editor
    elements.scriptTextarea.value = '';
    const titleInput = document.getElementById('scriptTitle');
    if (titleInput) titleInput.value = '';
    elements.charCounter.value = 0;
    elements.scriptOverlayText.classList.remove('hidden');
    elements.scriptOverlayText.textContent = 'Processing video to generate script...';
    setScriptButtonsDisabled(true);

    const formData = new FormData();
    // If auto-select was used, send filename instead of blob
    if (autoSelectFile) {
      formData.append('auto_select_file', autoSelectFile);
    } else {
      formData.append('video_file', videoFile);
    }
    // Include video topic if provided
    if (elements.videoTopic.value.trim() !== '') {
      formData.append('video_topic', elements.videoTopic.value.trim());
    }

    // Include target char count if lock toggle is active
    if (charLockActive && lockedCharCount > 0) {
      formData.append('target_chars', lockedCharCount.toString());
    }

    // Include mute raw audio flag
    if (elements.muteToggle.checked) {
      formData.append('mute_raw_audio', 'true');
    }

    const response = await fetch('/start_processing', {
      method: 'POST',
      body: formData
    });

    const result = await response.json();
    if (result.status === 'error') throw new Error(result.message);

    addLog('✅ Processing request sent successfully', 'success');

  } catch (error) {
    addLog(`❌ Error: ${error.message}`, 'error');
    resetProcessingState();
    alert(`Failed to start processing: ${error.message}`);
  }
}

// ==========================================
// PROGRESS UPDATES
// ==========================================
function updateProgress(percentage, message = '') {
  elements.progressFill.style.width = `${percentage}%`;
  elements.progressPercentage.textContent = `${Math.round(percentage)}%`;
  if (message) elements.progressMessage.textContent = message;
}

function updateStepStatus(stepId, status) {
  const el = document.querySelector(`.step-item[data-step="${stepId}"]`);
  if (!el) return;
  el.classList.remove('queued', 'running', 'completed', 'failed');
  el.classList.add(status);
}

// ==========================================
// LOG MANAGEMENT
// ==========================================
function addLog(message, type = '') {
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  entry.textContent = message;
  elements.logsTerminal.appendChild(entry);
  elements.logsTerminal.scrollTop = elements.logsTerminal.scrollHeight;
}

function clearLogs() {
  elements.logsTerminal.innerHTML = '<div class="log-entry">Ready to process...</div>';
}

function setupClearLogs() {
  elements.clearLogsBtn.addEventListener('click', clearLogs);
}

// ==========================================
// SCRIPT REVIEW ACTIONS
// ==========================================
function showScriptForReview(scriptText) {
  elements.scriptTextarea.value = scriptText;
  const len = scriptText.length;
  elements.charCounter.value = len;

  // Auto-update locked char count when lock is active
  if (charLockActive) {
    lockedCharCount = len;
  }

  // Reset audio state for fresh/modified scripts
  resetAudioState();

  // Hide the center overlay text
  elements.scriptOverlayText.classList.add('hidden');

  setScriptButtonsDisabled(false);
  elements.scriptTextarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
  elements.scriptTextarea.focus();
}

function resetAudioState() {
  audioGenerated = false;
  elements.apAudio.pause();
  elements.apAudio.src = '';
  elements.apPlayBtn.textContent = '▶';
  elements.apTime.textContent = '0:00 / 0:00';
  elements.apProgress.value = 0;
  // Reset approve button to Generate Audio
  elements.approveIcon.textContent = '🔉';
  elements.approveLabel.textContent = 'Generate Audio';
}

function onAudioReady(url) {
  audioGenerated = true;
  elements.apAudio.src = url;
  elements.audioPlayer.classList.remove('hidden');
  // Hide overlay
  elements.scriptOverlayText.classList.add('hidden');
  // Switch approve button to Approve mode
  elements.approveIcon.textContent = '✅';
  elements.approveLabel.textContent = 'Approve';
  setScriptButtonsDisabled(false);
  addLog('🔊 Audio generated — preview it, then Approve to continue', 'success');
}

function formatTime(seconds) {
  if (isNaN(seconds) || !isFinite(seconds)) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function setScriptButtonsDisabled(disabled) {
  elements.btnApprove.disabled = disabled;
  elements.btnReduce.disabled = disabled;
  elements.btnExtend.disabled = disabled;
  elements.btnRegenerate.disabled = disabled;
}

function setupScriptReview() {
  elements.scriptTextarea.addEventListener('input', () => {
    const len = elements.scriptTextarea.value.length;
    elements.charCounter.value = len;
    if (elements.scriptTextarea.value.trim() === '') {
      elements.scriptOverlayText.classList.remove('hidden');
      elements.scriptOverlayText.textContent = 'Script is empty. Type or regenerate.';
    } else {
      elements.scriptOverlayText.classList.add('hidden');
    }
  });

  elements.btnRegenerate.addEventListener('click', () => {
    setScriptButtonsDisabled(true);
    resetAudioState();
    const payload = { action: 'regenerate', text: '' };
    if (charLockActive && lockedCharCount > 0) payload.target_chars = lockedCharCount;
    socket.emit('script_review_response', payload);
    elements.scriptOverlayText.classList.remove('hidden');
    elements.scriptOverlayText.textContent = '🔄 Regenerating script...';
    elements.scriptTextarea.value = '';
    addLog('🔄 Regenerating script...', 'warning');
  });

  elements.btnExtend.addEventListener('click', () => {
    setScriptButtonsDisabled(true);
    resetAudioState();

    // Send 'extend' with the current script text so the backend can extend it by ~50%
    const payload = { action: 'extend', text: elements.scriptTextarea.value };
    if (charLockActive && lockedCharCount > 0) payload.target_chars = lockedCharCount;
    socket.emit('script_review_response', payload);

    elements.scriptOverlayText.classList.remove('hidden');
    elements.scriptOverlayText.textContent = '➕ Extending script...';
    elements.scriptTextarea.value = '';
    addLog('➕ Extending script by ~50%...', 'warning');
  });

  elements.btnReduce.addEventListener('click', () => {
    setScriptButtonsDisabled(true);
    resetAudioState();

    // Send 'reduce' with the current script text so the backend can halve it
    const payload = { action: 'reduce', text: elements.scriptTextarea.value };
    if (charLockActive && lockedCharCount > 0) payload.target_chars = lockedCharCount;
    socket.emit('script_review_response', payload);

    elements.scriptOverlayText.classList.remove('hidden');
    elements.scriptOverlayText.textContent = '➖ Reducing script...';
    elements.scriptTextarea.value = '';
    addLog('➖ Reducing script by ~50%...', 'warning');
  });

  // Approve button: dual-purpose (Generate Audio / Approve)
  elements.btnApprove.addEventListener('click', () => {
    setScriptButtonsDisabled(true);
    if (!audioGenerated) {
      // First click: generate audio
      // Save the script text first
      socket.emit('script_review_response', { action: 'generate_audio', text: elements.scriptTextarea.value });
      elements.scriptOverlayText.classList.remove('hidden');
      elements.scriptOverlayText.textContent = '';
      addLog('🔉 Generating TTS audio...', 'warning');
    } else {
      // Second click: approve and continue pipeline
      socket.emit('script_review_response', { action: 'approve', text: elements.scriptTextarea.value });
      addLog('✅ Script approved', 'success');
    }
  });

  // --- Audio player controls ---
  elements.apPlayBtn.addEventListener('click', () => {
    if (elements.apAudio.paused) {
      elements.apAudio.play();
      elements.apPlayBtn.textContent = '⏸';
    } else {
      elements.apAudio.pause();
      elements.apPlayBtn.textContent = '▶';
    }
  });

  elements.apAudio.addEventListener('timeupdate', () => {
    const current = elements.apAudio.currentTime;
    const duration = elements.apAudio.duration || 0;
    elements.apTime.textContent = `${formatTime(current)} / ${formatTime(duration)}`;
    if (duration > 0) {
      elements.apProgress.value = (current / duration) * 100;
    }
  });

  elements.apAudio.addEventListener('ended', () => {
    elements.apPlayBtn.textContent = '▶';
  });

  elements.apAudio.addEventListener('loadedmetadata', () => {
    const duration = elements.apAudio.duration || 0;
    elements.apTime.textContent = `0:00 / ${formatTime(duration)}`;
  });

  elements.apProgress.addEventListener('input', () => {
    const duration = elements.apAudio.duration || 0;
    if (duration > 0) {
      elements.apAudio.currentTime = (elements.apProgress.value / 100) * duration;
    }
  });

  // --- Char lock toggle ---
  elements.charLockToggle.addEventListener('change', () => {
    charLockActive = elements.charLockToggle.checked;
    if (charLockActive) {
      // Lock: save current char count
      lockedCharCount = parseInt(elements.charCounter.value) || 0;
      addLog(`🔒 Char count locked at ${lockedCharCount}`, 'success');
    } else {
      addLog('🔓 Char count unlocked', 'warning');
    }
  });
}

// ==========================================
// PROCESSING COMPLETE
// ==========================================
let finalVideoUrl = null;

function onProcessingComplete(files) {
  isProcessing = false;
  addLog('🎉 All processing completed!', 'success');

  // Find the final burned-subtitle video (the last mp4 that isn't output_9x16_letterbox.mp4)
  const finalVideo = files.reverse().find(f =>
    f.endsWith('.mp4') && f !== 'output_9x16_letterbox.mp4'
  );

  if (finalVideo) {
    finalVideoUrl = `/files/${encodeURIComponent(finalVideo)}`;
    elements.startBtn.disabled = false;
    elements.startBtn.querySelector('.btn-icon').textContent = '✅';
    elements.startBtn.querySelector('.btn-text').textContent = 'Download Video';
    elements.startBtn.classList.add('btn-download-ready');

    // Show completed video in the right preview panel
    elements.completedThumbnail.classList.add('hidden');
    elements.completedOverlay.classList.add('hidden');
    elements.completedVideoPreview.src = finalVideoUrl;
    elements.completedVideoPreview.classList.remove('hidden');
  } else {
    // Fallback if no final video found
    resetProcessingState();
  }
}

// ==========================================
// ERROR HANDLING
// ==========================================
function onProcessingError(message) {
  addLog(`❌ Processing error: ${message}`, 'error');
  resetProcessingState();
  alert(`Processing failed: ${message}`);
}

function resetProcessingState() {
  isProcessing = false;
  elements.startBtn.disabled = false;
  elements.startBtn.querySelector('.btn-text').textContent = 'Start Processing';
  setScriptButtonsDisabled(false); // In case it failed mid-review
}

// ==========================================
// INITIALIZE
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  initializeSocket();
  setupFileUpload();
  setupStartButton();
  setupClearLogs();
  setupScriptReview();

  const titleInput = document.getElementById('scriptTitle');
  if (titleInput) {
    titleInput.addEventListener('change', (e) => {
      if (socket && e.target.value.trim() !== '') {
        socket.emit('update_title', { title: e.target.value.trim() });
      }
    });
  }
});
