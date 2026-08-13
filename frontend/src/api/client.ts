async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('access_token')
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(path, { ...options, headers })
  
  if (!res.ok) {
    let errorMessage = `${res.status} ${res.statusText}`
    try {
      const errorData = await res.json()
      // Varsa FastAPI'den gelen detayı kullan
      if (errorData && errorData.detail) {
        if (Array.isArray(errorData.detail)) {
          errorMessage = errorData.detail[0].msg
        } else {
          errorMessage = errorData.detail
        }
      }
    } catch (e) {
      // JSON değilse yoksay
    }
    throw new Error(errorMessage)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
}
