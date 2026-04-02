import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Persona {
    id: string;
    name: string;
    systemPrompt: string;
    isDefault?: boolean;
}

export const DEFAULT_PERSONAS: Persona[] = [
    {
        id: 'default-professional',
        name: 'Professional Writer',
        systemPrompt: 'You are a highly professional, articulate, and concise writer. Adopt a formal, polite, and objective tone. Ensure grammar and style are impeccable.',
        isDefault: true,
    },
    {
        id: 'default-developer',
        name: 'Senior Developer',
        systemPrompt: 'You are a senior software engineer. Provide clean, highly optimized, and thoroughly documented code. Focus on best practices, performance, and security. Speak directly without generic fluff.',
        isDefault: true,
    },
    {
        id: 'default-exam',
        name: 'Exam Assistant',
        systemPrompt: 'You are an incredibly patient and helpful exam preparation tutor. Break down complex topics into simple, digestible concepts. Provide step-by-step explanations, analogies, and practice questions if applicable.',
        isDefault: true,
    }
];

interface PersonaState {
    personas: Persona[];
    globalPersonaId: string | null;
    addPersona: (persona: Omit<Persona, 'id' | 'isDefault'>) => void;
    updatePersona: (id: string, overrides: Partial<Persona>) => void;
    deletePersona: (id: string) => void;
    setGlobalPersona: (id: string | null) => void;
    getGlobalPersona: () => Persona | undefined;
}

export const usePersonaStore = create<PersonaState>()(
    persist(
        (set, get) => ({
            personas: [...DEFAULT_PERSONAS],
            globalPersonaId: null,

            addPersona: (personaData) => {
                const newPersona: Persona = {
                    id: `persona-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
                    ...personaData,
                    isDefault: false
                };
                set((state) => ({ personas: [...state.personas, newPersona] }));
            },

            updatePersona: (id, overrides) => set((state) => ({
                personas: state.personas.map((p) => p.id === id && !p.isDefault ? { ...p, ...overrides } : p)
            })),

            deletePersona: (id) => set((state) => {
                // Prevent deleting default personas
                const personaToDelete = state.personas.find(p => p.id === id);
                if (personaToDelete?.isDefault) return state;

                const nextPersonas = state.personas.filter((p) => p.id !== id);
                return {
                    personas: nextPersonas,
                    // If we deleted the actively selected global persona, reset it
                    globalPersonaId: state.globalPersonaId === id ? null : state.globalPersonaId
                };
            }),

            setGlobalPersona: (id) => set({ globalPersonaId: id }),

            getGlobalPersona: () => {
                const state = get();
                return state.personas.find(p => p.id === state.globalPersonaId);
            }
        }),
        {
            name: 'multi-llm-personas-storage',
            version: 1,
        }
    )
);
