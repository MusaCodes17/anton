// Pure conversation helpers. Persistence moved server-side in R2.6 (see
// services/api.js chatHistoryApi + hooks/useApi.js) — this file no longer
// touches localStorage; it just builds conversation objects and titles.

// Mirror of the backend cap (services/chat_history.MAX_CONVERSATIONS). The
// server enforces it authoritatively; this is only for local trimming/hints.
export const MAX_CONVERSATIONS = 50

export function createConversation(model) {
  return {
    id: crypto.randomUUID(),
    title: null,
    model,
    displayMessages: [],
    apiMessages: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }
}

export function generateTitle(firstUserMessage) {
  return firstUserMessage.trim().slice(0, 40) || 'New conversation'
}
