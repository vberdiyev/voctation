let selectedAudioFile = null;
let currentTranscriptFile = null;
let currentTranscriptText = null;
let currentOutlineFile = null;
let currentOutlineText = null;
let isProcessing = false;

const API_BASE = '';

// Process indicator management
function showProcessIndicator(message) {
    removeProcessIndicator();
    const indicator = document.createElement('div');
    indicator.className = 'process-indicator';
    indicator.id = 'processIndicator';
    indicator.innerHTML = `<span class="spinner"></span>${message}`;
    document.body.appendChild(indicator);
}

function removeProcessIndicator() {
    const existing = document.getElementById('processIndicator');
    if (existing) existing.remove();
}

function showNotification(message, type = 'success') {
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => notification.remove(), 5000);
}

function downloadFile(content, filename) {
    const element = document.createElement('a');
    element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(content));
    element.setAttribute('download', filename);
    element.style.display = 'none';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
}

function setButtonLoading(button, isLoading, loadingText, originalText) {
    if (isLoading) {
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.innerHTML = `<span class="spinner"></span>${loadingText}`;
    } else {
        button.disabled = false;
        button.innerHTML = originalText || button.dataset.originalText || button.textContent;
    }
}

function loadAudioFiles() {
    const audioList = document.getElementById('audioList');
    if (!audioList) return;

    showProcessIndicator('Loading audio files...');

    fetch('/api/audio-files')
        .then(r => {
            if (!r.ok) throw new Error('Failed to load audio files');
            return r.json();
        })
        .then(files => {
            removeProcessIndicator();
            audioList.innerHTML = '';
            if (files.length === 0) {
                audioList.innerHTML = '<div class="file-item empty">No audio files</div>';
            } else {
                files.forEach(file => {
                    const div = document.createElement('div');
                    div.className = 'file-item';
                    div.textContent = file;
                    div.onclick = () => selectAudioFile(div, file);
                    audioList.appendChild(div);
                });
            }
        })
        .catch(e => {
            removeProcessIndicator();
            console.error('Error loading audio files:', e);
            showNotification('Failed to load audio files', 'error');
        });
}

function selectAudioFile(element, file) {
    document.querySelectorAll('#audioList .file-item').forEach(el => el.classList.remove('selected'));
    element.classList.add('selected');
    selectedAudioFile = file;
    document.getElementById('transcribeBtn').disabled = false;
    showNotification('Selected: ' + file, 'info');
}

function loadTemplates() {
    const select = document.getElementById('promptSelect');
    if (!select) return;

    showProcessIndicator('Loading templates...');

    fetch('/api/prompt-templates')
        .then(r => {
            if (!r.ok) throw new Error('Failed to load templates');
            return r.json();
        })
        .then(templates => {
            removeProcessIndicator();
            templates.forEach(t => {
                const option = document.createElement('option');
                option.value = t;
                option.textContent = t.replace('.md', '').replace(/_/g, ' ');
                select.appendChild(option);
            });
        })
        .catch(e => {
            removeProcessIndicator();
            console.error('Error loading templates:', e);
            showNotification('Failed to load templates', 'error');
        });
}

function uploadFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    if (isProcessing) {
        showNotification('Please wait for current operation to complete', 'warning');
        e.target.value = '';
        return;
    }

    isProcessing = true;
    showProcessIndicator('Uploading audio file...');
    showNotification('Uploading ' + file.name + '...', 'info');

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/upload-audio', { method: 'POST', body: formData })
        .then(r => {
            if (!r.ok) throw new Error(`Upload failed: ${r.status} ${r.statusText}`);
            return r.json();
        })
        .then(data => {
            e.target.value = '';
            removeProcessIndicator();
            showNotification('Uploaded: ' + data.filename, 'success');
            setTimeout(loadAudioFiles, 300);
        })
        .catch(err => {
            removeProcessIndicator();
            showNotification(err.message || 'Upload failed', 'error');
        })
        .finally(() => {
            isProcessing = false;
        });
}

function transcribeAudio() {
    if (!selectedAudioFile) {
        showNotification('Select audio file first', 'warning');
        return;
    }

    if (isProcessing) {
        showNotification('Please wait for current operation to complete', 'warning');
        return;
    }

    isProcessing = true;
    const btn = document.getElementById('transcribeBtn');
    setButtonLoading(btn, true, 'Transcribing...', 'Transcribe Audio');
    showProcessIndicator('Processing audio with Whisper model...');

    fetch('/api/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: selectedAudioFile })
    })
    .then(r => {
        if (!r.ok) throw new Error('Transcription failed');
        return r.json();
    })
    .then(data => {
        if (data.status === 'success') {
            currentTranscriptFile = data.transcript_file;
            currentTranscriptText = data.text;
            document.getElementById('transcriptFileName').textContent = data.transcript_file;

            const transcriptContent = document.getElementById('transcriptContent');
            transcriptContent.textContent = data.text;
            transcriptContent.classList.remove('empty');

            document.getElementById('summarizeBtn').disabled = false;
            document.getElementById('downloadTranscriptBtn').disabled = false;

            removeProcessIndicator();
            showNotification('Transcription complete', 'success');
        } else {
            throw new Error('Transcription failed');
        }
    })
    .catch(e => {
        removeProcessIndicator();
        showNotification('Error: ' + e.message, 'error');
    })
    .finally(() => {
        isProcessing = false;
        setButtonLoading(btn, false, null, 'Transcribe Audio');
    });
}

function summarizeTranscript() {
    if (!currentTranscriptFile) {
        showNotification('Transcribe audio first or upload a transcript', 'warning');
        return;
    }

    const template = document.getElementById('promptSelect').value;
    if (!template) {
        showNotification('Select a template', 'warning');
        return;
    }

    if (isProcessing) {
        showNotification('Please wait for current operation to complete', 'warning');
        return;
    }

    isProcessing = true;
    const btn = document.getElementById('summarizeBtn');
    setButtonLoading(btn, true, 'Summarizing...', 'Summarize');
    showProcessIndicator('Connecting to Gemini API...');

    fetch('/api/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            transcript_file: currentTranscriptFile,
            template: template
        })
    })
    .then(r => {
        if (!r.ok) throw new Error('Summarization failed');
        return r.json();
    })
    .then(data => {
        if (data.status === 'success') {
            currentOutlineFile = data.outline_file;
            currentOutlineText = data.content;
            document.getElementById('outlineFileName').textContent = data.outline_file;

            const outlineContent = document.getElementById('outlineContent');
            // Render markdown if marked is available, otherwise show plain text
            if (typeof marked !== 'undefined' && marked.parse) {
                outlineContent.innerHTML = marked.parse(data.content);
            } else {
                outlineContent.textContent = data.content;
            }
            outlineContent.classList.remove('empty');

            document.getElementById('copyBtn').disabled = false;
            document.getElementById('editBtn').disabled = false;
            document.getElementById('downloadOutlineBtn').disabled = false;

            removeProcessIndicator();
            showNotification('Summary complete', 'success');
        } else {
            throw new Error('Summarization failed');
        }
    })
    .catch(e => {
        removeProcessIndicator();
        showNotification('Error: ' + e.message, 'error');
    })
    .finally(() => {
        isProcessing = false;
        setButtonLoading(btn, false, null, 'Summarize');
    });
}

function copyToClipboard() {
    if (!currentOutlineText) {
        showNotification('No content to copy', 'warning');
        return;
    }

    navigator.clipboard.writeText(currentOutlineText).then(() => {
        showNotification('Copied to clipboard', 'success');
    }).catch(() => showNotification('Copy failed', 'error'));
}

function editOutline() {
    if (!currentOutlineFile) return;
    showNotification('Edit: user-data/outlines/' + currentOutlineFile, 'info');
}

function downloadTranscript() {
    if (!currentTranscriptText || !currentTranscriptFile) {
        showNotification('No transcript to download', 'warning');
        return;
    }
    showProcessIndicator('Preparing download...');
    downloadFile(currentTranscriptText, currentTranscriptFile);
    removeProcessIndicator();
    showNotification('Downloaded: ' + currentTranscriptFile, 'success');
}

function downloadOutline() {
    if (!currentOutlineText || !currentOutlineFile) {
        showNotification('No summary to download', 'warning');
        return;
    }
    showProcessIndicator('Preparing download...');
    downloadFile(currentOutlineText, currentOutlineFile);
    removeProcessIndicator();
    showNotification('Downloaded: ' + currentOutlineFile, 'success');
}

function uploadMdFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    if (isProcessing) {
        showNotification('Please wait for current operation to complete', 'warning');
        e.target.value = '';
        return;
    }

    isProcessing = true;
    showProcessIndicator('Uploading transcript file...');
    showNotification('Uploading ' + file.name + '...', 'info');

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/upload-transcript', { method: 'POST', body: formData })
        .then(r => {
            if (!r.ok) throw new Error(`Upload failed: ${r.status} ${r.statusText}`);
            return r.json();
        })
        .then(data => {
            currentTranscriptText = data.text;
            currentTranscriptFile = data.filename;

            document.getElementById('transcriptFileName').textContent = data.filename;

            const transcriptContent = document.getElementById('transcriptContent');
            transcriptContent.textContent = data.text;
            transcriptContent.classList.remove('empty');

            document.getElementById('downloadTranscriptBtn').disabled = false;
            document.getElementById('summarizeBtn').disabled = false;

            removeProcessIndicator();
            showNotification('Transcript uploaded: ' + data.filename, 'success');
            e.target.value = '';
        })
        .catch(err => {
            console.error('Upload error:', err);
            removeProcessIndicator();
            showNotification(err.message || 'Upload failed', 'error');
            e.target.value = '';
        })
        .finally(() => {
            isProcessing = false;
        });
}

// Update file input button labels on change
function updateFileInputLabel(inputId, labelSelector) {
    const input = document.getElementById(inputId);
    if (!input) return;

    input.addEventListener('change', function() {
        const label = document.querySelector(labelSelector);
        if (label && this.files.length > 0) {
            label.textContent = this.files[0].name;
        }
    });
}

// Attach event listeners
window.addEventListener('load', function() {
    const fileInput = document.getElementById('fileInput');
    if (fileInput) fileInput.addEventListener('change', uploadFile);

    const transcribeBtn = document.getElementById('transcribeBtn');
    if (transcribeBtn) transcribeBtn.addEventListener('click', transcribeAudio);

    const summarizeBtn = document.getElementById('summarizeBtn');
    if (summarizeBtn) summarizeBtn.addEventListener('click', summarizeTranscript);

    const copyBtn = document.getElementById('copyBtn');
    if (copyBtn) copyBtn.addEventListener('click', copyToClipboard);

    const editBtn = document.getElementById('editBtn');
    if (editBtn) editBtn.addEventListener('click', editOutline);

    const downloadTranscriptBtn = document.getElementById('downloadTranscriptBtn');
    if (downloadTranscriptBtn) downloadTranscriptBtn.addEventListener('click', downloadTranscript);

    const downloadOutlineBtn = document.getElementById('downloadOutlineBtn');
    if (downloadOutlineBtn) downloadOutlineBtn.addEventListener('click', downloadOutline);

    const mdFileInput = document.getElementById('mdFileInput');
    if (mdFileInput) mdFileInput.addEventListener('change', uploadMdFile);

    // Update file input labels
    updateFileInputLabel('fileInput', 'label[for="fileInput"]');
    updateFileInputLabel('mdFileInput', 'label[for="mdFileInput"]');

    loadAudioFiles();
    loadTemplates();
});
