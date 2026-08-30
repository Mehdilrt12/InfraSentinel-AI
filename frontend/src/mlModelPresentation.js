const ALGORITHM_LABELS = {
  isolationforest: 'Isolation Forest',
  iforest: 'Isolation Forest',
}

export function getAlgorithmDisplayName(algorithm) {
  const raw = String(algorithm || 'Isolation Forest').trim()
  const compact = raw.replace(/[\s_-]/g, '').toLowerCase()
  if (ALGORITHM_LABELS[compact]) return ALGORITHM_LABELS[compact]
  return raw.replace(/([a-z])([A-Z])/g, '$1 $2')
}

export function getModelDisplayName(model) {
  const algorithm = getAlgorithmDisplayName(model?.algorithm)
  const number = Number(model?.display_number)
  return Number.isInteger(number) && number > 0
    ? `${algorithm} — Modèle ${number}`
    : algorithm
}

export function orderModelHistory(models = []) {
  return [...models].sort((left, right) => {
    const byNumber = Number(right?.display_number || 0) - Number(left?.display_number || 0)
    if (byNumber) return byNumber
    const byCreation = Date.parse(right?.created_at || 0) - Date.parse(left?.created_at || 0)
    if (Number.isFinite(byCreation) && byCreation) return byCreation
    return String(right?.id || '').localeCompare(String(left?.id || ''))
  })
}

export function findModelByTechnicalVersion(models = [], technicalVersion) {
  return models.find((model) => model.version === technicalVersion) || null
}
