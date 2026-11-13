import type { Overview, Revision, Review } from './types'

export function productName(data: Overview, id: string) { return data.products.find(product => product.id === id)?.name || id }
export function revisionName(data: Overview, revision: Revision) { return `${productName(data, revision.product_id)} / ${revision.label}` }
export function lotName(data: Overview, id: string) { return data.lots.find(lot => lot.id === id)?.reference || id }
export const valueOf = (form: FormData, name: string) => String(form.get(name) || '').trim()

/** An open human task cannot be superseded by another photo. Closed retakes need a valid replacement. */
export function isReviewUnresolved(review: Review, data: Overview) {
  if (review.status !== 'closed') return true
  if (!review.quarantined && (review.outcome === 'accept' || review.outcome === 'reject')) return false
  const original = data.captures.find(item => item.id === review.capture_id || item.capture_id === review.capture_id || item.inspection_id === review.inspection_id)
  const replacement = review.resolved_by ? data.captures.find(item => item.id === review.resolved_by) : undefined
  const validReplacement = original && replacement && replacement.status === 'done'
    && replacement.lot_id === original.lot_id && replacement.revision_id === original.revision_id
    && replacement.physical_part_id === original.physical_part_id && replacement.retake_of === original.id
    && !!replacement.inspection_id && !data.reviews.some(item => item.inspection_id === replacement.inspection_id && item.quarantined)
  return !validReplacement
}

/** Capture attempts, physical parts and the human outcome of each attempt in one lot. */
export function lotStats(data: Overview, lotId: string) {
  const captures = data.captures.filter(item => item.lot_id === lotId)
  const reviews = new Map(data.reviews.filter(item => item.lot_id === lotId).map(item => [item.inspection_id, item]))
  const stats = { captures: captures.length, parts: new Set(captures.map(item => item.physical_part_id)).size, accept: 0, reject: 0, hold: 0, retake: 0, open: 0 }
  for (const capture of captures) {
    const review = capture.inspection_id ? reviews.get(capture.inspection_id) : undefined
    const outcome = review?.status === 'closed' && review.outcome ? review.outcome : 'open'
    stats[outcome] += 1
  }
  return stats
}
