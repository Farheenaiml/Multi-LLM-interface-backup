import React, { useState, useEffect } from 'react';
import './FileDirectoryModal.css';
import { useAppStore } from '../../store';

export interface FileInfo {
  id: string;
  name: string;
  originalName?: string; // Original file name if different
  type: string;
  size: number;
  uri: string;
}

interface FileDirectoryModalProps {
  sessionId: string;
  isOpen: boolean;
  onClose: () => void;
  onSelectFiles: (files: FileInfo[]) => void;
  onSendDirect: (modelId: string, files: FileInfo[]) => void;
}

export const FileDirectoryModal: React.FC<FileDirectoryModalProps> = ({
  sessionId,
  isOpen,
  onClose,
  onSelectFiles,
  onSendDirect
}) => {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedUris, setSelectedUris] = useState<Set<string>>(new Set());
  const [selectedModelId, setSelectedModelId] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
      fetchFiles();
      setSelectedUris(new Set()); // Reset selection on open
    }
  }, [isOpen, sessionId]);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:5000/session/${sessionId}/files`);
      if (response.ok) {
        const data = await response.json();
        setFiles(data.files || []);
        
        // Update global map
        const map: Record<string, string> = {};
        (data.files || []).forEach((f: any) => { map[f.uri] = f.originalName || f.name; });
        useAppStore.getState().setSessionFilesMap(map);
      }
    } catch (error) {
      console.error('Failed to fetch session files:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleFile = (uri: string) => {
    const newSelected = new Set(selectedUris);
    if (newSelected.has(uri)) {
      newSelected.delete(uri);
    } else {
      newSelected.add(uri);
    }
    setSelectedUris(newSelected);
  };

  const handleConfirm = () => {
    const selectedFiles = files.filter(f => selectedUris.has(f.uri));
    if (!selectedModelId) {
      // Just attach the files to the main prompt selector
      onSelectFiles(selectedFiles);
    } else {
      // Direct send to selected model
      onSendDirect(selectedModelId, selectedFiles);
    }
    onClose();
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    else return (bytes / 1048576).toFixed(1) + ' MB';
  };

  // Import model list from store
  const availableModels = useAppStore(state => state.availableModels);

  if (!isOpen) return null;

  return (
    <div className="file-directory-modal-overlay">
      <div className="file-directory-modal">
        <div className="modal-header">
          <h3>Session Files Directory</h3>
          <div className="modal-header-actions">
            <button className="upload-btn-header" onClick={() => (document.getElementById('modal-file-upload') as HTMLInputElement)?.click()}>
              + Upload New
            </button>
            <input 
              type="file" 
              id="modal-file-upload" 
              style={{ display: 'none' }} 
              onChange={(e) => {
                if (e.target.files?.[0]) {
                  const file = e.target.files[0];
                  if (file.size > 15 * 1024 * 1024) {
                    alert(`File ${file.name} exceeds the 15MB limit and cannot be uploaded.`);
                    return;
                  }
                  const formData = new FormData();
                  formData.append('file', file);
                  fetch(`http://localhost:5000/session/${sessionId}/upload`, {
                    method: 'POST',
                    body: formData
                  })
                  .then(async res => {
                    if (!res.ok) {
                      const errorText = await res.text();
                      throw new Error(errorText);
                    }
                    return res.json();
                  })
                  .then(() => fetchFiles())
                  .catch(err => {
                    console.error('Upload error:', err);
                    alert(`Upload failed: ${err.message}`);
                  });
                }
              }}
            />
            <button className="close-btn" onClick={onClose}>&times;</button>
          </div>
        </div>
        <div className="modal-content">
          {loading ? (
            <div className="loading">Loading files...</div>
          ) : files.length === 0 ? (
            <div className="empty-state">No files uploaded in this session yet.</div>
          ) : (
            <div className="file-list">
              {files.map(file => (
                <div 
                  key={file.id} 
                  className={`file-item ${selectedUris.has(file.uri) ? 'selected' : ''}`}
                  onClick={() => handleToggleFile(file.uri)}
                >
                  <input 
                    type="checkbox" 
                    checked={selectedUris.has(file.uri)}
                    readOnly
                  />
                  <span className="file-icon">📄</span>
                  <div className="file-details">
                    <span className="file-name">{file.originalName ?? file.name}</span>
                    <span className="file-meta">{formatSize(file.size)} &bull; {file.type.split('/')[1]?.toUpperCase() || 'FILE'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
          <div className="modal-footer">
            <span className="selected-count">{selectedUris.size} files selected</span>
            {/* Model selector */}
              {/* Model selector is now optional; if not chosen, user will be prompted on attach */}
              <select value={selectedModelId} onChange={e => setSelectedModelId(e.target.value)} className="model-select">
                <option value="">Select model (optional)</option>
                {availableModels.map(m => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            <div className="modal-actions">
              <button className="cancel-btn" onClick={onClose}>Cancel</button>
              <button 
                className="confirm-btn" 
                onClick={handleConfirm}
                disabled={selectedUris.size === 0}
              >
                {selectedModelId ? 'Send to Model' : 'Attach Selected'}
              </button>
            </div>
          </div>
      </div>
    </div>
  );
};
