const BASE = '/api'

async function request(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : text || res.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data
}

function safeJson(text) {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export const api = {
  listCampaigns: () => request('GET', '/campaigns'),
  getCampaign: (id) => request('GET', `/campaigns/${id}`),
  listOffers: () => request('GET', '/meta/offers'),
  getCampaignOffers: (id) => request('GET', `/campaigns/${id}/offers`),
  addCampaignOffer: (id, offerId) => request('POST', `/campaigns/${id}/offers`, { offer_id: offerId }),
  removeCampaignOffer: (id, offerId) => request('DELETE', `/campaigns/${id}/offers/${offerId}`),
  setOfferWeight: (id, offerId, share) => request('PUT', `/campaigns/${id}/offers/${offerId}/weight`, { share }),
  previewWeights: (offerIds, pins) => request('POST', '/offer-weights/preview', { offer_ids: offerIds, pins }),
  createCampaignWithOffer: (data) => request('POST', '/campaign-creator', data),
  updateCampaign: (id, data) => request('PATCH', `/campaigns/${id}`, data),
  listGroups: () => request('GET', '/meta/groups'),
  listTrafficSources: () => request('GET', '/meta/traffic-sources'),
  listChanges: (limit = 50) => request('GET', `/changes?limit=${limit}`),
  listCountries: () => request('GET', '/meta/countries'),
  getCreatorDefaults: () => request('GET', '/meta/creator-defaults'),
}
