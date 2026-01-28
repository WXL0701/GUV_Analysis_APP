import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 5 * 60 * 60 * 1000,
})

// Request interceptor
http.interceptors.request.use(
  (config) => {
    // Add token if exists (Use sessionStorage for window isolation)
    const token = sessionStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

export default http
