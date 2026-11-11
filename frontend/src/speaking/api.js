export async function api(path, options = {}) {
  const response = await fetch(path, options)
  let data
  try { data = await response.json() } catch { throw new Error('服务回复异常，请确认本机启动窗口仍在运行。') }
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : '输入不符合要求，请检查后重试。')
    error.status = response.status
    throw error
  }
  return data
}
export const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
