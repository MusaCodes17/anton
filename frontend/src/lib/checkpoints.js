const STORAGE_PREFIX = 'shoe-checkpoint-prompted'

/** Has the 100km-checkpoint note prompt already been shown (and dismissed/saved) for this shoe? */
export function hasPromptedCheckpoint(shoeId, checkpointKm) {
  return localStorage.getItem(`${STORAGE_PREFIX}:${shoeId}:${checkpointKm}`) === '1'
}

/** Record that the checkpoint prompt was shown, so it isn't shown again — regardless of Save or Skip. */
export function markCheckpointPrompted(shoeId, checkpointKm) {
  localStorage.setItem(`${STORAGE_PREFIX}:${shoeId}:${checkpointKm}`, '1')
}
