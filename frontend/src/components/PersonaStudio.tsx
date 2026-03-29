import React, { useState } from 'react';
import { usePersonaStore } from '../store/personaStore';
import './PersonaStudio.css';

interface PersonaStudioProps {
    isVisible: boolean;
    onClose: () => void;
}

export const PersonaStudio: React.FC<PersonaStudioProps> = ({ isVisible, onClose }) => {
    const { personas, globalPersonaId, setGlobalPersona, addPersona, updatePersona, deletePersona } = usePersonaStore();

    const [editingId, setEditingId] = useState<string | null>(null);
    const [draftName, setDraftName] = useState('');
    const [draftPrompt, setDraftPrompt] = useState('');

    if (!isVisible) return null;

    const handleCreate = () => {
        setEditingId('new');
        setDraftName('');
        setDraftPrompt('');
    };

    const handleEdit = (id: string, name: string, prompt: string) => {
        setEditingId(id);
        setDraftName(name);
        setDraftPrompt(prompt);
    };

    const handleSave = () => {
        if (!draftName.trim() || !draftPrompt.trim()) return;

        if (editingId === 'new') {
            addPersona({ name: draftName, systemPrompt: draftPrompt });
        } else if (editingId) {
            updatePersona(editingId, { name: draftName, systemPrompt: draftPrompt });
        }
        setEditingId(null);
    };

    return (
        <div className="persona-studio-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div className="persona-studio-modal">
                <header className="persona-studio-header">
                    <h2>🎭 Persona Studio</h2>
                    <button className="close-btn" onClick={onClose}>×</button>
                </header>

                <div className="persona-studio-content">
                    <div className="persona-list">
                        <div className="list-header">
                            <h3>Available Personas</h3>
                            {editingId === null && (
                                <button className="create-btn" onClick={handleCreate}>+ New Persona</button>
                            )}
                        </div>

                        {personas.map(persona => (
                            <div
                                key={persona.id}
                                className={`persona-card ${globalPersonaId === persona.id ? 'active' : ''} ${persona.isDefault ? 'default' : ''}`}
                                onClick={() => setGlobalPersona(globalPersonaId === persona.id ? null : persona.id)}
                            >
                                <div className="persona-card-content">
                                    <h4>
                                        {globalPersonaId === persona.id && <span className="active-indicator">★</span>}
                                        {persona.name}
                                        {persona.isDefault && <span className="default-badge">System</span>}
                                    </h4>
                                    <p>{persona.systemPrompt}</p>
                                </div>
                                {!persona.isDefault && (
                                    <div className="persona-card-actions" onClick={e => e.stopPropagation()}>
                                        <button title="Edit" onClick={() => handleEdit(persona.id, persona.name, persona.systemPrompt)}>✏️</button>
                                        <button title="Delete" onClick={() => deletePersona(persona.id)} className="delete-btn">🗑️</button>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {editingId !== null && (
                        <div className="persona-editor">
                            <h3>{editingId === 'new' ? 'Create New Persona' : 'Edit Persona'}</h3>
                            <div className="editor-form">
                                <input
                                    type="text"
                                    placeholder="Persona Name (e.g., Code Reviewer)"
                                    value={draftName}
                                    onChange={(e) => setDraftName(e.target.value)}
                                />
                                <textarea
                                    placeholder="System Prompt (e.g., You are a meticulous code reviewer...)"
                                    value={draftPrompt}
                                    onChange={(e) => setDraftPrompt(e.target.value)}
                                    rows={8}
                                />
                                <div className="editor-actions">
                                    <button className="cancel-btn" onClick={() => setEditingId(null)}>Cancel</button>
                                    <button className="save-btn" onClick={handleSave} disabled={!draftName.trim() || !draftPrompt.trim()}>Save</button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
