let selectedAudioFile = null;
let currentTranscriptFile = null;
let currentTranscriptText = null;
let currentOutlineFile = null;
let currentOutlineText = null;

const API_BASE = '';

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

function loadAudioFiles() {
    const audioList = document.getElementById('audioList');
    if (!audioList) return;

    fetch('/api/audio-files')
        .then(r => r.json())
        .then(files => {
            audioList.innerHTML = '';
            if (files.length === 0) {
                audioList.innerHTML = '<div class="file-item empty">No audio files</div>';
            } else {
                files.forEach(file => {
                    const div = document.createElement('div');
                    div.className = 'file-item';
                    div.textContent = file;
                    div.onclick = () => {
                        document.querySelectorAll('#audioList .file-item').forEach(el => el.classList.remove('selected'));
                        div.classList.add('selected');
                        selectedAudioFile = file;
                        document.getElementById('transcribeBtn').disabled = false;
                        showNotification('Selected: ' + file, 'info');
                    };
                    audioList.appendChild(div);
                });
            }
        })
        .catch(e => console.log('Error loading audio:', e));
}

function loadTemplates() {
    const select = document.getElementById('promptSelect');
    if (!select) return;

    fetch('/api/prompt-templates')
        .then(r => r.json())
        .then(templates => {
            templates.forEach(t => {
                const option = document.createElement('option');
                option.value = t;
                option.textContent = t.replace('.md', '').replace(/_/g, ' ');
                select.appendChild(option);
            });
        })
        .catch(e => console.log('Error loading templates:', e));
}

function uploadFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/upload-audio', { method: 'POST', body: formData })
        .then(r => {
            if (!r.ok) throw new Error(`Upload failed: ${r.status} ${r.statusText}`);
            return r.json();
        })
        .then(data => {
            e.target.value = '';
            showNotification('Uploaded: ' + data.filename, 'success');
            setTimeout(loadAudioFiles, 300);
        })
        .catch(err => showNotification(err.message || 'Upload failed', 'error'));
}

function transcribeAudio() {
    if (!selectedAudioFile) {
        showNotification('Select audio file first', 'warning');
        return;
    }

    const btn = document.getElementById('transcribeBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Transcribing...';

    fetch('/api/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: selectedAudioFile })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            currentTranscriptFile = data.transcript_file;
            currentTranscriptText = data.text;
            document.getElementById('transcriptFileName').textContent = data.transcript_file;
            document.getElementById('transcriptContent').textContent = data.text;
            document.getElementById('transcriptContent').classList.remove('empty');
            document.getElementById('summarizeBtn').disabled = false;
            document.getElementById('downloadTranscriptBtn').disabled = false;
            showNotification('Transcription complete', 'success');
        } else {
            showNotification('Transcription failed', 'error');
        }
    })
    .catch(e => showNotification('Error: ' + e.message, 'error'))
    .finally(() => {
        btn.disabled = false;
        btn.textContent = '🎙️ Transcribe Audio';
    });
}

function summarizeTranscript() {
    if (!currentTranscriptFile) {
        showNotification('Transcribe audio first', 'warning');
        return;
    }

    const template = document.getElementById('promptSelect').value;
    if (!template) {
        showNotification('Select template', 'warning');
        return;
    }

    const btn = document.getElementById('summarizeBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Summarizing...';

    fetch('/api/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            transcript_file: currentTranscriptFile,
            template: template
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            currentOutlineFile = data.outline_file;
            currentOutlineText = data.content;
            document.getElementById('outlineFileName').textContent = data.outline_file;
            document.getElementById('outlineContent').textContent = data.content;
            document.getElementById('outlineContent').classList.remove('empty');
            document.getElementById('copyBtn').disabled = false;
            document.getElementById('editBtn').disabled = false;
            document.getElementById('downloadOutlineBtn').disabled = false;
            showNotification('Summary complete', 'success');
        } else {
            showNotification('Summarization failed', 'error');
        }
    })
    .catch(e => showNotification('Error: ' + e.message, 'error'))
    .finally(() => {
        btn.disabled = false;
        btn.textContent = '✨ Summarize';
    });
}

function copyToClipboard() {
    const text = document.getElementById('outlineContent').textContent;
    navigator.clipboard.writeText(text).then(() => {
        showNotification('Copied to clipboard', 'success');
    }).catch(() => showNotification('Copy failed', 'error'));
}

function editOutline() {
    if (!currentOutlineFile) return;
    showNotification('Edit: user-data/outlines/' + currentOutlineFile, 'info');
}

function downloadTranscript() {
    if (!currentTranscriptText) return;
    downloadFile(currentTranscriptText, currentTranscriptFile);
}

function downloadOutline() {
    if (!currentOutlineText) return;
    downloadFile(currentOutlineText, currentOutlineFile);
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

    loadAudioFiles();
    loadTemplates();
});
