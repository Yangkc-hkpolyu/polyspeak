export async function api(path, options = {}) {
  const response = await fetch(path, options)
  let data
  try { data = await response.json() } catch { throw new Error('The server returned an unexpected response. Check that the local server is still running.') }
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Please check your input and try again.')
    error.status = response.status
    throw error
  }
  return data
}
export const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
